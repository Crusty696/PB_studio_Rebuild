"""
OllamaService — zentraler Lifecycle-Manager für Ollama + Gemma 4.

Alle Aufrufe aus dem Rest der App laufen ausschliesslich über diese Klasse.
Kein anderes Modul importiert httpx oder kennt Port 11434.

K7-Fix: chat() und vision() sind jetzt SYNCHRON (httpx.Client statt AsyncClient).
        Kein asyncio.run() mehr noetig — kein GUI-Freeze.
K8-Fix: Vor jedem Inference wird der Pause-Status des OllamaClient geprueft,
        damit der VRAM-Schutz nicht umgangen wird.
"""

import subprocess
import os
import httpx
import json
import socket
import logging
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"

# B-239: Default-Modell wird live ueber /api/tags resolved.
# Reihenfolge: installiertes PB_OLLAMA_MODEL env-var > Gemma-4-Family-Match >
# RECOMMENDED_MODELS aus ollama_client > erstes verfuegbares.
# Hartcoded-Tag "gemma4:e4b" existierte nirgends als Ollama-Tag und
# war ueberall hinterlegt -> jeder LLM-Call gab 404. Siehe B-239.
_GEMMA4_FAMILY_RE = "gemma4"  # family-Feld in /api/tags
OLLAMA_MODEL: str | None = None  # Lazy resolved, siehe _resolve_default_model()


def _resolve_default_model(base_url: str = OLLAMA_BASE) -> str | None:
    """Findet das aktuell beste verfuegbare Default-Modell.

    Reihenfolge:
    1. ``PB_OLLAMA_MODEL`` env-var, wenn dieses Modell installiert ist
    2. Auto-Auswahl ``select_best_model("chat")``: bestes installiertes
       Chat-faehiges Modell das in den VRAM (GTX 1060, 6 GB) passt, groesste
       Parameterzahl zuerst
    3. Fallback: erstes installiertes completion-faehiges Modell

    Returns ``None`` wenn Ollama nicht erreichbar oder leer.
    """
    try:
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            resp = client.get("/api/tags")
            if resp.status_code != 200:
                return None
            models = resp.json().get("models", [])
    except (httpx.RequestError, ValueError):
        return None

    if not models:
        return None

    installed = {m["name"] for m in models if m.get("name")}
    user_override = os.environ.get("PB_OLLAMA_MODEL")
    if user_override:
        if user_override in installed:
            return user_override
        logger.warning(
            "PB_OLLAMA_MODEL='%s' ist nicht installiert; waehle bestes verfuegbares Modell.",
            user_override,
        )

    try:
        from services.ollama_client import OllamaClient
        client = OllamaClient(base_url=base_url)
        # Auto-Auswahl: bestes Chat-faehiges Modell das in den VRAM (GTX 1060,
        # 6 GB) passt, groesste Parameterzahl zuerst. Loest die alte feste
        # Gemma-Prioritaet ab -> nutzt automatisch das beste installierte Modell.
        best = client.select_best_model("chat")
        if best:
            return best
        # Fallback: erstes installiertes completion-faehiges Modell
        for model in sorted(installed):
            if client.model_supports_completion(model):
                return model
    except ImportError:
        pass

    return None


def _find_ollama_bin() -> Path:
    """Ollama-Binary suchen: PyInstaller-Bundle > System-PATH > Standard-Pfade."""
    import sys
    if getattr(sys, 'frozen', False):  # PyInstaller-Bundle
        # PB Studio buendelt KEIN Ollama (pb_studio.spec haelt kein redist/).
        # System-Ollama ist dokumentierte Voraussetzung. Ein gebuendeltes
        # redist/ollama.exe wird nur genutzt, wenn es tatsaechlich existiert —
        # sonst faellt die Suche auf die System-Installationspfade durch,
        # statt einen nicht-existenten Pfad an Popen zu geben ([WinError 2]).
        bundled = Path(sys._MEIPASS) / 'redist' / ('ollama.exe' if os.name == 'nt' else 'ollama')
        if bundled.exists():
            return bundled

    # Bekannte Installationspfade
    candidates = [
        Path.home() / '.local' / 'bin' / 'ollama',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Ollama' / 'ollama.exe',
        Path('C:/Program Files/Ollama/ollama.exe'),
        Path('/usr/local/bin/ollama'),
        Path('/usr/bin/ollama'),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
            
    return Path('ollama')  # Fallback auf System-PATH


class OllamaService:
    """Singleton. Verwaltet Ollama-Prozess und stellt chat/vision bereit."""
    
    _instance: 'OllamaService | None' = None
    _instance_lock = threading.Lock()
    _process: subprocess.Popen | None = None

    @classmethod
    def get(cls) -> 'OllamaService':
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._is_ready = False
        self._model_cached = False
        self._start_lock = threading.Lock()
        self._start_thread: threading.Thread | None = None
        # B-239: Aufgeloester Default-Modellname (Cache nach erstem Lookup).
        self._default_model: str | None = None
        self._default_model_lock = threading.Lock()

    def get_default_model(self, force_refresh: bool = False) -> str | None:
        """Liefert den aktuell besten Default-Modellnamen (cached).

        Wird bei jedem Inference-Call benutzt, der kein explizites
        ``model``-Argument bekommt. Cache wird per ``force_refresh=True``
        oder nach erfolgreichem ``ensure_model()`` invalidiert.
        """
        with self._default_model_lock:
            if self._default_model is None or force_refresh:
                self._default_model = _resolve_default_model()
            return self._default_model

    # ── Lifecycle ─────────────────────────────────────────────

    def start_background(self) -> threading.Thread:
        """Startet Ollama headless in einem Daemon-Thread.

        App-Start und UI-Setup duerfen nicht bis zu 60s auf den
        HTTP-Ready-Check von ``start()`` warten. Diese Methode startet genau
        einen Hintergrund-Thread; weitere Aufrufe geben denselben Thread
        zurueck, solange er laeuft.
        """
        with self._start_lock:
            if self._start_thread is not None and self._start_thread.is_alive():
                return self._start_thread

            self._start_thread = threading.Thread(
                target=self.start,
                name="PB-Ollama-HeadlessStart",
                daemon=True,
            )
            self._start_thread.start()
            return self._start_thread

    def ready_cached(self) -> bool:
        """Liefert den bekannten Ready-Status ohne Netzwerkprobe."""
        return self._is_ready

    def start(self) -> None:
        """Ollama als versteckter Subprocess starten (no-op falls schon läuft)."""
        if self._is_api_ready():
            logger.info("Ollama: API bereits aktiv auf Port 11434")
            self._is_ready = True
            return
        if self._is_port_open(port=11434):
            logger.info("Ollama: Port 11434 offen, warte auf HTTP-API...")
            self._wait_for_api_ready(timeout_s=60.0, interval_s=0.5)
            return

        ollama_bin = _find_ollama_bin()
        logger.info("Starte Ollama von: %s", ollama_bin)

        env = os.environ.copy()
        # VRAM sofort freigeben nach Inference (Fix F-001)
        env['OLLAMA_KEEP_ALIVE'] = '0'

        # Versteckter Prozess (kein CMD-Fenster unter Windows)
        creation_flags = 0x08000000 if os.name == 'nt' else 0

        try:
            self._process = subprocess.Popen(
                [str(ollama_bin), "serve"],
                env=env,
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Ollama-Prozess gestartet (PID: %d)", self._process.pid)

            # B-113 / BUG-A10 / B-240: poll for HTTP-API-readiness so
            # callers that do ``service.start(); service.ensure_model(...)``
            # don't race the server-startup window. Bounded at ~60 s — der
            # cuda_v12-Cold-Load (HDD) braucht ~26 s ehe der Server
            # tatsaechlich Requests bedient. Frueher pollte das nur
            # ``_is_port_open()`` (3 s) — false-positive wenn Subprocess
            # Port oeffnet bevor er HTTP-Requests akzeptiert.
            self._wait_for_api_ready(timeout_s=60.0, interval_s=0.5)
        except Exception as e:
            logger.error("Fehler beim Starten von Ollama: %s", e)

    def stop(self) -> None:
        """Beendet den Ollama-Prozess sauber."""
        start_thread = self._start_thread
        if start_thread is not None and start_thread.is_alive():
            start_thread.join(timeout=1.0)
        if self._process:
            logger.info("Stoppe Ollama-Prozess...")
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            self._is_ready = False

    def _is_port_open(self, port: int = 11434) -> bool:
        """Prüft ob der Ollama-Port bereits belegt ist."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('localhost', port)) == 0

    def _is_api_ready(self) -> bool:
        """B-240: Vollstaendiger API-Ready-Check (TCP-Port + HTTP /api/version).

        Vermeidet false-positive wenn Subprocess Port oeffnet, bevor er
        HTTP-Requests bedient (typisch waehrend cuda_v12-Cold-Load).
        """
        if not self._is_port_open():
            return False
        try:
            with httpx.Client(base_url=OLLAMA_BASE, timeout=2.0) as client:
                return client.get("/api/version").status_code == 200
        except (httpx.RequestError, httpx.TimeoutException):
            return False

    def _wait_for_api_ready(self, timeout_s: float, interval_s: float) -> bool:
        """Warte begrenzt auf echte Ollama-HTTP-Readiness."""
        import time as _time

        deadline = _time.monotonic() + timeout_s
        while _time.monotonic() < deadline:
            if self._is_api_ready():
                self._is_ready = True
                logger.info(
                    "Ollama: API ready nach %.2fs",
                    timeout_s - (deadline - _time.monotonic()),
                )
                return True
            _time.sleep(interval_s)
        logger.warning(
            "Ollama: API nach %.0fs noch nicht ready - "
            "is_ready bleibt False, Caller kann re-poll'en.",
            timeout_s,
        )
        self._is_ready = False
        return False

    def _inference_timeout(self, read_timeout_s: float | None = None) -> httpx.Timeout:
        """B-242: Inference darf Cold-Load nicht per Read-Timeout abbrechen."""
        return httpx.Timeout(connect=10.0, read=read_timeout_s, write=None, pool=10.0)

    def _is_model_warm(self, model: str) -> bool:
        """B-242: Pruefe ob ``model`` aktuell in VRAM geladen ist (``/api/ps``).

        Wenn nicht warm, sollte Caller ``ensure_model()`` vorab rufen —
        ``ensure_model()`` hat offenes Read-Timeout und kann den
        Cold-Load (bis ~120 s fuer 4-GB-Modelle aus HDD-Cache)
        durchlaufen lassen, ohne dass der httpx-Client von ``chat()``
        die Connection abbricht.
        """
        try:
            with httpx.Client(base_url=OLLAMA_BASE, timeout=3.0) as client:
                resp = client.get("/api/ps")
                if resp.status_code != 200:
                    return False
                running = {m.get("name") for m in resp.json().get("models", [])}
                return model in running
        except (httpx.RequestError, httpx.TimeoutException):
            return False

    @property
    def is_ready(self) -> bool:
        """Prüft (schnell), ob die API antwortet."""
        if self._is_ready:
            return True
        # B-240: vollstaendiger API-Check statt nur Port-Open
        self._is_ready = self._is_api_ready()
        return self._is_ready

    # ── Modell-Management ──────────────────────────────────────

    def ensure_model(self, model_name: str | None = None, progress_cb: Callable[[str, float], None] | None = None) -> bool:
        """Stellt sicher dass das Modell geladen ist (laedt falls noetig).

        Synchron — blockiert den aufrufenden Thread bis der Download abgeschlossen ist.
        Wenn ``model_name`` None ist, wird das Default-Modell verwendet
        (B-239: Auto-Detect statt Hardcoded ``gemma4:e4b``).
        """
        if not self.is_ready:
            return False

        if model_name is None:
            model_name = self.get_default_model()
            if model_name is None:
                logger.warning("ensure_model: Kein Default-Modell ermittelbar (keine Modelle installiert?)")
                return False

        # B-037 / B113: connect-Timeout setzen (10s) damit ein toter
        # Ollama-Server schnell erkannt wird; read/write offen lassen
        # weil Modell-Pull bei grossen Modellen Stunden dauern kann.
        _pull_timeout = httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0)
        with httpx.Client(base_url=OLLAMA_BASE, timeout=_pull_timeout) as client:
            # Pruefen ob Modell bereits da ist
            try:
                tags = client.get("/api/tags")
                if tags.status_code == 200:
                    models = tags.json().get("models", [])
                    if any(m.get("name") == model_name for m in models):
                        logger.info("Modell '%s' bereits vorhanden.", model_name)
                        return True
            except Exception as e:
                logger.warning("Fehler beim Pruefen der Modelle: %s", e)

            # Modell laden via API
            logger.info("Lade Modell '%s' herunter...", model_name)
            try:
                with client.stream("POST", "/api/pull", json={"name": model_name}) as response:
                    for line in response.iter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        status = chunk.get('status', '')
                        total = chunk.get('total', 0)
                        completed = chunk.get('completed', 0)

                        pct = completed / total if total > 0 else 0
                        if progress_cb:
                            progress_cb(status, pct)

                logger.info("Modell '%s' erfolgreich geladen.", model_name)
                return True
            except Exception as e:
                logger.error("Fehler beim Laden des Modells '%s': %s", model_name, e)
                return False

    # ── Inference ─────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        num_predict: int = 1024,
    ) -> str:
        """Synchroner Wrapper fuer Chat-Inference (K7-Fix: kein async mehr).

        Prueft vor dem Request den Pause-Status des OllamaClient (K8-Fix),
        damit VRAM-Schutz nicht umgangen wird.

        B-239: ``model=None`` -> Auto-Detect Default-Modell (kein Hardcode mehr).
        B-239: ``num_predict=1024`` Default — Reasoning-Modelle (Gemma 4)
        brauchen ~700 Tokens fuers Thinking + die eigentliche Antwort. Der
        Ollama-Default 128 schneidet die echte Antwort weg.
        """
        # K8-Fix: Pause-Check — VRAM-Schutz respektieren
        from services.ollama_client import get_ollama_client
        oc = get_ollama_client()
        if oc.is_paused:
            logger.warning("OllamaService.chat(): OllamaClient ist pausiert — Request abgelehnt.")
            return "Fehler: OllamaClient ist pausiert (GPU-intensive Operation laeuft)"

        if model is None:
            model = self.get_default_model()
            if model is None:
                return "Fehler: Kein Ollama-Modell verfuegbar (Tipp: 'ollama pull gemma3:4b')"

        # B-242: Cold-Load-Schutz. ensure_model() prueft/pullt das Modell
        # vorab. Der eigentliche Chat-Request nutzt danach offenen
        # Read-Timeout, damit Ollama einen HDD-Cold-Load nicht als
        # Client-Abbruch sieht.
        if not self._is_model_warm(model):
            logger.info("OllamaService.chat(): Modell '%s' nicht warm — ensure_model() vorab.", model)
            if not self.ensure_model(model):
                return f"Fehler: Modell '{model}' konnte nicht geladen werden"

        with httpx.Client(base_url=OLLAMA_BASE, timeout=self._inference_timeout()) as client:
            try:
                response = client.post("/api/chat", json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": num_predict},
                })
                if response.status_code == 200:
                    # B1-Fix: Thinking models return response in "thinking" field instead of "content"
                    content = response.json().get("message", {}).get("content", "")
                    if not content:
                        content = response.json().get("message", {}).get("thinking", "")
                    return content
                return f"Fehler: {response.status_code}"
            except Exception as e:
                logger.error("Ollama Chat Fehler: %s", e)
                return f"Fehler: {e}"

    def vision(
        self,
        image_paths: list[str],
        prompt: str,
        model: str | None = None,
        num_predict: int = 1024,
        read_timeout_s: float | None = None,
    ) -> str:
        """Synchroner Wrapper fuer Vision-Inference (K7-Fix: kein async mehr).

        Prueft vor dem Request den Pause-Status des OllamaClient (K8-Fix),
        damit VRAM-Schutz nicht umgangen wird.
        B-239: ``model=None`` -> Auto-Detect.
        B-242: offener Read-Timeout, weil Vision-Modelle Cold-Load brauchen.
        """
        # K8-Fix: Pause-Check — VRAM-Schutz respektieren
        from services.ollama_client import get_ollama_client
        oc = get_ollama_client()
        if oc.is_paused:
            logger.warning("OllamaService.vision(): OllamaClient ist pausiert — Request abgelehnt.")
            return "Fehler: OllamaClient ist pausiert (GPU-intensive Operation laeuft)"

        if model is None:
            model = self.get_default_model()
            if model is None:
                return "Fehler: Kein Ollama-Modell verfuegbar"

        # B-242: Cold-Load-Schutz analog zu chat(). Vision-Modelle (Moondream
        # etc.) sind oft kleiner, aber Cold-Load aus HDD-Cache kann ebenfalls
        # > 60 s dauern. Der finale Request nutzt offenen Read-Timeout.
        if not self._is_model_warm(model):
            logger.info("OllamaService.vision(): Modell '%s' nicht warm — ensure_model() vorab.", model)
            if not self.ensure_model(model):
                return f"Fehler: Modell '{model}' konnte nicht geladen werden"

        import base64

        def encode_image(path):
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        images_b64 = [encode_image(p) for p in image_paths if os.path.exists(p)]

        with httpx.Client(base_url=OLLAMA_BASE, timeout=self._inference_timeout(read_timeout_s=read_timeout_s)) as client:
            try:
                response = client.post("/api/chat", json={
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": prompt,
                        "images": images_b64
                    }],
                    "stream": False,
                    "options": {"num_predict": num_predict},
                })
                if response.status_code == 200:
                    content = response.json().get("message", {}).get("content", "")
                    if content:
                        return content
                    logger.info(
                        "OllamaService.vision(): /api/chat returned empty content "
                        "for '%s' — retrying via /api/generate.",
                        model,
                    )
                    generate_response = client.post("/api/generate", json={
                        "model": model,
                        "prompt": prompt,
                        "images": images_b64,
                        "stream": False,
                        "options": {"num_predict": num_predict},
                    })
                    if generate_response.status_code == 200:
                        return generate_response.json().get("response", "")
                    return f"Fehler: {generate_response.status_code}"
                return f"Fehler: {response.status_code}"
            except Exception as e:
                logger.error("Ollama Vision Fehler: %s", e)
                return f"Fehler: {e}"

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

from services.ollama_client import _normalize_ollama_host

logger = logging.getLogger(__name__)

# Wie viele Zeichen des Antwort-Bodys in die Fehlermeldung wandern. Genug fuer
# Ollamas Fehlertexte, kurz genug fuer eine Logzeile.
_FEHLER_BODY_MAX = 300


def _fehlertext(response, endpunkt: str, model: str) -> str:
    """Statuscode UND Begruendung aus einer fehlgeschlagenen Ollama-Antwort.

    Vorher stand hier nur ``f"Fehler: {response.status_code}"`` — der Body
    wurde verworfen. Bei den HTTP-500-Fehlern der Nacht vom 14.08. war deshalb
    nicht feststellbar, WARUM Ollama ablehnte; die Ursache (eine
    Ollama-Version, die das Modell nicht laden konnte) liess sich erst durch
    manuelle Nachstellung finden. Das hat Stunden gekostet, die diese eine
    Zeile gespart haette.
    """
    grund = ""
    try:
        daten = response.json()
        if isinstance(daten, dict):
            grund = str(daten.get("error") or daten.get("message") or "")
    except Exception:
        try:
            grund = (response.text or "")[:_FEHLER_BODY_MAX]
        except Exception:
            grund = ""
    grund = grund.strip()[:_FEHLER_BODY_MAX]

    logger.error(
        "Ollama %s antwortete %s fuer Modell '%s'%s",
        endpunkt, response.status_code, model,
        f": {grund}" if grund else " (ohne Begruendung im Body)",
    )
    return f"{response.status_code}{f' — {grund}' if grund else ''}"

# B-760: localhost -> 127.0.0.1 (IPv6-::1-Falle unter Windows; fremde
# Ollama-Instanz auf ::1 zog Vision am 2026-08-04 auf CPU).
OLLAMA_BASE = _normalize_ollama_host("http://localhost:11434")

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


# B-780: Untergrenze fuer ein plausibles ollama-Binary. Reale Groessen
# liegen bei ~34 MB (0.32.6) bzw. ~39 MB (0.21.2); 1 MB trennt sicher
# zwischen echtem Binary und Platzhalter/Textdatei, ohne kuenftige
# schlankere Builds auszusperren.
_MIN_OLLAMA_BIN_BYTES: int = 1_000_000


def _find_ollama_bin() -> Path:
    """Ollama-Binary suchen: PB_OLLAMA_BIN > PyInstaller-Bundle > System-PATH > Standard-Pfade."""
    import sys
    # GPU-Fix (2026-07-17): expliziter Override auf eine bestimmte ollama.exe.
    # Noetig, weil das System-Ollama 0.30.10 auf der GTX 1060 / Treiber 546.33
    # NUR CPU laeuft (CUDA verlangt Treiber 570+). Die GPU-faehige 0.21.2
    # (cuda_v12/Pascal) wird per PB_OLLAMA_BIN erzwungen. Hat Vorrang.
    env_bin = os.environ.get("PB_OLLAMA_BIN")
    if env_bin:
        p = Path(env_bin)
        if p.exists():
            # B-780: exists() allein reicht nicht — ein Platzhalter oder
            # abgebrochener Download passiert den Check und wird als
            # gueltiges Binary geloggt. Praeventive Haertung; der
            # urspruengliche Verdacht, der Pin HIER sei eine 1-Byte-Datei,
            # war ein Messfehler (das Binary ist intakt, 41 MB, 0.21.2 —
            # Korrektur 2026-08-09). Ein kaputter Pin maskierte
            # damit jede funktionierende Alternative, und der Start
            # scheiterte erst spaeter unverstaendlich.
            try:
                size = p.stat().st_size
            except OSError as exc:
                logger.warning(
                    "PB_OLLAMA_BIN='%s' nicht lesbar (%s) — normale Suche.",
                    env_bin, exc,
                )
                size = -1
            if size >= _MIN_OLLAMA_BIN_BYTES:
                logger.info("Ollama-Binary via PB_OLLAMA_BIN: %s", p)
                return p
            if size >= 0:
                logger.warning(
                    "PB_OLLAMA_BIN='%s' ist nur %d Byte gross (erwartet >= %d) "
                    "— unbrauchbarer Platzhalter, normale Suche.",
                    env_bin, size, _MIN_OLLAMA_BIN_BYTES,
                )
        else:
            logger.warning("PB_OLLAMA_BIN='%s' existiert nicht — normale Suche.", env_bin)

    if getattr(sys, 'frozen', False):  # PyInstaller-Bundle
        # PB Studio buendelt Ollama optional: pb_studio.spec packt redist/
        # (ollama.exe + lib, 0.21.2/cuda_v12 fuer GTX 1060) INS Bundle, sofern
        # redist/ beim Build lokal vorhanden ist (2.5 GB, gitignored, vendored).
        # Das gebuendelte redist/ollama.exe wird nur genutzt, wenn es tatsaechlich
        # existiert — sonst faellt die Suche auf die System-Installationspfade
        # durch (System-Ollama als Fallback), statt einen nicht-existenten Pfad
        # an Popen zu geben ([WinError 2]).
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


def _emit_model_status(phase: str, model: str, task: str) -> None:
    """Meldet den Modell-Lade-Status an die UI (ModelStatusField).

    Defensiv: schlaegt nie fehl, auch ohne laufende Qt-App (Tests/headless).
    """
    try:
        from services.model_load_status import ModelLoadStatus
        status = ModelLoadStatus.get()
        if phase == "loading":
            status.set_loading(model, task)
        elif phase == "ready":
            status.set_ready(model, task)
        elif phase == "error":
            status.set_error(model, task)
    except Exception:
        pass


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
        self._stop_requested = threading.Event()
        self._stop_generation = 0
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

    # ── GPU-Fail-fast (2026-07-17) ────────────────────────────

    def verify_gpu(self, model: str | None = None, timeout_s: float = 120.0) -> tuple[str, str]:
        """Prueft, ob Ollama die Inferenz WIRKLICH auf der GPU macht.

        User-Hartregel: kein LLM darf auf der CPU laufen. Das System-Ollama
        0.30.10 laeuft auf der GTX 1060 / Treiber 546.33 nur CPU (CUDA verlangt
        Treiber 570+); die GPU-faehige 0.21.2 laeuft via CUDA/cuda_v12.

        Laedt kurz ein Modell (1 Token) und liest ``/api/ps`` ``size_vram``.
        Returns ``(state, detail)``; state = ``gpu`` | ``partial`` | ``cpu`` |
        ``unknown``. Bei ``cpu``/``partial`` wird CRITICAL geloggt.
        """
        try:
            if model is None:
                model = self.get_default_model()
            if not model:
                return ("unknown", "kein Modell verfuegbar")
            with httpx.Client(base_url=OLLAMA_BASE, timeout=timeout_s) as c:
                c.post("/api/generate", json={
                    "model": model, "prompt": "hi", "stream": False,
                    "keep_alive": "30s", "options": {"num_predict": 1},
                })
                ps = c.get("/api/ps").json()
            loaded = ps.get("models", []) or []
            me = next((m for m in loaded if m.get("name") == model),
                      loaded[0] if loaded else None)
            if not me:
                return ("unknown", "Modell nicht in /api/ps")
            size = int(me.get("size") or 0)
            vram = int(me.get("size_vram") or 0)
            if vram <= 0:
                logger.critical(
                    "OLLAMA LAEUFT AUF CPU! Modell '%s' size_vram=0 — GPU-Pflicht "
                    "verletzt. Ursache pruefen: Ollama-Version (0.21.2 noetig fuer "
                    "GTX 1060/Treiber 546.33; 0.30.10 = CPU) via PB_OLLAMA_BIN.",
                    model)
                return ("cpu", f"{model}: size_vram=0 (CPU)")
            if size and vram < size * 0.9:
                logger.critical(
                    "OLLAMA nur TEILWEISE auf GPU: '%s' VRAM=%d/%d Bytes.",
                    model, vram, size)
                return ("partial", f"{model}: {vram}/{size} VRAM (teilweise CPU)")
            logger.info("Ollama GPU-Check OK: '%s' size_vram=%d Bytes (GPU).", model, vram)
            return ("gpu", f"{model}: {vram} Bytes VRAM (GPU)")
        except Exception as e:
            logger.warning("Ollama GPU-Check fehlgeschlagen: %s", e)
            return ("unknown", str(e))

    def verify_gpu_async(self) -> None:
        """Feuert ``verify_gpu`` in einem Daemon-Thread und meldet bei CPU/partial
        einen lauten Fehler ans Status-Feld (ModelLoadStatus) — nie stiller CPU."""
        def _run():
            state, detail = self.verify_gpu()
            if state in ("cpu", "partial"):
                _emit_model_status("error", f"CPU-BETRIEB ({detail})", "gpu-guard")
        threading.Thread(target=_run, name="OllamaGpuVerify", daemon=True).start()

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
                if not self._stop_requested.is_set():
                    return self._start_thread

                cancelled_thread = self._start_thread
                stop_generation = self._stop_generation
                restart_thread = threading.Thread(
                    target=self._restart_after_cancelled_start,
                    args=(cancelled_thread, stop_generation),
                    name="PB-Ollama-HeadlessRestart",
                    daemon=True,
                )
                self._start_thread = restart_thread
                restart_thread.start()
                return restart_thread

            self._stop_requested.clear()
            self._start_thread = threading.Thread(
                target=self.start,
                name="PB-Ollama-HeadlessStart",
                daemon=True,
            )
            self._start_thread.start()
            return self._start_thread

    def _restart_after_cancelled_start(
        self,
        cancelled_thread: threading.Thread,
        stop_generation: int,
    ) -> None:
        """Startet erst neu, nachdem der stornierte Startthread beendet ist."""
        cancelled_thread.join()
        with self._start_lock:
            if (
                self._start_thread is not threading.current_thread()
                or self._stop_generation != stop_generation
            ):
                return
            self._stop_requested.clear()
        self.start()

    def ready_cached(self) -> bool:
        """Liefert den bekannten Ready-Status ohne Netzwerkprobe."""
        return self._is_ready

    def start(self) -> None:
        """Ollama als versteckter Subprocess starten (no-op falls schon läuft)."""
        with self._start_lock:
            if self._stop_requested.is_set():
                start_thread = self._start_thread
                if (
                    start_thread is threading.current_thread()
                    or (start_thread is not None and start_thread.is_alive())
                ):
                    return
                # Direkter synchroner Restart nach vollständig beendetem Stop.
                self._stop_requested.clear()
        if self._stop_requested.is_set():
            return
        if self._is_api_ready():
            if self._stop_requested.is_set():
                return
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

        # B-604: Vulkan-Backend unterbinden + CUDA (GTX 1060) forcieren.
        # Der llama-server-Backend-Prozess crasht in ggml-vulkan.dll — das
        # verletzt zudem die GPU-Hartregel (ausschliesslich GTX 1060 via CUDA,
        # kein Vulkan, keine Intel-iGPU). Env-Fix (User-Entscheid).
        # UNVERIFIZIERT ob dies den 46-Min-Vulkan-Crash tatsaechlich behebt
        # (Root-Cause via Mini-Dump nicht 100% geklaert) — Verifikation im
        # Backlog. Beide Vars sind aber belegt und in die richtige Richtung
        # (CUDA-only, Vulkan aus) wirkend, ohne Regressions-Risiko am
        # System-Ollama-Fallback-Pfad.
        #
        # OLLAMA_VULKAN=0 -> Vulkan-Backend-Discovery deaktivieren.
        #   Beleg: envconfig `EnableVulkan = BoolWithDefault("OLLAMA_VULKAN")`
        #   https://pkg.go.dev/github.com/ollama/ollama/envconfig
        # CUDA_VISIBLE_DEVICES=0 -> nur GTX 1060 (cuda:0) sichtbar.
        #   Versions-unabhaengiger CUDA-Standard.
        #   https://docs.ollama.com/gpu
        env['OLLAMA_VULKAN'] = '0'
        env['CUDA_VISIBLE_DEVICES'] = '0'

        # Versteckter Prozess (kein CMD-Fenster unter Windows)
        creation_flags = 0x08000000 if os.name == 'nt' else 0

        try:
            # B-740: Stop-Request und Popen muessen unter demselben Lock
            # liegen. Sonst kann stop() zwischen Check und Popen fertig werden
            # und der Startthread danach einen unbeaufsichtigten Serve starten.
            with self._start_lock:
                if self._stop_requested.is_set():
                    return
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
        with self._start_lock:
            self._stop_generation += 1
            self._stop_requested.set()
            # B-740: Lock bis nach Ownership-Cleanup halten. Ein paralleler
            # Restart darf keinen neuen Popen in self._process eintragen,
            # den dieser Stop anschliessend als vermeintlich alten Handle
            # loescht und dadurch unbeaufsichtigt laesst.
            start_thread = self._start_thread
            if (
                start_thread is not None
                and start_thread is not threading.current_thread()
                and start_thread.is_alive()
            ):
                start_thread.join(timeout=1.0)
            process = self._process
            if process:
                logger.info("Stoppe Ollama-Prozess...")
                if os.name == "nt" and process.poll() is None:
                    # B-740: Ollama `serve` erzeugt einen engine-runner. Parent
                    # zuerst einzeln zu terminieren orphaned den Runner. `/T`
                    # beendet ausschliesslich den von PB gestarteten Prozessbaum.
                    tree_killed = False
                    try:
                        result = subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                            timeout=5,
                        )
                        tree_killed = result.returncode == 0
                    except (OSError, subprocess.SubprocessError) as exc:
                        logger.warning(
                            "Ollama-Prozessbaum konnte nicht beendet werden; "
                            "falle auf Parent-Cleanup zurück: %s",
                            exc,
                        )
                    if not tree_killed and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                elif process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                self._process = None
                self._is_ready = False

    def _is_port_open(self, port: int = 11434) -> bool:
        """Prüft ob der Ollama-Port bereits belegt ist."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # B-760: 127.0.0.1 statt localhost — konsistent zu OLLAMA_BASE.
            return s.connect_ex(('127.0.0.1', port)) == 0

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
            if self._stop_requested.is_set():
                self._is_ready = False
                return False
            if self._is_api_ready():
                if self._stop_requested.is_set():
                    self._is_ready = False
                    return False
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
        read_timeout_s: float | None = None,
        task: str = "chat",
    ) -> str:
        """Synchroner Wrapper fuer Chat-Inference (K7-Fix: kein async mehr).

        Prueft vor dem Request den Pause-Status des OllamaClient (K8-Fix),
        damit VRAM-Schutz nicht umgangen wird.

        B-239: ``model=None`` -> Auto-Detect Default-Modell (kein Hardcode mehr).
        B-239: ``num_predict=1024`` Default — Reasoning-Modelle (Gemma 4)
        brauchen ~700 Tokens fuers Thinking + die eigentliche Antwort. Der
        Ollama-Default 128 schneidet die echte Antwort weg.

        B-669: ``read_timeout_s`` (analog ``vision()``) erlaubt dem Aufrufer,
        den Request zu binden. Default bleibt ``None`` = offener Read
        (B-242, Cold-Load-Schutz) — nur explizit bindende Callsites laufen
        nicht mehr unbegrenzt gegen einen haengenden Socket.
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
            _emit_model_status("loading", model, task)
            if not self.ensure_model(model):
                _emit_model_status("error", model, task)
                return f"Fehler: Modell '{model}' konnte nicht geladen werden"

        with httpx.Client(base_url=OLLAMA_BASE, timeout=self._inference_timeout(read_timeout_s=read_timeout_s)) as client:
            try:
                response = client.post("/api/chat", json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": num_predict},
                })
                if response.status_code == 200:
                    _emit_model_status("ready", model, task)
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
        task: str = "vision",
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
        warm_before = self._is_model_warm(model)
        logger.info(
            "B-599 OllamaService.vision warm_state before model=%s warm=%s read_timeout_s=%s images=%d",
            model,
            warm_before,
            read_timeout_s,
            len(image_paths),
        )
        if not warm_before:
            logger.info("OllamaService.vision(): Modell '%s' nicht warm — ensure_model() vorab.", model)
            _emit_model_status("loading", model, task)
            if not self.ensure_model(model):
                _emit_model_status("error", model, task)
                return f"Fehler: Modell '{model}' konnte nicht geladen werden"
        warm_after = self._is_model_warm(model)
        logger.info(
            "B-599 OllamaService.vision warm_state after_ensure model=%s warm=%s read_timeout_s=%s",
            model,
            warm_after,
            read_timeout_s,
        )

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
                    # Fixplan 2026-07-07: Thinking-Modelle (gemma4:e4b) legen
                    # die Antwort sonst ins "thinking"-Feld und "content"
                    # bleibt leer — num_predict wird vom Denken aufgefressen.
                    # Nicht-Thinking-Modelle ignorieren das Feld.
                    "think": False,
                    "options": {"num_predict": num_predict},
                })
                if response.status_code == 200:
                    _emit_model_status("ready", model, task)
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
                        "think": False,
                        "options": {"num_predict": num_predict},
                    })
                    if generate_response.status_code == 200:
                        return generate_response.json().get("response", "")
                    return f"Fehler: {_fehlertext(generate_response, '/api/generate', model)}"
                return f"Fehler: {_fehlertext(response, '/api/chat', model)}"
            except Exception as e:
                logger.error("Ollama Vision Fehler: %s", e)
                return f"Fehler: {e}"

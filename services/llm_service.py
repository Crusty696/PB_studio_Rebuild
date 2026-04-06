"""
Lokaler LLM-Service — Ollama-Prozess-Lifecycle-Management für PB Studio.

Startet Ollama als unsichtbaren Hintergrund-Prozess (kein CMD-Fenster),
kommuniziert per HTTP mit dem Modell und beendet den Prozess sauber
beim App-Exit.

Nutzt den bestehenden OllamaClient fuer die eigentliche HTTP-Kommunikation.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from services.ollama_client import OllamaClient, get_ollama_client

logger = logging.getLogger(__name__)

# Windows: CREATE_NO_WINDOW Flag — verhindert CMD-Popup
CREATE_NO_WINDOW = 0x08000000

# Ollama-Binary Suchpfade (relativ zum Projekt-Root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_BIN_PATHS = [
    _PROJECT_ROOT / "bin" / "ollama" / "ollama.exe",
    _PROJECT_ROOT / "bin" / "ollama.exe",
]

# Standard-Modell fuer Edit-Prompts
DEFAULT_EDIT_MODEL = "gemma4:e4b"

# Maximale Wartezeit fuer Server-Start (Sekunden)
OLLAMA_STARTUP_TIMEOUT_SEC = 30
OLLAMA_STARTUP_POLL_INTERVAL_SEC = 0.5

# System-Prompt fuer Edit-Aufgaben
EDIT_SYSTEM_PROMPT = """\
Du bist ein präziser JSON-Assistent für PB Studio, eine Video/Audio-Produktionssoftware.
Antworte IMMER mit validem JSON. Kein Text davor oder danach.
Deine Antwort muss dieses Format haben:
{"result": "<deine Antwort>", "confidence": <0.0-1.0>}
"""


class LocalLLMService:
    """Singleton-Service: Verwaltet den Ollama-Prozess und bietet LLM-Zugriff.

    Startet Ollama als Hintergrund-Prozess, wartet auf Bereitschaft
    und bietet eine einfache prompt_to_edit()-Methode fuer LLM-Aufrufe.

    Verwendung:
        service = LocalLLMService.instance()
        service.start()
        result = service.prompt_to_edit("Beschreibe diesen Clip in 3 Worten")
        service.stop()
    """

    _instance: LocalLLMService | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._started = False
        self._model: str = DEFAULT_EDIT_MODEL
        self._ollama_bin: Path | None = None
        self._client: OllamaClient | None = None

        # atexit-Handler registrieren fuer sauberes Beenden
        atexit.register(self._cleanup)

    @classmethod
    def instance(cls) -> LocalLLMService:
        """Gibt die Singleton-Instanz zurück. Thread-safe."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = LocalLLMService()
                    logger.info("LocalLLMService: Singleton erstellt.")
        return cls._instance

    # ------------------------------------------------------------------
    # Ollama-Binary finden
    # ------------------------------------------------------------------

    def _find_ollama_binary(self) -> Path | None:
        """Sucht die Ollama-Executable in bekannten Pfaden und im System-PATH."""
        # 1. Projekt-relative Pfade pruefen
        for path in OLLAMA_BIN_PATHS:
            if path.is_file():
                logger.info("LocalLLMService: Ollama gefunden: %s", path)
                return path

        # 2. System-PATH pruefen
        system_ollama = shutil.which("ollama")
        if system_ollama:
            resolved = Path(system_ollama).resolve()
            logger.info("LocalLLMService: Ollama im PATH gefunden: %s", resolved)
            return resolved

        logger.warning(
            "LocalLLMService: Ollama nicht gefunden. "
            "Erwartet in: %s oder im System-PATH.",
            ", ".join(str(p) for p in OLLAMA_BIN_PATHS),
        )
        return None

    # ------------------------------------------------------------------
    # Prozess-Lifecycle
    # ------------------------------------------------------------------

    def start(self, model: str | None = None) -> bool:
        """Startet den Ollama-Server als Hintergrund-Prozess.

        Args:
            model: Optionales Modell (Standard: gemma3:4b).

        Returns:
            True wenn der Server erfolgreich gestartet wurde oder bereits laeuft.
        """
        with self._lock:
            if self._started and self._process and self._process.poll() is None:
                logger.debug("LocalLLMService: Server laeuft bereits (PID %d).", self._process.pid)
                return True

            if model:
                self._model = model

            # Pruefen ob Ollama bereits extern laeuft
            client = get_ollama_client()
            if client.is_available():
                logger.info("LocalLLMService: Externer Ollama-Server erkannt, nutze diesen.")
                self._client = client
                self._started = True
                return True

            # Binary finden
            self._ollama_bin = self._find_ollama_binary()
            if not self._ollama_bin:
                logger.error("LocalLLMService: Kann Ollama nicht starten — Binary nicht gefunden.")
                return False

            # Prozess starten
            try:
                cmd = [str(self._ollama_bin), "serve"]
                creation_flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0

                # AMD RX 7800 XT compatibility + VRAM-freundliches Verhalten
                env = os.environ.copy()
                env["OLLAMA_KEEP_ALIVE"] = "0"           # Modell sofort aus VRAM nach Inference
                env["HSA_OVERRIDE_GFX_VERSION"] = "11.0.0"  # AMD RX 7800 XT ROCm-Kompatibilität

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                    env=env,
                )
                logger.info(
                    "LocalLLMService: Ollama gestartet (PID %d, Binary: %s).",
                    self._process.pid,
                    self._ollama_bin,
                )
            except OSError as e:
                logger.error("LocalLLMService: Fehler beim Starten von Ollama: %s", e)
                return False

            # Auf Server-Bereitschaft warten
            self._client = get_ollama_client()
            if not self._wait_for_server():
                logger.error("LocalLLMService: Server-Timeout nach %ds.", OLLAMA_STARTUP_TIMEOUT_SEC)
                # _terminate_process statt self.stop() — Lock ist bereits gehalten
                self._terminate_process()
                return False

            self._started = True
            logger.info("LocalLLMService: Server bereit.")
            return True

    def _wait_for_server(self) -> bool:
        """Pollt den Health-Endpoint bis der Server antwortet."""
        client = self._client or get_ollama_client()
        deadline = time.monotonic() + OLLAMA_STARTUP_TIMEOUT_SEC

        while time.monotonic() < deadline:
            if client.is_available():
                return True
            # Pruefen ob der Prozess abgestuerzt ist
            if self._process and self._process.poll() is not None:
                logger.error(
                    "LocalLLMService: Ollama-Prozess beendet mit Code %d.",
                    self._process.returncode,
                )
                return False
            time.sleep(OLLAMA_STARTUP_POLL_INTERVAL_SEC)

        return False

    def _terminate_process(self) -> None:
        """Beendet den Ollama-Prozess. Muss mit self._lock gehalten aufgerufen werden."""
        self._started = False
        if self._process is not None:
            pid = self._process.pid
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                    logger.info("LocalLLMService: Ollama beendet (PID %d).", pid)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    try:
                        self._process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logger.error("LocalLLMService: Prozess konnte nicht beendet werden (PID %d).", pid)
                    logger.warning("LocalLLMService: Ollama musste gekillt werden (PID %d).", pid)
            except OSError as e:
                logger.debug("LocalLLMService: Fehler beim Beenden: %s", e)
            finally:
                self._process = None

    def stop(self) -> None:
        """Beendet den Ollama-Prozess sauber."""
        with self._lock:
            self._terminate_process()

    def _cleanup(self) -> None:
        """atexit-Handler: Beendet den Ollama-Prozess beim App-Exit."""
        if self._process is not None:
            logger.info("LocalLLMService: atexit — beende Ollama-Prozess...")
            self.stop()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True wenn der LLM-Service aktiv und erreichbar ist."""
        if not self._started:
            return False
        client = self._client or get_ollama_client()
        return client.is_available()

    @property
    def current_model(self) -> str:
        """Aktuell konfiguriertes Modell."""
        return self._model

    @current_model.setter
    def current_model(self, model: str) -> None:
        self._model = model

    # ------------------------------------------------------------------
    # LLM-Prompting
    # ------------------------------------------------------------------

    def prompt_to_edit(self, user_text: str, model: str | None = None) -> dict[str, Any]:
        """Sendet einen Prompt an das lokale LLM und gibt JSON zurück.

        Kommuniziert per HTTP mit Ollama auf localhost:11434.
        Das Modell wird angewiesen, strukturiertes JSON zurückzugeben.

        Args:
            user_text: Der Benutzer-Prompt (z.B. "Beschreibe diesen Clip").
            model: Optionales Modell-Override (Standard: self._model).

        Returns:
            dict mit der LLM-Antwort, z.B.:
            {"result": "...", "confidence": 0.85}
            Bei Fehlern: {"error": "...", "result": None, "confidence": 0.0}

        Raises:
            RuntimeError: Wenn der Service nicht gestartet ist.
        """
        if not self._started:
            raise RuntimeError(
                "LocalLLMService ist nicht gestartet. "
                "Rufe zuerst .start() auf."
            )

        use_model = model or self._model
        client = self._client or get_ollama_client()

        try:
            raw_response = client.chat(
                model=use_model,
                user_message=user_text,
                system_prompt=EDIT_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=1024,
            )

            # JSON parsen — LLMs wrappen JSON oft in Markdown-Fences
            cleaned = raw_response.strip()
            if "```" in cleaned:
                # Extrahiere JSON aus ```json ... ``` oder ``` ... ```
                fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", cleaned, re.DOTALL)
                if fence_match:
                    cleaned = fence_match.group(1).strip()

            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    return parsed
                # Falls Array oder anderer Typ: einpacken
                return {"result": parsed, "confidence": 0.5}
            except json.JSONDecodeError:
                # LLM hat kein valides JSON geliefert — Rohtext als Fallback
                logger.warning(
                    "LocalLLMService: LLM-Antwort war kein valides JSON, "
                    "nutze Rohtext als Fallback."
                )
                return {"result": raw_response, "confidence": 0.3}

        except Exception as e:
            logger.error("LocalLLMService.prompt_to_edit() Fehler: %s", e)
            return {"error": str(e), "result": None, "confidence": 0.0}

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def list_available_models(self) -> list[str]:
        """Gibt verfuegbare Modelle zurueck (delegiert an OllamaClient)."""
        client = self._client or get_ollama_client()
        return client.list_models()

    def __repr__(self) -> str:
        status = "running" if self.is_running else "stopped"
        pid = self._process.pid if self._process and self._process.poll() is None else None
        return f"LocalLLMService(model={self._model!r}, status={status}, pid={pid})"

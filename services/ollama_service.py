"""
OllamaService — zentraler Lifecycle-Manager für Ollama + Gemma 4.

Alle Aufrufe aus dem Rest der App laufen ausschliesslich über diese Klasse.
Kein anderes Modul importiert httpx oder kennt Port 11434.
"""

import subprocess
import os
import asyncio
import httpx
import json
import socket
import time
import logging
from pathlib import Path
from typing import Callable, Any

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:e4b"


def _find_ollama_bin() -> Path:
    """Ollama-Binary suchen: PyInstaller-Bundle > System-PATH > Standard-Pfade."""
    import sys
    if getattr(sys, 'frozen', False):  # PyInstaller-Bundle
        base = Path(sys._MEIPASS) / 'redist'
        return base / ('ollama.exe' if os.name == 'nt' else 'ollama')
    
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
    _process: subprocess.Popen | None = None

    @classmethod
    def get(cls) -> 'OllamaService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._is_ready = False
        self._model_cached = False

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """Ollama als versteckter Subprocess starten (no-op falls schon läuft)."""
        if self._is_port_open():
            logger.info('Ollama: bereits aktiv auf Port 11434')
            self._is_ready = True
            return

        ollama_bin = _find_ollama_bin()
        logger.info("Starte Ollama von: %s", ollama_bin)

        env = os.environ.copy()
        # AMD RX 7800 XT (gfx1101) Support (Fix für ROCm auf Windows)
        env['HSA_OVERRIDE_GFX_VERSION'] = '11.0.0'
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
        except Exception as e:
            logger.error("Fehler beim Starten von Ollama: %s", e)

    def stop(self) -> None:
        """Beendet den Ollama-Prozess sauber."""
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

    @property
    def is_ready(self) -> bool:
        """Prüft (schnell), ob die API antwortet."""
        if self._is_ready:
            return True
        self._is_ready = self._is_port_open()
        return self._is_ready

    # ── Modell-Management ──────────────────────────────────────

    async def ensure_model(self, model_name: str = OLLAMA_MODEL, progress_cb: Callable[[str, float], None] | None = None) -> bool:
        """Stellt sicher dass das Modell geladen ist (lädt falls nötig)."""
        if not self.is_ready:
            return False

        async with httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=None) as client:
            # Prüfen ob Modell bereits da ist
            try:
                tags = await client.get("/api/tags")
                if tags.status_code == 200:
                    models = tags.json().get("models", [])
                    if any(m.get("name") == model_name for m in models):
                        logger.info("Modell '%s' bereits vorhanden.", model_name)
                        return True
            except Exception as e:
                logger.warning("Fehler beim Prüfen der Modelle: %s", e)

            # Modell laden via API
            logger.info("Lade Modell '%s' herunter...", model_name)
            try:
                async with client.stream("POST", "/api/pull", json={"name": model_name}) as response:
                    async for line in response.aiter_lines():
                        if not line: continue
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

    async def chat(self, messages: list[dict], model: str = OLLAMA_MODEL) -> str:
        """Wrapper für Chat-Inference."""
        async with httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=60.0) as client:
            try:
                response = await client.post("/api/chat", json={
                    "model": model,
                    "messages": messages,
                    "stream": False
                })
                if response.status_code == 200:
                    return response.json().get("message", {}).get("content", "")
                return f"Fehler: {response.status_code}"
            except Exception as e:
                logger.error("Ollama Chat Fehler: %s", e)
                return f"Fehler: {e}"

    async def vision(self, image_paths: list[str], prompt: str, model: str = OLLAMA_MODEL) -> str:
        """Wrapper für Vision-Inference."""
        import base64
        
        def encode_image(path):
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        images_b64 = [encode_image(p) for p in image_paths if os.path.exists(p)]
        
        async with httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0) as client:
            try:
                response = await client.post("/api/chat", json={
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": prompt,
                        "images": images_b64
                    }],
                    "stream": False
                })
                if response.status_code == 200:
                    return response.json().get("message", {}).get("content", "")
                return f"Fehler: {response.status_code}"
            except Exception as e:
                logger.error("Ollama Vision Fehler: %s", e)
                return f"Fehler: {e}"

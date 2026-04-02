"""
Ollama HTTP-API-Client für PB Studio.

Kommuniziert mit einem lokal laufenden Ollama-Server
(Standard: http://localhost:11434).

Keine Abhängigkeiten ausser dem stdlib `urllib` — kein requests,
kein httpx. Läuft offline, keine API-Kosten.

Koordination mit dem ModelManager:
- Bevor GPU-intensive Modelle (Demucs, SigLIP) geladen werden,
  sollte Ollama kein schweres Inference laufen (VRAM-Konkurrenz).
- OllamaClient gibt 'paused'-Flag weiter; ModelManager ruft
  pause/resume auf, wenn nötig.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Default-Modelle für GTX 1060 (6 GB VRAM)
RECOMMENDED_MODELS = [
    "qwen2.5:7b-instruct-q4_K_M",   # ~4.5 GB — beste Qualität
    "phi3:mini",                      # ~2.3 GB — schnell, kompakt
    "llama3.1:8b-instruct-q4_K_M",   # ~4.7 GB — Allrounder
    "qwen2.5:1.5b-instruct",         # ~1.0 GB — sehr klein, schnell
    "qwen2.5:0.5b-instruct",         # ~0.4 GB — minimal
]

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_TIMEOUT_SEC = 120  # Chat-Inference kann dauern


class OllamaClient:
    """HTTP-Client für einen lokal laufenden Ollama-Server.

    Thread-safe. Alle Methoden können aus beliebigen Threads aufgerufen werden.

    Verwendung:
        client = OllamaClient()
        if client.is_available():
            models = client.list_models()
            reply = client.chat("qwen2.5:1.5b-instruct", "Hallo!")
    """

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout: int = DEFAULT_TIMEOUT_SEC,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._lock = threading.Lock()
        self._paused = False  # VRAM-Koordination: True = keine neuen Requests

    # ------------------------------------------------------------------
    # VRAM-Koordination
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Setzt Pause-Flag — neue Chat-Requests werden abgelehnt.

        Wird vom ModelManager gesetzt, wenn GPU-intensive Modelle laden.
        """
        with self._lock:
            if not self._paused:
                self._paused = True
                logger.info("OllamaClient: Pausiert (GPU-intensive Operation aktiv).")

    def resume(self) -> None:
        """Hebt Pause auf."""
        with self._lock:
            if self._paused:
                self._paused = False
                logger.info("OllamaClient: Fortgesetzt.")

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    # ------------------------------------------------------------------
    # Server-Erkennung
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Prüft ob Ollama läuft (via GET /api/version, Timeout 2s)."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/version",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_version(self) -> str | None:
        """Gibt die Ollama-Serverversion zurück oder None wenn nicht erreichbar."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/version",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                return data.get("version")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Modell-Verwaltung
    # ------------------------------------------------------------------

    def list_models(self) -> list[str]:
        """Gibt Liste der lokal verfügbaren Ollama-Modelle zurück.

        Returns:
            Liste von Modellnamen (z.B. ["qwen2.5:7b-instruct-q4_K_M", ...])
            Leere Liste wenn Ollama nicht läuft.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = data.get("models", [])
                return [m["name"] for m in models if isinstance(m, dict) and "name" in m]
        except Exception as e:
            logger.debug("OllamaClient.list_models() fehlgeschlagen: %s", e)
            return []

    def model_exists(self, model_name: str) -> bool:
        """Prüft ob ein bestimmtes Modell lokal verfügbar ist."""
        return model_name in self.list_models()

    def get_best_available_model(self) -> str | None:
        """Gibt das beste verfügbare Modell aus RECOMMENDED_MODELS zurück.

        Reihenfolge: Qualität vs. VRAM-Bedarf (bevorzugt kleinere Modelle
        die sicher in 6 GB passen wenn GPU-Applikation auch läuft).
        """
        available = set(self.list_models())
        for model in RECOMMENDED_MODELS:
            if model in available:
                return model
        # Fallback: erstes verfügbares Modell
        if available:
            return next(iter(available))
        return None

    # ------------------------------------------------------------------
    # Chat Completion
    # ------------------------------------------------------------------

    def chat(
        self,
        model: str,
        user_message: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> str:
        """Sendet eine Chat-Anfrage an Ollama und gibt die Antwort zurück.

        Args:
            model: Ollama-Modellname (z.B. "qwen2.5:1.5b-instruct")
            user_message: Benutzernachricht
            system_prompt: Optional System-Prompt
            temperature: Kreativität (0.0-1.0, Standard 0.1 für JSON-Output)
            max_tokens: Maximale Ausgabelänge

        Returns:
            Generierter Text

        Raises:
            RuntimeError: Wenn Ollama nicht erreichbar oder pausiert
            urllib.error.URLError: Bei Netzwerkfehler
        """
        with self._lock:
            if self._paused:
                raise RuntimeError(
                    "OllamaClient ist pausiert (GPU-intensive Operation läuft). "
                    "Bitte später erneut versuchen."
                )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        logger.debug("OllamaClient: Anfrage an %s mit Modell '%s'...", self.base_url, model)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
                # Ollama non-streaming response: {"message": {"role": "assistant", "content": "..."}}
                content = data.get("message", {}).get("content", "")
                logger.debug("OllamaClient: Antwort erhalten (%d Zeichen).", len(content))
                return content.strip()
        except urllib.error.URLError as e:
            logger.error("OllamaClient: Verbindungsfehler: %s", e)
            raise RuntimeError(f"Ollama nicht erreichbar: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("OllamaClient: Ungültige JSON-Antwort: %s", e)
            raise RuntimeError(f"Ollama hat ungültiges JSON zurückgegeben: {e}") from e

    def chat_with_history(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> str:
        """Sendet eine Chat-Anfrage mit vollständiger Message-History.

        Args:
            model: Ollama-Modellname
            messages: Liste von {"role": "system/user/assistant", "content": "..."}
            temperature: Kreativität
            max_tokens: Maximale Ausgabelänge

        Returns:
            Generierter Text
        """
        with self._lock:
            if self._paused:
                raise RuntimeError("OllamaClient ist pausiert.")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "").strip()
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama nicht erreichbar: {e}") from e

    # ------------------------------------------------------------------
    # Tool-Use / Function-Calling (AP-5)
    # ------------------------------------------------------------------

    def supports_tools(self, model: str) -> bool:
        """Prüft ob ein Modell Tool-Use / Function-Calling unterstützt.

        Qwen2.5, Llama 3.1+, Mistral 0.3+ und Phi3 unterstützen Tool-Use.
        Kleine Modelle (<1B) unterstützen es oft NICHT zuverlässig.
        """
        supported_prefixes = [
            "qwen2.5:", "qwen2:", "llama3.1:", "llama3.2:",
            "llama3.3:", "mistral:", "phi3:", "gemma2:",
        ]
        model_lower = model.lower()
        for prefix in supported_prefixes:
            if model_lower.startswith(prefix):
                # Kleine Modelle ausschliessen (<1B Parameter)
                if any(tiny in model_lower for tiny in [":0.5b", ":0.5b-", "0.5b-"]):
                    return False
                return True
        return False

    def chat_with_tools(
        self,
        model: str,
        user_message: str,
        tools: list[dict],
        system_prompt: str | None = None,
        messages: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """Sendet eine Chat-Anfrage mit Tool-Definitionen (Function-Calling).

        Ollama-kompatibel: Gibt entweder eine text-Antwort ODER tool_calls zurück.

        Args:
            model: Ollama-Modellname (muss Tool-Use unterstützen)
            user_message: Aktuelle Benutzeranfrage
            tools: Liste von Tool-Definitionen im OpenAI-Format:
                   [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
            system_prompt: Optionaler System-Prompt
            messages: Optionale vollständige Message-History (überschreibt user_message + system_prompt)
            temperature: Kreativität (Standard: 0.1 für deterministisches Tool-Calling)
            max_tokens: Max Ausgabelänge

        Returns:
            {
                "type": "tool_calls" | "text",
                "tool_calls": [{"function": {"name": ..., "arguments": {...}}}],  # bei tool_calls
                "content": str,   # bei text-Antwort
                "raw": dict,      # vollständige Ollama-Antwort
            }

        Raises:
            RuntimeError: Wenn Ollama nicht erreichbar oder pausiert
        """
        with self._lock:
            if self._paused:
                raise RuntimeError("OllamaClient ist pausiert.")

        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_message})

        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        logger.debug(
            "OllamaClient.chat_with_tools: Modell '%s', %d Tools definiert.", model, len(tools)
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
                msg = data.get("message", {})

                # Prüfe ob das Modell Tool-Calls zurückgegeben hat
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    # Argumente von JSON-String zu dict konvertieren falls nötig
                    parsed_calls = []
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        parsed_calls.append({
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": args,
                            }
                        })
                    return {
                        "type": "tool_calls",
                        "tool_calls": parsed_calls,
                        "content": "",
                        "raw": data,
                    }

                # Normale Text-Antwort
                content = msg.get("content", "").strip()
                return {
                    "type": "text",
                    "tool_calls": [],
                    "content": content,
                    "raw": data,
                }

        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama nicht erreichbar: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ollama hat ungültiges JSON zurückgegeben: {e}") from e

    # ------------------------------------------------------------------
    # Kontext-Info
    # ------------------------------------------------------------------

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Gibt Infos zu einem Modell zurück (Parameter, VRAM-Bedarf etc.)."""
        try:
            payload = json.dumps({"name": model}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception:
            return {}

    def __repr__(self) -> str:
        status = "verfügbar" if self.is_available() else "nicht erreichbar"
        paused = " [PAUSIERT]" if self.is_paused else ""
        return f"OllamaClient(url={self.base_url!r}, status={status}{paused})"


# Modulweite Singleton-Instanz (lazy — wird beim ersten Import nicht verbunden)
_default_client: OllamaClient | None = None
_client_lock = threading.Lock()


def get_ollama_client(base_url: str = DEFAULT_OLLAMA_URL) -> OllamaClient:
    """Gibt den modulweiten Singleton-OllamaClient zurück.

    Erstellt ihn beim ersten Aufruf. Wenn base_url sich ändert
    (User hat Settings geändert), wird ein neuer Client erstellt.
    """
    global _default_client
    with _client_lock:
        if _default_client is None or _default_client.base_url != base_url.rstrip("/"):
            _default_client = OllamaClient(base_url=base_url)
            logger.info("OllamaClient: Singleton erstellt für %s", base_url)
        return _default_client

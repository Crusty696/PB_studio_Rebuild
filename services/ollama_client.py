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

from services.timeout_constants import (
    HTTP_API_TIMEOUT_SEC,
    HTTP_HEALTH_CHECK_TIMEOUT_SEC,
    HTTP_MODEL_INFO_TIMEOUT_SEC,
)
from services.errors import (
    OllamaError,
    OllamaNotAvailableError,
    OllamaModelNotFoundError,
    OllamaPausedError,
)

logger = logging.getLogger(__name__)

# Default-Modelle für NVIDIA CUDA GPU.
# B-239: ``gemma4:e4b`` entfernt — existierte nirgends als Ollama-Tag.
# Live-Default wird in ``OllamaService._resolve_default_model`` per
# ``/api/tags``-Family-Match (gemma4) aufgeloest. Diese Liste ist
# der harte Fallback wenn keine Gemma-4-Variante installiert ist.
RECOMMENDED_MODELS = [
    "phi3:mini",                                                      # ~2.3 GB — schnell, Tool-Use, GTX 1060-tauglich
    "tripolskypetr/qwen3.5-uncensored-aggressive:4b",                 # ~2.7 GB — Qwen 3.5, Tool-Use
    "qwen2.5:7b-instruct-q4_K_M",                                     # ~4.4 GB — Qwen 2.5, Tool-Use
    "llama3.1:8b-instruct-q4_K_M",                                    # ~4.7 GB — Allrounder
    "llama3.1:8b",                                                    # ~4.7 GB — Allrounder (Standard-Tag)
    "llama3:8b",                                                      # ~4.3 GB — Bewaehrt
    "gemma3:4b",                                                      # ~3.3 GB — wenn vorhanden
    "gemma2:2b-instruct-q4_K_M",                                      # ~1.5 GB — Notfall-klein
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
            reply = client.chat("gemma3:4b", "Hallo!")
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
        self._unloadable_models: set[str] = set()  # Models that failed to load (RAM/VRAM)

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
            with urllib.request.urlopen(req, timeout=HTTP_HEALTH_CHECK_TIMEOUT_SEC) as resp:
                return resp.status == 200
        except (ConnectionError, TimeoutError, OSError, ValueError):
            return False

    def get_version(self) -> str | None:
        """Gibt die Ollama-Serverversion zurück oder None wenn nicht erreichbar."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/version",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=HTTP_HEALTH_CHECK_TIMEOUT_SEC) as resp:
                data = json.loads(resp.read())
                return data.get("version")
        except (ConnectionError, TimeoutError, OSError, ValueError):
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
            with urllib.request.urlopen(req, timeout=HTTP_API_TIMEOUT_SEC) as resp:
                data = json.loads(resp.read())
                models = data.get("models", [])
                return [m["name"] for m in models if isinstance(m, dict) and "name" in m]
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            logger.debug("OllamaClient.list_models() fehlgeschlagen: %s", e)
            return []

    def model_exists(self, model_name: str) -> bool:
        """Prüft ob ein bestimmtes Modell lokal verfügbar ist."""
        return model_name in self.list_models()

    def probe_model(self, model_name: str) -> bool:
        """Prüft ob ein Modell tatsächlich geladen werden kann (nicht nur heruntergeladen).

        Sendet eine minimale Inference-Anfrage. Gibt False zurück wenn das Modell
        z.B. wegen RAM/VRAM-Mangel nicht geladen werden kann.
        """
        payload = json.dumps({
            "model": model_name,
            "prompt": "hi",
            "stream": False,
            "options": {"num_predict": 1},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if "memory layout" in body:
                logger.warning(
                    "OllamaClient: Modell '%s' kann nicht geladen werden "
                    "(nicht genug RAM/VRAM): %s", model_name, body.strip(),
                )
            else:
                logger.warning("OllamaClient: probe_model('%s') HTTP %d: %s",
                               model_name, e.code, body.strip())
            return False
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug("OllamaClient: probe_model('%s') fehlgeschlagen: %s", model_name, e)
            return False

    def get_best_available_model(self, probe: bool = False) -> str | None:
        """Gibt das beste verfügbare Modell aus RECOMMENDED_MODELS zurück.

        Args:
            probe: Wenn True, wird jedes Modell per Mini-Inference getestet.
                   Langsam (~5s pro Modell), aber erkennt RAM/VRAM-Probleme.
                   Standard False für schnelle Checks, True beim App-Start.
        """
        available = set(self.list_models())
        for model in RECOMMENDED_MODELS:
            if model in available:
                if probe:
                    if self.probe_model(model):
                        logger.info("OllamaClient: Bestes ladbares Modell: '%s'", model)
                        return model
                    else:
                        logger.info("OllamaClient: '%s' heruntergeladen aber nicht ladbar, überspringe.", model)
                        continue
                return model
        # Fallback: erstes verfügbares Modell
        if available:
            candidate = next(iter(available))
            if probe and not self.probe_model(candidate):
                return None
            return candidate
        return None

    # ------------------------------------------------------------------
    # Model Fallback
    # ------------------------------------------------------------------

    def _find_fallback_model(self, failed_model: str) -> str | None:
        """Findet ein alternatives Modell wenn das gewünschte nicht ladbar ist."""
        # H-20 FIX: Protect _unloadable_models set access with lock (thread-safe)
        with self._lock:
            self._unloadable_models.add(failed_model)
            available = set(self.list_models()) - self._unloadable_models

        for model in RECOMMENDED_MODELS:
            if model in available:
                return model
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
        _in_fallback: bool = False,
    ) -> str:
        """Sendet eine Chat-Anfrage an Ollama und gibt die Antwort zurück.

        Args:
            model: Ollama-Modellname (z.B. "qwen2.5:1.5b-instruct")
            user_message: Benutzernachricht
            system_prompt: Optional System-Prompt
            temperature: Kreativität (0.0-1.0, Standard 0.1 für JSON-Output)
            max_tokens: Maximale Ausgabelänge
            _in_fallback: Internal flag to prevent infinite recursion (H-5 fix)

        Returns:
            Generierter Text

        Raises:
            OllamaPausedError: Wenn OllamaClient pausiert ist
            OllamaNotAvailableError: Wenn Ollama nicht erreichbar
            OllamaModelNotFoundError: Wenn Modell nicht in RAM/VRAM passt
            OllamaError: Bei HTTP oder JSON-Fehlern
        """
        with self._lock:
            if self._paused:
                raise OllamaPausedError(
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
                # B1-Fix: Thinking models return response in "thinking" field instead of "content"
                content = data.get("message", {}).get("content", "")
                if not content:
                    content = data.get("message", {}).get("thinking", "")
                logger.debug("OllamaClient: Antwort erhalten (%d Zeichen).", len(content))
                return content.strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if "memory layout" in body:
                # H-5 FIX: Prevent infinite recursion by disallowing fallback-of-fallback
                if _in_fallback:
                    logger.error(
                        "OllamaClient: Fallback-Modell '%s' passt auch nicht in RAM/VRAM. "
                        "Keine weiteren Fallbacks möglich.", model,
                    )
                    raise OllamaModelNotFoundError(
                        model=model,
                        reason="Fallback-Modell passt nicht in RAM/VRAM"
                    ) from e

                logger.warning(
                    "OllamaClient: Modell '%s' passt nicht in RAM/VRAM. "
                    "Suche alternatives Modell...", model,
                )
                fallback = self._find_fallback_model(model)
                if fallback:
                    logger.info("OllamaClient: Fallback auf '%s'.", fallback)
                    return self.chat(fallback, user_message, system_prompt, temperature, max_tokens, _in_fallback=True)
                raise OllamaModelNotFoundError(
                    model=model,
                    reason="Passt nicht in RAM/VRAM und kein Fallback verfuegbar"
                ) from e
            logger.error("OllamaClient: HTTP-Fehler %d: %s", e.code, body.strip())
            raise OllamaError(f"HTTP-Fehler {e.code}: {body.strip()}", model=model, http_code=e.code) from e
        except urllib.error.URLError as e:
            logger.error("OllamaClient: Verbindungsfehler: %s", e)
            raise OllamaNotAvailableError(f"Ollama nicht erreichbar: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("OllamaClient: Ungültige JSON-Antwort: %s", e)
            raise OllamaError(f"Ungültiges JSON von Ollama: {e}", model=model) from e

    def chat_with_history(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 512,
        _in_fallback: bool = False,
    ) -> str:
        """Sendet eine Chat-Anfrage mit vollständiger Message-History.

        Args:
            model: Ollama-Modellname
            messages: Liste von {"role": "system/user/assistant", "content": "..."}
            temperature: Kreativität
            max_tokens: Maximale Ausgabelänge
            _in_fallback: Internal flag to prevent infinite recursion (HIGH-1 fix)

        Returns:
            Generierter Text
        """
        with self._lock:
            if self._paused:
                raise OllamaPausedError("OllamaClient ist pausiert.")

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
                # B1-Fix: Thinking models return response in "thinking" field instead of "content"
                content = data.get("message", {}).get("content", "")
                if not content:
                    content = data.get("message", {}).get("thinking", "")
                return content.strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "memory layout" in err_body:
                # HIGH-1 FIX: Prevent infinite recursion by disallowing fallback-of-fallback
                if _in_fallback:
                    logger.error(
                        "OllamaClient: Fallback-Modell '%s' passt auch nicht in RAM/VRAM. "
                        "Keine weiteren Fallbacks möglich.", model,
                    )
                    raise OllamaModelNotFoundError(
                        model=model,
                        reason="Fallback-Modell passt nicht in RAM/VRAM"
                    ) from e

                fallback = self._find_fallback_model(model)
                if fallback:
                    logger.warning("OllamaClient: '%s' nicht ladbar, Fallback auf '%s'.", model, fallback)
                    return self.chat_with_history(fallback, messages, temperature, max_tokens, _in_fallback=True)
                raise OllamaModelNotFoundError(
                    model=model,
                    reason="Passt nicht in RAM/VRAM und kein Fallback verfuegbar"
                ) from e
            raise OllamaError(f"HTTP-Fehler {e.code}: {err_body.strip()}", model=model, http_code=e.code) from e
        except urllib.error.URLError as e:
            raise OllamaNotAvailableError(f"Ollama nicht erreichbar: {e}") from e

    # ------------------------------------------------------------------
    # Vision / Multimodal Inference (AUD-128)
    # ------------------------------------------------------------------

    def chat_vision(
        self,
        model: str,
        user_message: str,
        images_base64: list[str],
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
        _in_fallback: bool = False,
    ) -> str:
        """Sendet eine multimodale Chat-Anfrage mit Bildern an Ollama.

        Funktioniert mit Vision-fähigen Modellen (z.B. gemma3:4b, llava, bakllava).
        Bilder werden als base64-Strings übergeben.

        Args:
            model: Ollama-Modellname (muss Vision unterstützen)
            user_message: Text-Prompt zum Bild
            images_base64: Liste von base64-codierten JPEG/PNG Bildern (max 3)
            system_prompt: Optionaler System-Prompt
            temperature: Kreativität (Standard: 0.1 für strukturierten JSON-Output)
            max_tokens: Maximale Ausgabelänge
            _in_fallback: Internal flag to prevent infinite recursion (HIGH-2 fix)

        Returns:
            Generierter Text

        Raises:
            OllamaPausedError: Wenn OllamaClient pausiert ist
            OllamaNotAvailableError: Wenn Ollama nicht erreichbar
            OllamaError: Bei HTTP oder JSON-Fehlern
        """
        with self._lock:
            if self._paused:
                raise OllamaPausedError(
                    "OllamaClient ist pausiert (GPU-intensive Operation läuft)."
                )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": user_message,
            "images": images_base64,
        })

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

        logger.debug(
            "OllamaClient.chat_vision: Modell '%s', %d Bild(er).", model, len(images_base64)
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                data = json.loads(raw)
                content = data.get("message", {}).get("content", "")
                return content.strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "memory layout" in err_body:
                # HIGH-2 FIX: Prevent infinite recursion by disallowing fallback-of-fallback
                if _in_fallback:
                    logger.error(
                        "OllamaClient.chat_vision: Fallback-Modell '%s' passt auch nicht in RAM/VRAM. "
                        "Keine weiteren Fallbacks möglich.", model,
                    )
                    raise OllamaModelNotFoundError(
                        model=model,
                        reason="Fallback-Modell passt nicht in RAM/VRAM"
                    ) from e

                fallback = self._find_fallback_model(model)
                if fallback:
                    logger.warning("OllamaClient.chat_vision: '%s' nicht ladbar, Fallback auf '%s'.", model, fallback)
                    return self.chat_vision(fallback, user_message, images_base64, system_prompt, temperature, max_tokens, _in_fallback=True)
                raise OllamaModelNotFoundError(
                    model=model,
                    reason="Passt nicht in RAM/VRAM und kein Fallback verfuegbar"
                ) from e
            logger.error("OllamaClient.chat_vision: HTTP %d: %s", e.code, err_body.strip())
            raise OllamaError(f"HTTP-Fehler {e.code}: {err_body.strip()}", model=model, http_code=e.code) from e
        except urllib.error.URLError as e:
            logger.error("OllamaClient.chat_vision: Verbindungsfehler: %s", e)
            raise OllamaNotAvailableError(f"Ollama nicht erreichbar: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("OllamaClient.chat_vision: Ungültige JSON-Antwort: %s", e)
            raise OllamaError(f"Ungültiges JSON von Ollama: {e}", model=model) from e

    # ------------------------------------------------------------------
    # Tool-Use / Function-Calling (AP-5)
    # ------------------------------------------------------------------

    def supports_tools(self, model: str) -> bool:
        """Prüft ob ein Modell Tool-Use / Function-Calling unterstützt.

        Qwen2.5+, Qwen3+, Llama 3+, Mistral 0.3+, Phi3 und Gemma 2/3/4
        unterstützen Tool-Use. Kleine Modelle (<1B) unterstützen es
        oft NICHT zuverlässig.

        B-239: Erkennung erfolgt jetzt SUBSTRING-basiert (vorher Prefix),
        damit Community-Tags wie ``fredrezones55/Gemma-4-...:e2b`` oder
        ``tripolskypetr/qwen3.5-uncensored-aggressive:4b`` ebenfalls
        erkannt werden — sonst wuerde der Tool-Use-Pfad uebersprungen
        und auf brittle JSON-Freitext-Parsing zurueckgefallen.
        """
        supported_substrings = [
            "qwen2.5", "qwen2:", "qwen3", "qwen3.5",
            "llama3.1", "llama3.2", "llama3.3",
            "mistral",
            "phi3",
            "gemma2", "gemma-2", "gemma3", "gemma-3", "gemma4", "gemma-4",
        ]
        model_lower = model.lower()
        for needle in supported_substrings:
            if needle in model_lower:
                # Kleine Modelle ausschliessen (<1B Parameter)
                if any(tiny in model_lower for tiny in [":0.5b", "0.5b-", "-0.5b"]):
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
            OllamaPausedError: Wenn OllamaClient pausiert ist
            OllamaNotAvailableError: Wenn Ollama nicht erreichbar
            OllamaError: Bei HTTP oder JSON-Fehlern
        """
        with self._lock:
            if self._paused:
                raise OllamaPausedError("OllamaClient ist pausiert.")

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
            raise OllamaNotAvailableError(f"Ollama nicht erreichbar: {e}") from e
        except json.JSONDecodeError as e:
            raise OllamaError(f"Ungültiges JSON von Ollama: {e}", model=model) from e

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
            with urllib.request.urlopen(req, timeout=HTTP_MODEL_INFO_TIMEOUT_SEC) as resp:
                return json.loads(resp.read())
        except (ConnectionError, TimeoutError, OSError, ValueError):
            return {}

    def __repr__(self) -> str:
        # L-39 FIX: Read _paused directly under lock for consistency
        with self._lock:
            paused_state = self._paused
        status = "verfügbar" if self.is_available() else "nicht erreichbar"
        paused = " [PAUSIERT]" if paused_state else ""
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

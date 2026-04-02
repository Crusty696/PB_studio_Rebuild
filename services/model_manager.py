"""
Zentraler Model Manager — Singleton für striktes VRAM/RAM-Management.

REGEL: Es darf IMMER NUR EIN KI-Modell im RAM/VRAM liegen.
Wenn der Vision-Agent lädt, muss der Audio-Agent entladen werden
(torch.cuda.empty_cache() und gc.collect()).

Unterstützte Modell-Typen:
- HuggingFace transformers (AutoModel)
- faster-whisper (WhisperModel)
- Custom models (via load_custom callback)
"""

import gc
import logging
import threading
from typing import Any

# torch wird LAZY importiert (spart ~11s Startup wenn ModelManager nicht sofort gebraucht wird)
torch = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Globaler GPU-Semaphore: Serialisiert alle GPU-Modell-Lade-Operationen
# (SigLIP, RAFT, beat_this) um VRAM-Races auf 6GB GTX 1060 zu verhindern
GPU_LOAD_LOCK = threading.Lock()


def _ensure_torch():
    """Lazy-Import von torch — wird beim ersten Zugriff geladen."""
    global torch
    if torch is None or not hasattr(torch, 'cuda'):
        import torch as _torch
        torch = _torch
    return torch


class ModelManager:
    """Singleton-Manager: Nur EIN Modell gleichzeitig im RAM/VRAM.

    Thread-safe durch Lock. Wird von allen Agenten geteilt.
    GPU-ZWANG: Wenn CUDA verfügbar ist, wird IMMER die GPU genutzt.
    """

    _instance = None
    _lock = threading.Lock()
    _gpu_logged = False  # Einmalig GPU-Status loggen

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, device: str | None = None):
        if self._initialized:
            return
        self._initialized = True

        # torch lazy laden (spart ~11s wenn ModelManager erst spät gebraucht wird)
        _ensure_torch()

        # GPU-ZWANG: Wenn CUDA da ist, wird CUDA erzwungen — kein stiller CPU-Fallback
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            self.device = "cuda"
            if device and device != "cuda":
                logger.info(
                    "GPU-ZWANG: Device '%s' überschrieben → 'cuda' (CUDA ist verfügbar!)",
                    device,
                )
        else:
            self.device = "cpu"

        self._current_model_id: str | None = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._pipe: Any = None
        self._model_type: str | None = None  # "transformers", "whisper", "vision"
        self._extras: dict[str, Any] = {}  # Zusätzliche Objekte (Processor etc.)
        self._swap_lock = threading.RLock()  # Reentrant — erlaubt nested acquire

        # Prominenten GPU-Status loggen (einmalig)
        self._log_gpu_hardware()
        logger.info("ModelManager initialisiert auf Device: %s", self.device)

    def _log_gpu_hardware(self) -> None:
        """Loggt den GPU-Hardware-Status prominent ins Terminal und speichert ihn."""
        with ModelManager._lock:
            if ModelManager._gpu_logged:
                return
            ModelManager._gpu_logged = True

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_total = float(props.total_memory) / 1024 / 1024
            self._gpu_info = {
                "name": gpu_name,
                "vram_total_mb": round(vram_total, 0),
                "cuda_version": torch.version.cuda or "N/A",
            }
            banner = (
                f"\n{'=' * 60}\n"
                f"  HARDWARE AKTIV: {gpu_name}\n"
                f"  VRAM: {vram_total:.0f} MB | CUDA: {self._gpu_info['cuda_version']}\n"
                f"  GPU-ZWANG: Alle KI-Modelle laufen auf CUDA\n"
                f"{'=' * 60}\n"
            )
            # Direkt auf stdout für maximale Sichtbarkeit
            print(banner)
            logger.info("HARDWARE AKTIV: %s (%.0f MB VRAM, CUDA %s)",
                        gpu_name, vram_total, self._gpu_info['cuda_version'])
        else:
            self._gpu_info = {"name": "CPU", "vram_total_mb": 0, "cuda_version": None}
            banner = (
                f"\n{'=' * 60}\n"
                f"  WARNUNG: Keine CUDA-GPU erkannt!\n"
                f"  Alle KI-Modelle laufen auf CPU (langsam)\n"
                f"{'=' * 60}\n"
            )
            print(banner)
            logger.warning("Keine CUDA-GPU erkannt — CPU-Modus aktiv")

    @property
    def gpu_info(self) -> dict:
        """Gibt GPU-Hardware-Info zurück (für UI-Anzeige)."""
        return getattr(self, '_gpu_info', {"name": "unbekannt", "vram_total_mb": 0})

    @property
    def current_model_id(self) -> str | None:
        return self._current_model_id

    @property
    def is_loaded(self) -> bool:
        return self._current_model_id is not None

    @property
    def model_type(self) -> str | None:
        return self._model_type

    def unload(self) -> None:
        """Entlädt das aktuelle Modell komplett und gibt GPU/RAM frei."""
        with self._swap_lock:
            if self._current_model_id is None:
                return

            old_id = self._current_model_id
            old_type = self._model_type
            logger.info("ModelManager: Entlade '%s' (Typ: %s)...", old_id, old_type)

            # Model auf CPU verschieben bevor Referenzen gelöscht werden (sofortige VRAM-Freigabe)
            for obj in (self._model, self._pipe):
                if obj is not None and hasattr(obj, 'cpu'):
                    try:
                        obj.cpu()
                    except Exception:
                        pass

            # Alle Referenzen löschen
            self._pipe = None
            self._model = None
            self._tokenizer = None
            self._extras.clear()
            self._current_model_id = None
            self._model_type = None

            # Aggressives Aufräumen — doppelter Pass fuer fragmentierten VRAM
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            logger.info(
                "ModelManager: '%s' entladen. GPU-Cache geleert, GC ausgeführt.", old_id
            )

            # Ollama fortsetzen — GPU ist jetzt frei
            self._resume_ollama_if_paused()

    def load_transformers(self, model_id: str) -> tuple:
        """Lädt ein HuggingFace transformers Modell (Text-Generation).

        Returns:
            (tokenizer, model, pipeline)
        """
        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "transformers":
                return self._tokenizer, self._model, self._pipe

            # Ollama pausieren, bevor GPU belegt wird
            self._pause_ollama_if_active()

            # Altes Modell entladen
            self.unload()

            # B-05: VRAM pre-check — fragmentierten Speicher freigeben vor dem Laden
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()

            logger.info("ModelManager: Lade transformers '%s' auf %s...", model_id, self.device)

            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_id,
                )
                dtype = torch.float32 if self.device == "cpu" else torch.float16
                self._model = AutoModelForCausalLM.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    device_map={"": self.device},
                )
                self._model.eval()

                # KEIN device= wenn device_map verwendet wurde (HuggingFace ValueError)
                self._pipe = pipeline(
                    "text-generation",
                    model=self._model,
                    tokenizer=self._tokenizer,
                )
            except torch.cuda.OutOfMemoryError:
                logger.error("OOM beim Laden von transformers '%s' — räume auf.", model_id)
                self.unload()
                raise RuntimeError(
                    f"VRAM reicht nicht für transformers '{model_id}'. "
                    f"GPU-Speicher wurde freigegeben."
                )

            self._current_model_id = model_id
            self._model_type = "transformers"
            logger.info("ModelManager: transformers '%s' geladen.", model_id)

            return self._tokenizer, self._model, self._pipe

    def load_whisper(self, model_size: str = "large-v3") -> Any:
        """Lädt ein faster-whisper Modell für Transkription.

        Args:
            model_size: "tiny", "base", "small", "medium", "large-v3"

        Returns:
            WhisperModel-Instanz
        """
        model_id = f"whisper-{model_size}"

        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "whisper":
                return self._model

            # Ollama pausieren, bevor GPU belegt wird
            self._pause_ollama_if_active()

            # Altes Modell entladen
            self.unload()

            # B-05: VRAM pre-check — fragmentierten Speicher freigeben vor dem Laden
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()

            logger.info("ModelManager: Lade faster-whisper '%s' auf %s...", model_size, self.device)

            from faster_whisper import WhisperModel

            try:
                # Compute-Type nach GPU-Architektur:
                # - Volta/Turing/Ampere (sm >= 7.0): float16 (schnell, ~3GB fuer large-v3)
                # - Pascal (sm 6.x, GTX 1060): int8 (unterstuetzt ab sm_6.1, ~1.5GB fuer large-v3)
                # - CPU: int8
                if self.device == "cuda":
                    cap = torch.cuda.get_device_capability(0)
                    compute_type = "float16" if cap[0] >= 7 else "int8"
                    logger.info(
                        "ModelManager: faster-whisper compute_type=%s (GPU sm %d.%d)",
                        compute_type, cap[0], cap[1],
                    )
                else:
                    compute_type = "int8"
                    logger.info(
                        "ModelManager: faster-whisper compute_type=%s (CPU)", compute_type,
                    )
                self._model = WhisperModel(
                    model_size,
                    device=self.device,
                    compute_type=compute_type,
                )
            except torch.cuda.OutOfMemoryError:
                logger.error("OOM beim Laden von whisper '%s' — räume auf.", model_size)
                self.unload()
                raise RuntimeError(
                    f"VRAM reicht nicht für whisper '{model_size}'. "
                    f"GPU-Speicher wurde freigegeben."
                )

            self._current_model_id = model_id
            self._model_type = "whisper"
            logger.info("ModelManager: faster-whisper '%s' geladen.", model_size)

            return self._model

    def load_vision(self, model_id: str = "vikhyatk/moondream2") -> tuple:
        """Lädt ein Vision-Modell (Moondream2) für Bildanalyse.

        Returns:
            (model, tokenizer) — Moondream2-spezifisch
        """
        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "vision":
                return self._model, self._tokenizer

            # Ollama pausieren, bevor GPU belegt wird
            self._pause_ollama_if_active()

            # Altes Modell entladen
            self.unload()

            logger.info("ModelManager: Lade Vision-Modell '%s' auf %s...", model_id, self.device)

            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Moondream2 hat Custom-Architektur die trust_remote_code braucht.
            # Erlaubt nur fuer verifizierte Modelle (siehe pb-commander Governance).
            _TRUSTED_MODELS = {"vikhyatk/moondream2"}
            needs_trust = model_id in _TRUSTED_MODELS

            # VRAM aggressiv freigeben vor dem Laden (P1 Fix)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_id,
                    trust_remote_code=needs_trust,
                )
                dtype = torch.float32 if self.device == "cpu" else torch.float16
                self._model = AutoModelForCausalLM.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    device_map={"": self.device},
                    trust_remote_code=needs_trust,
                )
                self._model.eval()
            except torch.cuda.OutOfMemoryError:
                logger.error("OOM beim Laden von vision '%s' — räume auf.", model_id)
                self.unload()
                from services.errors import CUDAOutOfMemoryError
                raise CUDAOutOfMemoryError(operation=f"Vision '{model_id}' laden")

            self._current_model_id = model_id
            self._model_type = "vision"
            logger.info("ModelManager: Vision '%s' geladen.", model_id)

            return self._model, self._tokenizer

    def load_siglip(self, model_id: str = "google/siglip-so400m-patch14-384") -> tuple:
        """Lädt SigLIP Vision+Text Encoder für 1152-dim Embeddings.

        Returns:
            (model, processor) — SigLIP-spezifisch
        """
        import time as _time

        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "siglip":
                return self._model, self._extras.get("processor")

            # Ollama pausieren, bevor GPU belegt wird
            self._pause_ollama_if_active()

            self.unload()

            # P1 Fix: VRAM aggressiv freigeben und warten bevor neues Modell geladen wird.
            # GTX 1060 (6 GB): beat_this belegt ~2 GB, SigLIP braucht ~2.5 GB.
            # Ohne Pause kann fragmentierter VRAM einen Segfault verursachen.
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()
                vram_free = (torch.cuda.get_device_properties(0).total_memory
                             - torch.cuda.memory_allocated(0)) / (1024**3)
                logger.info("ModelManager: VRAM frei vor SigLIP-Load: %.1f GB", vram_free)
                if vram_free < 3.0:
                    logger.warning("ModelManager: Wenig VRAM (%.1f GB) — warte 2s fuer Cleanup", vram_free)
                    _time.sleep(2)
                    gc.collect()
                    torch.cuda.empty_cache()
                    vram_free = (torch.cuda.get_device_properties(0).total_memory
                                 - torch.cuda.memory_allocated(0)) / (1024**3)
                    logger.info("ModelManager: VRAM nach Cleanup: %.1f GB", vram_free)

            logger.info("ModelManager: Lade SigLIP '%s' auf %s...", model_id, self.device)

            from transformers import AutoModel, AutoProcessor

            try:
                self._extras["processor"] = AutoProcessor.from_pretrained(model_id)
                dtype = torch.float32 if self.device == "cpu" else torch.float16
                self._model = AutoModel.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                )
                self._model.to(self.device)
                self._model.eval()
            except torch.cuda.OutOfMemoryError:
                logger.error("OOM beim Laden von SigLIP '%s' — räume auf.", model_id)
                self.unload()
                from services.errors import CUDAOutOfMemoryError
                raise CUDAOutOfMemoryError(operation=f"SigLIP '{model_id}' laden")
            except Exception as e:
                logger.error(
                    "SigLIP '%s' konnte nicht geladen werden: %s — räume auf.",
                    model_id, e,
                )
                self.unload()
                raise RuntimeError(
                    f"SigLIP '{model_id}' Laden fehlgeschlagen: {e}"
                ) from e

            self._current_model_id = model_id
            self._model_type = "siglip"
            logger.info("ModelManager: SigLIP '%s' geladen.", model_id)

            return self._model, self._extras["processor"]

    def ensure_loaded(self, model_id: str, model_type: str = "transformers") -> Any:
        """Stellt sicher, dass das angegebene Modell geladen ist.

        FIX B-006: GPU_LOAD_LOCK serialisiert parallele Modell-Laden
        um VRAM-Crashes zu verhindern wenn mehrere Agenten gleichzeitig laden.

        Args:
            model_id: Modell-ID oder Whisper-Größe
            model_type: "transformers", "whisper", "vision"
        """
        # FIX B-006: Globaler GPU_LOAD_LOCK verhindert Race-Condition bei concurrent loads
        with GPU_LOAD_LOCK:
            if model_type == "whisper":
                result = self.load_whisper(model_id)
            elif model_type == "vision":
                result = self.load_vision(model_id)
            elif model_type == "siglip":
                result = self.load_siglip(model_id)
            elif model_type == "raft":
                result = self.load_raft()
            else:
                result = self.load_transformers(model_id)

        # AUD-11: last_used_at in Registry aktualisieren (best-effort)
        try:
            from services.model_lifecycle_service import get_model_lifecycle_service
            get_model_lifecycle_service().touch_last_used(model_id)
        except Exception:
            pass

        return result

    def load_raft(self) -> tuple:
        """Lädt RAFT Small Optical Flow Modell für Motion-Analyse.

        Registriert RAFT im ModelManager sodass es beim Laden anderer
        Modelle (Whisper, SigLIP, beat_this) automatisch entladen wird.
        SigLIP (~2.5 GB) + RAFT (~0.1 GB) dürfen koexistieren auf 6 GB VRAM.

        Returns:
            (raft_model, device) — direkt verwendbar für torch inference
        """
        model_id = "raft_small"

        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "raft":
                return self._model, torch.device(self.device)

            self._pause_ollama_if_active()

            # SigLIP (~2.5 GB) + RAFT (~0.1 GB) passt auf 6 GB — Koexistenz erlaubt
            if self._model_type != "siglip":
                self.unload()

            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()
                logger.info(
                    "ModelManager: Lade RAFT Small auf CUDA (%s)...",
                    torch.cuda.get_device_name(0),
                )
            else:
                logger.info("ModelManager: Lade RAFT Small auf CPU...")

            import torchvision.models.optical_flow as _of

            device = torch.device(self.device)
            raft = _of.raft_small(weights=_of.Raft_Small_Weights.DEFAULT)
            try:
                raft = raft.to(device)
            except torch.cuda.OutOfMemoryError:
                logger.warning("[RAFT] OOM — entlade SigLIP und versuche erneut...")
                # SigLIP jetzt auch entladen und nochmal versuchen
                self.unload()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()
                try:
                    raft = raft.to(device)
                except torch.cuda.OutOfMemoryError:
                    logger.error("OOM beim Laden von RAFT — VRAM nicht ausreichend")
                    del raft
                    raise RuntimeError(
                        "VRAM reicht nicht für RAFT. GPU-Speicher wurde freigegeben."
                    )

            raft = raft.eval()
            self._model = raft
            self._current_model_id = model_id
            self._model_type = "raft"
            logger.info("ModelManager: RAFT Small geladen auf %s", device)

            return self._model, device

    def load_ollama(self, model: str, base_url: str = "http://localhost:11434") -> "OllamaHandle":
        """Registriert Ollama als aktiven LLM-Backend im ModelManager.

        Ollama läuft als separater Prozess und belegt kein VRAM durch den
        ModelManager, ABER: wenn andere GPU-intensive Modelle (Demucs, SigLIP)
        geladen werden, wird Ollama automatisch pausiert.

        Returns:
            OllamaHandle — Wrapper der chat() delegiert und VRAM-Events empfängt.
        """
        from services.ollama_client import get_ollama_client

        client = get_ollama_client(base_url)
        if not client.is_available():
            raise RuntimeError(
                f"Ollama ist nicht erreichbar unter {base_url}. "
                "Bitte Ollama starten: 'ollama serve'"
            )

        handle = OllamaHandle(client=client, model=model, manager=self)
        logger.info(
            "ModelManager: Ollama-Backend registriert (Modell: '%s', URL: %s).",
            model, base_url,
        )

        # AUD-11: last_used_at in Registry aktualisieren (best-effort)
        try:
            from services.model_lifecycle_service import get_model_lifecycle_service
            get_model_lifecycle_service(base_url).touch_last_used(model)
        except Exception:
            pass

        return handle

    def _pause_ollama_if_active(self) -> None:
        """Pausiert den Ollama-Client falls registriert.

        Wird intern vor dem Laden GPU-intensiver Modelle aufgerufen.
        """
        from services.ollama_client import _default_client
        if _default_client is not None and not _default_client.is_paused:
            _default_client.pause()
            logger.info("ModelManager: Ollama pausiert vor GPU-Modell-Load.")

    def _resume_ollama_if_paused(self) -> None:
        """Setzt den Ollama-Client fort falls pausiert."""
        from services.ollama_client import _default_client
        if _default_client is not None and _default_client.is_paused:
            _default_client.resume()
            logger.info("ModelManager: Ollama nach GPU-Operation fortgesetzt.")

    def get_vram_usage(self) -> dict:
        """Gibt aktuelle VRAM-Nutzung zurück (nur CUDA)."""
        if not torch.cuda.is_available():
            return {"device": "cpu", "vram_used_mb": 0, "vram_total_mb": 0}

        used = torch.cuda.memory_allocated() / 1024 / 1024
        total = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
        return {
            "device": torch.cuda.get_device_name(0),
            "vram_used_mb": round(used, 1),
            "vram_total_mb": round(total, 1),
            "model_loaded": self._current_model_id,
            "model_type": self._model_type,
        }


class OllamaHandle:
    """Leichter Wrapper der den Ollama-Client an den ModelManager koppelt.

    Koordiniert VRAM-Events: Wenn ein GPU-intensives Modell geladen wird,
    pausiert dieser Handle automatisch den Ollama-Client.
    """

    def __init__(self, client, model: str, manager: "ModelManager"):
        self._client = client
        self.model = model
        self._manager = manager

    def chat(
        self,
        user_message: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> str:
        """Delegiert an OllamaClient.chat() mit VRAM-Schutz."""
        return self._client.chat(
            model=self.model,
            user_message=user_message,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_with_history(self, messages: list[dict], **kwargs) -> str:
        """Delegiert an OllamaClient.chat_with_history()."""
        return self._client.chat_with_history(
            model=self.model,
            messages=messages,
            **kwargs,
        )

    @property
    def is_available(self) -> bool:
        return self._client.is_available()

    def __repr__(self) -> str:
        return f"OllamaHandle(model={self.model!r}, url={self._client.base_url!r})"

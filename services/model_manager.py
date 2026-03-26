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
                logger.warning(
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

            # Aggressives Aufräumen
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            logger.info(
                "ModelManager: '%s' entladen. GPU-Cache geleert, GC ausgeführt.", old_id
            )

    def load_transformers(self, model_id: str) -> tuple:
        """Lädt ein HuggingFace transformers Modell (Text-Generation).

        Returns:
            (tokenizer, model, pipeline)
        """
        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "transformers":
                return self._tokenizer, self._model, self._pipe

            # Altes Modell entladen
            self.unload()

            logger.info("ModelManager: Lade transformers '%s' auf %s...", model_id, self.device)

            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_id, trust_remote_code=True,
                )
                dtype = torch.float32 if self.device == "cpu" else torch.float16
                self._model = AutoModelForCausalLM.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    trust_remote_code=True,
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

            # Altes Modell entladen
            self.unload()

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

            # Altes Modell entladen
            self.unload()

            logger.info("ModelManager: Lade Vision-Modell '%s' auf %s...", model_id, self.device)

            from transformers import AutoModelForCausalLM, AutoTokenizer

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_id, trust_remote_code=True,
                )
                dtype = torch.float32 if self.device == "cpu" else torch.float16
                self._model = AutoModelForCausalLM.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    trust_remote_code=True,
                    device_map={"": self.device},
                )
                self._model.eval()
            except torch.cuda.OutOfMemoryError:
                logger.error("OOM beim Laden von vision '%s' — räume auf.", model_id)
                self.unload()
                raise RuntimeError(
                    f"VRAM reicht nicht für vision '{model_id}'. "
                    f"GPU-Speicher wurde freigegeben."
                )

            self._current_model_id = model_id
            self._model_type = "vision"
            logger.info("ModelManager: Vision '%s' geladen.", model_id)

            return self._model, self._tokenizer

    def load_siglip(self, model_id: str = "google/siglip-so400m-patch14-384") -> tuple:
        """Lädt SigLIP Vision+Text Encoder für 1152-dim Embeddings.

        Returns:
            (model, processor) — SigLIP-spezifisch
        """
        with self._swap_lock:
            if self._current_model_id == model_id and self._model_type == "siglip":
                return self._model, self._extras.get("processor")

            self.unload()

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
                raise RuntimeError(
                    f"VRAM reicht nicht für SigLIP '{model_id}'. "
                    f"GPU-Speicher wurde freigegeben."
                )
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

        Args:
            model_id: Modell-ID oder Whisper-Größe
            model_type: "transformers", "whisper", "vision"
        """
        if model_type == "whisper":
            return self.load_whisper(model_id)
        elif model_type == "vision":
            return self.load_vision(model_id)
        elif model_type == "siglip":
            return self.load_siglip(model_id)
        else:
            return self.load_transformers(model_id)

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

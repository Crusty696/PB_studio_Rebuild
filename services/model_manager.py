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

import torch

logger = logging.getLogger(__name__)


class ModelManager:
    """Singleton-Manager: Nur EIN Modell gleichzeitig im RAM/VRAM.

    Thread-safe durch Lock. Wird von allen Agenten geteilt.
    """

    _instance = None
    _lock = threading.Lock()

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

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._current_model_id: str | None = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._pipe: Any = None
        self._model_type: str | None = None  # "transformers", "whisper", "vision"
        self._extras: dict[str, Any] = {}  # Zusätzliche Objekte (Processor etc.)
        self._swap_lock = threading.RLock()  # Reentrant — erlaubt nested acquire

        logger.info("ModelManager initialisiert auf Device: %s", self.device)

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

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_id, trust_remote_code=True,
            )
            dtype = torch.float32 if self.device == "cpu" else torch.float16
            self._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                dtype=dtype,
                trust_remote_code=True,
            )
            self._model.to(self.device)
            self._model.eval()

            self._pipe = pipeline(
                "text-generation",
                model=self._model,
                tokenizer=self._tokenizer,
                device=self.device if self.device != "cpu" else -1,
            )

            self._current_model_id = model_id
            self._model_type = "transformers"
            logger.info("ModelManager: transformers '%s' geladen.", model_id)

            return self._tokenizer, self._model, self._pipe

    def load_whisper(self, model_size: str = "base") -> Any:
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

            compute_type = "float16" if self.device == "cuda" else "int8"
            self._model = WhisperModel(
                model_size,
                device=self.device,
                compute_type=compute_type,
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

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_id, trust_remote_code=True,
            )
            dtype = torch.float32 if self.device == "cpu" else torch.float16
            self._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                dtype=dtype,
                trust_remote_code=True,
                device_map={"": self.device},
            )
            self._model.eval()

            self._current_model_id = model_id
            self._model_type = "vision"
            logger.info("ModelManager: Vision '%s' geladen.", model_id)

            return self._model, self._tokenizer

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

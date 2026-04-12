"""
Zentraler Model Manager — Singleton für striktes VRAM/RAM-Management.

REGEL: Es darf IMMER NUR EIN KI-Modell im RAM/VRAM liegen.
Wenn der Vision-Agent lädt, muss der Audio-Agent entladen werden
(torch.cuda.empty_cache() und gc.collect()).

Unterstützte Modell-Typen:
- HuggingFace transformers (AutoModel)
- Custom models (via load_custom callback)
"""

import gc
import logging
import threading
import psutil
from functools import wraps
from typing import Any

# torch wird LAZY importiert
# (spart ~11s Startup wenn ModelManager nicht sofort gebraucht wird)
torch = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Compat: RuntimeError existiert erst ab PyTorch 2.0.
# In torch 1.12 ist es ein normaler RuntimeError.
def _is_cuda_oom(exc: Exception) -> bool:
    """Prueft ob eine Exception ein CUDA OOM ist (kompatibel mit torch 1.12+)."""
    if hasattr(torch, 'cuda') and hasattr(torch.cuda, 'OutOfMemoryError'):
        return isinstance(exc, RuntimeError)
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()

# Globaler GPU-Semaphore: Serialisiert alle GPU-Modell-Lade-Operationen
# (SigLIP, RAFT, beat_this) um VRAM-Races auf 6GB GTX 1060 zu verhindern.
# FIX: RLock erlaubt verschachtelte Aufrufe (reentrant).
GPU_LOAD_LOCK = threading.RLock()

# Globaler Inferenz-Lock: Verhindert gleichzeitige Berechnungen auf der GPU
# (z.B. Vision-Analyse + Audio-Separation), was auf 6GB-Karten zu OOM führt.
# FIX: RLock für maximale Stabilität bei komplexen Pipelines.
GPU_EXECUTION_LOCK = threading.RLock()

# F-011: OOM-Handler Schwellwerte (in GB)
# Wenn weniger als diese Werte verfügbar sind, wird proaktiv entladen
OOM_RAM_THRESHOLD_GB = 2.0  # Min 2GB freier RAM
OOM_VRAM_THRESHOLD_GB = 1.5  # Min 1.5GB freies VRAM


def _ensure_torch():
    """Lazy-Import von torch — wird beim ersten Zugriff geladen."""
    global torch
    if torch is None or not hasattr(torch, 'cuda'):
        import torch as _torch
        torch = _torch
    return torch


def oom_recovery(func):
    """Decorator für robuste Error-Recovery bei OOM-Fehlern (Fix F-047).

    Versucht bis zu 3-mal, eine GPU-Operation durchzuführen, wobei zwischen
    den Versuchen zunehmend aggressiv Speicher freigegeben wird.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        import time as _time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                is_oom = "out of memory" in error_str or "cuda error: out of memory" in error_str

                if not is_oom or attempt == max_retries - 1:
                    raise e

                wait_time = (attempt + 1) * 2
                logger.warning(
                    "OOM in %s (Versuch %d/%d) — warte %ds und räume auf...",
                    func.__name__, attempt + 1, max_retries, wait_time
                )

                _ensure_torch()
                # C-6 FIX: Alle GPU-Operationen muessen gelockt sein
                with GPU_LOAD_LOCK:
                    # Aggressiver Cleanup
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()

                    if attempt == 1:
                        # Im zweiten Versuch entladen wir ALLES
                        logger.info("OOM persistiert — erzwinge vollständigen Modell-Unload.")
                        ModelManager().unload()

                # Kurze Pause damit Treiber/OS sich fangen kann
                _time.sleep(wait_time)

        # H-6 FIX: Return None if all retries exhausted without raising
        # (should not normally reach here, but explicit is better than implicit)
        return None

    return wrapper


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
            if device and device == "cuda":
                logger.warning(
                    "B-015: Device 'cuda' angefordert, aber CUDA nicht verfügbar — Fallback auf 'cpu'.",
                )

        self._current_model_id: str | None = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._pipe: Any = None
        self._model_type: str | None = None  # "transformers", "vision", "siglip", "raft"
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

        _ensure_torch()
        
        # Versuche CUDA initialisierung zu erzwingen um echte Fehler zu sehen
        cuda_ok = False
        cuda_error = ""
        try:
            cuda_ok = torch.cuda.is_available()
            if not cuda_ok:
                # Prüfen ob CUDA-DLLs fehlen
                torch.cuda.init() # Erzwingt init
        except Exception as e:
            cuda_error = str(e)
            cuda_ok = False

        if cuda_ok:
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
                f"  HARDWARE BESCHLEUNIGUNG AKTIV: {gpu_name}\n"
                f"  VRAM: {vram_total:.0f} MB | CUDA: {self._gpu_info['cuda_version']}\n"
                f"  STATUS: Alle KI-Modelle laufen auf der GPU\n"
                f"{'=' * 60}\n"
            )
            print(banner)
        else:
            self._gpu_info = {"name": "CPU", "vram_total_mb": 0, "cuda_version": None}
            banner = (
                f"\n{'!' * 60}\n"
                f"  WARNUNG: GPU-BESCHLEUNIGUNG NICHT MOEGLICH!\n"
                f"  Fehler: {cuda_error or 'Keine CUDA-GPU erkannt'}\n"
                f"  Grund: Meistens fehlt der NVIDIA-Treiber (Version 530+).\n"
                f"  AKTION: Bitte NVIDIA-Treiber installieren und PC neustarten!\n"
                f"  HINWEIS: Modelle laufen jetzt EXTREM LANGSAM auf der CPU.\n"
                f"{'!' * 60}\n"
            )
            print(banner)
            logger.error("CUDA-Initialisierungsfehler: %s", cuda_error)

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

    def check_memory_available(self) -> dict:
        """F-011: Prüft verfügbaren RAM und VRAM.

        Returns:
            dict mit {
                "ram_available_gb": float,
                "vram_available_gb": float,
                "ram_sufficient": bool,
                "vram_sufficient": bool,
                "needs_unload": bool
            }
        """
        _ensure_torch()

        # RAM-Check mit psutil
        ram_stats = psutil.virtual_memory()
        ram_available_gb = ram_stats.available / (1024**3)
        ram_sufficient = ram_available_gb >= OOM_RAM_THRESHOLD_GB

        # VRAM-Check (nur bei CUDA)
        vram_available_gb = 0.0
        vram_sufficient = True
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_total = props.total_memory
            vram_used = torch.cuda.memory_allocated(0)
            vram_available_gb = (vram_total - vram_used) / (1024**3)
            vram_sufficient = vram_available_gb >= OOM_VRAM_THRESHOLD_GB

        needs_unload = not ram_sufficient or not vram_sufficient

        return {
            "ram_available_gb": round(ram_available_gb, 2),
            "vram_available_gb": round(vram_available_gb, 2),
            "ram_sufficient": ram_sufficient,
            "vram_sufficient": vram_sufficient,
            "needs_unload": needs_unload,
        }

    def _handle_oom_prevention(self, operation: str = "model load") -> None:
        """F-011: Proaktiver OOM-Handler — entlädt Modelle wenn Speicher knapp wird.

        Args:
            operation: Beschreibung der Operation (für Logging)

        Raises:
            RuntimeError: Wenn auch nach Unload nicht genug Speicher verfügbar ist
        """
        mem_status = self.check_memory_available()

        if not mem_status["needs_unload"]:
            return  # Genug Speicher verfügbar

        logger.warning(
            "F-011 OOM-Handler: Niedriger Speicher erkannt vor %s — "
            "RAM: %.2f GB verfügbar (Min: %.1f GB), VRAM: %.2f GB verfügbar (Min: %.1f GB)",
            operation,
            mem_status["ram_available_gb"],
            OOM_RAM_THRESHOLD_GB,
            mem_status["vram_available_gb"],
            OOM_VRAM_THRESHOLD_GB,
        )

        # Wenn ein Modell geladen ist, proaktiv entladen
        if self.is_loaded:
            logger.info(
                "F-011 OOM-Handler: Entlade aktuelles Modell '%s' um OOM zu vermeiden...",
                self._current_model_id,
            )
            self.unload()

            # Nach Unload nochmal prüfen
            mem_status = self.check_memory_available()
            if mem_status["needs_unload"]:
                # Immer noch zu wenig Speicher — kritischer Zustand
                logger.error(
                    "F-011 OOM-Handler: KRITISCH — Nach Unload immer noch zu wenig Speicher! "
                    "RAM: %.2f GB, VRAM: %.2f GB",
                    mem_status["ram_available_gb"],
                    mem_status["vram_available_gb"],
                )
                raise RuntimeError(
                    f"OOM: Nicht genug Speicher für {operation}. "
                    f"RAM: {mem_status['ram_available_gb']:.2f} GB verfügbar "
                    f"(Min: {OOM_RAM_THRESHOLD_GB:.1f} GB), "
                    f"VRAM: {mem_status['vram_available_gb']:.2f} GB verfügbar "
                    f"(Min: {OOM_VRAM_THRESHOLD_GB:.1f} GB). "
                    "Bitte andere Programme schließen oder System-RAM erhöhen."
                )
            else:
                logger.info(
                    "F-011 OOM-Handler: Nach Unload genug Speicher frei — "
                    "RAM: %.2f GB, VRAM: %.2f GB",
                    mem_status["ram_available_gb"],
                    mem_status["vram_available_gb"],
                )
        else:
            # Kein Modell geladen aber Speicher trotzdem knapp — systemweites Problem
            logger.error(
                "F-011 OOM-Handler: KRITISCH — Niedriger Speicher aber kein Modell geladen! "
                "Systemweiter Speichermangel. RAM: %.2f GB, VRAM: %.2f GB",
                mem_status["ram_available_gb"],
                mem_status["vram_available_gb"],
            )
            raise RuntimeError(
                f"OOM: Systemweiter Speichermangel vor {operation}. "
                f"RAM: {mem_status['ram_available_gb']:.2f} GB verfügbar "
                f"(Min: {OOM_RAM_THRESHOLD_GB:.1f} GB). "
                "Bitte andere Programme schließen oder System-RAM erhöhen."
            )

    def unload(self) -> None:
        """Entlädt das aktuelle Modell komplett und gibt GPU/RAM frei."""
        # BUG-016 Fix: torch ist auf Modul-Ebene None bis _ensure_torch() laeuft
        _ensure_torch()
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
                    except (RuntimeError, AttributeError) as e:
                        logger.warning("Moving model to CPU before unload: %s", e)

            # F-019 Fix: Move _extras objects to CPU before clearing
            for key, obj in list(self._extras.items()):
                if obj is not None and hasattr(obj, 'cpu'):
                    try:
                        obj.cpu()
                    except (RuntimeError, AttributeError) as e:
                        logger.warning("Moving extra '%s' to CPU before unload: %s", key, e)

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

            # F-011: Proaktiver OOM-Check vor Laden
            self._handle_oom_prevention(f"vision '{model_id}' laden")

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

                # FIX: transformers >=5.3 ruft model.all_tied_weights_keys.keys()
                # in mark_tied_weights_as_initialized() auf.  Moondream2's
                # HfMoondream-Klasse definiert dieses Attribut nicht, was einen
                # AttributeError INNERHALB von from_pretrained() auslöst.
                # Workaround: PreTrainedModel temporär patchen, damit jede
                # Subklasse einen Fallback-Wert erbt.
                from transformers.modeling_utils import PreTrainedModel
                _had_attr = hasattr(PreTrainedModel, "all_tied_weights_keys")
                if not _had_attr:
                    PreTrainedModel.all_tied_weights_keys = {}

                try:
                    self._model = AutoModelForCausalLM.from_pretrained(
                        model_id,
                        torch_dtype=dtype,
                        device_map={"": self.device},
                        trust_remote_code=needs_trust,
                    )
                finally:
                    # Patch wieder entfernen, wenn es vorher nicht existierte,
                    # damit andere Modelle nicht beeinflusst werden.
                    if not _had_attr:
                        try:
                            del PreTrainedModel.all_tied_weights_keys
                        except AttributeError:
                            pass

                # Sicherheitsnetz: Falls das geladene Modell-Objekt selbst
                # das Attribut immer noch nicht hat (z.B. bei zukünftigen
                # transformers-Versionen), setzen wir es direkt.
                if not hasattr(self._model, "all_tied_weights_keys"):
                    self._model.all_tied_weights_keys = {}

                self._model.eval()
            except RuntimeError:
                logger.error("OOM beim Laden von vision '%s' — räume auf.", model_id)
                self.unload()
                from services.errors import CUDAOutOfMemoryError
                raise CUDAOutOfMemoryError(operation=f"Vision '{model_id}' laden")
            except (OSError, EnvironmentError) as e:
                logger.error("Vision-Modell '%s' nicht gefunden: %s", model_id, e)
                self.unload()
                from services.errors import MLModelNotFoundError
                raise MLModelNotFoundError(
                    model_id,
                    hint=(
                        f"Bitte Modell herunterladen: "
                        f"huggingface-cli download {model_id}"
                    ),
                ) from e

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

            # F-011: Proaktiver OOM-Check vor Laden
            self._handle_oom_prevention(f"SigLIP '{model_id}' laden")

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
                # use_fast=False: Die neue Rust-basierte Fast-Processor-Variante
                # (SiglipImageProcessor) erzeugt interne Threads, die mit Qt's
                # Thread-Modell kollidieren und zu ACCESS_VIOLATION fuehren.
                self._extras["processor"] = AutoProcessor.from_pretrained(
                    model_id, use_fast=False
                )
                dtype = torch.float32 if self.device == "cpu" else torch.float16
                self._model = AutoModel.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                )
                self._model.to(self.device)
                self._model.eval()
            except RuntimeError:
                logger.error("OOM beim Laden von SigLIP '%s' — räume auf.", model_id)
                self.unload()
                from services.errors import CUDAOutOfMemoryError
                raise CUDAOutOfMemoryError(operation=f"SigLIP '{model_id}' laden")
            except (OSError, EnvironmentError) as e:
                logger.error("SigLIP-Modell '%s' nicht gefunden: %s", model_id, e)
                self.unload()
                from services.errors import MLModelNotFoundError
                raise MLModelNotFoundError(
                    model_id,
                    hint=(
                        f"Bitte Modell herunterladen: "
                        f"huggingface-cli download {model_id}"
                    ),
                ) from e
            except (ImportError, MemoryError, ValueError, RuntimeError) as e:
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
            model_id: Modell-ID
            model_type: "transformers", "vision", "siglip", "raft"
        """
        # FIX B-006: Globaler GPU_LOAD_LOCK verhindert Race-Condition bei concurrent loads
        with GPU_LOAD_LOCK:
            if model_type == "vision":
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
        except (ImportError, RuntimeError, AttributeError) as e:
            logger.warning("Updating last_used_at in model registry for '%s': %s", model_id, e)

        return result

    def load_raft(self) -> tuple:
        """Lädt RAFT Small Optical Flow Modell für Motion-Analyse.

        Registriert RAFT im ModelManager sodass es beim Laden anderer
        Modelle (SigLIP, beat_this) automatisch entladen wird.
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

            # F-011: Proaktiver OOM-Check vor Laden (RAFT ist klein, aber Sicherheit)
            self._handle_oom_prevention("RAFT Small laden")

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
            except RuntimeError:
                logger.warning("[RAFT] OOM — entlade SigLIP und versuche erneut...")
                # SigLIP jetzt auch entladen und nochmal versuchen
                self.unload()
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()
                try:
                    raft = raft.to(device)
                except RuntimeError:
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
            OllamaHandle — Wrapper der chat() delegiert und VRAM-Events empvängt.
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
        except (ImportError, RuntimeError, AttributeError) as e:
            logger.warning("Updating last_used_at in model registry for Ollama model '%s': %s", model, e)

        return handle

    def _pause_ollama_if_active(self) -> None:
        """Pausiert den Ollama-Client (F-001 Fix).
        Da OLLAMA_KEEP_ALIVE=0 gesetzt ist, ist der VRAM bereits leer.
        Das Flag verhindert lediglich neue Inferenz-Anfragen während GPU-Tasks.
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

    def _ensure_vram_for_model(self, required_vram_gb: float) -> None:
        """F-011: Stellt sicher, dass genug VRAM für ein Modell verfügbar ist.

        Entlädt das aktuell geladene Modell (z.B. Vision/Moondream), falls
        der freie VRAM nicht ausreicht oder der Gesamt-VRAM knapp ist (< 6GB).
        """
        if not torch.cuda.is_available():
            return

        props = torch.cuda.get_device_properties(0)
        total_vram_gb = props.total_memory / (1024**3)
        
        mem_status = self.check_memory_available()
        vram_available_gb = mem_status["vram_available_gb"]

        # Wenn Gesamt-VRAM < 6GB, sind wir besonders aggressiv beim Entladen
        is_low_vram_gpu = total_vram_gb < 6.0
        
        needs_unload = False
        if vram_available_gb < required_vram_gb:
            needs_unload = True
            reason = f"Zu wenig freier VRAM (Verfügbar: {vram_available_gb:.1f}GB, Benötigt: {required_vram_gb:.1f}GB)"
        elif is_low_vram_gpu and self.is_loaded:
            # Auf 6GB Karten (GTX 1060 etc.) entladen wir IMMER bevor wir ein LLM via Ollama nutzen,
            # um Segfaults/Swapping zu minimieren.
            needs_unload = True
            reason = f"Low-VRAM GPU erkannt ({total_vram_gb:.1f}GB Gesamt-VRAM)"

        if needs_unload and self.is_loaded:
            logger.info("ModelManager: Entlade '%s' für VRAM-Koordination (%s).", 
                        self._current_model_id, reason)
            self.unload()


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
        # VRAM koordinieren: Falls Gemma 4 (oder andere) VRAM braucht, 
        # Vision-Modell entladen falls Speicher knapp.
        self._manager._ensure_vram_for_model(required_vram_gb=2.5)
        
        return self._client.chat(
            model=self.model,
            user_message=user_message,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_with_history(self, messages: list[dict], **kwargs) -> str:
        """Delegiert an OllamaClient.chat_with_history()."""
        # VRAM koordinieren
        self._manager._ensure_vram_for_model(required_vram_gb=2.5)
        
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

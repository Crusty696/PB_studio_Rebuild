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
from contextlib import contextmanager
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
    # H20 FIX: torch ist auf Modul-Ebene None bis _ensure_torch() laeuft
    if torch is None:
        return False
    # K6 FIX: Pruefe auf torch.cuda.OutOfMemoryError (nicht alle RuntimeErrors!)
    if hasattr(torch, 'cuda') and hasattr(torch.cuda, 'OutOfMemoryError'):
        return isinstance(exc, torch.cuda.OutOfMemoryError)
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()

# Globaler GPU-Semaphore: Serialisiert alle GPU-Modell-Lade-Operationen
# (SigLIP, RAFT, beat_this) um VRAM-Races auf 6GB GTX 1060 zu verhindern.
# FIX: RLock erlaubt verschachtelte Aufrufe (reentrant).
GPU_LOAD_LOCK = threading.RLock()

# Globaler Inferenz-Lock: Verhindert gleichzeitige Berechnungen auf der GPU
# (z.B. Vision-Analyse + Audio-Separation), was auf 6GB-Karten zu OOM führt.
# FIX: RLock für maximale Stabilität bei komplexen Pipelines.
GPU_EXECUTION_LOCK = threading.RLock()


@contextmanager
def gpu_resource_lease(reason: str = "gpu operation"):
    """Single lease fuer GPU Load/Inference/Unload Koordination.

    Reihenfolge ist absichtlich stabil: erst Execution, dann Load.
    Damit kann kein Inferenzpfad waehrend eines Loads/Unloads dazwischenfunken.
    """
    with GPU_EXECUTION_LOCK:
        with GPU_LOAD_LOCK:
            yield

# M-42 FIX: Lock für thread-sicheren torch-Import
_TORCH_IMPORT_LOCK = threading.Lock()

# F-011: OOM-Handler Schwellwerte (in GB)
# Wenn weniger als diese Werte verfügbar sind, wird proaktiv entladen
OOM_RAM_THRESHOLD_GB = 1.0  # Min 1GB freier RAM (Surface Book 2: begrenzt)
OOM_VRAM_THRESHOLD_GB = 1.5  # Min 1.5GB freies VRAM

# M-44 FIX: Vision model trust configuration (moved from method scope for maintainability)
# Trusted models that require trust_remote_code=True
VISION_TRUSTED_MODELS = {"vikhyatk/moondream2"}
# Revision pins for trusted models (prevents arbitrary code execution)
VISION_TRUSTED_REVISIONS: dict[str, str | None] = {
    # VAD-83 FIX: "2025.01.11" was not a valid HuggingFace git identifier.
    # Set to None (use latest) until a verified commit hash can be pinned.
    "vikhyatk/moondream2": None,
}


def _ensure_torch():
    """Lazy-Import von torch — wird beim ersten Zugriff geladen.

    M-42 FIX: Double-checked locking pattern verhindert Race Conditions
    bei gleichzeitigem Import durch mehrere Threads.
    """
    global torch
    if torch is None or not hasattr(torch, 'cuda'):
        with _TORCH_IMPORT_LOCK:
            # Double-check inside lock to prevent duplicate imports
            if torch is None or not hasattr(torch, 'cuda'):
                import torch as _torch
                torch = _torch
    return torch


def get_cuda_memory_info_bytes(device: int = 0) -> tuple[int, int]:
    """Return (free_bytes, total_bytes) for CUDA with external VRAM included."""
    _ensure_torch()
    if not torch.cuda.is_available():
        return 0, 0

    mem_get_info = getattr(torch.cuda, "mem_get_info", None)
    if mem_get_info is not None:
        try:
            free_bytes, total_bytes = mem_get_info(device)
            return int(free_bytes), int(total_bytes)
        except (RuntimeError, TypeError, AttributeError) as exc:
            logger.warning("torch.cuda.mem_get_info() fehlgeschlagen, fallback: %s", exc)

    props = torch.cuda.get_device_properties(device)
    total_bytes = int(props.total_memory)
    used_bytes = int(torch.cuda.memory_allocated(device))
    return max(total_bytes - used_bytes, 0), total_bytes


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

        # H21 FIX: Alle Retries erschoepft — letzte Exception werfen statt None
        # zurueckzugeben, da Caller oft ein Tuple erwarten und sonst mit
        # TypeError crashen.
        raise RuntimeError(
            f"OOM in {func.__name__}: Alle {max_retries} Retries erschoepft."
        )

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
                    inst = super().__new__(cls)
                    # B-122 Fix: ALLE State-Felder werden in __new__ unter
                    # cls._lock gesetzt, BEVOR cls._instance veroeffentlicht
                    # wird. Sonst koennte ein zweiter Thread cls._instance
                    # in Halb-State sehen — speziell __init__ early-return
                    # vor self._swap_lock = RLock() fuehrte zu AttributeError.
                    inst._initialized = False
                    # M-60 FIX: Set _gpu_info default in __new__ to prevent AttributeError
                    # if __init__ early-returns before _log_gpu_hardware() runs
                    inst._gpu_info = {"name": "unbekannt", "vram_total_mb": 0}
                    inst._current_model_id = None
                    inst._model = None
                    inst._tokenizer = None
                    inst._pipe = None
                    inst._model_type = None
                    inst._extras = {}
                    # B-194: Auxiliary-Slot fuer ko-residente Modelle (z.B. RAFT
                    # neben SigLIP). Vorher rief load_raft() self.unload() auf,
                    # was die SigLIP-Tensoren auf CPU schob — die in workers/
                    # video.py gehaltene Reference wurde damit unbrauchbar
                    # (Mixed-Device-RuntimeError, faelschlich als OOM geloggt).
                    inst._aux_model = None
                    inst._aux_model_id = None
                    inst._aux_model_type = None
                    inst._aux_extras = {}
                    inst._swap_lock = threading.RLock()
                    inst.device = "cpu"  # provisorisch, wird in __init__ ueberschrieben
                    cls._instance = inst
        return cls._instance

    def __init__(self, device: str | None = None):
        if self._initialized:
            return

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

        # B-218: Flag-Bit fuer "CUDA-Context koennte stale sein" — wird vom
        # Power-Event-Listener (WM_POWERBROADCAST/PBT_APMRESUMESUSPEND) und
        # bei expliziter notify_power_resume() gesetzt. Vor dem naechsten
        # GPU-Op wird via cuda_health_check() probed; bei Fail wird auf
        # CPU zurueckgeschaltet UND alle Slots invalidiert (geladene Tensoren
        # zeigen auf toten Context). Verhindert STATUS_STACK_BUFFER_OVERRUN
        # nach Laptop-Andocken/Sleep-Wakeup.
        self._cuda_suspect_stale = False

        # Prominenten GPU-Status loggen (einmalig)
        self._log_gpu_hardware()
        logger.info("ModelManager initialisiert auf Device: %s", self.device)

        # B-122: ``_initialized=True`` ZULETZT setzen. Wenn ein zweiter
        # Thread genau jetzt ``ModelManager()`` aufruft, hat er bereits
        # alle State-Felder aus __new__ und sieht entweder _initialized=False
        # (laeuft __init__ ebenfalls durch — idempotent, da torch.is_available
        # und die Logger-Aufrufe alle deterministisch sind) oder True
        # (early-return mit allen Feldern bereit).
        self._initialized = True

    # ── B-218: CUDA-Context-Health (Laptop-Dock/Sleep-Resume) ─────────────

    def cuda_health_check(self) -> bool:
        """B-218: Probe ob der CUDA-Context noch lebt.

        Wird gerufen vor jedem GPU-Allokat-Pfad. Bei Laptop mit Mobile-GPU
        verliert die GPU nach Andocken/Sleep den Power-State; ein vorher
        initialisierter CUDA-Context wird intern invalid, aber
        ``torch.cuda.is_available()`` luegt weiter "True". Der naechste
        echte cuda-Call (z.B. ``tensor.to('cuda')``) crasht dann nativ
        mit STATUS_STACK_BUFFER_OVERRUN.

        Diese Probe versucht eine MINI-Allocation (1-Element-Tensor +
        synchronize). Wenn das werfend / blockend ist, ist der Context
        tot. Kosten: ~0.2-1ms wenn Context lebt; bei totem Context faengt
        try/except entweder den RuntimeError oder die Probe selbst
        crasht mit demselben Bug — letzterer Fall ist hier nicht
        rettbar (siehe notify_power_resume + auto_fallback).

        Returns:
            True wenn CUDA usable, False wenn dead/unavailable.
        """
        _ensure_torch()
        if not torch.cuda.is_available():
            return False
        try:
            # Tiny-Probe: ein-Element-Tensor + synchronize. Zwingt den
            # cuda-Runtime, mindestens einen Op auszufuehren — bei stale
            # Context wirft das RuntimeError ("CUDA error: ...").
            probe = torch.zeros(1, device="cuda")
            probe = probe + 1.0  # erzwingt Kernel-Launch
            torch.cuda.synchronize()
            del probe
            return True
        except (RuntimeError, AssertionError) as exc:
            logger.warning(
                "B-218: CUDA health-check FAILED — Context vermutlich stale "
                "(Laptop-Dock/Sleep-Resume?): %s", exc,
            )
            return False

    def notify_power_resume(self) -> None:
        """B-218: vom Power-Event-Listener nach Resume aufgerufen.

        Markiert den Cache als verdaechtig — beim naechsten load_*-Call
        wird zwangsweise health-check + ggf. CPU-Fallback ausgeloest.
        Idempotent: wiederholtes Aufrufen ist sicher.
        """
        with self._swap_lock:
            self._cuda_suspect_stale = True
            logger.info(
                "B-218: Power-Resume signalisiert — CUDA-Context wird beim "
                "naechsten Modell-Load probed."
            )

    def _ensure_cuda_or_fallback(self, operation: str) -> None:
        """B-218: Vor jedem GPU-allocating Load aufrufen.

        Wenn ``device == "cuda"`` und (a) der Suspect-Flag gesetzt ist
        ODER (b) cuda_health_check() False zurueckgibt, schalten wir
        den Manager auf ``device = "cpu"`` und entladen alle Slots.
        Damit laufen nachfolgende Loads sauber auf CPU statt nativ zu
        crashen.

        Wenn CUDA wieder zurueckkommt (z.B. nach Re-Dock), wird beim
        naechsten erfolgreichen health-check wieder auf "cuda" gehoben.
        """
        with self._swap_lock:
            if self.device != "cuda":
                # Schon auf CPU — pruefe ob CUDA wieder da ist (Re-Dock).
                if self._cuda_suspect_stale or torch.cuda.is_available():
                    self._cuda_suspect_stale = False
                    if self.cuda_health_check():
                        logger.info(
                            "B-218: CUDA wieder verfuegbar (vermutlich Re-Dock) — "
                            "device wechselt zurueck cpu -> cuda fuer %s",
                            operation,
                        )
                        self.device = "cuda"
                return

            # device == "cuda": pruefen ob Context noch lebt.
            if not self._cuda_suspect_stale:
                return  # No reason to probe — schneller Pfad.

            self._cuda_suspect_stale = False
            if self.cuda_health_check():
                # Context lebt; alles OK.
                return

            # Context ist tot — Fallback auf CPU.
            logger.warning(
                "B-218: CUDA-Context verloren vor %s — Fallback auf CPU. "
                "Geladene GPU-Modelle werden invalidiert.",
                operation,
            )
            self._unload_aux_no_lock()
            self._unload_main_no_lock()
            self.device = "cpu"

    def _unload_aux_no_lock(self) -> None:
        """B-218 helper: aux-Slot ohne erneuten Lock-Acquire (Caller haelt)."""
        if self._aux_model is not None:
            try:
                del self._aux_model
            except Exception:
                pass
            self._aux_model = None
        self._aux_model_id = None
        self._aux_model_type = None
        self._aux_extras = {}

    def _unload_main_no_lock(self) -> None:
        """B-218 helper: main-Slot ohne erneuten Lock-Acquire (Caller haelt)."""
        if self._model is not None:
            try:
                del self._model
            except Exception:
                pass
            self._model = None
        self._tokenizer = None
        self._pipe = None
        self._current_model_id = None
        self._model_type = None
        self._extras = {}
        gc.collect()

    def _log_gpu_hardware(self) -> None:
        """Loggt den GPU-Hardware-Status prominent ins Terminal und speichert ihn."""
        with ModelManager._lock:
            if ModelManager._gpu_logged:
                return
            ModelManager._gpu_logged = True

        _ensure_torch()

        # Surface Book 2: GPU aus Error-47 reaktivieren bevor CUDA init
        try:
            from services.startup_checks import _recover_gpu_error47
            _recover_gpu_error47()
        except (ImportError, Exception) as exc:
            logger.debug("GPU Error-47 Recovery uebersprungen: %s", exc)

        # H3 FIX: NICHT torch.cuda.init() aufrufen — das erzeugt einen
        # zweiten CUDA-Kontext (+200-300MB VRAM) wenn main.py bereits
        # den Kontext initialisiert hat. is_available() genuegt.
        cuda_ok = False
        cuda_error = ""
        try:
            cuda_ok = torch.cuda.is_available()
            if not cuda_ok:
                cuda_error = "torch.cuda.is_available() returned False"
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
        vram_total_gb = 0.0
        if torch.cuda.is_available():
            vram_free, vram_total = get_cuda_memory_info_bytes(0)
            vram_available_gb = vram_free / (1024**3)
            vram_total_gb = vram_total / (1024**3)
            vram_sufficient = vram_available_gb >= OOM_VRAM_THRESHOLD_GB

        needs_unload = not ram_sufficient or not vram_sufficient

        return {
            "ram_available_gb": round(ram_available_gb, 2),
            "vram_available_gb": round(vram_available_gb, 2),
            "vram_total_gb": round(vram_total_gb, 2),
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
        # Aggressiver GC vor dem Check — Python haelt oft GB an toten Objekten
        gc.collect()
        if torch is not None and hasattr(torch, 'cuda') and torch.cuda.is_available():
            torch.cuda.empty_cache()

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

    def unload_raft(self) -> None:
        """B-194: Public-Alias zum gezielten RAFT-Cleanup ohne main-Modell
        anzufassen. Idempotent (no-op falls kein aux-Modell geladen oder
        falls aktuelles aux nicht RAFT ist).
        """
        with self._swap_lock:
            if self._aux_model_type == "raft":
                self._unload_aux()

    def _unload_aux(self) -> None:
        """B-194: Entlaedt nur das auxiliary-Modell (RAFT), ohne das main-
        Modell anzufassen. Wird von ``load_raft()`` aufgerufen statt der
        bisherigen ``self.unload()``-Falle, die SigLIP zerstoerte.
        """
        _ensure_torch()
        # Hinweis: Caller muss bereits den ``_swap_lock`` halten.
        if self._aux_model is None:
            return
        old_id = self._aux_model_id
        old_type = self._aux_model_type
        logger.info("ModelManager: Entlade aux-Modell '%s' (Typ: %s)...", old_id, old_type)

        try:
            if hasattr(self._aux_model, "cpu"):
                self._aux_model.cpu()
        except (RuntimeError, AttributeError) as e:
            logger.warning("aux-Modell auf CPU schieben fehlgeschlagen: %s", e)

        for key, obj in list(self._aux_extras.items()):
            if obj is not None and hasattr(obj, "cpu"):
                try:
                    obj.cpu()
                except (RuntimeError, AttributeError) as e:
                    logger.warning("aux-Extra '%s' auf CPU schieben fehlgeschlagen: %s", key, e)

        self._aux_model = None
        self._aux_model_id = None
        self._aux_model_type = None
        self._aux_extras.clear()

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()
            torch.cuda.empty_cache()
        logger.info("ModelManager: aux-Modell '%s' entladen.", old_id)

    def unload(self) -> None:
        """Entlädt das aktuelle Modell komplett und gibt GPU/RAM frei."""
        # BUG-016 Fix: torch ist auf Modul-Ebene None bis _ensure_torch() laeuft
        _ensure_torch()
        with self._swap_lock:
            # B-194: Aux (RAFT) erst — sonst kann main-Tensor-Cleanup von
            # einem noch resident gehaltenen aux-Modell partiell blockiert
            # bleiben.
            self._unload_aux()

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

            # B-123: ``torch.cuda.synchronize()`` aus dem unload-Pfad
            # entfernt. Auf einer stuck GPU (Code-47, siehe D-022)
            # blockt synchronize() ohne Timeout — und unload() ist der
            # zentrale Cleanup. Wenn er blockt, blockt alles.
            # Doppel-empty_cache + GC reicht fuer fragmentierten VRAM.
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.empty_cache()

            logger.info(
                "ModelManager: '%s' entladen. GPU-Cache geleert, GC ausgeführt.", old_id
            )

            # Ollama fortsetzen — GPU ist jetzt frei
            self._resume_ollama_if_paused()

    @staticmethod
    def _all_finite(tensor) -> bool:
        """True wenn der Tensor keine NaN/Inf enthaelt."""
        import torch
        return bool(torch.isfinite(tensor).all().item())

    def _load_with_fp16_nan_guard(self, load_fn, smoke_fn, label: str):
        """B-336: Auf GPU zuerst in fp16 laden (VRAM-schonend), dann per
        Smoke-Inferenz auf NaN/Inf pruefen. Pascal (GTX 1060) hat keinen echten
        fp16-Durchsatz und kann NaN liefern — in dem Fall in fp32 neu laden.

        Auf CPU immer fp32. Wirft die Smoke-Inferenz selbst (z.B. weil das Modell
        anderen Input braucht), wird fp16 behalten (keine erzwungene VRAM-
        Verdopplung ohne belegtes Problem).

        ``load_fn(dtype) -> model`` baut+platziert das Modell.
        ``smoke_fn(model) -> bool`` liefert True wenn die Ausgabe endlich ist.
        """
        import torch
        if self.device == "cpu":
            return load_fn(torch.float32)
        model = load_fn(torch.float16)
        try:
            ok = smoke_fn(model)
        except Exception as exc:  # noqa: BLE001 — Smoke darf Load nie kippen
            logger.debug("B-336: fp16-Smoke fuer %s nicht ausfuehrbar (%s) — behalte fp16",
                         label, exc)
            return model
        if ok:
            return model
        logger.warning("B-336: %s lieferte in fp16 NaN/Inf auf %s — lade in fp32 neu.",
                       label, self.device)
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return load_fn(torch.float32)

    def load_vision(self, model_id: str = "vikhyatk/moondream2") -> tuple:
        """Lädt ein Vision-Modell (Moondream2) für Bildanalyse.

        Returns:
            (model, tokenizer) — Moondream2-spezifisch
        """
        with self._swap_lock:
            # B-218: Health-Check + ggf. CPU-Fallback vor cuda-Allokat.
            self._ensure_cuda_or_fallback(f"vision '{model_id}' laden")

            if self._current_model_id == model_id and self._model_type == "vision":
                return self._model, self._tokenizer

            # Ollama pausieren, bevor GPU belegt wird
            self._pause_ollama_if_active()

            try:
                self.unload()
                self._handle_oom_prevention(f"vision '{model_id}' laden")

                logger.info("ModelManager: Lade Vision-Modell '%s' auf %s...", model_id, self.device)

                from transformers import AutoModelForCausalLM, AutoTokenizer

                # M-44 FIX: Use module-level constants (defined at top of file)
                needs_trust = model_id in VISION_TRUSTED_MODELS
                pinned_revision = VISION_TRUSTED_REVISIONS.get(model_id)
                if needs_trust and pinned_revision is None:
                    logger.warning(
                        "HIGH-3: trust_remote_code=True fuer '%s' ohne Revision-Pin! "
                        "Bitte eine bekannte Revision in _TRUSTED_REVISIONS eintragen.",
                        model_id,
                    )

                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                    gc.collect()
                    torch.cuda.empty_cache()

                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_id, trust_remote_code=needs_trust,
                    revision=pinned_revision,
                )
                # Moondream2 Compat: all_tied_weights_keys Patch
                from transformers.modeling_utils import PreTrainedModel

                def _build_vision(dt):
                    _had_attr = hasattr(PreTrainedModel, "all_tied_weights_keys")
                    if not _had_attr:
                        PreTrainedModel.all_tied_weights_keys = {}
                    try:
                        m = AutoModelForCausalLM.from_pretrained(
                            model_id, torch_dtype=dt,
                            device_map={"": self.device},
                            trust_remote_code=needs_trust,
                            revision=pinned_revision,
                        )
                    finally:
                        if not _had_attr:
                            try:
                                del PreTrainedModel.all_tied_weights_keys
                            except AttributeError:
                                pass
                    if not hasattr(m, "all_tied_weights_keys"):
                        m.all_tied_weights_keys = {}
                    m.eval()
                    return m

                def _smoke_vision(m):
                    ids = torch.tensor([[0, 1, 2, 3]], device=self.device)
                    with torch.no_grad():
                        out = m(input_ids=ids)
                    logits = getattr(out, "logits", out)
                    return self._all_finite(logits)

                # B-336: fp16 mit NaN-Guard + fp32-Fallback (Pascal/GTX 1060).
                self._model = self._load_with_fp16_nan_guard(
                    _build_vision, _smoke_vision, f"Vision '{model_id}'")
                self._current_model_id = model_id
                self._model_type = "vision"
                logger.info("ModelManager: Vision '%s' geladen.", model_id)
                return self._model, self._tokenizer

            except Exception:
                self.unload()
                raise
            finally:
                self._resume_ollama_if_paused()

    def load_siglip(self, model_id: str = "google/siglip-so400m-patch14-384") -> tuple:
        """Lädt SigLIP Vision+Text Encoder für 1152-dim Embeddings.

        Returns:
            (model, processor) — SigLIP-spezifisch
        """

        with self._swap_lock:
            # B-218: Health-Check + ggf. CPU-Fallback vor cuda-Allokat.
            self._ensure_cuda_or_fallback(f"SigLIP '{model_id}' laden")

            if self._current_model_id == model_id and self._model_type == "siglip":
                return self._model, self._extras.get("processor")

            # Ollama pausieren, bevor GPU belegt wird
            self._pause_ollama_if_active()

            try:
                self.unload()

                # F-011: Proaktiver OOM-Check vor Laden
                self._handle_oom_prevention(f"SigLIP '{model_id}' laden")

                # P1 Fix: VRAM aggressiv freigeben
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                    gc.collect()
                    torch.cuda.empty_cache()

                logger.info("ModelManager: Lade SigLIP '%s' auf %s...", model_id, self.device)

                from transformers import AutoModel, AutoProcessor

                # use_fast=False: Rust Fast-Processor kollidiert mit Qt Threads
                # B-037 / B615: model_id wird aus der LOCKED-Liste gewaehlt
                # (D-008 SigLIP-so400m), kein User-Input. Revision nicht
                # gepinnt weil ModelManager bewusst Latest-on-HF-Mirror
                # zieht — Modell wird via safetensors weights_only=True
                # geladen, kein Code-Execution-Vektor.
                self._extras["processor"] = AutoProcessor.from_pretrained(  # nosec B615
                    model_id, use_fast=False
                )

                def _build_siglip(dt):
                    # SigLIP initializes some tensors on CPU during
                    # from_pretrained(); CPU half ops can fail before the model
                    # is moved to CUDA. Load fp32 first, then cast on CUDA.
                    load_dtype = torch.float32 if dt == torch.float16 else dt
                    m = AutoModel.from_pretrained(  # nosec B615
                        model_id, torch_dtype=load_dtype,
                    )
                    m.to(self.device)
                    if self.device == "cuda" and dt == torch.float16:
                        m.half()
                    m.eval()
                    return m

                def _smoke_siglip(m):
                    px = torch.randn(
                        1, 3, 384, 384,
                        dtype=next(m.parameters()).dtype, device=self.device,
                    )
                    with torch.no_grad():
                        feats = m.get_image_features(pixel_values=px)
                    return self._all_finite(feats)

                # B-336: fp16 mit NaN-Guard + fp32-Fallback (Pascal/GTX 1060).
                self._model = self._load_with_fp16_nan_guard(
                    _build_siglip, _smoke_siglip, f"SigLIP '{model_id}'")

                self._current_model_id = model_id
                self._model_type = "siglip"
                logger.info("ModelManager: SigLIP '%s' geladen.", model_id)

                return self._model, self._extras["processor"]

            except Exception:
                # Bei JEDEM Fehler: aufraeeumen und Ollama IMMER resumieren
                self.unload()
                raise
            finally:
                # Ollama IMMER fortsetzen — auch bei OOM/Fehler
                self._resume_ollama_if_paused()

    def ensure_loaded(self, model_id: str, model_type: str = "transformers") -> Any:
        """Stellt sicher, dass das angegebene Modell geladen ist.

        FIX B-006: GPU_LOAD_LOCK serialisiert parallele Modell-Laden
        um VRAM-Crashes zu verhindern wenn mehrere Agenten gleichzeitig laden.

        Args:
            model_id: Modell-ID
            model_type: "transformers", "vision", "siglip", "raft"
        """
        # GPU-Lease deckt Load + moegliches Unload gegen laufende Inferenz ab.
        with gpu_resource_lease(f"ensure_loaded:{model_type}"):
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

        B-194: RAFT lebt jetzt im aux-Slot, damit ein parallel resident
        gehaltenes main-Modell (z.B. SigLIP fuer Batch-Captioning) nicht
        durch das Laden von RAFT auf CPU geschoben wird. Vorher rief
        ``load_raft()`` ``self.unload()`` (H17-Pfad) — das machte den
        Koexistenz-Vertrag (~2.5 GB SigLIP + ~0.1 GB RAFT auf 6 GB VRAM)
        kaputt: in workers/video.py gehaltene SigLIP-References zeigten
        nach RAFT-Load auf CPU-Tensoren waehrend Inputs auf CUDA lagen
        → Mixed-Device-RuntimeError, der von der OOM-Recovery faelschlich
        als "OOM bei SigLIP Batch" geloggt wurde.

        Returns:
            (raft_model, device) — direkt verwendbar für torch inference
        """
        model_id = "raft_small"

        with self._swap_lock:
            # B-218: vor JEDEM cuda-Allocate pruefen, ob Context noch lebt
            # (Laptop-Dock/Sleep-Resume kann ihn killen, ohne dass
            # is_available() das merkt).
            self._ensure_cuda_or_fallback("RAFT Small laden")

            # Cache-Hit im aux-Slot
            if self._aux_model_type == "raft" and self._aux_model is not None:
                return self._aux_model, torch.device(self.device)

            self._pause_ollama_if_active()

            try:
                # B-194: nur ein vorhandenes aux-Modell entladen — main
                # (z.B. SigLIP) bleibt unangetastet.
                self._unload_aux()

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
                    # B-194: OOM beim aux-Load darf NICHT main entladen.
                    # Nur aux-Slot raeumen + Retry.
                    logger.warning("[RAFT] OOM — aux-Slot raeume und versuche erneut...")
                    self._unload_aux()
                    torch.cuda.empty_cache()
                    gc.collect()
                    raft = raft.to(device)

                raft = raft.eval()
                self._aux_model = raft
                self._aux_model_id = model_id
                self._aux_model_type = "raft"
                logger.info("ModelManager: RAFT Small geladen auf %s (aux-Slot)", device)
                return self._aux_model, device

            except Exception:
                # B-194: Bei Hard-Failure nur aux raeumen, main nicht antasten.
                self._unload_aux()
                raise
            finally:
                self._resume_ollama_if_paused()

    def load_ollama(self, model: str, base_url: str = "http://localhost:11434") -> "OllamaHandle":
        """Registriert Ollama als aktiven LLM-Backend im ModelManager.

        Ollama läuft als separater Prozess und belegt kein VRAM durch den
        ModelManager, ABER: wenn andere GPU-intensive Modelle (Demucs, SigLIP)
        geladen werden, wird Ollama automatisch pausiert.

        **B-124 / Hinweis zur State-Semantik:** ``_current_model_id`` und
        ``_model_type`` werden hier ABSICHTLICH NICHT gesetzt. Konsequenz:
        ``is_loaded`` bleibt nach ``load_ollama()`` False, weil der
        Singleton-State-Tracker nur Modelle mit Lifecycle (load/unload)
        verfolgt — Ollama ist ein externer Prozess. Caller die wissen
        wollen ob Ollama aktiv ist, sollen ``OllamaHandle.is_available``
        nutzen, NICHT ``ModelManager.is_loaded``.

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

        free_bytes, total_bytes = get_cuda_memory_info_bytes(0)
        used = (total_bytes - free_bytes) / 1024 / 1024
        total = total_bytes / 1024 / 1024
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

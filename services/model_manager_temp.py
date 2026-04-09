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
import psutil
from functools import wraps
from typing import Any

# torch wird LAZY importiert
# (spart ~11s Startup wenn ModelManager nicht sofort gebraucht wird)
torch = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Globaler GPU-Semaphore: Serialisiert alle GPU-Modell-Lade-Operationen
# (SigLIP, RAFT, beat_this) um VRAM-Races auf 6GB GTX 1060 zu verhindern
GPU_LOAD_LOCK = threading.Lock()

# F-011: OOM-Handler Schwellwerte (in GB)
# Wenn weniger als diese Werte verfügbar sind, wird proaktiv entladen
OOM_RAM_THRESHOLD_GB = 2.0  # Min 2GB freier RAM
OOM_VRAM_THRESHOLD_GB = 1.5  # Min 1.5GB freies VRAM


def _ensure_torch():

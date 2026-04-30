"""Feature-Flag-Bridge auto_edit_phase3 ↔ PacingPipeline.

Die Bridge ist der offizielle Entscheidungspunkt fuer den Studio-Brain-
Pacing-Pfad. Default bleibt der Legacy-Pfad; mit
`PB_USE_STUDIO_BRAIN_PIPELINE=1` wird der Studio-Brain-Pipeline-Setup in
`services.pacing_service` aktiviert.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

ENV_VAR = "PB_USE_STUDIO_BRAIN_PIPELINE"
_TRUE = {"1", "true", "yes", "on"}


def use_studio_brain_pipeline() -> bool:
    """True wenn die Studio-Brain-Pipeline aktiviert wurde.

    Aktivierung **ausschließlich** über Environment-Variable, damit Tests
    deterministisch bleiben (kein DB-Setting, kein YAML).
    """
    return os.environ.get(ENV_VAR, "").strip().lower() in _TRUE


def maybe_use_studio_brain_pipeline(*, audio_id: int, video_clip_ids: list[int]) -> bool:
    """Return True when the Studio-Brain pacing path should run."""
    enabled = use_studio_brain_pipeline()
    if enabled:
        logger.info(
            "PB_USE_STUDIO_BRAIN_PIPELINE=1: Studio-Brain-Pacing aktiv. "
            "audio_id=%d, %d clips.",
            audio_id, len(video_clip_ids),
        )
    return enabled

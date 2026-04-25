"""Foundation Slice 0 / R-S0-2: Feature-Flag-Bridge auto_edit_phase3 ↔ PacingPipeline.

Aktuell ist die Bridge ein **Stub** — sie liest die Flag und entscheidet,
ob der Studio-Brain-Pfad aktiv ist. Solange Slice 1 die eigentliche
Mapping-Logik (auto_edit-Inputs → ClipFeatures/AudioContext, Output →
TimelineSegment-Liste) noch nicht geliefert hat, fällt der Code auch
bei Flag=True transparent auf den Legacy-Pfad zurück und loggt eine
Warnung.

Das ist die abgesicherte Basis für die spätere echte Verdrahtung:

- Default-Flag = False → bit-identisches Legacy-Verhalten (Snapshot-Test).
- Flag=True (env `PB_USE_STUDIO_BRAIN_PIPELINE=1`) → Hook für Slice 1.

R-S0-2 Risk-Mitigation: Eine Feature-Flag-Schicht **ohne** Funktionalität
ist sicherer als ein halb-fertiger Bridge-Code, der unter Last divergiert.
Die Flag wird in Slice 1 mit der echten Pipeline gefüllt.
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
    """Convenience-Hook für `auto_edit_phase3`.

    Heute: True → Warning loggen + False zurückgeben (Slice-1-TODO).
    Damit bleibt der Caller-Code identisch, sobald Slice 1 die echte
    Verdrahtung liefert (return True + neuer Pfad).
    """
    if not use_studio_brain_pipeline():
        return False
    logger.warning(
        "PB_USE_STUDIO_BRAIN_PIPELINE=1 gesetzt, aber Bridge noch nicht "
        "implementiert (Slice 1). Falle auf Legacy-Pfad zurück. "
        "audio_id=%d, %d clips.",
        audio_id, len(video_clip_ids),
    )
    return False

"""services.audio — Aggregator-Index für Audio-Domain Services.

Cycle 14 / Option C: Logische Gruppierung der ~10 Audio-Service-Module
ohne physische Moves. Vorhandene Imports bleiben kompatibel.

Neue Caller können nutzen:

.. code-block:: python

    from services.audio import (
        AudioAnalyzer,
        BeatAnalysisService,
        OnsetRhythmService,
        StructureDetectionService,
        DEFAULT_SR, HOP_LENGTH,
    )

Statt der bisherigen 5 separaten Imports.
"""
from __future__ import annotations

# Re-Exports — Public-API der Audio-Domain
from services.audio_service import AudioAnalyzer, track_lock  # noqa: F401
from services.audio_constants import (  # noqa: F401
    DEFAULT_SR,
    HOP_LENGTH,
)
from services.beat_analysis_service import BeatAnalysisService  # noqa: F401
from services.onset_rhythm_service import (  # noqa: F401
    OnsetRhythmService,
    PercussiveOnset,
    RhythmAnalysis,
)
from services.structure_detection_service import (  # noqa: F401
    StructureDetectionService,
    StructureResult,
    StructureSegmentResult,
)

__all__ = [
    "AudioAnalyzer",
    "BeatAnalysisService",
    "OnsetRhythmService",
    "PercussiveOnset",
    "RhythmAnalysis",
    "StructureDetectionService",
    "StructureResult",
    "StructureSegmentResult",
    "track_lock",
    "DEFAULT_SR",
    "HOP_LENGTH",
]

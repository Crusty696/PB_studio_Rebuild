# database/__init__.py
# Re-exports alles für Rückwärtskompatibilität — alle bestehenden Imports
# ``from database import engine, AudioTrack, ...`` funktionieren unverändert.

from sqlalchemy.orm import Session  # noqa: F401  (re-export für project_manager)

from database.session import (  # noqa: F401
    EngineProxy,
    engine,
    get_raw_engine,
    nullpool_session,
    get_active_project_id,
    set_project,
)

from database.models import (  # noqa: F401
    Base,
    Project,
    AnalysisJob,
    AnalysisArtifact,
    StepDep,
    ProjectSource,
    AudioTrack,
    VideoClip,
    Scene,
    Beatgrid,
    WaveformData,
    AVPacingData,
    PacingBlueprint,
    AudioVideoAnchor,
    ClipAnchor,
    AIPacingMemory,
    StructureSegment,
    HotCue,
    ModelRegistry,
    AgentFeedback,
    StylePreset,
    TimelineEntry,
    AnalysisStatus,
    TimelineSnapshot,
    ProjectNote,
)

from database.migrations import init_db  # noqa: F401

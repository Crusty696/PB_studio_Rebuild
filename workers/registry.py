"""Worker-Registry: Registriert alle Worker-Klassen fuer das Command Pattern.

Agenten-Tools emittieren nur agent_command_signal → Main-Thread baut Worker.
Importiert als Side-Effect: `import workers.registry`
"""

from services.task_manager import GlobalTaskManager
from services.pacing_service import AdvancedPacingSettings

from .analysis import AnalysisWorker
from .audio import StemSeparationWorker
from .video import VideoAnalysisWorker
from .import_export import ExportWorker, ProxyCreationWorker
from .edit import AutoEditWorker
from .debug import DummyProgressWorker


GlobalTaskManager.register_worker(
    "separate_stems",
    StemSeparationWorker,
    "Stem-Separation #{track_id}",
    mapper=lambda kw: {"track_id": kw["track_id"]},
)

GlobalTaskManager.register_worker(
    "analyze_audio",
    AnalysisWorker,
    "Audio-Analyse #{track_id}",
    mapper=lambda kw: {"track_id": kw["track_id"], "title": kw.get("title", f"Track #{kw['track_id']}")},
)

GlobalTaskManager.register_worker(
    "analyze_video",
    VideoAnalysisWorker,
    "Video-Analyse #{clip_id}",
    mapper=lambda kw: {"clip_id": kw["clip_id"], "title": kw.get("title", f"Clip #{kw['clip_id']}")},
)

GlobalTaskManager.register_worker(
    "create_proxy",
    ProxyCreationWorker,
    "Proxy #{clip_id}",
    mapper=lambda kw: {"clip_id": kw["clip_id"], "video_path": kw["video_path"]},
)

GlobalTaskManager.register_worker(
    "auto_edit",
    AutoEditWorker,
    "Auto-Edit",
    mapper=lambda kw: {
        # register_actions.py emittiert "audio_track_id"; AutoEditWorker erwartet "audio_id"
        "audio_id": kw.get("audio_id") or kw["audio_track_id"],
        "video_ids": kw["video_ids"],
        "settings": kw.get("settings") or AdvancedPacingSettings(),
    },
)

GlobalTaskManager.register_worker(
    "export_timeline",
    ExportWorker,
    "Export: {output_name}",
    mapper=lambda kw: {
        "project_id": kw.get("project_id", 1),
        "output_name": kw.get("output_name", "output.mp4"),
        "resolution": kw.get("resolution", "1920x1080"),
        "fps": kw.get("fps", 30),
    },
)

GlobalTaskManager.register_worker(
    "teste_ladebalken",
    DummyProgressWorker,
    "Test-Ladebalken ({steps}s)",
    mapper=lambda kw: {"steps": kw.get("steps", 10), "interval_ms": kw.get("interval_ms", 1000)},
)

# --- Phase 4: Audio-Analyse Worker ---
from .audio_analysis import (
    KeyDetectionWorker, LUFSAnalysisWorker, AudioClassifyWorker,
    SpectralAnalysisWorker, StructureDetectionWorker,
)

GlobalTaskManager.register_worker(
    "detect_key",
    KeyDetectionWorker,
    "Key-Erkennung #{audio_track_id}",
    mapper=lambda kw: {"audio_track_id": kw["audio_track_id"], "file_path": kw["file_path"]},
)

GlobalTaskManager.register_worker(
    "analyze_lufs",
    LUFSAnalysisWorker,
    "LUFS-Analyse #{audio_track_id}",
    mapper=lambda kw: {"audio_track_id": kw["audio_track_id"], "file_path": kw["file_path"]},
)

GlobalTaskManager.register_worker(
    "classify_audio",
    AudioClassifyWorker,
    "Audio-Klassifikation #{audio_track_id}",
    mapper=lambda kw: {
        "audio_track_id": kw["audio_track_id"],
        "file_path": kw["file_path"],
        "bpm": kw.get("bpm"),
    },
)

GlobalTaskManager.register_worker(
    "analyze_spectral",
    SpectralAnalysisWorker,
    "Spektral-Analyse #{audio_track_id}",
    mapper=lambda kw: {"audio_track_id": kw["audio_track_id"], "file_path": kw["file_path"]},
)

GlobalTaskManager.register_worker(
    "detect_structure",
    StructureDetectionWorker,
    "Struktur-Erkennung #{audio_track_id}",
    mapper=lambda kw: {
        "audio_track_id": kw["audio_track_id"],
        "file_path": kw["file_path"],
        "bpm": kw.get("bpm"),
        "beat_positions": kw.get("beat_positions"),
        "energy_per_beat": kw.get("energy_per_beat"),
    },
)

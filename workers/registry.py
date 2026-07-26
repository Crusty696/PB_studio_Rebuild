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

def _map_auto_edit(kw: dict) -> dict:
    """Mapper fuer die auto_edit-Action.

    Die Chat-Action ``services/actions/edit/timeline_actions.py::auto_edit``
    sendet neben audio_track_id/video_ids auch die DJ-Regler
    (base_cut_rate, energy_reactivity, breakdown_behavior, vibe). Vorher
    nahm der Mapper nur audio_id/video_ids/settings entgegen — alle
    Pacing-Parameter wurden still verworfen. Sie werden jetzt in die
    ``AdvancedPacingSettings`` gefaltet, die der AutoEditWorker erwartet.
    """
    settings = kw.get("settings")
    if settings is None:
        settings = AdvancedPacingSettings()
        if kw.get("base_cut_rate") is not None:
            settings.base_cut_rate = int(round(float(kw["base_cut_rate"])))
        if kw.get("energy_reactivity") is not None:
            settings.energy_reactivity = int(round(float(kw["energy_reactivity"])))
        if kw.get("breakdown_behavior") is not None:
            settings.breakdown_behavior = str(kw["breakdown_behavior"])
        if kw.get("vibe") is not None:
            settings.vibe = str(kw["vibe"])
    return {
        # register_actions.py emittiert "audio_track_id"; AutoEditWorker erwartet "audio_id"
        "audio_id": kw.get("audio_id") or kw["audio_track_id"],
        "video_ids": kw["video_ids"],
        "settings": settings,
    }


GlobalTaskManager.register_worker(
    "auto_edit",
    AutoEditWorker,
    "Auto-Edit",
    mapper=_map_auto_edit,
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

"""Worker-Registry: Registriert alle Worker-Klassen fuer das Command Pattern.

Agenten-Tools emittieren nur agent_command_signal → Main-Thread baut Worker.
Importiert als Side-Effect: `import workers.registry`
"""
import logging

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


# --- Userentscheidung 2026-08-31: auto_ducking und convert_videos per Chat ---
#
# Beide Worker existieren seit jeher, waren aber nie registriert. Die Aktionen
# meldeten deshalb "kein Worker registriert" (d175a51) und liefen nur ueber die
# Oberflaeche. Der User hat entschieden, beide freizuschalten.
#
# Die Mapper bauen die Konstruktor-Argumente genauso zusammen wie die
# UI-Pfade — ui/controllers/stems.py:265-292 und
# ui/controllers/convert.py:249-284. Sie werfen bewusst NICHT: der Mapper
# laeuft in einem Qt-Slot (_build_and_execute_task) ohne Fehlerbehandlung.
# Fehlende Daten werden deshalb an den Worker durchgereicht, der sie ueber
# sein error-Signal im TaskManagerDock sichtbar macht.

from .audio import AutoDuckingWorker
from .import_export import BatchConvertWorker


def _map_auto_ducking(kw: dict) -> dict:
    """audio_track_id -> (music_path, voice_path, output_path)."""
    import re
    from pathlib import Path

    from database import nullpool_session, AudioTrack
    from services.stem_router import resolve_stem_path

    track_id = kw.get("audio_track_id") or kw.get("track_id")
    music_path = voice_path = ""
    title = f"track_{track_id}"
    try:
        with nullpool_session() as session:
            track = session.get(AudioTrack, track_id)
            if track is not None:
                # B-822/B-824: gespeicherte Pfade sind projektrelativ.
                music_path = resolve_stem_path(track.stem_other_path) or ""
                voice_path = resolve_stem_path(track.stem_vocals_path) or ""
                title = track.title or title
    except Exception:  # noqa: BLE001 — Mapper darf den Qt-Slot nicht sprengen
        logging.exception("auto_ducking-Mapper: DB-Zugriff fehlgeschlagen")

    ducked_dir = Path(__file__).resolve().parent.parent / "storage" / "ducked"
    try:
        ducked_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logging.exception("auto_ducking-Mapper: Ducked-Ordner nicht anlegbar")
    safe_title = re.sub(r'[<>:"/\|?*]', "_", title)
    return {
        "music_path": music_path,
        "voice_path": voice_path,
        "output_path": str(ducked_dir / f"{safe_title}_ducked.wav"),
    }


def _map_convert_videos(kw: dict) -> dict:
    """codec-Kurzname -> (vcodec, ext), Videoliste aus dem Pool.

    Dieselbe Codec-Zuordnung wie ui/controllers/convert.py:261-276, inklusive
    NVENC-Erkennung. GPU-Hartregel: nur h264_nvenc/hevc_nvenc, sonst CPU.
    """
    codec = str(kw.get("codec") or "h264").lower()
    if codec == "h265":
        vcodec, ext = "hevc_nvenc", ".mp4"
    elif codec == "prores":
        vcodec, ext = "prores_ks", ".mov"
    else:
        try:
            from services.convert_service import detect_nvenc
            has_nvenc = bool(detect_nvenc().get("h264_nvenc"))
        except Exception:  # noqa: BLE001 — Mapper darf den Qt-Slot nicht sprengen
            logging.exception("convert_videos-Mapper: NVENC-Erkennung fehlgeschlagen")
            has_nvenc = False
        vcodec, ext = ("h264_nvenc" if has_nvenc else "libx264"), ".mp4"

    try:
        from services.ingest_service import get_all_video
        videos = get_all_video()
    except Exception:  # noqa: BLE001 — Mapper darf den Qt-Slot nicht sprengen
        logging.exception("convert_videos-Mapper: Video-Pool nicht lesbar")
        videos = []

    return {
        "videos": videos,
        "resolution": str(kw.get("resolution") or "1920x1080"),
        "fps": str(kw.get("fps") or "30"),
        "vcodec": vcodec,
        "ext": ext,
    }


GlobalTaskManager.register_worker(
    "auto_ducking",
    AutoDuckingWorker,
    "Auto-Ducking #{audio_track_id}",
    mapper=_map_auto_ducking,
)

GlobalTaskManager.register_worker(
    "convert_videos",
    BatchConvertWorker,
    "Video-Convert -> {resolution} @ {fps}fps",
    mapper=_map_convert_videos,
)

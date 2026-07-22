"""Medien-bezogene Chat-Actions (AUFRAEUM B1). Verbatim aus edit_actions.py."""

from services.action_registry import action_registry
from services.actions.edit._common import (
    _logger,
    _get_task_manager,
    _get_main_window,
)

__all__ = [
    "import_file",
    "delete_media",
    "list_media",
    "convert_videos",
    "refresh_media",
]


@action_registry.register(
    name="import_file",
    description="Importiert eine Audio- oder Videodatei in das aktuelle Projekt.",
    param_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Vollständiger Pfad zur Datei."
            },
            "project_id": {
                "type": "integer",
                "description": "ID des Zielprojekts."
            }
        },
        "required": ["file_path", "project_id"]
    }
)
def import_file(file_path: str, project_id: int) -> dict:
    from pathlib import Path
    from services.ingest_service import ingest_audio, ingest_video, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
    ext = Path(file_path).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        result = ingest_audio(file_path, project_id)
    elif ext in VIDEO_EXTENSIONS:
        result = ingest_video(file_path, project_id)
    else:
        return {"error": f"Unbekanntes Format: {ext}"}
    if result is None:
        return {"message": "Datei bereits importiert."}
    return {"id": result.id, "title": getattr(result, 'title', ''), "type": type(result).__name__}


@action_registry.register(
    name="delete_media",
    description="Löscht ein importiertes Medium (Video oder Audio) per ID aus dem Projekt-Pool.",
    param_schema={
        "type": "object",
        "properties": {
            "media_id": {
                "type": "integer",
                "description": "ID des zu löschenden Mediums."
            },
            "media_type": {
                "type": "string",
                "description": "Typ des Mediums: 'audio' oder 'video'.",
                "enum": ["audio", "video"]
            }
        },
        "required": ["media_id", "media_type"]
    }
)
def delete_media(media_id: int, media_type: str) -> dict:
    from services.ingest_service import delete_selected_media
    try:
        video_ids = [media_id] if media_type == "video" else []
        audio_ids = [media_id] if media_type == "audio" else []

        count = delete_selected_media(video_ids, audio_ids)
        if count > 0:
            return {
                "status": "ok",
                "action": "delete_media",
                "media_id": media_id,
                "media_type": media_type,
                "message": f"{media_type.capitalize()} mit ID {media_id} wurde erfolgreich gelöscht.",
            }
        else:
            return {"error": f"Medium mit ID {media_id} konnte nicht in der Datenbank gefunden werden."}
    except Exception as e:
        _logger.exception("Fehler in delete_media-Aktion")
        return {"error": f"Fehler beim Löschen des Mediums: {e}"}


@action_registry.register(
    name="list_media",
    description="Listet alle importierten Audio-Tracks und Video-Clips im aktuellen Projekt auf.",
    param_schema={"type": "object", "properties": {}}
)
def list_media() -> dict:
    from services.ingest_service import get_all_audio, get_all_video

    try:
        audios = get_all_audio()
        videos = get_all_video()
        audio_list = [
            {
                "id": a["id"],
                "title": a.get("title", ""),
                "type": "audio",
                "duration": a.get("duration"),
                "bpm": a.get("bpm"),
                "key": a.get("key"),
            }
            for a in audios
        ]
        video_list = [
            {
                "id": v["id"],
                "title": v.get("title", ""),
                "type": "video",
                "duration": v.get("duration"),
                "resolution": v.get("resolution"),
                "fps": v.get("fps"),
            }
            for v in videos
        ]
        return {
            "audio_count": len(audio_list),
            "video_count": len(video_list),
            "audio": audio_list,
            "video": video_list,
        }
    except Exception as e:
        _logger.exception("Fehler in list_media-Aktion")
        return {"error": f"Fehler beim Auflisten der Medien: {e}"}


@action_registry.register(
    name="convert_videos",
    description="Startet Batch-Konvertierung aller Videos im Pool in ein einheitliches Format.",
    param_schema={
        "type": "object",
        "properties": {
            "resolution": {
                "type": "string",
                "description": "Ziel-Auflösung, z.B. '1920x1080' (Standard) oder '3840x2160'."
            },
            "fps": {
                "type": "string",
                "description": "Ziel-FPS, z.B. '30' (Standard) oder '60'."
            },
            "codec": {
                "type": "string",
                "description": "Video-Codec: 'h264' (Standard), 'h265' oder 'prores'.",
                "enum": ["h264", "h265", "prores"]
            }
        }
    }
)
def convert_videos(
    resolution: str = "1920x1080",
    fps: str = "30",
    codec: str = "h264",
) -> dict:
    tm = _get_task_manager()
    if tm is None:
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit("convert_videos", {
        "resolution": resolution,
        "fps": fps,
        "codec": codec,
    })
    return {
        "status": "Task in Warteschlange",
        "action": "convert_videos",
        "resolution": resolution,
        "fps": fps,
        "codec": codec,
        "message": f"Batch-Konvertierung gestartet ({resolution}, {fps}fps, {codec}). Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="refresh_media",
    description="Aktualisiert die Medien-Tabelle (Audio + Video Pool) aus der Datenbank.",
    param_schema={"type": "object", "properties": {}}
)
def refresh_media() -> dict:
    mw = _get_main_window()
    if not mw or not hasattr(mw, "media_table_controller"):
        return {"error": "Media-Table-Controller nicht verfügbar."}

    try:
        mw.media_table_controller._refresh_media_table()
        return {
            "status": "ok",
            "action": "refresh_media",
            "message": "Medien-Tabelle wurde aktualisiert.",
        }
    except Exception as e:
        _logger.exception("Fehler in refresh_media-Aktion")
        return {"error": f"Fehler beim Aktualisieren: {e}"}

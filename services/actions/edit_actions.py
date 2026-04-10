"""Edit actions: file import, auto-edit/pacing, timeline export,
action listing, and test utilities.
"""

import logging

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)


def _get_task_manager():
    """Gibt den TaskManager zurueck ohne QApplication-Kopplung."""
    from services.task_manager import GlobalTaskManager
    return GlobalTaskManager.instance()


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
    name="auto_edit",
    description="Erstellt automatisch eine Timeline mit Schnitten auf den Beats der Musik.",
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks (liefert Beat-Positionen)."
            },
            "base_cut_rate": {
                "type": "number",
                "description": "Beats zwischen Schnitten (1=jeden Beat, 4=jeden Downbeat, 16=alle 4 Bars). Default: 4"
            },
            "energy_reactivity": {
                "type": "number",
                "description": "Energie-Reaktivität in Prozent (0-100). Default: 50"
            },
            "breakdown_behavior": {
                "type": "string",
                "description": "Verhalten bei Breakdowns: 'halve', 'force16', 'none'. Default: 'halve'",
                "enum": ["halve", "force16", "none"]
            },
            "vibe": {
                "type": "string",
                "description": "Vibe-Keyword für semantische Video-Auswahl (z.B. 'dark', 'euphoric')."
            }
        },
        "required": ["audio_track_id"]
    }
)
def auto_edit(
    audio_track_id: int,
    base_cut_rate: float = None,
    energy_reactivity: float = None,
    breakdown_behavior: str = None,
    vibe: str = None,
) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut AutoEditWorker."""
    from services.ingest_service import get_all_video

    video_ids = [v["id"] for v in get_all_video()]
    if not video_ids:
        return {"timeline": [], "message": "Keine Videos im Projekt gefunden."}

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    signal_params = {"audio_track_id": audio_track_id, "video_ids": video_ids}
    if base_cut_rate is not None:
        signal_params["base_cut_rate"] = base_cut_rate
    if energy_reactivity is not None:
        signal_params["energy_reactivity"] = energy_reactivity
    if breakdown_behavior is not None:
        signal_params["breakdown_behavior"] = breakdown_behavior
    if vibe is not None:
        signal_params["vibe"] = vibe

    tm.agent_command_signal.emit("auto_edit", signal_params)
    return {
        "status": "Task in Warteschlange",
        "action": "auto_edit",
        "audio_track_id": audio_track_id,
        "video_count": len(video_ids),
        "message": f"Auto-Edit mit {len(video_ids)} Videos gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="export_timeline",
    description="Exportiert die aktuelle Timeline als fertige Videodatei.",
    param_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "integer",
                "description": "ID des Projekts zum Exportieren."
            },
            "output_path": {
                "type": "string",
                "description": "Pfad für die Ausgabedatei (optional)."
            }
        },
        "required": ["project_id"]
    }
)
def export_timeline_action(project_id: int, output_path: str | None = None) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut ExportWorker."""
    output_name = output_path or "output.mp4"
    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "export_timeline", {"project_id": project_id, "output_name": output_name}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "export_timeline",
        "output_name": output_name,
        "message": f"Timeline-Export '{output_name}' gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="list_actions",
    description="Zeigt alle verfügbaren Aktionen an, die die KI ausführen kann.",
    param_schema={"type": "object", "properties": {}}
)
def list_actions() -> list[str]:
    return action_registry.list_actions()

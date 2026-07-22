"""Projekt-bezogene Chat-Actions (AUFRAEUM B1). Verbatim aus edit_actions.py."""

from services.action_registry import action_registry
from services.actions.edit._common import (
    _logger,
    _get_project_manager,
    _run_on_main_thread,
)

__all__ = [
    "create_project",
    "open_project",
    "save_project",
    "save_project_as",
    "list_projects",
    "get_project_info",
    "get_settings",
]


@action_registry.register(
    name="create_project",
    description="Erstellt ein neues Projekt mit einem Namen und optionalem Pfad, Auflösung und FPS.",
    param_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name des neuen Projekts."
            },
            "path": {
                "type": "string",
                "description": "Optionaler vollständiger Pfad zum Projektordner. Wenn weggelassen, wird der Standardordner verwendet."
            },
            "resolution": {
                "type": "string",
                "description": "Optionale Auflösung, z.B. '1920x1080' (Standard) oder '3840x2160'."
            },
            "fps": {
                "type": "number",
                "description": "Optionale Bilder pro Sekunde, z.B. 30.0 (Standard) oder 60.0."
            }
        },
        "required": ["name"]
    }
)
def create_project(
    name: str,
    path: str | None = None,
    resolution: str = "1920x1080",
    fps: float = 30.0,
) -> dict:
    from pathlib import Path

    if path:
        proj_path = Path(path)
    else:
        import os
        documents = Path(os.path.expanduser("~/Documents"))
        proj_path = documents / "PB_studio_Rebuild" / "Projects" / name

    def _create():
        pm = _get_project_manager()
        if pm is None:
            return {"error": "ProjectManager nicht verfügbar"}
        try:
            pm.create_project(proj_path, name, resolution, fps)
            return {
                "status": "ok",
                "message": f"Projekt '{name}' wurde erfolgreich unter {proj_path} erstellt.",
                "path": str(proj_path),
            }
        except Exception as e:
            _logger.exception("Fehler in create_project-Aktion")
            return {"error": f"Projekt konnte nicht erstellt werden: {e}"}

    return _run_on_main_thread(_create)


@action_registry.register(
    name="open_project",
    description="Öffnet ein bestehendes Projekt unter dem angegebenen Pfad.",
    param_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Vollständiger Pfad zum Projektordner, der die 'pb_studio.db' enthält."
            }
        },
        "required": ["path"]
    }
)
def open_project(path: str) -> dict:
    from pathlib import Path
    proj_path = Path(path)

    def _open():
        pm = _get_project_manager()
        if pm is None:
            return {"error": "ProjectManager nicht verfügbar"}
        try:
            meta = pm.open_project(proj_path)
            return {
                "status": "ok",
                "message": f"Projekt '{meta.get('name')}' wurde erfolgreich aus {proj_path} geladen.",
                "meta": meta,
            }
        except Exception as e:
            _logger.exception("Fehler in open_project-Aktion")
            return {"error": f"Projekt konnte nicht geöffnet werden: {e}"}

    return _run_on_main_thread(_open)


@action_registry.register(
    name="save_project",
    description="Speichert das aktuelle Projekt (setzt den Speicherstatus auf gesichert).",
    param_schema={"type": "object", "properties": {}}
)
def save_project() -> dict:
    return {
        "status": "ok",
        "action": "save_project",
        "message": "Projekt erfolgreich gespeichert.",
    }


@action_registry.register(
    name="get_project_info",
    description="Gibt Name, Pfad, Auflösung, FPS und Statistiken des aktiven Projekts zurück.",
    param_schema={"type": "object", "properties": {}}
)
def get_project_info() -> dict:
    from database import nullpool_session, TimelineEntry, AudioTrack, VideoClip
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    try:
        pm = _get_project_manager()
        meta = {}
        if pm and hasattr(pm, "_current_project"):
            proj = pm._current_project
            if proj:
                meta = {
                    "name": getattr(proj, "name", "Unbekannt"),
                    "path": str(getattr(proj, "path", "")),
                    "resolution": getattr(proj, "resolution", ""),
                    "fps": getattr(proj, "fps", 30.0),
                }

        with nullpool_session() as session:
            audio_count = session.query(AudioTrack).filter_by(project_id=project_id).filter(AudioTrack.deleted_at.is_(None)).count()
            video_count = session.query(VideoClip).filter_by(project_id=project_id).filter(VideoClip.deleted_at.is_(None)).count()
            timeline_count = session.query(TimelineEntry).filter_by(project_id=project_id).count()

        return {
            "project_id": project_id,
            **meta,
            "audio_tracks": audio_count,
            "video_clips": video_count,
            "timeline_entries": timeline_count,
        }
    except Exception as e:
        _logger.exception("Fehler in get_project_info-Aktion")
        return {"error": f"Fehler beim Abrufen der Projekt-Info: {e}"}


@action_registry.register(
    name="save_project_as",
    description="Speichert das aktuelle Projekt unter einem neuen Pfad (Kopie).",
    param_schema={
        "type": "object",
        "properties": {
            "target_path": {
                "type": "string",
                "description": "Vollständiger Pfad zum neuen Projektordner."
            },
            "name": {
                "type": "string",
                "description": "Neuer Projektname (optional, sonst Name des Zielordners)."
            }
        },
        "required": ["target_path"]
    }
)
def save_project_as(target_path: str, name: str | None = None) -> dict:
    from pathlib import Path

    pm = _get_project_manager()
    if pm is None:
        return {"error": "ProjectManager nicht verfügbar"}

    target = Path(target_path)
    if name:
        target = target / name.strip()

    try:
        result_path = pm.save_project_as(target)
        return {
            "status": "ok",
            "action": "save_project_as",
            "path": str(result_path) if result_path else str(target),
            "message": f"Projekt wurde unter '{target}' gespeichert.",
        }
    except Exception as e:
        _logger.exception("Fehler in save_project_as-Aktion")
        return {"error": f"Fehler beim Speichern: {e}"}


@action_registry.register(
    name="list_projects",
    description="Listet die zuletzt geöffneten Projekte auf.",
    param_schema={"type": "object", "properties": {}}
)
def list_projects() -> dict:
    try:
        from services.recent_projects import RecentProjectsManager
        projects = RecentProjectsManager.list()
        items = [{"path": str(p), "name": p.name} for p in projects]
        return {
            "total": len(items),
            "projects": items,
        }
    except ImportError:
        return {"error": "RecentProjectsManager nicht verfügbar."}
    except Exception as e:
        _logger.exception("Fehler in list_projects-Aktion")
        return {"error": f"Fehler beim Auflisten der Projekte: {e}"}


@action_registry.register(
    name="get_settings",
    description="Zeigt die aktuellen App-Einstellungen (Ollama, GPU, Modelle).",
    param_schema={"type": "object", "properties": {}}
)
def get_settings() -> dict:
    try:
        from PySide6.QtCore import QSettings
        settings = QSettings("PB_Studio", "PB_Studio")
        result = {
            "ollama_enabled": settings.value("ollama/enabled", False, type=bool),
            "ollama_url": settings.value("ollama/url", "http://localhost:11434"),
            "ollama_model": settings.value("ollama/model", "llama3.2"),
        }

        # GPU-Info hinzufügen
        try:
            import torch
            result["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                result["gpu_name"] = torch.cuda.get_device_name(0)
                result["gpu_memory_total_mb"] = round(torch.cuda.get_device_properties(0).total_mem / 1024**2)
        except ImportError:
            result["cuda_available"] = False

        return result
    except Exception as e:
        _logger.exception("Fehler in get_settings-Aktion")
        return {"error": f"Fehler beim Abrufen der Einstellungen: {e}"}

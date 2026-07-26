"""Projekt-bezogene Chat-Actions (AUFRAEUM B1). Verbatim aus edit_actions.py."""

from services.action_registry import action_registry
from services.actions.edit._common import (
    _logger,
    _get_main_window,
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
    """Ruft den echten Save-Pfad der UI auf.

    Vorher gab die Action hart ``status: ok`` zurueck ohne irgendetwas zu
    speichern — der ChatDock markierte das Projekt danach als sauber.
    Der reale Speicherpfad ist ``ProjectManagementController._save_project``
    (Fenster-State + _mark_clean); er muss im Main-Thread laufen.
    """
    def _save():
        mw = _get_main_window()
        if mw is None:
            return {"error": "Hauptfenster nicht verfügbar."}

        controller = getattr(mw, "project_management", None)
        if controller is None or not hasattr(controller, "_save_project"):
            return {"error": "Speicherfunktion nicht verfügbar (ProjectManagementController fehlt)."}

        pm = _get_project_manager()
        project_path = getattr(pm, "current_project_path", None) if pm else None
        if project_path is None:
            return {"error": "Kein Projekt geöffnet — es gibt nichts zu speichern."}

        try:
            controller._save_project()
        except Exception as e:
            _logger.exception("Fehler in save_project-Aktion")
            return {"error": f"Fehler beim Speichern: {e}"}

        return {
            "status": "ok",
            "action": "save_project",
            "path": str(project_path),
            "message": f"Projekt unter '{project_path}' gespeichert.",
        }

    return _run_on_main_thread(_save)


@action_registry.register(
    name="get_project_info",
    description="Gibt Name, Pfad, Auflösung, FPS und Statistiken des aktiven Projekts zurück.",
    param_schema={"type": "object", "properties": {}}
)
def get_project_info() -> dict:
    from database import nullpool_session, Project, TimelineEntry, AudioTrack, VideoClip
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    try:
        # ProjectManager hat kein ``_current_project`` — die reale API ist
        # ``current_project_path``; Name/Resolution/FPS stehen in der
        # projects-Tabelle des aktiven Projekts.
        pm = _get_project_manager()
        project_path = getattr(pm, "current_project_path", None) if pm else None

        meta = {}
        with nullpool_session() as session:
            proj = session.get(Project, project_id)
            if proj is not None:
                meta = {
                    "name": proj.name or "Unbekannt",
                    "path": str(project_path) if project_path else (proj.path or ""),
                    "resolution": proj.resolution or "",
                    "fps": float(proj.fps) if proj.fps is not None else 30.0,
                }
            elif project_path is not None:
                meta = {"path": str(project_path)}

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
        from pathlib import Path
        from services.recent_projects import RecentProjectsManager
        # RecentProjectsManager hat kein ``list()`` — die API ist ``get_all()``
        # und liefert Pfad-Strings, keine Objekte mit ``.name``.
        projects = RecentProjectsManager.get_all()
        items = [{"path": str(p), "name": Path(p).name} for p in projects]
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
        # Der echte Settings-Store ist services/settings_store.py (JSON) —
        # QSettings("PB_Studio","PB_Studio") war ein Phantom-Store und lieferte
        # immer die Defaults.
        from services.settings_store import get_ollama_settings
        ollama = get_ollama_settings()
        result = {
            "ollama_enabled": bool(ollama.get("enabled", True)),
            "ollama_url": ollama.get("url", "http://localhost:11434"),
            "ollama_model": ollama.get("model", ""),
        }

        # GPU-Info hinzufügen
        try:
            import torch
            result["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                result["gpu_name"] = torch.cuda.get_device_name(0)
                # torch-API heisst total_memory, nicht total_mem
                result["gpu_memory_total_mb"] = round(
                    torch.cuda.get_device_properties(0).total_memory / 1024**2
                )
        except ImportError:
            result["cuda_available"] = False

        return result
    except Exception as e:
        _logger.exception("Fehler in get_settings-Aktion")
        return {"error": f"Fehler beim Abrufen der Einstellungen: {e}"}

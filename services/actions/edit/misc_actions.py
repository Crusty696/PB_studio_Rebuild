"""Sonstige Chat-Actions (AUFRAEUM B1). Verbatim aus edit_actions.py."""

from services.action_registry import action_registry
from services.actions.edit._common import (
    _logger,
    _get_task_manager,
    _get_main_window,
)

__all__ = [
    "list_actions",
    "rl_feedback",
    "clear_search",
    "cancel_task",
]


@action_registry.register(
    name="list_actions",
    description="Zeigt alle verfügbaren Aktionen an, die die KI ausführen kann.",
    param_schema={"type": "object", "properties": {}}
)
def list_actions() -> list[str]:
    return action_registry.list_actions()


@action_registry.register(
    name="rl_feedback",
    description="Gibt Reinforcement-Learning-Feedback (positiv/negativ) auf den aktuellen Auto-Edit.",
    param_schema={
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "description": "Bewertung: 'positive' (gut) oder 'negative' (schlecht).",
                "enum": ["positive", "negative"]
            }
        },
        "required": ["sentiment"]
    }
)
def rl_feedback(sentiment: str) -> dict:
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    # audio_track_id aus dem aktuellen Zustand ableiten
    mw = _get_main_window()
    audio_id = None
    if mw and hasattr(mw, "audio_combo"):
        audio_id = mw.audio_combo.currentData()

    if audio_id is None:
        return {"error": "Kein Audio-Track ausgewählt. Bitte zuerst einen Track wählen."}

    try:
        from services.pacing_service import record_rl_feedback
        success = record_rl_feedback(audio_id, sentiment, project_id)
        if success:
            emoji = "👍" if sentiment == "positive" else "👎"
            return {
                "status": "ok",
                "action": "rl_feedback",
                "sentiment": sentiment,
                "audio_track_id": audio_id,
                "message": f"{emoji} {sentiment.title()}-Feedback gespeichert. "
                           "Wird beim nächsten Auto-Edit berücksichtigt.",
            }
        return {"error": "Feedback konnte nicht gespeichert werden."}
    except Exception as e:
        _logger.exception("Fehler in rl_feedback-Aktion")
        return {"error": f"Fehler beim Speichern des Feedbacks: {e}"}


@action_registry.register(
    name="clear_search",
    description="Setzt den Video-Suchfilter zurück und zeigt alle Videos im Pool an.",
    param_schema={"type": "object", "properties": {}}
)
def clear_search() -> dict:
    mw = _get_main_window()
    if not mw:
        return {"error": "Hauptfenster nicht verfügbar."}

    try:
        if hasattr(mw, "search_input"):
            mw.search_input.clear()
        if hasattr(mw, "media_table_controller"):
            mw.media_table_controller._refresh_media_table()
        return {
            "status": "ok",
            "action": "clear_search",
            "message": "Suchfilter zurückgesetzt — alle Videos werden angezeigt.",
        }
    except Exception as e:
        _logger.exception("Fehler in clear_search-Aktion")
        return {"error": f"Fehler beim Zurücksetzen der Suche: {e}"}


@action_registry.register(
    name="cancel_task",
    description="Bricht einen laufenden Hintergrund-Task ab.",
    param_schema={
        "type": "object",
        "properties": {
            "task_name": {
                "type": "string",
                "description": "Name oder Teil des Task-Namens zum Abbrechen. Wenn leer, wird der erste laufende Task abgebrochen."
            }
        }
    }
)
def cancel_task(task_name: str = "") -> dict:
    tm = _get_task_manager()
    if tm is None:
        return {"error": "TaskManager nicht verfügbar."}

    try:
        tasks = tm.get_all_tasks()
        running = [t for t in tasks if t.status == "running"]

        if not running:
            return {"error": "Keine laufenden Tasks vorhanden."}

        if task_name:
            # Suche nach Name
            target = None
            for t in running:
                if task_name.lower() in t.name.lower():
                    target = t
                    break
            if not target:
                names = [t.name for t in running]
                return {
                    "error": f"Kein laufender Task mit '{task_name}' gefunden.",
                    "running_tasks": names,
                }
        else:
            target = running[0]

        tm.cancel_task(target.task_id)
        return {
            "status": "ok",
            "action": "cancel_task",
            "cancelled_task": target.name,
            "message": f"Task '{target.name}' wurde abgebrochen.",
        }
    except Exception as e:
        _logger.exception("Fehler in cancel_task-Aktion")
        return {"error": f"Fehler beim Abbrechen: {e}"}

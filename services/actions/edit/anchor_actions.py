"""Anker-bezogene Chat-Actions (AUFRAEUM B1). Verbatim aus edit_actions.py."""

from services.action_registry import action_registry
from services.actions.edit._common import (
    _logger,
    _get_main_window,
    _run_on_main_thread,
)

__all__ = [
    "add_anchor",
    "sync_anchors",
    "remove_anchor",
    "learn_anchor",
]


@action_registry.register(
    name="add_anchor",
    description="Fügt einen Sync-Anker zur Timeline hinzu (Zeitpunkt auf Audio → Szene/Clip).",
    param_schema={
        "type": "object",
        "properties": {
            "time_seconds": {
                "type": "number",
                "description": "Zeitpunkt des Ankers auf der Audio-Timeline in Sekunden."
            },
            "scene_id": {
                "type": "string",
                "description": "Optionale ID der Szene oder des Clips (z.B. '5' oder 'clip_3')."
            }
        },
        "required": ["time_seconds"]
    }
)
def add_anchor(time_seconds: float, scene_id: str | None = None) -> dict:
    from database import nullpool_session, ClipAnchor, TimelineEntry
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    try:
        with nullpool_session() as session:
            # Finde den zum Zeitpunkt nächstgelegenen Timeline-Eintrag.
            # Vorher: order_by(start_time).first() -> IMMER der erste Clip,
            # unabhaengig von time_seconds.
            video_entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=project_id, track="video")
                .order_by(TimelineEntry.start_time)
                .all()
            )
            if not video_entries:
                return {"error": "Keine Video-Clips auf der Timeline. Bitte erst Clips hinzufügen."}

            def _distance(entry) -> float:
                start = float(entry.start_time) if entry.start_time is not None else 0.0
                end = float(entry.end_time) if entry.end_time is not None else start
                if start <= time_seconds <= end:
                    return 0.0
                return min(abs(time_seconds - start), abs(time_seconds - end))

            closest_entry = min(video_entries, key=_distance)

            # B-930: ClipAnchor kennt weder ``anchor_time`` noch ``scene_id`` —
            # die Spalten heissen ``time_offset``, ``label``, ``color``
            # (database/models.py). Die alte Fassung warf deshalb bei JEDEM
            # Aufruf einen TypeError, den der except-Block unten in eine
            # Fehlermeldung verwandelte; ``clip_anchors`` blieb dauerhaft leer.
            #
            # ``time_offset`` ist relativ zum Clip-Start, nicht absolut:
            # ui/timeline.py:1009 rechnet ``x_px = time_offset * PIXELS_PER_SECOND``
            # und prueft gegen die Clipbreite. Die uebergebene Zeit ist eine
            # Timeline-Zeit, also muss der Clip-Start abgezogen werden.
            entry_start = (
                float(closest_entry.start_time)
                if closest_entry.start_time is not None else 0.0
            )
            anchor = ClipAnchor(
                timeline_entry_id=closest_entry.id,
                time_offset=max(0.0, time_seconds - entry_start),
                label=scene_id or None,
            )
            session.add(anchor)
            session.commit()
            # B-930: ``_TrackedSession`` erbt SQLAlchemys Default
            # ``expire_on_commit=True``. Nach dem commit ist ``closest_entry``
            # abgelaufen, und der Zugriff unten liegt ausserhalb des
            # with-Blocks — die Session ist dann zu. Ohne diese Zeile endet
            # ein erfolgreich geschriebener Anker in einem
            # DetachedInstanceError und damit in einer Fehlermeldung.
            entry_id = closest_entry.id

        return {
            "status": "ok",
            "action": "add_anchor",
            "anchor_time": time_seconds,
            "scene_id": scene_id or "",
            "timeline_entry_id": entry_id,
            "message": f"Sync-Anker bei {time_seconds:.2f}s hinzugefügt"
                       + (f" (Szene: {scene_id})" if scene_id else "") + ".",
        }
    except Exception as e:
        _logger.exception("Fehler in add_anchor-Aktion")
        return {"error": f"Fehler beim Hinzufügen des Ankers: {e}"}


@action_registry.register(
    name="sync_anchors",
    description="Synchronisiert alle Sync-Anker — richtet Video-Clips an Audio-Ankern auf der Timeline aus.",
    param_schema={"type": "object", "properties": {}}
)
def sync_anchors() -> dict:
    def _sync():
        mw = _get_main_window()
        if not mw or not hasattr(mw, "timeline_view"):
            return {"error": "Timeline-View nicht verfügbar."}

        try:
            synced = mw.timeline_view.sync_anchors()
            if synced:
                mw.timeline_view.load_from_db()
                return {
                    "status": "ok",
                    "action": "sync_anchors",
                    "message": "Anker synchronisiert — Video-Clips an Audio-Ankern ausgerichtet.",
                }
            return {
                "error": "Keine Anker gefunden. Bitte setze zuerst Anker mit 'add_anchor'."
            }
        except Exception as e:
            _logger.exception("Fehler in sync_anchors-Aktion")
            return {"error": f"Fehler beim Synchronisieren: {e}"}

    return _run_on_main_thread(_sync)


@action_registry.register(
    name="remove_anchor",
    description="Entfernt einen Sync-Anker per ID aus der Datenbank.",
    param_schema={
        "type": "object",
        "properties": {
            "anchor_id": {
                "type": "integer",
                "description": "ID des zu entfernenden Ankers."
            }
        },
        "required": ["anchor_id"]
    }
)
def remove_anchor(anchor_id: int) -> dict:
    from database import nullpool_session, ClipAnchor

    try:
        with nullpool_session() as session:
            anchor = session.get(ClipAnchor, anchor_id)
            if not anchor:
                return {"error": f"Anker #{anchor_id} nicht gefunden."}

            session.delete(anchor)
            session.commit()

        return {
            "status": "ok",
            "action": "remove_anchor",
            "anchor_id": anchor_id,
            "message": f"Anker #{anchor_id} wurde entfernt.",
        }
    except Exception as e:
        _logger.exception("Fehler in remove_anchor-Aktion")
        return {"error": f"Fehler beim Entfernen des Ankers: {e}"}


@action_registry.register(
    name="learn_anchor",
    description="Speichert einen Anker als KI-Lernregel für zukünftige Auto-Edits.",
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des Audio-Tracks."
            },
            "anchor_time": {
                "type": "number",
                "description": "Zeitpunkt des Ankers in Sekunden."
            },
            "scene_id": {
                "type": "integer",
                "description": "Optionale Szenen-ID."
            }
        },
        "required": ["audio_track_id", "anchor_time"]
    }
)
def learn_anchor(audio_track_id: int, anchor_time: float, scene_id: int | None = None) -> dict:
    try:
        from services.pacing_service import learn_from_anchor
        label = f"Chat-Anker@{anchor_time:.2f}s"
        success = learn_from_anchor(audio_track_id, anchor_time, scene_id, label)
        if success:
            return {
                "status": "ok",
                "action": "learn_anchor",
                "audio_track_id": audio_track_id,
                "anchor_time": anchor_time,
                "message": f"KI-Regel gelernt: Anker bei {anchor_time:.2f}s wird beim nächsten Auto-Edit berücksichtigt.",
            }
        return {"error": "Regel konnte nicht gespeichert werden."}
    except Exception as e:
        _logger.exception("Fehler in learn_anchor-Aktion")
        return {"error": f"Fehler beim Lernen des Ankers: {e}"}

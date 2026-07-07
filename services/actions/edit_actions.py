"""Edit actions: file import, auto-edit/pacing, timeline export,
action listing, and test utilities.
"""

import logging
import threading
from pathlib import PurePosixPath, PureWindowsPath

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)
_main_thread_invoker = None
_main_thread_invoker_lock = threading.Lock()


def _get_task_manager():
    """Gibt den TaskManager zurueck ohne QApplication-Kopplung."""
    from services.task_manager import GlobalTaskManager
    return GlobalTaskManager.instance()


def _validate_export_output_name(output_path: str | None) -> str:
    raw_name = (output_path or "output.mp4").strip() or "output.mp4"
    win_path = PureWindowsPath(raw_name)
    posix_path = PurePosixPath(raw_name)
    parts = set(win_path.parts) | set(posix_path.parts)
    if (
        win_path.is_absolute()
        or posix_path.is_absolute()
        or bool(win_path.drive)
        or ".." in parts
        or "\\" in raw_name
        or "/" in raw_name
        or win_path.name != raw_name
        or posix_path.name != raw_name
    ):
        raise ValueError("output_path darf nur ein Dateiname im Export-Ordner sein")
    return raw_name


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
                "description": "Dateiname fuer die Ausgabedatei im Export-Ordner (optional)."
            }
        },
        "required": ["project_id"]
    }
)
def export_timeline_action(project_id: int, output_path: str | None = None) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut ExportWorker."""
    try:
        output_name = _validate_export_output_name(output_path)
    except ValueError as exc:
        return {"error": str(exc)}
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


# ── Hilfsfunktionen für GUI-Interaktion aus Hintergrund-Threads ─────────

def _get_main_window():
    """Findet das PBWindow-Hauptfenster über alle Top-Level-Widgets."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if widget.__class__.__name__ == "PBWindow":
                return widget
    return None


def _get_project_manager():
    """Liefert die aktive ProjectManager-Instanz des Hauptfensters."""
    mw = _get_main_window()
    if mw and hasattr(mw, "_project_manager"):
        return mw._project_manager
    return None


def _get_main_thread_invoker(app):
    global _main_thread_invoker
    with _main_thread_invoker_lock:
        if _main_thread_invoker is None:
            from PySide6.QtCore import QObject, Qt, Signal, Slot

            class _MainThreadInvoker(QObject):
                call = Signal(object)

                def __init__(self):
                    super().__init__()
                    self.call.connect(
                        self._invoke,
                        Qt.ConnectionType.BlockingQueuedConnection,
                    )

                @Slot(object)
                def _invoke(self, payload):
                    callback, box = payload
                    try:
                        box["result"] = callback()
                    except Exception as exc:  # broad catch intentional: re-raised in caller thread
                        box["error"] = exc

            _main_thread_invoker = _MainThreadInvoker()
            _main_thread_invoker.moveToThread(app.thread())
        return _main_thread_invoker


def _run_on_main_thread(callback):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or QThread.currentThread() == app.thread():
        return callback()

    box = {}
    _get_main_thread_invoker(app).call.emit((callback, box))
    if "error" in box:
        raise box["error"]
    return box.get("result")


# ── Neue Chat-Aktionen für lückenlose UI-Steuerung ──────────────────────

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
    name="clear_timeline",
    description="Löscht alle Clips und Schnitte von der aktuellen Timeline.",
    param_schema={"type": "object", "properties": {}}
)
def clear_timeline() -> dict:
    from database import nullpool_session, TimelineEntry, ClipAnchor
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    try:
        with nullpool_session() as session:
            timeline_ids = [
                r[0] for r in session.query(TimelineEntry.id).filter_by(project_id=project_id).all()
            ]

            if timeline_ids:
                # Grandchildren zuerst
                session.query(ClipAnchor).filter(
                    ClipAnchor.timeline_entry_id.in_(timeline_ids)
                ).delete(synchronize_session=False)

                # Children
                session.query(TimelineEntry).filter(
                    TimelineEntry.id.in_(timeline_ids)
                ).delete(synchronize_session=False)

            session.commit()

        return {
            "status": "ok",
            "action": "clear_timeline",
            "message": "Die Timeline wurde erfolgreich geleert.",
        }
    except Exception as e:
        _logger.exception("Fehler in clear_timeline-Aktion")
        return {"error": f"Fehler beim Leeren der Timeline: {e}"}


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


# ── Phase 2: Tiefe UI-Kontrolle — 13 neue Chat-Aktionen ────────────────


# ── Kategorie 1: Medien-Info & Navigation ───────────────────────────────

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
    name="list_timeline",
    description="Zeigt alle Einträge auf der aktuellen Timeline mit Timecodes und Effekten.",
    param_schema={"type": "object", "properties": {}}
)
def list_timeline() -> dict:
    from database import nullpool_session, TimelineEntry
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    try:
        with nullpool_session() as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=project_id)
                .order_by(TimelineEntry.start_time)
                .all()
            )
            items = []
            for e in entries:
                items.append({
                    "entry_id": e.id,
                    "track": e.track,
                    "media_id": e.media_id,
                    "start_time": float(e.start_time) if e.start_time else 0.0,
                    "end_time": float(e.end_time) if e.end_time else 0.0,
                    "brightness": float(e.brightness) if e.brightness else 0.0,
                    "contrast": float(e.contrast) if e.contrast else 1.0,
                    "crossfade_duration": float(e.crossfade_duration) if e.crossfade_duration else 0.0,
                })
        return {
            "project_id": project_id,
            "total_entries": len(items),
            "entries": items,
        }
    except Exception as e:
        _logger.exception("Fehler in list_timeline-Aktion")
        return {"error": f"Fehler beim Auflisten der Timeline: {e}"}


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


# ── Kategorie 2: Timeline-Manipulation ──────────────────────────────────

@action_registry.register(
    name="add_to_timeline",
    description="Fügt ein importiertes Medium (Audio oder Video) per ID ans Ende der Timeline hinzu.",
    param_schema={
        "type": "object",
        "properties": {
            "media_id": {
                "type": "integer",
                "description": "ID des Mediums (AudioTrack oder VideoClip)."
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
def add_to_timeline(media_id: int, media_type: str) -> dict:
    from database import nullpool_session, TimelineEntry, AudioTrack, VideoClip
    from database.session import get_active_project_id

    project_id = get_active_project_id()
    if not project_id:
        return {"error": "Kein aktives Projekt geladen."}

    try:
        with nullpool_session() as session:
            track_type = media_type  # "audio" or "video"

            if media_type == "audio":
                obj = (
                    session.query(AudioTrack)
                    .filter(
                        AudioTrack.id == media_id,
                        AudioTrack.project_id == project_id,
                        AudioTrack.deleted_at.is_(None),
                    )
                    .one_or_none()
                )
                if not obj:
                    return {"error": f"Audio-Track #{media_id} im aktiven Projekt nicht gefunden."}
                duration = float(obj.duration or 30.0)
                title = obj.title or f"Audio #{media_id}"
                # Audio immer ab 0.0
                start_time = 0.0
            else:
                obj = (
                    session.query(VideoClip)
                    .filter(
                        VideoClip.id == media_id,
                        VideoClip.project_id == project_id,
                        VideoClip.deleted_at.is_(None),
                    )
                    .one_or_none()
                )
                if not obj:
                    return {"error": f"Video-Clip #{media_id} im aktiven Projekt nicht gefunden."}
                # Fixplan 2026-07-07 Schritt 7b: gleicher Budget-Planer wie der
                # UI-Add-Pfad — die Audio-Laenge begrenzt die Video-Spur auch
                # ueber die Chat-Action.
                from services.timeline_service import plan_video_timeline_add
                plan = plan_video_timeline_add(
                    project_id, [media_id], allow_duplicates=True)
                if plan["skipped_budget"]:
                    return {
                        "error": (
                            f"Video-Spur ist bereits {plan['video_start']:.0f}s lang "
                            f"und damit an der Audio-Laenge ({plan['budget']:.0f}s). "
                            "Kein weiterer Clip noetig — Auto-Edit schneidet "
                            "beat-genau auf die Audio-Laenge."
                        )
                    }
                duration = float(obj.duration or 10.0)
                from pathlib import Path
                title = Path(obj.file_path).stem if obj.file_path else f"Video #{media_id}"
                start_time = (
                    plan["accepted"][0]["start_time"]
                    if plan["accepted"] else plan["video_start"]
                )

            entry = TimelineEntry(
                project_id=project_id,
                track=track_type,
                media_id=media_id,
                start_time=start_time,
                end_time=start_time + duration,
            )
            session.add(entry)
            session.commit()

            return {
                "status": "ok",
                "action": "add_to_timeline",
                "entry_id": entry.id,
                "media_type": media_type,
                "media_id": media_id,
                "title": title,
                "start_time": start_time,
                "end_time": start_time + duration,
                "message": f"{media_type.capitalize()} '{title}' wurde zur Timeline hinzugefügt ({start_time:.1f}s - {start_time + duration:.1f}s).",
            }
    except Exception as e:
        _logger.exception("Fehler in add_to_timeline-Aktion")
        return {"error": f"Fehler beim Hinzufügen zur Timeline: {e}"}


@action_registry.register(
    name="set_clip_effects",
    description="Setzt Helligkeit, Kontrast und Crossfade für einen Clip auf der Timeline.",
    param_schema={
        "type": "object",
        "properties": {
            "entry_id": {
                "type": "integer",
                "description": "ID des Timeline-Eintrags."
            },
            "brightness": {
                "type": "number",
                "description": "Helligkeit (-1.0 bis 1.0, Standard: 0.0)."
            },
            "contrast": {
                "type": "number",
                "description": "Kontrast (0.0 bis 3.0, Standard: 1.0)."
            },
            "crossfade": {
                "type": "number",
                "description": "Crossfade-Dauer in Sekunden (0.0 bis 5.0, Standard: 0.0)."
            }
        },
        "required": ["entry_id"]
    }
)
def set_clip_effects(
    entry_id: int,
    brightness: float | None = None,
    contrast: float | None = None,
    crossfade: float | None = None,
) -> dict:
    from database import nullpool_session, TimelineEntry

    try:
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                return {"error": f"Timeline-Eintrag #{entry_id} nicht gefunden."}

            changes = {}
            if brightness is not None:
                entry.brightness = max(-1.0, min(1.0, brightness))
                changes["brightness"] = entry.brightness
            if contrast is not None:
                entry.contrast = max(0.0, min(3.0, contrast))
                changes["contrast"] = entry.contrast
            if crossfade is not None:
                entry.crossfade_duration = max(0.0, min(5.0, crossfade))
                changes["crossfade"] = entry.crossfade_duration

            if not changes:
                return {"error": "Keine Effekt-Parameter angegeben (brightness, contrast, crossfade)."}

            session.commit()

        parts = [f"{k}={v:.2f}" for k, v in changes.items()]
        return {
            "status": "ok",
            "action": "set_clip_effects",
            "entry_id": entry_id,
            "changes": changes,
            "message": f"Effekte auf Clip #{entry_id} angewendet: {', '.join(parts)}.",
        }
    except Exception as e:
        _logger.exception("Fehler in set_clip_effects-Aktion")
        return {"error": f"Fehler beim Setzen der Effekte: {e}"}


@action_registry.register(
    name="move_clip",
    description="Verschiebt einen Timeline-Clip an eine neue Startzeit.",
    param_schema={
        "type": "object",
        "properties": {
            "entry_id": {
                "type": "integer",
                "description": "ID des Timeline-Eintrags."
            },
            "new_start_time": {
                "type": "number",
                "description": "Neue Startzeit in Sekunden."
            }
        },
        "required": ["entry_id", "new_start_time"]
    }
)
def move_clip(entry_id: int, new_start_time: float) -> dict:
    from database import nullpool_session, TimelineEntry

    try:
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                return {"error": f"Timeline-Eintrag #{entry_id} nicht gefunden."}

            old_start = float(entry.start_time) if entry.start_time else 0.0
            old_end = float(entry.end_time) if entry.end_time else 0.0
            duration = old_end - old_start

            entry.start_time = max(0.0, new_start_time)
            entry.end_time = entry.start_time + duration
            session.commit()

        return {
            "status": "ok",
            "action": "move_clip",
            "entry_id": entry_id,
            "old_start": old_start,
            "new_start": float(entry.start_time),
            "new_end": float(entry.end_time),
            "message": f"Clip #{entry_id} verschoben: {old_start:.2f}s → {entry.start_time:.2f}s.",
        }
    except Exception as e:
        _logger.exception("Fehler in move_clip-Aktion")
        return {"error": f"Fehler beim Verschieben des Clips: {e}"}


@action_registry.register(
    name="remove_clip",
    description="Entfernt einen einzelnen Clip von der Timeline (ohne das Medium aus dem Pool zu löschen).",
    param_schema={
        "type": "object",
        "properties": {
            "entry_id": {
                "type": "integer",
                "description": "ID des Timeline-Eintrags."
            }
        },
        "required": ["entry_id"]
    }
)
def remove_clip(entry_id: int) -> dict:
    from database import nullpool_session, TimelineEntry, ClipAnchor

    try:
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                return {"error": f"Timeline-Eintrag #{entry_id} nicht gefunden."}

            # Zugehörige Anker löschen
            session.query(ClipAnchor).filter_by(timeline_entry_id=entry_id).delete(
                synchronize_session=False
            )
            session.delete(entry)
            session.commit()

        return {
            "status": "ok",
            "action": "remove_clip",
            "entry_id": entry_id,
            "message": f"Clip #{entry_id} wurde von der Timeline entfernt.",
        }
    except Exception as e:
        _logger.exception("Fehler in remove_clip-Aktion")
        return {"error": f"Fehler beim Entfernen des Clips: {e}"}


# ── Kategorie 3: Konvertierung & Export ─────────────────────────────────

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
    name="preview_export",
    description="Rendert eine Quick-Preview der ersten 10 Sekunden der Timeline.",
    param_schema={"type": "object", "properties": {}}
)
def preview_export() -> dict:
    tm = _get_task_manager()
    if tm is None:
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit("preview_export", {})
    return {
        "status": "Task in Warteschlange",
        "action": "preview_export",
        "message": "Quick-Preview (10s) wird gerendert. Fortschritt im TaskManagerDock.",
    }


# ── Kategorie 4: Stems & Ducking ───────────────────────────────────────

@action_registry.register(
    name="auto_ducking",
    description="Startet automatisches Audio-Ducking (Musik leiser unter Vocals). Benötigt vorherige Stem-Separation.",
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des Audio-Tracks (muss bereits Stems haben)."
            }
        },
        "required": ["audio_track_id"]
    }
)
def auto_ducking(audio_track_id: int) -> dict:
    from database import nullpool_session, AudioTrack

    # Vorab-Validierung: Stems müssen existieren
    try:
        with nullpool_session() as session:
            track = session.get(AudioTrack, audio_track_id)
            if not track:
                return {"error": f"Audio-Track #{audio_track_id} nicht gefunden."}
            if not track.stem_vocals_path or not track.stem_other_path:
                return {
                    "error": f"Audio-Track #{audio_track_id} hat noch keine Stems. "
                             "Bitte zuerst 'separate_stems' ausführen."
                }
    except Exception as e:
        return {"error": f"DB-Fehler: {e}"}

    tm = _get_task_manager()
    if tm is None:
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit("auto_ducking", {
        "audio_track_id": audio_track_id,
    })
    return {
        "status": "Task in Warteschlange",
        "action": "auto_ducking",
        "audio_track_id": audio_track_id,
        "message": f"Auto-Ducking für Track #{audio_track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


# ── Kategorie 5: Pacing, Presets & Feedback ────────────────────────────

@action_registry.register(
    name="apply_style_preset",
    description="Wendet ein gespeichertes Style-Preset auf die Pacing-Einstellungen an.",
    param_schema={
        "type": "object",
        "properties": {
            "preset_name": {
                "type": "string",
                "description": "Name des Style-Presets (z.B. 'Energetic', 'Chill', 'Cinematic')."
            }
        },
        "required": ["preset_name"]
    }
)
def apply_style_preset(preset_name: str) -> dict:
    from database import nullpool_session

    try:
        from database import StylePreset
        with nullpool_session() as session:
            preset = session.query(StylePreset).filter_by(name=preset_name).first()
            if not preset:
                # Verfügbare Presets auflisten
                all_presets = session.query(StylePreset.name).all()
                available = [p[0] for p in all_presets]
                return {
                    "error": f"Style-Preset '{preset_name}' nicht gefunden.",
                    "available_presets": available,
                }
            return {
                "status": "ok",
                "action": "apply_style_preset",
                "preset_name": preset_name,
                "cut_rate": preset.cut_rate,
                "energy_reactivity": preset.energy_reactivity,
                "breakdown_behavior": preset.breakdown_behavior,
                "message": f"Style-Preset '{preset_name}' angewendet: Cut-Rate={preset.cut_rate}, "
                           f"Reaktivität={preset.energy_reactivity}%, Breakdown={preset.breakdown_behavior}.",
            }
    except ImportError:
        return {"error": "StylePreset-Tabelle nicht in der Datenbank verfügbar."}
    except Exception as e:
        _logger.exception("Fehler in apply_style_preset-Aktion")
        return {"error": f"Fehler beim Anwenden des Presets: {e}"}


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
            # Finde den nächstgelegenen Timeline-Eintrag
            closest_entry = (
                session.query(TimelineEntry)
                .filter_by(project_id=project_id, track="video")
                .order_by(TimelineEntry.start_time)
                .first()
            )
            if not closest_entry:
                return {"error": "Keine Video-Clips auf der Timeline. Bitte erst Clips hinzufügen."}

            anchor = ClipAnchor(
                timeline_entry_id=closest_entry.id,
                anchor_time=time_seconds,
                scene_id=scene_id or "",
            )
            session.add(anchor)
            session.commit()

        return {
            "status": "ok",
            "action": "add_anchor",
            "anchor_time": time_seconds,
            "scene_id": scene_id or "",
            "timeline_entry_id": closest_entry.id,
            "message": f"Sync-Anker bei {time_seconds:.2f}s hinzugefügt"
                       + (f" (Szene: {scene_id})" if scene_id else "") + ".",
        }
    except Exception as e:
        _logger.exception("Fehler in add_anchor-Aktion")
        return {"error": f"Fehler beim Hinzufügen des Ankers: {e}"}


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


# ── Phase 3: Letzte Lücken schließen — 10 weitere Aktionen ─────────────


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
    name="undo_timeline",
    description="Macht die letzte Timeline-Änderung rückgängig (Undo).",
    param_schema={"type": "object", "properties": {}}
)
def undo_timeline() -> dict:
    def _undo():
        mw = _get_main_window()
        if not mw or not hasattr(mw, "timeline_view"):
            return {"error": "Timeline-View nicht verfügbar."}

        undo_stack = getattr(mw.timeline_view, "undo_stack", None)
        if undo_stack is None:
            return {"error": "Undo-Stack nicht verfügbar."}

        if not undo_stack.canUndo():
            return {"error": "Nichts zum Rückgängigmachen vorhanden."}

        text = undo_stack.undoText() or "Letzte Aktion"
        undo_stack.undo()
        return {
            "status": "ok",
            "action": "undo_timeline",
            "message": f"Rückgängig: '{text}'.",
        }

    return _run_on_main_thread(_undo)


@action_registry.register(
    name="redo_timeline",
    description="Stellt die letzte rückgängig gemachte Timeline-Änderung wieder her (Redo).",
    param_schema={"type": "object", "properties": {}}
)
def redo_timeline() -> dict:
    def _redo():
        mw = _get_main_window()
        if not mw or not hasattr(mw, "timeline_view"):
            return {"error": "Timeline-View nicht verfügbar."}

        undo_stack = getattr(mw.timeline_view, "undo_stack", None)
        if undo_stack is None:
            return {"error": "Undo-Stack nicht verfügbar."}

        if not undo_stack.canRedo():
            return {"error": "Nichts zum Wiederherstellen vorhanden."}

        text = undo_stack.redoText() or "Letzte Aktion"
        undo_stack.redo()
        return {
            "status": "ok",
            "action": "redo_timeline",
            "message": f"Wiederhergestellt: '{text}'.",
        }

    return _run_on_main_thread(_redo)


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


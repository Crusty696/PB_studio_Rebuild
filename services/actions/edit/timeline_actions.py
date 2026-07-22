"""Timeline-bezogene Chat-Actions (AUFRAEUM B1). Verbatim aus edit_actions.py."""

from services.action_registry import action_registry
from services.actions.edit._common import (
    _logger,
    _get_task_manager,
    _validate_export_output_name,
    _get_main_window,
    _run_on_main_thread,
)

__all__ = [
    "auto_edit",
    "export_timeline_action",
    "clear_timeline",
    "list_timeline",
    "add_to_timeline",
    "set_clip_effects",
    "move_clip",
    "remove_clip",
    "preview_export",
    "undo_timeline",
    "redo_timeline",
    "apply_style_preset",
    "auto_ducking",
]


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
            # B-653 Fix 2: manueller Add schrieb bisher OHNE Overlap-
            # Normalisierung — voll-lange Clips stapelten sich unsichtbar
            # ueber Auto-Edit-Segmente. Der Resolver schiebt Kollisionen nach
            # rechts, laesst bewusste Luecken aber unangetastet (KEIN repair,
            # das wuerde Gaps schliessen und manuelle Platzierung zerstoeren).
            if track_type == "video":
                try:
                    from services.timeline_service import resolve_video_overlaps
                    resolve_video_overlaps(project_id)
                except Exception as _rex:  # noqa: BLE001 — Add selbst gilt
                    _logger.warning("add_to_timeline: Overlap-Resolver fehlgeschlagen: %s", _rex)

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

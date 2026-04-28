"""Audio actions: import, beat analysis, stem separation,
key detection, LUFS, classification, spectral analysis, structure detection.
"""

import logging

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)


def _get_task_manager():
    """Gibt den TaskManager zurueck ohne QApplication-Kopplung."""
    from services.task_manager import GlobalTaskManager
    return GlobalTaskManager.instance()


def _get_audio_track_file_path(audio_track_id: int) -> str | None:
    """Holt file_path eines AudioTracks aus der DB (leichtgewichtiger Lookup)."""
    from sqlalchemy.orm import Session as SASession
    from database import engine, AudioTrack
    with SASession(engine) as session:
        track = session.get(AudioTrack, audio_track_id)
        return track.file_path if track else None


def _get_audio_track_bpm(audio_track_id: int) -> float | None:
    """Holt BPM eines AudioTracks aus der DB."""
    from sqlalchemy.orm import Session as SASession
    from database import engine, AudioTrack
    with SASession(engine) as session:
        track = session.get(AudioTrack, audio_track_id)
        return track.bpm if track else None


@action_registry.register(
    name="analyze_audio",
    description="Analysiert eine Audiodatei: BPM, Beat-Positionen und Energiekurve.",
    param_schema={
        "type": "object",
        "properties": {
            "track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["track_id"]
    }
)
def analyze_audio(track_id: int) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut AnalysisWorker."""
    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "analyze_audio", {"track_id": track_id}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "analyze_audio",
        "track_id": track_id,
        "message": f"Audio-Analyse fuer Track #{track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="separate_stems",
    description=(
        "Trennt Audiotracks in Stems (Vocals, Drums, Bass, Other) mittels KI. "
        "Nutze diese Aktion wenn der User nach 'Stems', 'Stem-Files', 'Stem-Separation', "
        "'Spuren trennen' oder 'Vocals extrahieren' fragt. "
        "Wenn track_id weggelassen wird, werden ALLE importierten Audiotracks automatisch verarbeitet."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "track_id": {
                "type": "integer",
                "description": "ID des AudioTracks. OPTIONAL: Wenn leer, werden ALLE Audiotracks verarbeitet."
            }
        },
        "required": []
    }
)
def separate_stems(track_id: int | None = None) -> dict:
    """Command Pattern: Emittiert nur Signal → Main-Thread baut Worker.

    Batch-Modus (track_id=None): Emittiert je einen Command pro Track.
    """
    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    if track_id is None:
        # Batch: Fuer jeden Audio-Track einen separaten Command emittieren
        from services.ingest_service import get_all_audio
        audios = get_all_audio()
        if not audios:
            return {"error": "Keine Audiotracks im Projekt gefunden."}
        for audio in audios:
            tm.agent_command_signal.emit(
                "separate_stems", {"track_id": audio["id"]}
            )
        return {
            "status": "Tasks in Warteschlange",
            "action": "separate_stems",
            "batch": True,
            "total": len(audios),
            "message": f"Stem-Separation fuer {len(audios)} Tracks gestartet. Fortschritt im TaskManagerDock.",
        }

    # Einzel-Modus
    tm.agent_command_signal.emit("separate_stems", {"track_id": track_id})
    return {
        "status": "Task in Warteschlange",
        "action": "separate_stems",
        "track_id": track_id,
        "message": f"Stem-Separation fuer Track #{track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="detect_key",
    description=(
        "Erkennt die musikalische Tonart eines Audio-Tracks (Key + Camelot-Notation). "
        "Nutze diese Aktion wenn der User nach 'Key', 'Tonart', 'Camelot' oder 'harmonisch' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["audio_track_id"]
    }
)
def detect_key_action(audio_track_id: int) -> dict:
    """Command Pattern: Emittiert Signal -> Main-Thread baut KeyDetectionWorker."""
    file_path = _get_audio_track_file_path(audio_track_id)
    if not file_path:
        return {"error": f"AudioTrack {audio_track_id} nicht gefunden."}

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfuegbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "detect_key", {"audio_track_id": audio_track_id, "file_path": file_path}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "detect_key",
        "audio_track_id": audio_track_id,
        "message": f"Key-Erkennung fuer Track #{audio_track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="analyze_lufs",
    description=(
        "Misst die Lautstaerke eines Audio-Tracks nach EBU R128 (LUFS). "
        "Nutze diese Aktion wenn der User nach 'Lautstaerke', 'LUFS', 'Loudness' oder 'Pegel' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["audio_track_id"]
    }
)
def analyze_lufs_action(audio_track_id: int) -> dict:
    """Command Pattern: Emittiert Signal -> Main-Thread baut LUFSAnalysisWorker."""
    file_path = _get_audio_track_file_path(audio_track_id)
    if not file_path:
        return {"error": f"AudioTrack {audio_track_id} nicht gefunden."}

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfuegbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "analyze_lufs", {"audio_track_id": audio_track_id, "file_path": file_path}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "analyze_lufs",
        "audio_track_id": audio_track_id,
        "message": f"LUFS-Analyse fuer Track #{audio_track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="classify_audio",
    description=(
        "Klassifiziert einen Audio-Track nach Mood, Genre und erkennt DJ-Mixes. "
        "Nutze diese Aktion wenn der User nach 'Genre', 'Mood', 'Stimmung', 'Musikstil' oder 'DJ-Mix' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["audio_track_id"]
    }
)
def classify_audio_action(audio_track_id: int) -> dict:
    """Command Pattern: Emittiert Signal -> Main-Thread baut AudioClassifyWorker."""
    file_path = _get_audio_track_file_path(audio_track_id)
    if not file_path:
        return {"error": f"AudioTrack {audio_track_id} nicht gefunden."}

    bpm = _get_audio_track_bpm(audio_track_id)

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfuegbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "classify_audio", {"audio_track_id": audio_track_id, "file_path": file_path, "bpm": bpm}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "classify_audio",
        "audio_track_id": audio_track_id,
        "message": f"Audio-Klassifikation fuer Track #{audio_track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="analyze_spectral",
    description=(
        "Analysiert die Frequenzverteilung eines Audio-Tracks (8-Band Spektral-Analyse). "
        "Nutze diese Aktion wenn der User nach 'Frequenzen', 'Spektrum', 'Bass', 'Hoehen' oder 'EQ' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["audio_track_id"]
    }
)
def analyze_spectral_action(audio_track_id: int) -> dict:
    """Command Pattern: Emittiert Signal -> Main-Thread baut SpectralAnalysisWorker."""
    file_path = _get_audio_track_file_path(audio_track_id)
    if not file_path:
        return {"error": f"AudioTrack {audio_track_id} nicht gefunden."}

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfuegbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "analyze_spectral", {"audio_track_id": audio_track_id, "file_path": file_path}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "analyze_spectral",
        "audio_track_id": audio_track_id,
        "message": f"Spektral-Analyse fuer Track #{audio_track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="detect_structure",
    description=(
        "Erkennt die Song-Struktur eines Audio-Tracks (Intro, Drop, Breakdown, Outro, ...). "
        "Nutze diese Aktion wenn der User nach 'Struktur', 'Song-Teile', 'Intro', 'Drop', "
        "'Breakdown' oder 'Segmente' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["audio_track_id"]
    }
)
def detect_structure_action(audio_track_id: int) -> dict:
    """Command Pattern: Emittiert Signal -> Main-Thread baut StructureDetectionWorker."""
    file_path = _get_audio_track_file_path(audio_track_id)
    if not file_path:
        return {"error": f"AudioTrack {audio_track_id} nicht gefunden."}

    bpm = _get_audio_track_bpm(audio_track_id)

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfuegbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "detect_structure", {
            "audio_track_id": audio_track_id,
            "file_path": file_path,
            "bpm": bpm,
        }
    )
    return {
        "status": "Task in Warteschlange",
        "action": "detect_structure",
        "audio_track_id": audio_track_id,
        "message": f"Struktur-Erkennung fuer Track #{audio_track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


# ---------------------------------------------------------------------------
# B-244: describe_audio_track — DB-Read, generiert Text-Beschreibung des Tracks
# ---------------------------------------------------------------------------

@action_registry.register(
    name="describe_audio_track",
    description=(
        "Beschreibt einen Audio-Track als lesbaren Text — BPM, Key, Genre, Mood, "
        "Stems-Status, LUFS, Drop/Breakdown-Timeline. Liest BEREITS analysierte "
        "Daten aus der DB (kein neuer Pipeline-Lauf). Ideal fuer DJ-Mix-Uebersichten "
        "und LLM-Kontext. "
        "Nutze diese Aktion wenn der User nach 'Beschreibe Track', 'Was ist auf "
        "Track X', 'Track-Info', 'Set-Uebersicht', 'Wann sind die Drops?', "
        "'Wie ist der Track aufgebaut?' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "track_id": {
                "type": "integer",
                "description": "ID des AudioTracks. OPTIONAL: Wenn leer, wird der erste Track des Projekts genommen."
            }
        },
        "required": []
    }
)
def describe_audio_track(track_id: int | None = None) -> dict:
    """Liest einen analysierten AudioTrack aus der DB und liefert Text-Beschreibung.

    Schreibt nichts in die DB, triggert keine Pipeline. Reiner Read.
    Keine Daten in der DB -> Hinweis welche Pipeline noch laufen muss.
    """
    try:
        from sqlalchemy.orm import Session as SASession
        from database import engine, AudioTrack, Beatgrid, StructureSegment

        with SASession(engine) as session:
            if track_id:
                track = session.get(AudioTrack, track_id)
            else:
                track = session.query(AudioTrack).first()

            if not track:
                return {
                    "status": "error",
                    "action": "describe_audio_track",
                    "message": (
                        "Kein AudioTrack gefunden. Bitte zuerst Audio importieren."
                        if track_id is None
                        else f"AudioTrack {track_id} nicht in DB."
                    ),
                }

            beatgrid = session.query(Beatgrid).filter_by(audio_track_id=track.id).first()
            segments = session.query(StructureSegment).filter_by(
                audio_track_id=track.id
            ).order_by(StructureSegment.start_time).all()

            # Felder waehrend Session offen lesen
            t_id = track.id
            t_title = track.title or "(unbenannt)"
            t_dur = track.duration
            t_bpm = track.bpm
            t_key = track.key
            t_key_conf = track.key_confidence
            t_genre = track.genre
            t_sub_genre = track.sub_genre
            t_mood = track.mood
            t_lufs = track.lufs
            t_is_dj = track.is_dj_mix
            t_harm_tension = track.harmonic_tension

            t_stems = {
                "vocals": bool(track.stem_vocals_path),
                "drums": bool(track.stem_drums_path),
                "bass": bool(track.stem_bass_path),
                "other": bool(track.stem_other_path),
            }

            beat_count = len(beatgrid.beat_positions or []) if beatgrid else 0

            seg_data = [
                {"start": s.start_time, "end": s.end_time, "label": s.label or "?"}
                for s in segments
            ]

        # Format
        def _fmt_time(secs: float) -> str:
            if secs is None:
                return "?"
            mins = int(secs // 60)
            sec = int(secs % 60)
            hours = mins // 60
            mins = mins % 60
            return f"{hours:d}h{mins:02d}m{sec:02d}s" if hours else f"{mins:02d}m{sec:02d}s"

        lines: list[str] = []
        title_line = f"Track #{t_id}: {t_title}"
        if t_dur:
            title_line += f" ({_fmt_time(t_dur)})"
        lines.append(title_line)
        lines.append("=" * len(title_line))

        # Header-Block
        if t_bpm:
            lines.append(f"BPM: {t_bpm:.1f}")
        else:
            lines.append("BPM: noch nicht analysiert (`analyze_audio` ausfuehren)")
        if t_key:
            key_str = f"Key: {t_key}"
            if t_key_conf:
                key_str += f" (Confidence: {t_key_conf:.2f})"
            lines.append(key_str)
        if t_genre:
            genre_str = t_genre
            if t_sub_genre:
                genre_str += f" / {t_sub_genre}"
            lines.append(f"Genre: {genre_str}")
        if t_mood:
            lines.append(f"Mood: {t_mood}")
        if t_lufs is not None:
            lines.append(f"LUFS: {t_lufs:.1f} dB")
        if t_harm_tension is not None:
            lines.append(f"Harmonic Tension: {t_harm_tension:.2f}")
        if t_is_dj is not None:
            lines.append(f"DJ-Mix erkannt: {'ja' if t_is_dj else 'nein'}")

        # Stems
        stems_done = sum(1 for v in t_stems.values() if v)
        if stems_done == 4:
            lines.append("Stems: alle 4 separiert (vocals, drums, bass, other)")
        elif stems_done > 0:
            done_list = [k for k, v in t_stems.items() if v]
            lines.append(f"Stems: {stems_done}/4 ({', '.join(done_list)})")
        else:
            lines.append("Stems: noch nicht separiert (`separate_stems` ausfuehren)")

        if beat_count > 0:
            lines.append(f"Beat-Grid: {beat_count} Beats erkannt")

        # Structure-Timeline
        if seg_data:
            drops = [s for s in seg_data if "drop" in s["label"].lower()]
            breakdowns = [s for s in seg_data if "breakdown" in s["label"].lower()]
            buildups = [s for s in seg_data if "buildup" in s["label"].lower()]

            stats: list[str] = []
            if drops:
                stats.append(f"{len(drops)} Drops")
            if breakdowns:
                stats.append(f"{len(breakdowns)} Breakdowns")
            if buildups:
                stats.append(f"{len(buildups)} Buildups")

            if stats:
                lines.append("")
                lines.append(f"Struktur: {', '.join(stats)}")

            lines.append("")
            lines.append("Timeline:")
            max_show = 30
            for s in seg_data[:max_show]:
                lines.append(f"  [{_fmt_time(s['start'])}-{_fmt_time(s['end'])}] {s['label']}")
            if len(seg_data) > max_show:
                lines.append(f"  ... + {len(seg_data) - max_show} weitere Segmente")
        else:
            lines.append("")
            lines.append("Struktur: noch nicht analysiert (`detect_structure` ausfuehren)")

        message = "\n".join(lines)

        return {
            "status": "ok",
            "action": "describe_audio_track",
            "track_id": t_id,
            "title": t_title,
            "bpm": t_bpm,
            "key": t_key,
            "genre": t_genre,
            "sub_genre": t_sub_genre,
            "mood": t_mood,
            "duration": t_dur,
            "lufs": t_lufs,
            "is_dj_mix": t_is_dj,
            "stems_done": stems_done,
            "beat_count": beat_count,
            "segment_count": len(seg_data),
            "drop_count": len([s for s in seg_data if "drop" in s["label"].lower()]),
            "breakdown_count": len([s for s in seg_data if "breakdown" in s["label"].lower()]),
            "message": message,
        }
    except Exception as exc:  # broad catch intentional — SQLAlchemy + format errors
        _logger.error("describe_audio_track fehlgeschlagen: %s", exc, exc_info=True)
        return {
            "status": "error",
            "action": "describe_audio_track",
            "message": f"Fehler: {exc}",
        }

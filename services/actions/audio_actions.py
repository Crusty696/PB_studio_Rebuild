"""Audio actions: import, beat analysis, stem separation, transcription,
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
    name="transcribe_audio",
    description="Transkribiert gesprochenen Text aus einer Audio/Video-Datei mit Zeitstempeln (faster-whisper).",
    param_schema={
        "type": "object",
        "properties": {
            "track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            },
            "file_path": {
                "type": "string",
                "description": "Alternativ: Direkter Pfad zur Audio/Video-Datei."
            }
        },
    }
)
def transcribe_audio(track_id: int | None = None, file_path: str | None = None) -> dict:
    """Transkription via faster-whisper — startet als Background-Worker."""
    if track_id is None and file_path is None:
        return {"status": "error", "message": "Weder track_id noch file_path angegeben."}

    # Wenn nur file_path gegeben, versuche track_id aus DB zu finden
    if track_id is None and file_path:
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            track = session.query(AudioTrack).filter_by(file_path=file_path).first()
            if track:
                track_id = track.id
            else:
                return {"status": "error", "message": f"Audio-Datei nicht in DB: {file_path}"}

    label = f"Track #{track_id}"
    tm = _get_task_manager()

    from workers.audio import TranscriptionWorker
    worker = TranscriptionWorker(track_id)
    task = tm.start_task(
        name=f"Transkription: {label}",
        worker=worker,
        description="faster-whisper Transkription",
    )

    task_id = task.task_id if hasattr(task, 'task_id') else str(task)
    return {
        "status": "Task gestartet",
        "action": "transcribe_audio",
        "task_id": task_id,
        "message": f"Transkription fuer {label} laeuft im Hintergrund.",
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

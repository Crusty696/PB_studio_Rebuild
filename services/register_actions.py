"""
Registriert die bestehenden PB Studio Funktionen im ActionRegistry.

Dieses Modul wird beim App-Start aufgerufen. Neue Funktionen einfach
hier mit @action_registry.register(...) hinzufügen.

Alle schweren KI-Aktionen registrieren sich beim globalen TaskManager,
damit Fortschrittsbalken im TaskManagerDock erscheinen.
"""

import logging

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)


def _get_task_manager():
    """Holt den TaskManager von der QApplication — Thread-safe, kein Ghost."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    return getattr(app, "task_manager", None) if app else None


# --- Audio-Aktionen ---

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
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    app.task_manager.agent_command_signal.emit(
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
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}
    tm_inst = app.task_manager

    if track_id is None:
        # Batch: Fuer jeden Audio-Track einen separaten Command emittieren
        from services.ingest_service import get_all_audio
        audios = get_all_audio()
        if not audios:
            return {"error": "Keine Audiotracks im Projekt gefunden."}
        for audio in audios:
            tm_inst.agent_command_signal.emit(
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
    tm_inst.agent_command_signal.emit("separate_stems", {"track_id": track_id})
    return {
        "status": "Task in Warteschlange",
        "action": "separate_stems",
        "track_id": track_id,
        "message": f"Stem-Separation fuer Track #{track_id} gestartet. Fortschritt im TaskManagerDock.",
    }


# --- Video-Aktionen ---

@action_registry.register(
    name="analyze_video",
    description="Analysiert einen Videoclip: Szenen, Dauer, Auflösung.",
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank."
            }
        },
        "required": ["clip_id"]
    }
)
def analyze_video(clip_id: int) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut VideoAnalysisWorker."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    app.task_manager.agent_command_signal.emit(
        "analyze_video", {"clip_id": clip_id}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "analyze_video",
        "clip_id": clip_id,
        "message": f"Video-Analyse fuer Clip #{clip_id} gestartet. Fortschritt im TaskManagerDock.",
    }


# --- Pacing-Aktionen ---

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
    from PySide6.QtWidgets import QApplication

    video_ids = [v["id"] for v in get_all_video()]
    if not video_ids:
        return {"timeline": [], "message": "Keine Videos im Projekt gefunden."}

    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
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

    app.task_manager.agent_command_signal.emit("auto_edit", signal_params)
    return {
        "status": "Task in Warteschlange",
        "action": "auto_edit",
        "audio_track_id": audio_track_id,
        "video_count": len(video_ids),
        "message": f"Auto-Edit mit {len(video_ids)} Videos gestartet. Fortschritt im TaskManagerDock.",
    }


# --- Ingest-Aktionen ---

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


# --- Export-Aktionen ---

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
    from PySide6.QtWidgets import QApplication

    output_name = output_path or "output.mp4"
    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    app.task_manager.agent_command_signal.emit(
        "export_timeline", {"project_id": project_id, "output_name": output_name}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "export_timeline",
        "output_name": output_name,
        "message": f"Timeline-Export '{output_name}' gestartet. Fortschritt im TaskManagerDock.",
    }


# --- KI-Agenten-Aktionen (Swarm) ---

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
    """Transkription via faster-whisper (noch nicht als Worker implementiert).

    Hinweis: TranscriptionWorker existiert noch nicht in workers/.
    Gibt eine klare Fehlermeldung zurueck statt einen stillen Drop via
    agent_command_signal (kein registrierter Worker wuerde KeyError ausloesen).
    """
    label = f"Track #{track_id}" if track_id else (file_path or "audio")
    _logger.warning(
        "transcribe_audio aufgerufen fuer %s, aber TranscriptionWorker "
        "ist noch nicht in workers/ implementiert.", label
    )
    return {
        "status": "not_implemented",
        "action": "transcribe_audio",
        "message": (
            f"Transkription fuer {label}: TranscriptionWorker noch nicht "
            "implementiert. Bitte zuerst workers/audio.py um eine "
            "TranscriptionWorker-Klasse ergaenzen und in workers/registry.py "
            "registrieren."
        ),
    }


@action_registry.register(
    name="analyze_video_content",
    description="Analysiert den visuellen Inhalt eines Videos mit KI (Moondream2). Extrahiert Frames und beschreibt Szenen.",
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank."
            },
            "file_path": {
                "type": "string",
                "description": "Alternativ: Direkter Pfad zur Videodatei."
            },
            "interval_sec": {
                "type": "number",
                "description": "Intervall in Sekunden zwischen Frame-Extraktionen (default: 5)."
            },
            "max_frames": {
                "type": "integer",
                "description": "Maximale Anzahl zu analysierender Frames (default: 10)."
            }
        },
    }
)
def analyze_video_content(
    clip_id: int | None = None,
    file_path: str | None = None,
    interval_sec: float = 5.0,
    max_frames: int = 10,
) -> dict:
    """Vision-Analyse via Moondream2 (noch nicht als Worker implementiert).

    Hinweis: VisionAnalysisWorker existiert noch nicht in workers/.
    Gibt eine klare Fehlermeldung zurueck statt einen stillen Drop via
    agent_command_signal (kein registrierter Worker wuerde KeyError ausloesen).
    """
    label = f"Clip #{clip_id}" if clip_id else (file_path or "video")
    _logger.warning(
        "analyze_video_content aufgerufen fuer %s, aber VisionAnalysisWorker "
        "ist noch nicht in workers/ implementiert.", label
    )
    return {
        "status": "not_implemented",
        "action": "analyze_video_content",
        "message": (
            f"Vision-Analyse fuer {label}: VisionAnalysisWorker noch nicht "
            "implementiert. Bitte zuerst workers/video.py um eine "
            "VisionAnalysisWorker-Klasse (Moondream2) ergaenzen und in "
            "workers/registry.py registrieren."
        ),
    }


# --- Modulare Video-Pipeline-Tools (Einzel-Schritte) ---

@action_registry.register(
    name="create_proxy",
    description=(
        "Erstellt Proxy-Videos (reduzierte Auflösung) für schnellere Bearbeitung und Analyse. "
        "Nutze diese Aktion wenn der User nach 'Proxy', 'Proxy-Daten', 'Proxy-Videos', "
        "'Vorschau-Videos' oder 'niedrige Auflösung' fragt. "
        "Wenn clip_id weggelassen wird, werden ALLE importierten Videos automatisch verarbeitet."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips. OPTIONAL: Wenn leer, werden ALLE Videos verarbeitet."
            },
            "target_height": {
                "type": "integer",
                "description": "Ziel-Höhe in Pixel (default: 480)."
            }
        },
        "required": []
    }
)
def create_proxy_action(clip_id: int | None = None, target_height: int = 480) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut ProxyCreationWorker.

    DB-Lookup (leichtgewichtig) bleibt hier um video_path zu ermitteln.
    """
    from sqlalchemy.orm import Session as SASession
    from database import engine, VideoClip
    from services.ingest_service import get_all_video
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}
    tm_inst = app.task_manager

    # Batch-Modus
    if clip_id is None:
        videos = get_all_video()
        if not videos:
            return {"error": "Keine Videoclips im Projekt gefunden."}
        # Alle Clips in EINER Session laden (statt pro Video eine neue Session öffnen).
        # Verhindert N+1-Session-Overhead bei großen Bibliotheken.
        video_ids = [v["id"] for v in videos]
        with SASession(engine) as session:
            clip_paths = {
                c.id: c.file_path
                for c in session.query(VideoClip).filter(VideoClip.id.in_(video_ids)).all()
                if c.file_path
            }
        queued = 0
        for video in videos:
            fp = clip_paths.get(video["id"])
            if fp:
                tm_inst.agent_command_signal.emit(
                    "create_proxy",
                    {"clip_id": video["id"], "video_path": fp},
                )
                queued += 1
        return {
            "status": "Tasks in Warteschlange",
            "action": "create_proxy",
            "batch": True,
            "total": queued,
            "message": f"Proxy-Erstellung fuer {queued} Videos gestartet. Fortschritt im TaskManagerDock.",
        }

    # Einzel-Modus: DB-Lookup fuer video_path
    with SASession(engine) as session:
        clip = session.get(VideoClip, clip_id)
        if clip is None:
            return {"error": f"VideoClip {clip_id} nicht gefunden."}
        video_path = clip.file_path

    tm_inst.agent_command_signal.emit(
        "create_proxy", {"clip_id": clip_id, "video_path": video_path}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "create_proxy",
        "clip_id": clip_id,
        "message": f"Proxy-Erstellung fuer Clip #{clip_id} gestartet. Fortschritt im TaskManagerDock.",
    }


@action_registry.register(
    name="detect_scenes",
    description="Erkennt Szenen-Grenzen in einem Video mittels PySceneDetect. Gibt Anzahl und Zeitstempel zurück.",
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank."
            },
            "use_proxy": {
                "type": "boolean",
                "description": "Proxy statt Original nutzen (default: true, schneller)."
            },
            "threshold": {
                "type": "number",
                "description": "Empfindlichkeit (default: 27.0, niedriger = mehr Szenen)."
            }
        },
        "required": ["clip_id"]
    }
)
def detect_scenes_action(clip_id: int, use_proxy: bool = True, threshold: float = 27.0) -> dict:
    """Erkennt Szenen in einem Video (nutzt Proxy wenn verfügbar und gewünscht)."""
    from sqlalchemy.orm import Session as SASession
    from database import engine, VideoClip
    from services.video_analysis_service import detect_scenes, store_scenes_in_db

    tm = _get_task_manager()
    task = tm.create_task(f"Szenen #{clip_id}", "PySceneDetect") if tm else None

    try:
        with SASession(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                if task and tm:
                    tm.finish_task(task.task_id, "error", "Clip nicht gefunden")
                return {"error": f"VideoClip {clip_id} nicht gefunden."}
            video_path = clip.proxy_path if (use_proxy and clip.proxy_path) else clip.file_path

        if task and tm:
            tm.update_task(task.task_id, 20, message="Szenen-Erkennung...")
        scenes = detect_scenes(video_path, threshold=threshold)
        store_scenes_in_db(clip_id, scenes)

        if task and tm:
            tm.finish_task(task.task_id, "finished", f"{len(scenes)} Szenen")
        return {
            "clip_id": clip_id,
            "source": "proxy" if use_proxy else "original",
            "scene_count": len(scenes),
            "scenes": [{"index": s.index, "start": s.start_time, "end": s.end_time} for s in scenes],
            "message": f"{len(scenes)} Szenen erkannt.",
        }
    except Exception as e:
        if task and tm:
            tm.finish_task(task.task_id, "error", str(e))
        raise


@action_registry.register(
    name="analyze_motion",
    description="Berechnet RAFT Optical Flow Motion-Scores für erkannte Szenen (GPU-beschleunigt).",
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank."
            },
            "use_proxy": {
                "type": "boolean",
                "description": "Proxy statt Original nutzen (default: true)."
            }
        },
        "required": ["clip_id"]
    }
)
def analyze_motion_action(clip_id: int, use_proxy: bool = True) -> dict:
    """Berechnet Motion-Scores via RAFT für alle Szenen eines Videos."""
    from sqlalchemy.orm import Session as SASession
    from database import engine, VideoClip, Scene
    from services.video_analysis_service import compute_motion_scores, SceneInfo, store_scenes_in_db

    tm = _get_task_manager()
    task = tm.create_task(f"Motion #{clip_id}", "RAFT Optical Flow") if tm else None

    try:
        with SASession(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                if task and tm:
                    tm.finish_task(task.task_id, "error", "Clip nicht gefunden")
                return {"error": f"VideoClip {clip_id} nicht gefunden."}
            video_path = clip.proxy_path if (use_proxy and clip.proxy_path) else clip.file_path

            db_scenes = session.query(Scene).filter_by(video_clip_id=clip_id).order_by(Scene.start_time).all()
            if not db_scenes:
                if task and tm:
                    tm.finish_task(task.task_id, "error", "Keine Szenen")
                return {"error": f"Keine Szenen für VideoClip {clip_id}. Führe zuerst 'detect_scenes' aus."}

            scenes = [
                SceneInfo(index=i, start_time=s.start_time, end_time=s.end_time)
                for i, s in enumerate(db_scenes)
            ]

        if task and tm:
            tm.update_task(task.task_id, 20, message="RAFT Motion berechnen...")
        scenes = compute_motion_scores(video_path, scenes)
        store_scenes_in_db(clip_id, scenes)

        if task and tm:
            tm.finish_task(task.task_id, "finished",
                           f"{len(scenes)} Szenen analysiert")
        return {
            "clip_id": clip_id,
            "source": "proxy" if use_proxy else "original",
            "scene_count": len(scenes),
            "motion_scores": [{"index": s.index, "motion": s.motion_score} for s in scenes],
            "avg_motion": round(sum(s.motion_score for s in scenes) / max(len(scenes), 1), 4),
            "message": f"Motion-Analyse für {len(scenes)} Szenen abgeschlossen.",
        }
    except Exception as e:
        if task and tm:
            tm.finish_task(task.task_id, "error", str(e))
        raise


@action_registry.register(
    name="generate_embeddings",
    description="Generiert SigLIP-Embeddings für Keyframes und speichert sie in LanceDB (für semantische Suche).",
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank."
            },
            "use_proxy": {
                "type": "boolean",
                "description": "Proxy statt Original für Keyframe-Extraktion nutzen (default: true)."
            }
        },
        "required": ["clip_id"]
    }
)
def generate_embeddings_action(clip_id: int, use_proxy: bool = True) -> dict:
    """Extrahiert Keyframes, generiert SigLIP-Embeddings und speichert in LanceDB."""
    from sqlalchemy.orm import Session as SASession
    from database import engine, VideoClip, Scene
    from services.video_analysis_service import (
        SceneInfo, extract_keyframes, generate_embeddings, store_embeddings,
    )

    tm = _get_task_manager()
    task = tm.create_task(f"Embeddings #{clip_id}", "SigLIP + LanceDB") if tm else None

    try:
        with SASession(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                if task and tm:
                    tm.finish_task(task.task_id, "error", "Clip nicht gefunden")
                return {"error": f"VideoClip {clip_id} nicht gefunden."}
            video_path = clip.proxy_path if (use_proxy and clip.proxy_path) else clip.file_path

            db_scenes = session.query(Scene).filter_by(video_clip_id=clip_id).order_by(Scene.start_time).all()
            if not db_scenes:
                if task and tm:
                    tm.finish_task(task.task_id, "error", "Keine Szenen")
                return {"error": f"Keine Szenen für VideoClip {clip_id}. Führe zuerst 'detect_scenes' aus."}

            scenes = [
                SceneInfo(index=i, start_time=s.start_time, end_time=s.end_time, motion_score=s.energy or 0.0)
                for i, s in enumerate(db_scenes)
            ]

        if task and tm:
            tm.update_task(task.task_id, 10, message="Keyframes extrahieren...")
        scenes = extract_keyframes(video_path, scenes)
        if task and tm:
            tm.update_task(task.task_id, 50, message="SigLIP Embeddings...")
        scenes = generate_embeddings(scenes)
        if task and tm:
            tm.update_task(task.task_id, 80, message="In LanceDB speichern...")
        stored = store_embeddings(video_path, scenes, clip_id)

        if task and tm:
            tm.finish_task(task.task_id, "finished", f"{stored} Embeddings")
        return {
            "clip_id": clip_id,
            "source": "proxy" if use_proxy else "original",
            "keyframes_extracted": sum(1 for s in scenes if s.keyframe_path),
            "embeddings_stored": stored,
            "message": f"{stored} SigLIP-Embeddings in LanceDB gespeichert.",
        }
    except Exception as e:
        if task and tm:
            tm.finish_task(task.task_id, "error", str(e))
        raise


@action_registry.register(
    name="search_video",
    description="Semantische Video-Suche: Findet Szenen die zu einer Text-Beschreibung passen (SigLIP + LanceDB).",
    param_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Suchtext, z.B. 'Sonnenuntergang am Strand' oder 'tanzende Menschen'."
            },
            "top_k": {
                "type": "integer",
                "description": "Anzahl Ergebnisse (default: 5)."
            }
        },
        "required": ["query"]
    }
)
def search_video_action(query: str, top_k: int = 5) -> dict:
    """Sucht Videos semantisch per Text-Beschreibung."""
    from services.video_analysis_service import search_videos_by_text
    results = search_videos_by_text(query, top_k=top_k)
    return {
        "query": query,
        "result_count": len(results),
        "results": results,
        "message": f"{len(results)} Treffer für '{query}'.",
    }


# --- Info-Aktionen ---

@action_registry.register(
    name="list_actions",
    description="Zeigt alle verfügbaren Aktionen an, die die KI ausführen kann.",
    param_schema={"type": "object", "properties": {}}
)
def list_actions() -> list[str]:
    return action_registry.list_actions()


# --- Phase 3: Keyframe-String Generator ---

@action_registry.register(
    name="generate_keyframe_strings",
    description=(
        "Generiert lesbaren Text-String aller erkannten Video-Szenen mit "
        "RAFT-Motion-Werten. Zeigt Ruhig/Moderat/Action/Extrem Kategorien. "
        "Nutze dies wenn der User nach 'Szenen', 'Keyframes', 'Motion-Analyse' "
        "oder 'Szenen-Uebersicht' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "video_id": {
                "type": "integer",
                "description": "ID eines einzelnen Videos. OPTIONAL: Wenn leer, alle Videos."
            }
        },
        "required": []
    }
)
def generate_keyframe_strings_action(video_id: int | None = None) -> str:
    from services.pacing_service import (
        generate_keyframe_string,
        generate_keyframe_strings_for_project,
    )
    if video_id is not None:
        return generate_keyframe_string(video_id)
    return generate_keyframe_strings_for_project()


# --- Test-Aktion: Dummy-Ladebalken ---

@action_registry.register(
    name="teste_ladebalken",
    description=(
        "Startet einen 10-Sekunden-Dummy-Task ueber die zentrale Task-Engine. "
        "Dient zum Testen des TaskManagerDock UI (Ladebalken). "
        "Nutze diese Aktion wenn der User 'teste ladebalken', 'test progress' "
        "oder 'ladebalken testen' schreibt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "steps": {
                "type": "integer",
                "description": "Anzahl Schritte (default: 10)."
            },
            "interval_ms": {
                "type": "integer",
                "description": "Millisekunden pro Schritt (default: 1000)."
            }
        },
        "required": []
    }
)
def teste_ladebalken(steps: int = 10, interval_ms: int = 1000) -> dict:
    """Command Pattern: Emittiert Signal → Main-Thread baut DummyProgressWorker."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or not hasattr(app, 'task_manager'):
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    app.task_manager.agent_command_signal.emit(
        "teste_ladebalken", {"steps": steps, "interval_ms": interval_ms}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "teste_ladebalken",
        "steps": steps,
        "interval_ms": interval_ms,
        "message": f"Dummy-Task gestartet: {steps} Schritte a {interval_ms}ms. Beobachte das TaskManagerDock!",
    }

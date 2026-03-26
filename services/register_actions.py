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
            }
        },
        "required": ["audio_track_id"]
    }
)
def auto_edit(audio_track_id: int) -> dict:
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

    app.task_manager.agent_command_signal.emit(
        "auto_edit", {"audio_track_id": audio_track_id, "video_ids": video_ids}
    )
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
    """Transkribiert Audio mit faster-whisper über den ModelManager."""
    import os
    from services.model_manager import ModelManager

    tm = _get_task_manager()
    label = f"#{track_id}" if track_id else os.path.basename(file_path or "audio")
    task = tm.create_task(f"Transkription {label}", "faster-whisper") if tm else None

    # Dateipfad ermitteln
    if file_path is None and track_id is not None:
        from sqlalchemy.orm import Session as SASession
        from database import engine, AudioTrack
        with SASession(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                if task and tm:
                    tm.finish_task(task.task_id, "error", "Track nicht gefunden")
                return {"error": f"AudioTrack {track_id} nicht gefunden."}
            file_path = track.file_path

    if not file_path or not os.path.exists(file_path):
        if task and tm:
            tm.finish_task(task.task_id, "error", "Datei nicht gefunden")
        return {"error": f"Datei nicht gefunden: {file_path}"}

    # Prüfe ob die Datei eine Audio-Spur hat (Videos ohne Audio abfangen)
    import subprocess
    try:
        probe = subprocess.run(
            ["ffprobe", "-i", file_path, "-show_streams", "-select_streams", "a",
             "-loglevel", "error", "-of", "csv=p=0"],
            capture_output=True, text=True, timeout=10,
        )
        if not probe.stdout.strip():
            return {
                "error": f"Keine Audio-Spur in Datei gefunden: {os.path.basename(file_path)}",
                "full_text": "",
                "segments": [],
                "segment_count": 0,
            }
    except Exception:
        pass  # ffprobe nicht verfügbar → trotzdem versuchen

    # ModelManager: Whisper laden (entlädt automatisch andere Modelle)
    mm = ModelManager()
    # "tiny" für schnelle Tests, "base" oder "small" für bessere Qualität
    whisper_size = os.environ.get("PB_WHISPER_SIZE", "large-v3")
    if task and tm:
        tm.update_task(task.task_id, 10, message="Whisper-Modell laden...")
    whisper_model = mm.load_whisper(whisper_size)

    # Transkription
    if task and tm:
        tm.update_task(task.task_id, 30, message="Transkribiere...")
    try:
        segments, info = whisper_model.transcribe(
            file_path,
            beam_size=5,
            language=None,  # Auto-detect
            vad_filter=True,
        )

        transcript_segments = []
        full_text_parts = []
        for segment in segments:
            seg_data = {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
            }
            transcript_segments.append(seg_data)
            full_text_parts.append(segment.text.strip())

        if task and tm:
            tm.finish_task(task.task_id, "finished",
                           f"{len(transcript_segments)} Segmente")
        return {
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
            "segments": transcript_segments,
            "full_text": " ".join(full_text_parts),
            "segment_count": len(transcript_segments),
        }
    except Exception as e:
        if task and tm:
            tm.finish_task(task.task_id, "error", str(e))
        raise


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
    """Analysiert Video-Inhalt visuell mit Moondream2.

    Optimiert für CPU: Bilder werden auf 256px skaliert,
    Inferenz läuft mit torch.no_grad() und kurzen Prompts.
    """
    import os
    import cv2
    import torch
    from PIL import Image
    from services.model_manager import ModelManager

    tm = _get_task_manager()
    label = f"#{clip_id}" if clip_id else os.path.basename(file_path or "video")
    task = tm.create_task(f"Vision {label}", "Moondream2 Video-Analyse") if tm else None

    # Dateipfad ermitteln
    if file_path is None and clip_id is not None:
        from sqlalchemy.orm import Session as SASession
        from database import engine, VideoClip
        with SASession(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                return {"error": f"VideoClip {clip_id} nicht gefunden."}
            file_path = clip.file_path

    if not file_path or not os.path.exists(file_path):
        if task and tm:
            tm.finish_task(task.task_id, "error", "Datei nicht gefunden")
        return {"error": f"Datei nicht gefunden: {file_path}"}

    if task and tm:
        tm.update_task(task.task_id, 10, message="Frames extrahieren...")

    # Frames extrahieren mit OpenCV
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return {"error": f"Video konnte nicht geöffnet werden: {file_path}"}

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        frame_interval = max(1, int(fps * interval_sec))  # Guard: nie 0

        frames_to_analyze = []
        timestamps = []
        frame_idx = 0

        while len(frames_to_analyze) < max_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            # BGR → RGB → PIL, skaliert auf 256px für schnelle CPU-Inferenz
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            # Skalierung: Höhe auf 256px, Seitenverhältnis beibehalten
            w, h = pil_image.size
            new_h = 256
            new_w = int(w * new_h / h)
            pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)

            frames_to_analyze.append(pil_image)
            timestamps.append(round(frame_idx / fps, 2))

            frame_idx += frame_interval
    finally:
        cap.release()

    if not frames_to_analyze:
        if task and tm:
            tm.finish_task(task.task_id, "error", "Keine Frames")
        return {"error": "Keine Frames extrahiert."}

    if task and tm:
        tm.update_task(task.task_id, 30, message="Vision-Modell laden...")

    # ModelManager: Moondream2 laden (entlädt automatisch andere Modelle)
    mm = ModelManager()

    # GPU-Check: Moondream2 nur mit CUDA sinnvoll nutzbar (CPU zu langsam)
    use_ai_vision = torch.cuda.is_available()

    if use_ai_vision:
        model, tokenizer = mm.load_vision("vikhyatk/moondream2")

    # Frames analysieren
    scene_descriptions = []

    if use_ai_vision:
        # GPU-Pfad: Moondream2 KI-Analyse
        # Phase 1: Alle Bilder vorcodieren (GPU-Batch-freundlich)
        encoded_images = []
        with torch.no_grad():
            for pil_img in frames_to_analyze:
                try:
                    encoded_images.append(model.encode_image(pil_img))
                except Exception:
                    encoded_images.append(None)

        # Phase 2: Descriptions generieren (sequentiell, aber ohne erneutes Encoding)
        with torch.no_grad():
            for i, (enc_img, ts) in enumerate(zip(encoded_images, timestamps)):
                try:
                    if enc_img is None:
                        raise RuntimeError("Encoding fehlgeschlagen")
                    description = model.answer_question(
                        enc_img,
                        "Describe this scene briefly.",
                        tokenizer,
                    )
                    scene_descriptions.append({
                        "frame_index": i,
                        "timestamp_sec": ts,
                        "description": description.strip(),
                    })
                except Exception as e:
                    scene_descriptions.append({
                        "frame_index": i,
                        "timestamp_sec": ts,
                        "description": f"[Fehler: {e}]",
                    })
                # VRAM-Cleanup nach jedem Frame (Moondream2 hält KV-Cache)
                if torch.cuda.is_available() and i % 4 == 3:
                    torch.cuda.empty_cache()

        # Encodings freigeben (können je nach Modell GPU-Tensors sein)
        del encoded_images
        # Moondream2 entladen — gibt ~3.6 GB VRAM frei
        mm.unload()
    else:
        # CPU-Fallback: OpenCV-basierte Bildanalyse (Farbe, Helligkeit, Kanten)
        import numpy as np
        for i, (pil_img, ts) in enumerate(zip(frames_to_analyze, timestamps)):
            try:
                arr = np.array(pil_img)
                # Basale Bildstatistiken
                brightness = int(arr.mean())
                r_mean, g_mean, b_mean = int(arr[:,:,0].mean()), int(arr[:,:,1].mean()), int(arr[:,:,2].mean())

                # Dominante Farbe bestimmen
                if r_mean > g_mean and r_mean > b_mean:
                    dominant = "rot/warm"
                elif g_mean > r_mean and g_mean > b_mean:
                    dominant = "gruen/natuerlich"
                elif b_mean > r_mean and b_mean > g_mean:
                    dominant = "blau/kalt"
                else:
                    dominant = "neutral"

                # Kantenerkennung für Komplexität
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                edge_ratio = float(edges.sum()) / (edges.shape[0] * edges.shape[1] * 255)

                complexity = "komplex" if edge_ratio > 0.1 else "mittel" if edge_ratio > 0.03 else "einfach"

                desc = (f"Frame bei {ts}s: Helligkeit={brightness}/255, "
                        f"Farbton={dominant} (R={r_mean},G={g_mean},B={b_mean}), "
                        f"Komplexitaet={complexity} ({edge_ratio:.2%} Kanten). "
                        f"[CPU-Modus: Fuer KI-Beschreibung GPU (CUDA) benoetigt]")

                scene_descriptions.append({
                    "frame_index": i,
                    "timestamp_sec": ts,
                    "description": desc,
                })
            except Exception as e:
                scene_descriptions.append({
                    "frame_index": i,
                    "timestamp_sec": ts,
                    "description": f"[Fehler: {e}]",
                })

    if task and tm:
        tm.finish_task(task.task_id, "finished",
                       f"{len(scene_descriptions)} Frames analysiert")
    return {
        "file_path": file_path,
        "duration_sec": round(duration, 2),
        "fps": round(fps, 2),
        "total_frames_analyzed": len(scene_descriptions),
        "interval_sec": interval_sec,
        "scenes": scene_descriptions,
        "summary": f"{len(scene_descriptions)} Szenen aus {round(duration, 1)}s Video analysiert.",
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

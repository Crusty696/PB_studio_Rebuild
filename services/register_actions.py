"""
Registriert die bestehenden PB Studio Funktionen im ActionRegistry.

Dieses Modul wird beim App-Start aufgerufen. Neue Funktionen einfach
hier mit @action_registry.register(...) hinzufügen.
"""

from services.action_registry import action_registry


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
    from services.audio_service import AudioAnalyzer
    return AudioAnalyzer().analyze_and_store(track_id)


@action_registry.register(
    name="separate_stems",
    description="Trennt einen Audiotrack in Stems (Vocals, Drums, Bass, Other) mittels KI.",
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
def separate_stems(track_id: int) -> dict:
    from services.ai_audio_service import AIAudioService
    return AIAudioService().separate_stems(track_id)


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
    from services.video_service import VideoAnalyzer
    return VideoAnalyzer().analyze_and_store(clip_id)


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
def auto_edit(audio_track_id: int) -> list:
    from services.pacing_service import PacingEngine
    return PacingEngine().auto_edit(audio_track_id)


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
    from services.ingest_service import IngestService
    return IngestService().import_file(file_path, project_id)


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
def export_timeline(project_id: int, output_path: str | None = None) -> dict:
    from services.export_service import ExportService
    return ExportService().export(project_id, output_path)


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

    # Dateipfad ermitteln
    if file_path is None and track_id is not None:
        from sqlalchemy.orm import Session as SASession
        from database import engine, AudioTrack
        with SASession(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                return {"error": f"AudioTrack {track_id} nicht gefunden."}
            file_path = track.file_path

    if not file_path or not os.path.exists(file_path):
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
    whisper_size = os.environ.get("PB_WHISPER_SIZE", "tiny")
    whisper_model = mm.load_whisper(whisper_size)

    # Transkription
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

    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
        "segments": transcript_segments,
        "full_text": " ".join(full_text_parts),
        "segment_count": len(transcript_segments),
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
    """Analysiert Video-Inhalt visuell mit Moondream2.

    Optimiert für CPU: Bilder werden auf 256px skaliert,
    Inferenz läuft mit torch.no_grad() und kurzen Prompts.
    """
    import os
    import cv2
    import torch
    from PIL import Image
    from services.model_manager import ModelManager

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
        return {"error": f"Datei nicht gefunden: {file_path}"}

    # Frames extrahieren mit OpenCV
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return {"error": f"Video konnte nicht geöffnet werden: {file_path}"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    frame_interval = int(fps * interval_sec)

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

    cap.release()

    if not frames_to_analyze:
        return {"error": "Keine Frames extrahiert."}

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
        with torch.no_grad():
            for i, (pil_img, ts) in enumerate(zip(frames_to_analyze, timestamps)):
                try:
                    enc_image = model.encode_image(pil_img)
                    description = model.answer_question(
                        enc_image,
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

    return {
        "file_path": file_path,
        "duration_sec": round(duration, 2),
        "fps": round(fps, 2),
        "total_frames_analyzed": len(scene_descriptions),
        "interval_sec": interval_sec,
        "scenes": scene_descriptions,
        "summary": f"{len(scene_descriptions)} Szenen aus {round(duration, 1)}s Video analysiert.",
    }


# --- Info-Aktionen ---

@action_registry.register(
    name="list_actions",
    description="Zeigt alle verfügbaren Aktionen an, die die KI ausführen kann.",
    param_schema={"type": "object", "properties": {}}
)
def list_actions() -> list[str]:
    return action_registry.list_actions()

"""Video actions: video analysis, CV content analysis, proxy creation,
scene detection, motion analysis, embedding generation, semantic search,
and keyframe string generation.
"""

import logging

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)


def _get_task_manager():
    """Gibt den TaskManager zurueck ohne QApplication-Kopplung."""
    from services.task_manager import GlobalTaskManager
    return GlobalTaskManager.instance()


def _get_active_video_clip(session, VideoClip, clip_id: int):
    return (
        session.query(VideoClip)
        .filter(VideoClip.id == clip_id, VideoClip.deleted_at.is_(None))
        .first()
    )


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
    from sqlalchemy.orm import Session as SASession
    from database import engine, VideoClip

    with SASession(engine) as session:
        if _get_active_video_clip(session, VideoClip, clip_id) is None:
            return {"error": f"VideoClip {clip_id} nicht gefunden."}

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

    tm.agent_command_signal.emit(
        "analyze_video", {"clip_id": clip_id}
    )
    return {
        "status": "Task in Warteschlange",
        "action": "analyze_video",
        "clip_id": clip_id,
        "message": f"Video-Analyse fuer Clip #{clip_id} gestartet. Fortschritt im TaskManagerDock.",
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
    """Vision-Analyse via Moondream2 — startet als Background-Worker."""
    if clip_id is None and file_path is None:
        return {"status": "error", "message": "Weder clip_id noch file_path angegeben."}

    # Video-Pfad aus DB laden wenn nur clip_id gegeben
    video_path = file_path
    if clip_id and not video_path:
        from database import engine, VideoClip
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            clip = _get_active_video_clip(session, VideoClip, clip_id)
            if clip:
                video_path = clip.file_path
            else:
                return {"status": "error", "message": f"VideoClip {clip_id} nicht in DB."}

    if not video_path:
        return {"status": "error", "message": "Kein Video-Pfad ermittelt."}

    label = f"Clip #{clip_id}" if clip_id else video_path
    tm = _get_task_manager()

    from workers.video import VisionAnalysisWorker
    worker = VisionAnalysisWorker(
        clip_id=clip_id or 0,
        video_path=video_path,
        interval_sec=interval_sec,
        max_frames=max_frames,
    )
    task = tm.start_task(
        name=f"Vision: {label}",
        worker=worker,
        description="Moondream2 Video-Inhaltsanalyse",
    )

    task_id = task.task_id if hasattr(task, 'task_id') else str(task)
    return {
        "status": "Task gestartet",
        "action": "analyze_video_content",
        "task_id": task_id,
        "message": f"Vision-Analyse fuer {label} laeuft im Hintergrund.",
    }


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

    tm = _get_task_manager()
    if tm is None:
        _logger.warning("TaskManager nicht verfügbar - App nicht bereit")
        return {"error": "App nicht initialisiert"}

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
                for c in session.query(VideoClip).filter(
                    VideoClip.id.in_(video_ids),
                    VideoClip.deleted_at.is_(None),
                ).all()
                if c.file_path
            }
        queued = 0
        for video in videos:
            fp = clip_paths.get(video["id"])
            if fp:
                tm.agent_command_signal.emit(
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
        clip = _get_active_video_clip(session, VideoClip, clip_id)
        if clip is None:
            return {"error": f"VideoClip {clip_id} nicht gefunden."}
        video_path = clip.file_path

    tm.agent_command_signal.emit(
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
            clip = _get_active_video_clip(session, VideoClip, clip_id)
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
    except Exception as e:  # broad catch intentional — re-raised after task error logging
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
            clip = _get_active_video_clip(session, VideoClip, clip_id)
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
    except Exception as e:  # broad catch intentional — re-raised after task error logging
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
            clip = _get_active_video_clip(session, VideoClip, clip_id)
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
    except Exception as e:  # broad catch intentional — re-raised after task error logging
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


# ---------------------------------------------------------------------------
# B-245: describe_video_clip — DB-Read, Reihrer Caption/Mood/Tags-Block
# ---------------------------------------------------------------------------

@action_registry.register(
    name="describe_video_clip",
    description=(
        "Beschreibt einen Video-Clip als lesbaren Text — Resolution, FPS, Dauer, "
        "alle erkannten Szenen mit AI-Caption (Moondream/Gemma Vision), Mood, "
        "Motion, Tags. Liest BEREITS analysierte Daten aus der DB (kein neuer "
        "Pipeline-Lauf). Ideal fuer LLM-Kontext bei stummen Videos. "
        "Nutze diese Aktion wenn der User nach 'Beschreibe Video', 'Was ist auf "
        "Clip X', 'Clip-Inhalt', 'Welche Szenen sind im Video?' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank. OPTIONAL: wenn leer, erster Clip."
            }
        },
        "required": []
    }
)
def describe_video_clip(clip_id: int | None = None) -> dict:
    """Liest einen analysierten VideoClip + Scenes aus der DB als Text-Block.

    Schreibt nichts, triggert keine Worker. Wenn Caption-Daten fehlen
    (Vision-Pipeline noch nicht durch), wird das im Output explizit
    markiert — der LLM kann dann selbst entscheiden ob er
    ``analyze_video_content`` triggert.
    """
    try:
        from sqlalchemy.orm import Session as SASession
        from database import engine, VideoClip, Scene

        with SASession(engine) as session:
            if clip_id:
                clip = _get_active_video_clip(session, VideoClip, clip_id)
            else:
                clip = session.query(VideoClip).filter(VideoClip.deleted_at.is_(None)).first()

            if not clip:
                return {
                    "status": "error",
                    "action": "describe_video_clip",
                    "message": (
                        "Kein VideoClip gefunden. Bitte zuerst Video importieren."
                        if clip_id is None
                        else f"VideoClip {clip_id} nicht in DB."
                    ),
                }

            scenes = (
                session.query(Scene)
                .filter_by(video_clip_id=clip.id)
                .order_by(Scene.start_time)
                .all()
            )

            c_id = clip.id
            c_title = getattr(clip, "title", None) or clip.file_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            c_dur = clip.duration
            c_w = clip.width
            c_h = clip.height
            c_fps = clip.fps
            c_codec = clip.codec
            c_proxy = bool(clip.proxy_path)

            scene_data = []
            for s in scenes:
                scene_data.append({
                    "start": s.start_time,
                    "end": s.end_time,
                    "label": s.label,
                    "energy": s.energy,
                    "ai_caption": s.ai_caption,  # JSON: {description, mood, motion, tags}
                    "ai_mood": s.ai_mood,
                    "ai_tags": s.ai_tags,
                })

        # Format
        def _fmt_time(secs: float | None) -> str:
            if secs is None:
                return "?"
            mins = int(secs // 60)
            sec = int(secs % 60)
            hours = mins // 60
            mins = mins % 60
            return f"{hours:d}h{mins:02d}m{sec:02d}s" if hours else f"{mins:02d}:{sec:02d}"

        lines: list[str] = []
        title_line = f"Video #{c_id}: {c_title}"
        if c_dur:
            title_line += f" ({_fmt_time(c_dur)}"
            if c_w and c_h:
                title_line += f", {c_w}x{c_h}"
            if c_fps:
                title_line += f"@{c_fps:.0f}fps"
            title_line += ")"
        lines.append(title_line)
        lines.append("=" * min(len(title_line), 70))

        if c_codec:
            lines.append(f"Codec: {c_codec}")
        lines.append(f"Proxy: {'erstellt' if c_proxy else 'nicht erstellt'}")

        if not scene_data:
            lines.append("")
            lines.append("Szenen: noch nicht erkannt (`detect_scenes` ausfuehren)")
        else:
            captioned = sum(1 for s in scene_data if s["ai_caption"] or s["label"])
            lines.append("")
            lines.append(f"Szenen: {len(scene_data)} erkannt, {captioned} mit AI-Caption")
            if captioned < len(scene_data):
                lines.append(
                    f"Hinweis: {len(scene_data) - captioned} Szenen ohne AI-Caption — "
                    f"`analyze_video_content` triggern fuer Vollstaendigkeit."
                )

            lines.append("")
            lines.append("Szenen-Timeline:")
            max_show = 25
            for s in scene_data[:max_show]:
                tr = f"[{_fmt_time(s['start'])}-{_fmt_time(s['end'])}]"
                meta_bits: list[str] = []
                if s["energy"] is not None:
                    meta_bits.append(f"energy: {s['energy']:.2f}")
                if s["ai_mood"]:
                    meta_bits.append(f"mood: {s['ai_mood']}")

                # ai_caption ist JSON dict {description, mood, motion, tags}
                cap = s["ai_caption"]
                description = ""
                motion = None
                tags_list: list[str] = []
                if isinstance(cap, dict):
                    description = cap.get("description", "") or ""
                    motion = cap.get("motion")
                    tags_list = cap.get("tags") or []
                elif isinstance(cap, str) and cap:
                    description = cap
                if motion:
                    meta_bits.append(f"motion: {motion}")

                # Fallback: ai_tags-Feld wenn keine im caption-dict
                if not tags_list and s["ai_tags"]:
                    if isinstance(s["ai_tags"], list):
                        tags_list = s["ai_tags"]

                meta_str = f" ({', '.join(meta_bits)})" if meta_bits else ""
                label_or_desc = description or s["label"] or "(keine Beschreibung)"
                lines.append(f"  {tr}{meta_str}")
                lines.append(f"     {label_or_desc}")
                if tags_list:
                    lines.append(f"     Tags: {', '.join(tags_list[:8])}")

            if len(scene_data) > max_show:
                lines.append(f"  ... + {len(scene_data) - max_show} weitere Szenen")

        message = "\n".join(lines)

        # Stats fuer LLM-Konsumenten
        captioned_count = sum(1 for s in scene_data if s["ai_caption"] or s["label"])
        moods_seen = sorted({s["ai_mood"] for s in scene_data if s["ai_mood"]})

        return {
            "status": "ok",
            "action": "describe_video_clip",
            "clip_id": c_id,
            "title": c_title,
            "duration": c_dur,
            "resolution": f"{c_w}x{c_h}" if c_w and c_h else None,
            "fps": c_fps,
            "scene_count": len(scene_data),
            "captioned_count": captioned_count,
            "captions_complete": (captioned_count == len(scene_data) and len(scene_data) > 0),
            "moods_seen": moods_seen,
            "proxy_ready": c_proxy,
            "message": message,
        }
    except Exception as exc:  # broad catch intentional — SQLAlchemy + format errors
        _logger.error("describe_video_clip fehlgeschlagen: %s", exc, exc_info=True)
        return {
            "status": "error",
            "action": "describe_video_clip",
            "message": f"Fehler: {exc}",
        }

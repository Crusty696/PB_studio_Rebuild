"""AI agent actions: Ollama queries, project summaries, pacing suggestions,
model status, knowledge-base search, and clip explanations.

All actions register via @action_registry.register on import.
Heavy GPU work (Vision analysis) is delegated to background workers.
Lightweight queries (Ollama chat, DB reads, status) run inline.
"""

import logging

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ollama_client():
    """Returns the OllamaClient singleton (lazy)."""
    from services.ollama_client import get_ollama_client
    return get_ollama_client()


def _get_task_manager():
    """Returns the TaskManager without QApplication coupling."""
    from services.task_manager import GlobalTaskManager
    return GlobalTaskManager.instance()


# ---------------------------------------------------------------------------
# 1. ask_ai — Free question to local LLM
# ---------------------------------------------------------------------------

@action_registry.register(
    name="ask_ai",
    description=(
        "Stellt eine freie Frage an den lokalen KI-Assistenten (Ollama LLM). "
        "Nutze diese Aktion wenn der User eine allgemeine Frage hat, die keine "
        "spezifische App-Aktion erfordert — z.B. 'Was ist LUFS?', "
        "'Erklaere mir Pacing', 'Tipps fuer DJ-Sets'."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Die Frage des Benutzers an den KI-Assistenten."
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximale Antwortlaenge in Tokens (default: 512)."
            }
        },
        "required": ["question"]
    }
)
def ask_ai(question: str, max_tokens: int = 512) -> dict:
    """Sends a free-form question to the local Ollama LLM and returns the answer."""
    try:
        client = _get_ollama_client()
        if not client.is_available():
            return {
                "status": "error",
                "action": "ask_ai",
                "message": "Ollama ist nicht erreichbar. Bitte starte Ollama mit 'ollama serve'.",
            }

        # Pick best available model
        import os
        model = os.environ.get("PB_OLLAMA_MODEL") or client.get_best_available_model()
        if not model:
            return {
                "status": "error",
                "action": "ask_ai",
                "message": "Kein Ollama-Modell installiert. Tipp: 'ollama pull qwen2.5:1.5b-instruct'.",
            }

        system_prompt = (
            "Du bist der KI-Assistent von PB Studio, einer professionellen "
            "Audio/Video-Produktionssoftware fuer DJs und Video-Editoren. "
            "Antworte praezise, hilfreich und auf Deutsch."
        )
        answer = client.chat(
            model=model,
            user_message=question,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return {
            "status": "ok",
            "action": "ask_ai",
            "model": model,
            "answer": answer,
            "message": answer,
        }
    except (ConnectionError, TimeoutError, ValueError, RuntimeError) as exc:
        _logger.error("ask_ai fehlgeschlagen: %s", exc, exc_info=True)
        return {"status": "error", "action": "ask_ai", "message": str(exc)}


# ---------------------------------------------------------------------------
# 2. summarize_project — Project overview from DB
# ---------------------------------------------------------------------------

@action_registry.register(
    name="summarize_project",
    description=(
        "Generiert einen Ueberblick ueber das aktuelle Projekt: "
        "importierte Medien, Analyse-Status, Stems, BPM, Szenen. "
        "Nutze diese Aktion wenn der User nach 'Projektstatus', "
        "'Uebersicht', 'Was ist importiert?' oder 'Zusammenfassung' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "integer",
                "description": "Projekt-ID (default: 1 = aktuelles Projekt)."
            }
        },
        "required": []
    }
)
def summarize_project(project_id: int = 1) -> dict:
    """Reads the current project state from the DB and returns a structured summary."""
    try:
        from services.ingest_service import get_all_audio, get_all_video

        audios = get_all_audio(project_id=project_id)
        videos = get_all_video(project_id=project_id)

        # Audio stats
        audio_summary = []
        bpm_values = []
        stems_done = 0
        for a in audios:
            info = {
                "id": a["id"],
                "title": a["title"],
                "bpm": a.get("bpm"),
                "stems": a.get("stems", "-"),
            }
            audio_summary.append(info)
            if a.get("bpm"):
                bpm_values.append(a["bpm"])
            if a.get("stems", "-") != "-":
                stems_done += 1

        # Video stats
        video_summary = []
        for v in videos:
            video_summary.append({
                "id": v["id"],
                "title": v["title"],
                "resolution": v.get("resolution"),
                "fps": v.get("fps"),
            })

        # Scene count from DB
        scene_count = 0
        try:
            from sqlalchemy.orm import Session as SASession
            from database import engine, Scene
            with SASession(engine) as session:
                video_ids = [v["id"] for v in videos]
                if video_ids:
                    scene_count = session.query(Scene).filter(
                        Scene.video_clip_id.in_(video_ids)
                    ).count()
        except Exception as exc:  # broad catch intentional — SQLAlchemy query can raise many error types
            _logger.warning("Failed to query scene count in summarize_project: %s", exc)

        bpm_range = ""
        if bpm_values:
            bpm_range = f"{min(bpm_values):.0f}-{max(bpm_values):.0f} BPM"

        summary_text = (
            f"Projekt #{project_id}: "
            f"{len(audios)} Audio-Tracks, {len(videos)} Video-Clips, "
            f"{scene_count} Szenen erkannt. "
            f"Stems: {stems_done}/{len(audios)} fertig. "
            f"BPM-Bereich: {bpm_range or 'noch nicht analysiert'}."
        )

        return {
            "status": "ok",
            "action": "summarize_project",
            "project_id": project_id,
            "audio_count": len(audios),
            "video_count": len(videos),
            "scene_count": scene_count,
            "stems_completed": stems_done,
            "bpm_range": bpm_range,
            "audios": audio_summary,
            "videos": video_summary,
            "message": summary_text,
        }
    except Exception as exc:  # broad catch intentional — SQLAlchemy + analysis errors
        _logger.error("summarize_project fehlgeschlagen: %s", exc, exc_info=True)
        return {"status": "error", "action": "summarize_project", "message": str(exc)}


# ---------------------------------------------------------------------------
# 3. suggest_pacing — Pacing suggestions based on audio analysis
# ---------------------------------------------------------------------------

@action_registry.register(
    name="suggest_pacing",
    description=(
        "Generiert Pacing-Vorschlaege basierend auf der Audio-Analyse. "
        "Berechnet optimale Schnittrate, empfiehlt Stem-Gewichtung und "
        "identifiziert Drops/Breakdowns. "
        "Nutze diese Aktion wenn der User nach 'Pacing', 'Schnittvorschlaege', "
        "'Cut-Rate', 'Auto-Edit Einstellungen' oder 'wie soll ich schneiden?' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks. OPTIONAL: Wenn leer, wird der erste Track genommen."
            }
        },
        "required": []
    }
)
def suggest_pacing(audio_track_id: int | None = None) -> dict:
    """Analyzes audio data and suggests optimal pacing settings."""
    try:
        from sqlalchemy.orm import Session as SASession
        from database import engine, AudioTrack, Beatgrid

        with SASession(engine) as session:
            # Find the track
            if audio_track_id:
                track = session.get(AudioTrack, audio_track_id)
            else:
                track = session.query(AudioTrack).first()

            if not track:
                return {
                    "status": "error",
                    "action": "suggest_pacing",
                    "message": "Kein AudioTrack gefunden. Bitte zuerst Audio importieren.",
                }

            track_id = track.id
            track_title = track.title
            bpm = track.bpm
            mood = getattr(track, "mood", None)
            genre = getattr(track, "genre", None)
            is_dj_mix = getattr(track, "is_dj_mix", False)

            # Beat data
            beatgrid = session.query(Beatgrid).filter_by(audio_track_id=track_id).first()
            has_beats = beatgrid is not None and beatgrid.beat_positions
            energy_data = None
            if beatgrid and beatgrid.energy_per_beat:
                import json as _json
                try:
                    energy_data = _json.loads(beatgrid.energy_per_beat) if isinstance(
                        beatgrid.energy_per_beat, str
                    ) else beatgrid.energy_per_beat
                except (ValueError, TypeError) as exc:
                    _logger.warning("Failed to parse energy_per_beat in suggest_pacing: %s", exc)

            # Structure segments
            from database import StructureSegment
            segments = session.query(StructureSegment).filter_by(
                audio_track_id=track_id
            ).order_by(StructureSegment.start_time).all()
            segment_labels = [s.label for s in segments] if segments else []

        # Build suggestions
        suggestions = {}

        # Base cut rate from BPM
        if bpm:
            if bpm < 100:
                suggestions["base_cut_rate"] = 8
                suggestions["tempo_note"] = "Langsamer Track — laengere Schnitte empfohlen"
            elif bpm < 130:
                suggestions["base_cut_rate"] = 4
                suggestions["tempo_note"] = "Mittleres Tempo — Standard-Schnittrate"
            elif bpm < 150:
                suggestions["base_cut_rate"] = 2
                suggestions["tempo_note"] = "Schneller Track — haeufigere Schnitte"
            else:
                suggestions["base_cut_rate"] = 2
                suggestions["tempo_note"] = "Sehr schneller Track — aggressive Schnitte moeglich"

        # Energy reactivity
        if energy_data and isinstance(energy_data, list) and len(energy_data) > 10:
            import statistics
            std_energy = statistics.stdev(energy_data)
            if std_energy > 0.3:
                suggestions["energy_reactivity"] = 75
                suggestions["energy_note"] = "Hohe Dynamik — reaktive Schnittrate empfohlen"
            elif std_energy > 0.15:
                suggestions["energy_reactivity"] = 50
                suggestions["energy_note"] = "Moderate Dynamik — Standard-Reaktivitaet"
            else:
                suggestions["energy_reactivity"] = 25
                suggestions["energy_note"] = "Konstante Energie — gleichmaessige Schnitte"
        else:
            suggestions["energy_reactivity"] = 50
            suggestions["energy_note"] = "Keine Energiedaten — Standard-Reaktivitaet"

        # Structure-based advice
        has_drops = any("drop" in s.lower() for s in segment_labels)
        has_breakdowns = any("breakdown" in s.lower() for s in segment_labels)
        if has_drops:
            suggestions["drop_behavior"] = "S_eff=1 fuer 16-32 Beats nach dem Drop"
        if has_breakdowns:
            suggestions["breakdown_behavior"] = "halve — Schnittrate halbieren in Breakdowns"

        # Genre/mood hints
        if genre:
            suggestions["genre"] = genre
        if mood:
            suggestions["mood"] = mood
            if mood in ("melancholic", "chill", "ambient"):
                suggestions["vibe_note"] = "Ruhige Stimmung — laengere, sanftere Schnitte"
            elif mood in ("energetic", "aggressive", "dark"):
                suggestions["vibe_note"] = "Energetische Stimmung — schnelle, harte Schnitte"

        # DJ-Mix detection
        if is_dj_mix:
            suggestions["dj_mix"] = True
            suggestions["dj_mix_note"] = (
                "DJ-Mix erkannt — Sektions-basiertes Pacing empfohlen "
                "(WARMUP→BUILDUP→DROP→BREAKDOWN→TRANSITION→COOLDOWN)"
            )

        summary = (
            f"Pacing-Vorschlaege fuer '{track_title}' "
            f"({bpm or '?'} BPM, {genre or '?'}, {mood or '?'}): "
            f"Base-Cut-Rate={suggestions.get('base_cut_rate', '?')} Beats, "
            f"Energy-Reactivity={suggestions.get('energy_reactivity', 50)}%."
        )

        return {
            "status": "ok",
            "action": "suggest_pacing",
            "audio_track_id": track_id,
            "title": track_title,
            "bpm": bpm,
            "has_beats": has_beats,
            "structure_segments": segment_labels,
            "suggestions": suggestions,
            "message": summary,
        }
    except Exception as exc:  # broad catch intentional — DB + analysis errors
        _logger.error("suggest_pacing fehlgeschlagen: %s", exc, exc_info=True)
        return {"status": "error", "action": "suggest_pacing", "message": str(exc)}


# ---------------------------------------------------------------------------
# 4. model_status — GPU / VRAM / Model status
# ---------------------------------------------------------------------------

@action_registry.register(
    name="model_status",
    description=(
        "Zeigt den aktuellen GPU/VRAM/Modell-Status an. "
        "Nutze diese Aktion wenn der User nach 'GPU', 'VRAM', 'Modell-Status', "
        "'Hardware', 'CUDA' oder 'welches Modell laeuft?' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def model_status() -> dict:
    """Returns current GPU, VRAM, and loaded model information."""
    result = {
        "status": "ok",
        "action": "model_status",
    }

    # ModelManager state
    try:
        from services.model_manager import ModelManager
        mm = ModelManager()
        result["gpu"] = mm.gpu_info
        result["device"] = mm.device
        result["current_model"] = mm.current_model_id
        result["model_type"] = mm.model_type
        result["model_loaded"] = mm.is_loaded
    except (ImportError, RuntimeError, AttributeError) as exc:
        result["gpu"] = {"name": "unbekannt", "error": str(exc)}
        result["device"] = "unbekannt"
        result["model_loaded"] = False

    # VRAM usage (if CUDA available)
    try:
        from services.model_manager import _ensure_torch
        torch = _ensure_torch()
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0) / 1024 / 1024
            reserved = torch.cuda.memory_reserved(0) / 1024 / 1024
            total = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
            result["vram"] = {
                "allocated_mb": round(allocated, 1),
                "reserved_mb": round(reserved, 1),
                "total_mb": round(total, 0),
                "free_mb": round(total - allocated, 1),
                "usage_percent": round(allocated / total * 100, 1) if total > 0 else 0,
            }
        else:
            result["vram"] = None
    except (ImportError, RuntimeError):
        result["vram"] = None

    # Ollama status
    try:
        client = _get_ollama_client()
        result["ollama_available"] = client.is_available()
        if result["ollama_available"]:
            result["ollama_version"] = client.get_version()
            result["ollama_models"] = client.list_models()
        else:
            result["ollama_version"] = None
            result["ollama_models"] = []
    except (ConnectionError, TimeoutError, OSError):
        result["ollama_available"] = False
        result["ollama_models"] = []

    # Build human-readable message
    gpu_name = result.get("gpu", {}).get("name", "unbekannt")
    vram_info = result.get("vram")
    vram_str = (
        f"{vram_info['allocated_mb']:.0f}/{vram_info['total_mb']:.0f} MB ({vram_info['usage_percent']}%)"
        if vram_info else "N/A"
    )
    model_str = result.get("current_model") or "keins geladen"
    ollama_str = "verfuegbar" if result.get("ollama_available") else "nicht erreichbar"
    ollama_models_str = ", ".join(result.get("ollama_models", [])[:5]) or "keine"

    result["message"] = (
        f"GPU: {gpu_name} | VRAM: {vram_str} | "
        f"Geladenes Modell: {model_str} | "
        f"Ollama: {ollama_str} (Modelle: {ollama_models_str})"
    )
    return result


# ---------------------------------------------------------------------------
# 5. search_knowledge — Knowledge base search
# ---------------------------------------------------------------------------

@action_registry.register(
    name="search_knowledge",
    description=(
        "Durchsucht die Knowledge-Base von PB Studio nach relevantem Domain-Wissen. "
        "Nutze diese Aktion wenn der User nach 'Wissen', 'Knowledge', 'Dokumentation', "
        "'wie funktioniert X?', 'erklaere Feature Y' oder 'Hilfe zu Z' fragt."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Suchbegriff oder Frage, z.B. 'Pacing-Algorithmus' oder 'Stem-Separation'."
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximale Zeichenanzahl des Ergebnisses (default: 2000)."
            }
        },
        "required": ["query"]
    }
)
def search_knowledge(query: str, max_chars: int = 2000) -> dict:
    """Searches the PB Studio knowledge base for relevant domain knowledge."""
    try:
        from services.knowledge_loader import get_knowledge_loader
        loader = get_knowledge_loader()

        # Get available knowledge files
        available = loader.get_available_files()
        if not available:
            return {
                "status": "ok",
                "action": "search_knowledge",
                "query": query,
                "result_count": 0,
                "knowledge": "",
                "message": "Knowledge-Base ist leer. Keine .md/.txt Dateien in data/knowledge/ gefunden.",
            }

        # Build context filtered by query relevance
        context = loader.build_context(query=query, max_chars=max_chars)

        if not context:
            # Fallback: list available topics
            file_names = [f.stem for f in available]
            return {
                "status": "ok",
                "action": "search_knowledge",
                "query": query,
                "result_count": 0,
                "available_topics": file_names,
                "knowledge": "",
                "message": (
                    f"Kein relevantes Wissen fuer '{query}' gefunden. "
                    f"Verfuegbare Themen: {', '.join(file_names)}"
                ),
            }

        return {
            "status": "ok",
            "action": "search_knowledge",
            "query": query,
            "result_count": 1,
            "knowledge": context,
            "message": context,
        }
    except (ValueError, RuntimeError, ImportError) as exc:
        _logger.error("search_knowledge fehlgeschlagen: %s", exc, exc_info=True)
        return {"status": "error", "action": "search_knowledge", "message": str(exc)}


# ---------------------------------------------------------------------------
# 6. explain_clip — Clip description via Moondream2 / VectorDB
# ---------------------------------------------------------------------------

@action_registry.register(
    name="explain_clip",
    description=(
        "Beschreibt den Inhalt eines Video-Clips anhand vorhandener Szenen-Beschreibungen "
        "(Moondream2) und Embeddings (SigLIP). Wenn keine Analyse vorliegt, wird eine "
        "Vision-Analyse im Hintergrund gestartet. "
        "Nutze diese Aktion wenn der User nach 'Was ist in diesem Clip?', "
        "'Clip beschreiben', 'Clip-Inhalt', 'Was zeigt Video X?' fragt."
    ),
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
def explain_clip(clip_id: int) -> dict:
    """Returns existing scene descriptions for a clip, or triggers vision analysis."""
    try:
        from sqlalchemy.orm import Session as SASession
        from database import engine, VideoClip, Scene

        with SASession(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                return {
                    "status": "error",
                    "action": "explain_clip",
                    "message": f"VideoClip {clip_id} nicht gefunden.",
                }

            clip_title = clip.title if hasattr(clip, "title") else ""
            clip_path = clip.file_path
            clip_duration = clip.duration

            # Get existing scene descriptions
            scenes = (
                session.query(Scene)
                .filter_by(video_clip_id=clip_id)
                .order_by(Scene.start_time)
                .all()
            )

        # If scenes with labels exist, return them directly
        described_scenes = []
        for s in scenes:
            label = s.label or ""
            if label.strip():
                described_scenes.append({
                    "index": s.scene_index if hasattr(s, "scene_index") else 0,
                    "start": s.start_time,
                    "end": s.end_time,
                    "description": label,
                    "energy": s.energy,
                })

        if described_scenes:
            # Build a human-readable description
            scene_texts = []
            for sc in described_scenes:
                time_range = f"{sc['start']:.1f}s-{sc['end']:.1f}s"
                scene_texts.append(f"[{time_range}] {sc['description']}")

            full_description = "\n".join(scene_texts)
            return {
                "status": "ok",
                "action": "explain_clip",
                "clip_id": clip_id,
                "title": clip_title or clip_path,
                "duration": clip_duration,
                "scene_count": len(described_scenes),
                "scenes": described_scenes,
                "message": (
                    f"Clip #{clip_id} ({len(described_scenes)} Szenen):\n{full_description}"
                ),
            }

        # No descriptions yet — trigger vision analysis in background
        tm = _get_task_manager()
        if tm is None:
            return {
                "status": "error",
                "action": "explain_clip",
                "message": "Keine Szenen-Beschreibungen vorhanden und TaskManager nicht bereit.",
            }

        tm.agent_command_signal.emit(
            "analyze_video_content",
            {"clip_id": clip_id, "file_path": clip_path},
        )
        return {
            "status": "pending",
            "action": "explain_clip",
            "clip_id": clip_id,
            "message": (
                f"Keine Szenen-Beschreibungen fuer Clip #{clip_id} vorhanden. "
                f"Vision-Analyse (Moondream2) wurde im Hintergrund gestartet. "
                f"Bitte in 1-2 Minuten erneut fragen."
            ),
        }
    except Exception as exc:  # broad catch intentional — DB + vision service + file errors
        _logger.error("explain_clip fehlgeschlagen: %s", exc, exc_info=True)
        return {"status": "error", "action": "explain_clip", "message": str(exc)}

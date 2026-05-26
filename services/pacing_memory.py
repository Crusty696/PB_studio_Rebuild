"""Pacing Memory — KI-Langzeitgedaechtnis fuer Schnitt-Entscheidungen.

Enthält:
- learn_from_anchor: Manuelle Schnitt-Entscheidungen persistieren
- record_rl_feedback: Reinforcement-Learning Feedback speichern
- _get_ai_memory_bias: Gespeicherte Lern-Beispiele abfragen
- auto_edit_to_beats: Legacy Phase 2 Wrapper
"""

from __future__ import annotations

import json
import logging

import numpy as np
from sqlalchemy.orm import Session

from database import engine, AudioTrack, AIPacingMemory, Beatgrid, Scene, TimelineEntry, VideoClip
from services.pacing_beat_grid import AdvancedPacingSettings

logger = logging.getLogger(__name__)


def learn_from_anchor(
    audio_track_id: int,
    anchor_time: float,
    scene_id: int | None = None,
    label: str = "",
) -> bool:
    """Speichert eine manuelle Schnitt-Entscheidung als KI-Lern-Beispiel.

    Liest den Audio-Kontext (BPM, Energie) zum Zeitpunkt des Ankers und
    die Video-Entscheidung (RAFT-Motion der Szene) und persistiert beides
    in AIPacingMemory fuer zukuenftige Auto-Edits.

    Args:
        audio_track_id: ID des AudioTrack-Objekts
        anchor_time:    Zeitstempel im Audio (Sekunden)
        scene_id:       Optionale Scene.id fuer Clip-Kontext
        label:          Beschreibung der Regel

    Returns:
        True bei Erfolg, False bei Fehler
    """
    import datetime

    try:
        from database import nullpool_session
        with nullpool_session() as session:
            # DB-10 Fix: Prüfe ob referenzierte Objekte noch existieren
            audio = session.query(AudioTrack).filter(
                AudioTrack.id == audio_track_id,
                AudioTrack.deleted_at.is_(None),
            ).one_or_none()
            if audio is None:
                logger.warning(
                    "learn_from_anchor: AudioTrack %d existiert nicht mehr oder ist geloescht, ueberspringe.",
                    audio_track_id,
                )
                return False
            scene = None
            if scene_id is not None:
                scene = session.query(Scene).join(VideoClip).filter(
                    Scene.id == scene_id,
                    VideoClip.deleted_at.is_(None),
                ).one_or_none()
                if scene is None:
                    logger.warning(
                        "learn_from_anchor: Scene %d existiert nicht mehr oder VideoClip ist geloescht, ueberspringe.",
                        scene_id,
                    )
                    return False

            # ── Audio-Kontext laden ──
            bpm = audio.bpm if audio else None

            overall_energy = None
            beatgrid = session.query(Beatgrid).filter_by(
                audio_track_id=audio_track_id
            ).first()
            if beatgrid and beatgrid.energy_per_beat and beatgrid.beat_positions:
                # H7-FIX: Column(JSON) deserialisiert automatisch.
                # Backward-compat: isinstance-Check fuer alte doppelt-serialisierte Daten.
                energy_data = json.loads(beatgrid.energy_per_beat) if isinstance(beatgrid.energy_per_beat, str) else beatgrid.energy_per_beat
                beats_pos = json.loads(beatgrid.beat_positions) if isinstance(beatgrid.beat_positions, str) else beatgrid.beat_positions
                if beats_pos:
                    beats_arr = np.array(beats_pos)
                    idx = int(np.argmin(np.abs(beats_arr - anchor_time)))
                    if 0 <= idx < len(energy_data):
                        overall_energy = float(energy_data[idx])

            # Stimmung aus Energie ableiten
            if overall_energy is not None:
                if overall_energy > 0.75:
                    mood = "drop"
                elif overall_energy > 0.55:
                    mood = "peak"
                elif overall_energy > 0.35:
                    mood = "buildup"
                elif overall_energy > 0.2:
                    mood = "breakdown"
                else:
                    mood = "warmup"
            else:
                mood = None

            # ── Video/Szenen-Kontext laden ──
            raft_motion = None
            if scene:
                raft_motion = scene.energy  # Scene.energy = RAFT motion score

            # Cut-Typ aus Kontext ableiten
            is_energetic = (overall_energy or 0.5) > 0.65 or (raft_motion or 0.5) > 0.65
            cut_type = "hard_cut" if is_energetic else "crossfade"
            crossfade = 0.0 if cut_type == "hard_cut" else 1.5

            _MOOD_TO_SECTION = {"drop": "DROP", "peak": "DROP", "buildup": "BUILDUP", "breakdown": "BREAKDOWN", "warmup": "WARMUP"}
            section_type = _MOOD_TO_SECTION.get(mood, mood.upper() if mood else None)

            mem = AIPacingMemory(
                created_at=datetime.datetime.now(),
                bpm=bpm,
                overall_energy=overall_energy,
                mood=mood,
                audio_time=anchor_time,
                raft_motion=raft_motion,
                cut_type=cut_type,
                crossfade_duration=crossfade,
                section_type=section_type,
                scene_id=scene_id,
                audio_track_id=audio_track_id,
                label=label or f"Anker@{anchor_time:.1f}s",
            )
            session.add(mem)
            session.commit()
            logger.info(
                "AI Memory: Regel gespeichert id=%d bpm=%.1f mood=%s motion=%.2f",
                mem.id, bpm or 0.0, mood or "?", raft_motion or 0.0,
            )
            return True
    except Exception as exc:  # broad catch intentional — SQLAlchemy commit can raise many error types
        logger.error("learn_from_anchor fehlgeschlagen: %s", exc)
        return False


def record_rl_feedback(audio_track_id: int, sentiment: str, project_id: int = 1) -> bool:
    """Speichert RL-Feedback (thumbs up/down) als AIPacingMemory Eintrag."""
    from datetime import datetime
    try:
        from database import nullpool_session
        with nullpool_session() as session:
            track = session.query(AudioTrack).filter(
                AudioTrack.id == audio_track_id,
                AudioTrack.deleted_at.is_(None),
            ).one_or_none()
            if track is None:
                logger.warning(
                    "record_rl_feedback: AudioTrack %d existiert nicht mehr oder ist geloescht, ueberspringe.",
                    audio_track_id,
                )
                return False
            entry_count = session.query(TimelineEntry).filter_by(
                project_id=project_id, track="video"
            ).count()

            mem = AIPacingMemory(
                created_at=datetime.now(),
                audio_track_id=audio_track_id,
                bpm=track.bpm if track else None,
                label=f"rl_feedback_{sentiment}",
                mood=sentiment,
                cut_type=f"feedback_{entry_count}_clips",
            )
            session.add(mem)
            session.commit()
            logger.info("RL-Feedback gespeichert: %s, audio=%d, clips=%d",
                        sentiment, audio_track_id, entry_count)
            return True
    except Exception as exc:  # broad catch intentional — SQLAlchemy commit can raise many error types
        logger.error("record_rl_feedback fehlgeschlagen: %s", exc)
        return False


def _get_ai_memory_bias(bpm: float, overall_energy: float) -> dict | None:
    """Sucht aehnliche Audio-Situationen im KI-Gedaechtnis.

    Vergleicht BPM und Energie mit gespeicherten Lern-Beispielen.
    Gibt ein Bias-Dict zurueck das auto_edit_phase3 beeinflusst,
    oder None wenn kein aehnliches Beispiel gefunden wurde.

    Schwellwert: BPM-Abweichung < 15% UND Energie-Abweichung < 25%.
    """
    try:
        with Session(engine) as session:
            # P-025 Fix: .limit(50) um unbegrenztes Laden zu verhindern
            memories = session.query(AIPacingMemory).filter(
                AIPacingMemory.bpm.between(bpm * 0.85, bpm * 1.15),
                AIPacingMemory.overall_energy.between(overall_energy - 0.25, overall_energy + 0.25)
            ).limit(50).all()
            if not memories:
                return None

            best_score = 999.0
            best_mem = None

            for mem in memories:
                if mem.bpm is None:
                    continue
                bpm_sim = abs(mem.bpm - bpm) / max(bpm, 1.0)
                energy_sim = abs((mem.overall_energy or 0.5) - overall_energy)
                score = bpm_sim + energy_sim
                if score < best_score:
                    best_score = score
                    best_mem = mem

            # Schwellwert: zu unaehnlich → kein Einfluss
            if best_mem is None or best_score > 0.5:
                return None

            logger.info(
                "AI Memory Bias aktiv: score=%.3f bpm=%.1f->%.1f mood=%s label='%s'",
                best_score, bpm, best_mem.bpm or 0.0,
                best_mem.mood or "?", best_mem.label or "",
            )
            return {
                "preferred_motion": best_mem.raft_motion,
                "preferred_cut_type": best_mem.cut_type,
                "preferred_crossfade": best_mem.crossfade_duration,
                "mood": best_mem.mood,
                "label": best_mem.label,
                "similarity_score": best_score,
            }
    except Exception as exc:  # broad catch intentional — SQLAlchemy query can raise many error types
        logger.warning("AI Memory Abfrage fehlgeschlagen: %s", exc)
        return None


# ── Legacy wrapper (backward compat) ──

def auto_edit_to_beats(
    audio_id: int,
    video_clip_ids: list[int],
    total_duration: float = 60.0,
    pacing_curve: list[float] | None = None,
    tempo: int = 50,
) -> list[dict]:
    """Legacy Phase 2 wrapper — delegiert an Phase 3 Engine."""
    # Map tempo slider to base_cut_rate
    if tempo >= 80:
        rate = 1
    elif tempo >= 60:
        rate = 2
    elif tempo >= 40:
        rate = 4
    elif tempo >= 20:
        rate = 8
    else:
        rate = 16

    settings = AdvancedPacingSettings(
        base_cut_rate=rate,
        energy_reactivity=50,
        breakdown_behavior="halve",
        manual_density_curve=pacing_curve,
    )
    # Deferred import to avoid circular dependency
    from services.pacing_service import auto_edit_phase3
    segments, _ = auto_edit_phase3(audio_id, video_clip_ids, settings)

    result = []
    for seg in segments:
        if seg.start >= total_duration:
            break
        end = min(seg.end, total_duration)
        result.append({
            "video_id": seg.video_id,
            "start": seg.start,
            "end": end,
            "source_start": seg.source_start,
        })
    return result

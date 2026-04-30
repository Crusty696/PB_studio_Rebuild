"""Analysis Status Service — VAD-39.

Verwaltet den Analyse-Status pro Medien-Datei über alle Analyse-Schritte hinweg.
Persistiert Fortschritt in der `analysis_status` Tabelle und bietet API für
Start/Done/Error-Tracking sowie Completion-Percentage-Berechnung.

Siehe Plan: VAD-36 (Daten-Analyse Status Dashboard)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import nullpool_session, AnalysisStatus, VideoClip, AudioTrack, Scene, Beatgrid, WaveformData

logger = logging.getLogger(__name__)

# B-253: Pub/Sub fuer Analysis-Completion-Events. Loest das UI-Refresh-Loch
# wenn eine Pipeline ueber das ActionRegistry / agent_command_signal /
# auto_workflow laeuft (statt ueber den UI-Button-Pfad). Ohne diesen Hook
# wird die UI nach z.B. stem_separation nicht aktualisiert obwohl DB +
# Disk schon korrekt sind. Subscriber registrieren sich via
# register_completion_listener() und kriegen pro mark_completed-Aufruf
# (media_type, media_id, step_key, value_summary)-Notification.
#
# Listener laufen im Thread des mark_completed-Callers (oft Worker-BG-Thread).
# UI-Code MUSS die Notification an den Main-Thread queuen (z.B. via
# QObject.signal mit Qt.QueuedConnection oder QTimer.singleShot).
_completion_listeners: list[Callable[[str, int, str, dict], None]] = []


def register_completion_listener(callback: Callable[[str, int, str, dict], None]) -> None:
    """B-253: Registriert eine Funktion die bei jedem mark_completed gerufen wird.

    Signatur: ``callback(media_type, media_id, step_key, value_summary)``.

    Achtung: Listener laufen im Caller-Thread (oft Background-Worker). Wenn
    der Listener UI-Code anfasst, muss er explizit den Main-Thread bemuehen
    (Qt-Signal mit QueuedConnection / QTimer.singleShot).

    Listener-Exceptions werden geloggt aber NICHT propagiert — sonst koennte
    ein UI-Bug die DB-Pipeline kippen.
    """
    if callback not in _completion_listeners:
        _completion_listeners.append(callback)


def unregister_completion_listener(callback: Callable[[str, int, str, dict], None]) -> None:
    """B-253: Entfernt einen registrierten Listener (z.B. fuer Tests oder Reload)."""
    try:
        _completion_listeners.remove(callback)
    except ValueError:
        pass

# Definierte Analyse-Schritte pro Media-Type (aus VAD-36 Plan)
VIDEO_STEPS = [
    "metadata_extract",      # FFprobe Metadaten
    "scene_detection",       # PySceneDetect Szenen-Erkennung
    "motion_scores",         # RAFT Optical Flow
    "keyframe_extraction",   # FFmpeg Keyframe-Export
    "siglip_embeddings",     # SigLIP Visual Embeddings
    "vector_db_storage",     # Embedding-Speicherung
    "ai_scene_caption",      # Gemma Vision Captioning
    "scene_db_storage",      # Scene-Daten in DB
    "structure_enrichment",  # Studio-Brain: Role/Mood/StyleBucket/CompatEdges (T1.3)
]

AUDIO_STEPS = [
    "bpm_detection",         # BPM + Beat-Erkennung
    "waveform_analysis",     # 3-Band Rekordbox Waveform
    "key_detection",         # ML Key Detection
    "lufs_analysis",         # EBU R128 Loudness
    "mood_genre_classify",   # AI Mood/Genre Klassifikation
    "spectral_analysis",     # 8-Band Spektral-Analyse
    "structure_detection",   # Song-Struktur (DROP/INTRO/..)
    "stem_separation",       # Demucs 4-Stem Separation
]


def mark_started(media_type: str, media_id: int, step_key: str) -> None:
    """Markiert einen Analyse-Schritt als gestartet.

    Setzt status='running' und started_at=now.
    Wenn der Eintrag noch nicht existiert, wird er angelegt.
    """
    with nullpool_session() as session:
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
            AnalysisStatus.step_key == step_key,
        )
        entry = session.execute(stmt).scalar_one_or_none()

        if entry is None:
            entry = AnalysisStatus(
                media_type=media_type,
                media_id=media_id,
                step_key=step_key,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(entry)
        else:
            entry.status = "running"
            entry.started_at = datetime.now(timezone.utc)
            entry.error_message = None  # Clear previous error

        session.commit()
        logger.info("Analysis started: %s/%d/%s", media_type, media_id, step_key)


def mark_done(media_type: str, media_id: int, step_key: str, value_summary: dict[str, Any] | None = None) -> None:
    """Markiert einen Analyse-Schritt als abgeschlossen.

    Setzt status='done', completed_at=now und speichert value_summary.
    """
    with nullpool_session() as session:
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
            AnalysisStatus.step_key == step_key,
        )
        entry = session.execute(stmt).scalar_one_or_none()

        if entry is None:
            # Create new entry directly as done (for backwards compat with existing data)
            entry = AnalysisStatus(
                media_type=media_type,
                media_id=media_id,
                step_key=step_key,
                status="done",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                value_summary=value_summary,
            )
            session.add(entry)
        else:
            entry.status = "done"
            entry.completed_at = datetime.now(timezone.utc)
            entry.value_summary = value_summary
            entry.error_message = None

        session.commit()
        logger.info("Analysis completed: %s/%d/%s (summary: %s)",
                   media_type, media_id, step_key, value_summary)

    # B-253: Listener AUSSERHALB der Session benachrichtigen (verhindert
    # dass UI-Refreshs in der DB-Transaktion haengen). Snapshot der
    # Liste damit Listener die sich selbst entfernen kein RuntimeError
    # ausloesen.
    for cb in list(_completion_listeners):
        try:
            cb(media_type, media_id, step_key, value_summary or {})
        except Exception as e:
            logger.warning(
                "B-253: Completion-Listener %s fuer %s/%d/%s fehlgeschlagen: %s",
                getattr(cb, "__name__", repr(cb)), media_type, media_id, step_key, e,
            )


def mark_error(media_type: str, media_id: int, step_key: str, error_msg: str) -> None:
    """Markiert einen Analyse-Schritt als fehlgeschlagen.

    Setzt status='error' und speichert error_message.
    """
    with nullpool_session() as session:
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
            AnalysisStatus.step_key == step_key,
        )
        entry = session.execute(stmt).scalar_one_or_none()

        if entry is None:
            entry = AnalysisStatus(
                media_type=media_type,
                media_id=media_id,
                step_key=step_key,
                status="error",
                started_at=datetime.now(timezone.utc),
                error_message=error_msg,
            )
            session.add(entry)
        else:
            entry.status = "error"
            entry.error_message = error_msg

        session.commit()
        logger.error("Analysis error: %s/%d/%s — %s", media_type, media_id, step_key, error_msg)


def get_status(media_type: str, media_id: int) -> dict[str, AnalysisStatus]:
    """Liefert den Status aller Analyse-Schritte für eine Medien-Datei.

    Returns:
        Dict mit step_key -> AnalysisStatus Mapping.
        Fehlende Schritte haben automatisch status='pending'.
    """
    with nullpool_session() as session:
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
        )
        entries = session.execute(stmt).scalars().all()

        # Build result dict
        result: dict[str, AnalysisStatus] = {}
        for entry in entries:
            # Detach from session to avoid lazy-load issues
            session.expunge(entry)
            result[entry.step_key] = entry

        return result


def get_completion_percent(media_type: str, media_id: int) -> float:
    """Berechnet den Gesamt-Fortschritt als Prozentsatz (0.0 - 100.0).

    Zählt alle 'done' Steps und teilt durch die Gesamtzahl der Steps für den Media-Type.
    """
    steps = VIDEO_STEPS if media_type == "video" else AUDIO_STEPS
    total_steps = len(steps)

    if total_steps == 0:
        return 100.0

    status_dict = get_status(media_type, media_id)
    completed_count = sum(1 for step in steps if status_dict.get(step) and status_dict[step].status == "done")

    return (completed_count / total_steps) * 100.0


def infer_from_db(media_type: str, media_id: int) -> None:
    """Leitet den Analyse-Status aus existierenden DB-Daten ab.

    Migration-Helper: Setzt status='done' für Schritte, deren Daten bereits in der DB vorhanden sind.
    Beispiel: Wenn Scenes existieren -> scene_detection='done'

    Wird beim ersten Laden einer Datei aufgerufen, um bestehende Analysen zu erkennen.
    """
    with nullpool_session() as session:
        if media_type == "video":
            _infer_video_status(session, media_id)
        elif media_type == "audio":
            _infer_audio_status(session, media_id)
        else:
            logger.warning("Unknown media_type for infer_from_db: %s", media_type)


def _infer_video_status(session: Session, video_id: int) -> None:
    """Infer video analysis status from existing DB data."""
    video = session.get(VideoClip, video_id)
    if not video:
        return

    # metadata_extract: duration, width, height, fps vorhanden?
    if video.duration and video.width and video.height and video.fps:
        _ensure_status_done(session, "video", video_id, "metadata_extract", {
            "duration": video.duration,
            "resolution": f"{video.width}x{video.height}",
            "fps": video.fps,
            "codec": video.codec,
        })

    # scene_detection: Scenes vorhanden?
    stmt = select(Scene).where(Scene.video_clip_id == video_id)
    scenes = session.execute(stmt).scalars().all()
    if scenes:
        _ensure_status_done(session, "video", video_id, "scene_detection", {
            "scenes": len(scenes),
        })

        # scene_db_storage: implizit auch done wenn Scenes existieren
        _ensure_status_done(session, "video", video_id, "scene_db_storage", {
            "scenes": len(scenes),
        })

        # ai_scene_caption: wenn mindestens eine Scene ai_caption hat
        captioned_count = sum(1 for s in scenes if s.ai_caption)
        if captioned_count > 0:
            _ensure_status_done(session, "video", video_id, "ai_scene_caption", {
                "captioned_scenes": captioned_count,
            })

    session.commit()


def _infer_audio_status(session: Session, audio_id: int) -> None:
    """Infer audio analysis status from existing DB data."""
    audio = session.get(AudioTrack, audio_id)
    if not audio:
        return

    # bpm_detection: Beatgrid vorhanden?
    if audio.beatgrid:
        _ensure_status_done(session, "audio", audio_id, "bpm_detection", {
            "bpm": audio.beatgrid.bpm,
            "beats": len(audio.beatgrid.beat_positions or []),
        })

    # waveform_analysis: WaveformData vorhanden?
    if audio.waveform_data:
        _ensure_status_done(session, "audio", audio_id, "waveform_analysis", {
            "num_samples": audio.waveform_data.num_samples,
        })

    # key_detection: Key + key_confidence vorhanden?
    if audio.key and audio.key_confidence:
        _ensure_status_done(session, "audio", audio_id, "key_detection", {
            "key": audio.key,
            "confidence": audio.key_confidence,
        })

    # lufs_analysis: LUFS vorhanden?
    if audio.lufs is not None:
        _ensure_status_done(session, "audio", audio_id, "lufs_analysis", {
            "lufs": audio.lufs,
        })

    # mood_genre_classify: mood + genre vorhanden?
    if audio.mood or audio.genre:
        _ensure_status_done(session, "audio", audio_id, "mood_genre_classify", {
            "mood": audio.mood,
            "genre": audio.genre,
        })

    # spectral_analysis: spectral_bands vorhanden?
    if audio.spectral_bands:
        _ensure_status_done(session, "audio", audio_id, "spectral_analysis", {
            "bands": len(audio.spectral_bands) if isinstance(audio.spectral_bands, list) else "present",
        })

    # structure_detection: StructureSegments vorhanden?
    if audio.structure_segments:
        _ensure_status_done(session, "audio", audio_id, "structure_detection", {
            "segments": len(audio.structure_segments),
        })

    # stem_separation: Stem-Pfade vorhanden?
    stem_count = sum(1 for p in [
        audio.stem_vocals_path,
        audio.stem_drums_path,
        audio.stem_bass_path,
        audio.stem_other_path,
    ] if p)
    if stem_count > 0:
        _ensure_status_done(session, "audio", audio_id, "stem_separation", {
            "stems": stem_count,
        })

    session.commit()


def _ensure_status_done(session: Session, media_type: str, media_id: int, step_key: str, value_summary: dict[str, Any]) -> None:
    """Helper: Setzt status='done' nur wenn noch kein Eintrag existiert."""
    stmt = select(AnalysisStatus).where(
        AnalysisStatus.media_type == media_type,
        AnalysisStatus.media_id == media_id,
        AnalysisStatus.step_key == step_key,
    )
    entry = session.execute(stmt).scalar_one_or_none()

    if entry is None:
        entry = AnalysisStatus(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status="done",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            value_summary=value_summary,
        )
        session.add(entry)
        logger.info("Inferred status='done' for %s/%d/%s", media_type, media_id, step_key)

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

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from database import (
    AnalysisStatus,
    AudioTrack,
    Beatgrid,
    Scene,
    StructureSegment,
    VideoClip,
    WaveformData,
    nullpool_session,
)

logger = logging.getLogger(__name__)

# B-581: Spalten des UNIQUE-Constraints uq_analysis_status_media_step
# (database/models.py). Dienen als ON CONFLICT-Target fuer idempotente
# Upserts, damit zwei parallele Worker fuer denselben Schritt nicht am
# UNIQUE-Constraint scheitern (read-then-insert-Race -> IntegrityError).
_UQ_COLS = ["media_type", "media_id", "step_key"]

# B-820: Ein User-Cancel wird als status='error' plus dieser error_message
# modelliert (mark_cancelled). Der Marker ist die einzige Unterscheidung
# zwischen "abgebrochen" und "fehlgeschlagen" — beides liegt sonst als
# status='error' in derselben Spalte. _ensure_status_done() muss ihn kennen,
# sonst hebt der Reconciler abgebrochene Schritte wieder auf 'done'.
CANCELLED_MARKER = "cancelled"

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

# Stage-Sichtbarkeit (User 2026-07-17): Audio-V2 faehrt zusaetzlich onset +
# av_pacing — diese Steps werden ANGEZEIGT (Panel), zaehlen aber bewusst NICHT
# in die %-Basis (AUDIO_STEPS) und gaten nicht das Cockpit: sonst wuerden
# frueher voll analysierte Tracks ploetzlich <100% anzeigen.
AUDIO_STEPS_OPTIONAL = [
    "onset_detection",       # Onset-Erkennung (Cut-Snap-Grundlage)
    "av_pacing_curves",      # AV-Pacing-Kurven (Audio->Video-Bruecke)
]


def mark_started(media_type: str, media_id: int, step_key: str) -> None:
    """Markiert einen Analyse-Schritt als gestartet.

    Setzt status='running' und started_at=now.
    Wenn der Eintrag noch nicht existiert, wird er angelegt.
    """
    now = datetime.now(timezone.utc)
    with nullpool_session() as session:
        # B-581: Idempotenter Upsert gegen uq_analysis_status_media_step.
        # Ersetzt das read-then-insert-Pattern, bei dem zwei parallele
        # Worker beide None lasen und beide INSERTeten -> IntegrityError.
        # Endzustand der Row ist identisch zum vorigen if/else-Zweig.
        stmt = sqlite_insert(AnalysisStatus).values(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status="running",
            started_at=now,
        ).on_conflict_do_update(
            index_elements=_UQ_COLS,
            set_=dict(
                status="running",
                started_at=now,
                completed_at=None,
                error_message=None,
            ),
        )
        session.execute(stmt)
        session.commit()
        logger.info("Analysis started: %s/%d/%s", media_type, media_id, step_key)


def mark_done(media_type: str, media_id: int, step_key: str, value_summary: dict[str, Any] | None = None) -> None:
    """Markiert einen Analyse-Schritt als abgeschlossen.

    Setzt status='done', completed_at=now und speichert value_summary.
    """
    now = datetime.now(timezone.utc)
    with nullpool_session() as session:
        # B-581: Idempotenter Upsert gegen uq_analysis_status_media_step.
        # INSERT setzt started_at+completed_at; bei Konflikt bleibt das
        # bestehende started_at erhalten (Original-else setzte es ebenfalls
        # nicht) und nur completed_at/value_summary/status werden aktualisiert.
        stmt = sqlite_insert(AnalysisStatus).values(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status="done",
            started_at=now,
            completed_at=now,
            value_summary=value_summary,
        ).on_conflict_do_update(
            index_elements=_UQ_COLS,
            set_=dict(
                status="done",
                completed_at=now,
                value_summary=value_summary,
                error_message=None,
            ),
        )
        session.execute(stmt)
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
    now = datetime.now(timezone.utc)
    with nullpool_session() as session:
        # B-581: Idempotenter Upsert gegen uq_analysis_status_media_step.
        # Bei Konflikt bleibt started_at erhalten (Original-else fasste es
        # nicht an); nur status+error_message werden aktualisiert.
        stmt = sqlite_insert(AnalysisStatus).values(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status="error",
            started_at=now,
            error_message=error_msg,
        ).on_conflict_do_update(
            index_elements=_UQ_COLS,
            set_=dict(status="error", error_message=error_msg),
        )
        session.execute(stmt)
        session.commit()
        logger.error("Analysis error: %s/%d/%s — %s", media_type, media_id, step_key, error_msg)


def mark_degraded(
    media_type: str,
    media_id: int,
    step_key: str,
    reason: str,
    value_summary: dict[str, Any] | None = None,
) -> None:
    """Markiert einen Analyse-Schritt als degradiert ("hat geraten").

    Zwischenzustand zwischen ``done`` und ``error``: der Schritt ist
    durchgelaufen, das Ergebnis stammt aber aus einem Fallback-/Rate-Pfad
    (z.B. Key ``Am`` mit confidence 0.0, Spektral-Baender alle 0.0) oder ist
    inhaltlich leer. Vorher gab es dafuer keinen eigenen Zustand — solche
    Laeufe bekamen ``done`` und damit ein gruenes Haekchen im Panel.

    Bewusste Eigenschaften:
    - ``AnalysisStatus.status`` ist eine freie String-Spalte
      (``database/models.py``: ``Column(String, ...)``) ohne Enum/CHECK-
      Constraint — der neue Wert braucht KEINE Migration.
    - ``done``/``error`` bleiben semantisch unveraendert. ``degraded`` zaehlt
      NICHT als ``done``, d.h. ``get_completion_percent`` und
      ``get_completion_percent_map`` (die auf ``status == "done"`` filtern)
      werten es als nicht abgeschlossen.
    - ``error_message`` traegt den Grund (analog ``mark_error``), damit das
      Panel ihn anzeigen kann.
    - Es werden KEINE Completion-Listener benachrichtigt (das ist
      ``mark_done`` vorbehalten — ein geratenes Ergebnis ist kein
      Completion-Event).
    """
    now = datetime.now(timezone.utc)
    with nullpool_session() as session:
        # B-581-Muster: idempotenter Upsert gegen uq_analysis_status_media_step.
        stmt = sqlite_insert(AnalysisStatus).values(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status="degraded",
            started_at=now,
            completed_at=now,
            value_summary=value_summary,
            error_message=reason,
        ).on_conflict_do_update(
            index_elements=_UQ_COLS,
            set_=dict(
                status="degraded",
                completed_at=now,
                value_summary=value_summary,
                error_message=reason,
            ),
        )
        session.execute(stmt)
        session.commit()
        logger.warning(
            "Analysis degraded: %s/%d/%s — %s", media_type, media_id, step_key, reason,
        )


def mark_cancelled(media_type: str, media_id: int, step_key: str) -> None:
    """Markiert einen Analyse-Schritt als abgebrochen, retry-faehig aber ohne Error-Log."""
    now = datetime.now(timezone.utc)
    with nullpool_session() as session:
        # B-581: Idempotenter Upsert gegen uq_analysis_status_media_step.
        # Bei Konflikt bleibt started_at erhalten (Original-else fasste es
        # nicht an); nur status+error_message werden aktualisiert.
        stmt = sqlite_insert(AnalysisStatus).values(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status="error",
            started_at=now,
            error_message=CANCELLED_MARKER,
        ).on_conflict_do_update(
            index_elements=_UQ_COLS,
            set_=dict(
                status="error",
                completed_at=None,
                error_message=CANCELLED_MARKER,
            ),
        )
        session.execute(stmt)
        session.commit()
        logger.info("Analysis cancelled: %s/%d/%s", media_type, media_id, step_key)


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


def get_completion_percent_map(media_type: str, media_ids: list[int]) -> dict[int, float]:
    """Berechnet Analyse-Prozente fuer mehrere Medien in einem DB-Read."""
    ids = [int(media_id) for media_id in media_ids if media_id is not None]
    if not ids:
        return {}

    steps = VIDEO_STEPS if media_type == "video" else AUDIO_STEPS
    total_steps = len(steps)
    if total_steps == 0:
        return {media_id: 100.0 for media_id in ids}
    step_set = set(steps)

    done_counts = {media_id: 0 for media_id in ids}
    with nullpool_session() as session:
        rows = session.execute(
            select(AnalysisStatus.media_id, AnalysisStatus.step_key).where(
                AnalysisStatus.media_type == media_type,
                AnalysisStatus.media_id.in_(ids),
                AnalysisStatus.status == "done",
            )
        ).all()

    seen: set[tuple[int, str]] = set()
    for media_id, step_key in rows:
        if step_key not in step_set:
            continue
        key = (int(media_id), str(step_key))
        if key in seen:
            continue
        seen.add(key)
        done_counts[int(media_id)] = done_counts.get(int(media_id), 0) + 1

    return {
        media_id: (done_counts.get(media_id, 0) / total_steps) * 100.0
        for media_id in ids
    }


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
            return
        session.commit()


def infer_many_from_db(media_type: str, media_ids: list[int]) -> None:
    """Leitet fehlende Analyse-Status fuer mehrere Medien aus DB-Daten ab."""
    ids = [int(media_id) for media_id in media_ids if media_id is not None]
    if not ids:
        return
    with nullpool_session() as session:
        rows = session.execute(
            select(AnalysisStatus).where(
                AnalysisStatus.media_type == media_type,
                AnalysisStatus.media_id.in_(ids),
            )
        ).scalars().all()
        status_entries = {
            (int(entry.media_id), str(entry.step_key)): entry
            for entry in rows
        }
        if media_type == "video":
            prefetch = _prefetch_video_facts(session, ids)
            for media_id in ids:
                _infer_video_status(
                    session, media_id,
                    status_entries=status_entries, prefetch=prefetch,
                )
        elif media_type == "audio":
            prefetch = _prefetch_audio_facts(session, ids)
            for media_id in ids:
                _infer_audio_status(
                    session, media_id,
                    status_entries=status_entries, prefetch=prefetch,
                )
        else:
            logger.warning("Unknown media_type for infer_many_from_db: %s", media_type)
            return
        session.commit()


# B-811: Bulk-Vorabladen fuer ``infer_many_from_db``.
#
# ``infer_many_from_db`` buendelte bisher nur die AnalysisStatus-Abfrage; die
# eigentlichen Fakten holte es weiter PRO Medium. Gemessen an der realen
# Projekt-DB ``outputs/test-tabelle`` (366 Clips): 733 SQL-Statements fuer einen
# einzigen Aufruf — 2*N+1 (VideoClip-Spalten + Scene-Captions je Clip). Auf dem
# Audio-Pfad sind es 4*N+1. Der Aufruf haengt an ``get_all_video`` /
# ``get_all_audio``, also an JEDEM Medien-Tabellen-Refresh (Projekt-Open,
# nach jedem Import). Waehrenddessen gibt es keine einzige Logzeile: bei
# belegter DB (Hintergrund-Writer, busy_timeout) kostet jede Rundreise
# zusaetzlich Wartezeit, und der Nutzer sieht nur Stillstand.
#
# Die Vorab-Dicts liefern exakt dieselben Werte wie die Einzelabfragen; wo
# frueher ``.first()`` eine beliebige Zeile gewann, gewinnt jetzt die erste
# Zeile derselben Ergebnismenge (``setdefault``).


def _prefetch_video_facts(session: Session, ids: list[int]) -> dict[str, dict]:
    clips = {
        row.id: row
        for row in session.execute(
            select(
                VideoClip.id,
                VideoClip.duration,
                VideoClip.width,
                VideoClip.height,
                VideoClip.fps,
                VideoClip.codec,
            ).where(VideoClip.id.in_(ids))
        ).all()
    }
    captions: dict[int, list] = {}
    for clip_id, caption in session.execute(
        select(Scene.video_clip_id, Scene.ai_caption).where(
            Scene.video_clip_id.in_(ids)
        )
    ).all():
        captions.setdefault(int(clip_id), []).append((caption,))
    return {"clips": clips, "captions": captions}


def _prefetch_audio_facts(session: Session, ids: list[int]) -> dict[str, dict]:
    tracks = {
        row.id: row
        for row in session.execute(
            select(
                AudioTrack.id,
                AudioTrack.key,
                AudioTrack.key_confidence,
                AudioTrack.lufs,
                AudioTrack.mood,
                AudioTrack.genre,
                AudioTrack.spectral_bands,
                AudioTrack.stem_vocals_path,
                AudioTrack.stem_drums_path,
                AudioTrack.stem_bass_path,
                AudioTrack.stem_other_path,
            ).where(AudioTrack.id.in_(ids))
        ).all()
    }
    beatgrids: dict[int, Any] = {}
    for row in session.execute(
        select(
            Beatgrid.audio_track_id, Beatgrid.bpm, Beatgrid.beat_positions
        ).where(Beatgrid.audio_track_id.in_(ids))
    ).all():
        beatgrids.setdefault(int(row.audio_track_id), row)
    waveforms: dict[int, Any] = {}
    for row in session.execute(
        select(
            WaveformData.audio_track_id, WaveformData.num_samples
        ).where(WaveformData.audio_track_id.in_(ids))
    ).all():
        waveforms.setdefault(int(row.audio_track_id), row)
    segment_counts = {
        int(track_id): int(count)
        for track_id, count in session.execute(
            select(StructureSegment.audio_track_id, func.count())
            .where(StructureSegment.audio_track_id.in_(ids))
            .group_by(StructureSegment.audio_track_id)
        ).all()
    }
    return {
        "tracks": tracks,
        "beatgrids": beatgrids,
        "waveforms": waveforms,
        "segment_counts": segment_counts,
    }


def _infer_video_status(
    session: Session,
    video_id: int,
    status_entries: dict[tuple[int, str], AnalysisStatus] | None = None,
    prefetch: dict[str, dict] | None = None,
) -> None:
    """Infer video analysis status from existing DB data.

    B-620: Laedt nur die tatsaechlich benoetigten Spalten statt voller
    ORM-Entities. ``session.get(VideoClip)`` zog vorher via
    ``lazy='joined'``/``lazy='selectin'`` alle Relationships mit — volle
    Scene-Rows inkl. ``keyframe_paths``/``embedding_indices``/``ai_tags``
    plus ``audio_video_anchors``. Die json.loads-Decodes dieser Blobs
    hielten den GIL sekundenlang und froren den Qt-Main-Thread ein
    (E-Live-Freezes 2-14s, freeze_stacks.log 2026-07-13).
    Status-Werte und value_summary bleiben identisch.
    """
    # B-811: im Bulk-Pfad kommen die Fakten aus zwei Sammelabfragen statt aus
    # zwei Abfragen PRO Clip. Der Einzelpfad (infer_from_db) bleibt unveraendert.
    if prefetch is None:
        video = session.execute(
            select(
                VideoClip.duration,
                VideoClip.width,
                VideoClip.height,
                VideoClip.fps,
                VideoClip.codec,
            ).where(VideoClip.id == video_id)
        ).first()
    else:
        video = prefetch["clips"].get(video_id)
    if not video:
        return

    # metadata_extract: duration, width, height, fps vorhanden?
    if video.duration and video.width and video.height and video.fps:
        _ensure_status_done(session, "video", video_id, "metadata_extract", {
            "duration": video.duration,
            "resolution": f"{video.width}x{video.height}",
            "fps": video.fps,
            "codec": video.codec,
        }, status_entries)

    # scene_detection: Scenes vorhanden? (nur ai_caption-Spalte laden —
    # gebraucht werden Anzahl + Caption-Truthiness, keine Blob-Spalten)
    if prefetch is None:
        scene_captions = session.execute(
            select(Scene.ai_caption).where(Scene.video_clip_id == video_id)
        ).all()
    else:
        scene_captions = prefetch["captions"].get(video_id, [])
    if scene_captions:
        scene_count = len(scene_captions)
        _ensure_status_done(
            session,
            "video",
            video_id,
            "scene_detection",
            {"scenes": scene_count},
            status_entries,
            preserve_reanalysis_status=True,
        )

        # scene_db_storage: implizit auch done wenn Scenes existieren
        _ensure_status_done(session, "video", video_id, "scene_db_storage", {
            "scenes": scene_count,
        }, status_entries)

        # ai_scene_caption: wenn mindestens eine Scene ai_caption hat
        captioned_count = sum(1 for (caption,) in scene_captions if caption)
        if captioned_count > 0:
            _ensure_status_done(session, "video", video_id, "ai_scene_caption", {
                "captioned_scenes": captioned_count,
            }, status_entries)


def _infer_audio_status(
    session: Session,
    audio_id: int,
    status_entries: dict[tuple[int, str], AnalysisStatus] | None = None,
    prefetch: dict[str, dict] | None = None,
) -> None:
    """Infer audio analysis status from existing DB data.

    B-620: Laedt nur die tatsaechlich benoetigten Spalten statt voller
    ORM-Entities. ``session.get(AudioTrack)`` zog vorher via
    ``lazy='joined'`` Beatgrid (onset_*/energy_per_beat/...) und
    WaveformData (band_low/mid/high) komplett mit — megabyte-grosse
    JSON-Blobs, deren json.loads den GIL sekundenlang hielt und den
    Qt-Main-Thread einfror (E-Live-Freezes 2-14s, freeze_stacks.log
    2026-07-13, Frame sqltypes.py:2821 process/json.loads).
    Status-Werte und value_summary bleiben identisch.
    """
    # B-811: siehe _infer_video_status — Bulk-Pfad nutzt vorgeladene Fakten.
    if prefetch is None:
        audio = session.execute(
            select(
                AudioTrack.key,
                AudioTrack.key_confidence,
                AudioTrack.lufs,
                AudioTrack.mood,
                AudioTrack.genre,
                AudioTrack.spectral_bands,
                AudioTrack.stem_vocals_path,
                AudioTrack.stem_drums_path,
                AudioTrack.stem_bass_path,
                AudioTrack.stem_other_path,
            ).where(AudioTrack.id == audio_id)
        ).first()
    else:
        audio = prefetch["tracks"].get(audio_id)
    if not audio:
        return

    # bpm_detection: Beatgrid vorhanden? (nur bpm + beat_positions laden —
    # beat_positions wird fuer den beats-Count gebraucht; onset_*/energy-
    # Blobs bleiben ungeladen)
    if prefetch is None:
        beatgrid = session.execute(
            select(Beatgrid.bpm, Beatgrid.beat_positions).where(
                Beatgrid.audio_track_id == audio_id
            )
        ).first()
    else:
        beatgrid = prefetch["beatgrids"].get(audio_id)
    if beatgrid:
        _ensure_status_done(session, "audio", audio_id, "bpm_detection", {
            "bpm": beatgrid.bpm,
            "beats": len(beatgrid.beat_positions or []),
        }, status_entries)

    # waveform_analysis: WaveformData vorhanden? (band_low/mid/high NICHT laden)
    if prefetch is None:
        waveform = session.execute(
            select(WaveformData.num_samples).where(
                WaveformData.audio_track_id == audio_id
            )
        ).first()
    else:
        waveform = prefetch["waveforms"].get(audio_id)
    if waveform:
        _ensure_status_done(session, "audio", audio_id, "waveform_analysis", {
            "num_samples": waveform.num_samples,
        }, status_entries)

    # key_detection: Key + key_confidence vorhanden?
    if audio.key and audio.key_confidence:
        _ensure_status_done(session, "audio", audio_id, "key_detection", {
            "key": audio.key,
            "confidence": audio.key_confidence,
        }, status_entries)

    # lufs_analysis: LUFS vorhanden?
    if audio.lufs is not None:
        _ensure_status_done(session, "audio", audio_id, "lufs_analysis", {
            "lufs": audio.lufs,
        }, status_entries)

    # mood_genre_classify: mood + genre vorhanden?
    if audio.mood or audio.genre:
        _ensure_status_done(session, "audio", audio_id, "mood_genre_classify", {
            "mood": audio.mood,
            "genre": audio.genre,
        }, status_entries)

    # spectral_analysis: spectral_bands vorhanden?
    if audio.spectral_bands:
        _ensure_status_done(session, "audio", audio_id, "spectral_analysis", {
            "bands": len(audio.spectral_bands) if isinstance(audio.spectral_bands, list) else "present",
        }, status_entries)

    # structure_detection: StructureSegments vorhanden? (COUNT statt
    # selectin-Load aller Segment-Rows)
    if prefetch is None:
        segment_count = session.execute(
            select(func.count()).select_from(StructureSegment).where(
                StructureSegment.audio_track_id == audio_id
            )
        ).scalar_one()
    else:
        segment_count = prefetch["segment_counts"].get(audio_id, 0)
    if segment_count:
        _ensure_status_done(session, "audio", audio_id, "structure_detection", {
            "segments": segment_count,
        }, status_entries)

    # stem_separation: Stem-Pfade vorhanden?
    # B-822: ein gesetzter Pfad allein genuegt nicht. Nach einer Projektkopie
    # zeigen die Spalten auf den alten Ort; solche Stems gehoeren nicht zu
    # diesem Projekt und duerfen es nicht als analysiert ausweisen.
    # Bewusst die schwaechere Pruefung: ob die Datei gerade existiert, bleibt
    # egal — B-461 reconciled fehlende Artefakte absichtlich.
    from services.stem_router import points_outside_project
    stem_count = sum(1 for p in [
        audio.stem_vocals_path,
        audio.stem_drums_path,
        audio.stem_bass_path,
        audio.stem_other_path,
    ] if p and not points_outside_project(p))
    if stem_count > 0:
        _ensure_status_done(session, "audio", audio_id, "stem_separation", {
            "stems": stem_count,
        }, status_entries)


def _ensure_status_done(
    session: Session,
    media_type: str,
    media_id: int,
    step_key: str,
    value_summary: dict[str, Any],
    status_entries: dict[tuple[int, str], AnalysisStatus] | None = None,
    *,
    preserve_reanalysis_status: bool = False,
) -> None:
    """Helper: Hebt einen Schritt auf status='done', wenn die DB es belegt.

    Legt einen fehlenden Eintrag an und reconciled einen vorhandenen, der noch
    nicht 'done' ist (B-461: ein echter Fehler wie ein FFmpeg-Timeout gilt als
    behoben, sobald der Wert nachweislich in der DB steht).

    B-820: Ausgenommen ist der bewusste User-Cancel
    (``status='error'`` plus ``error_message=CANCELLED_MARKER``). Eine Stage
    persistiert ihr Artefakt, bevor der Cancel-Check greift — die blosse
    Existenz des Artefakts belegt also NICHT, dass der Schritt regulaer zu Ende
    lief. Ohne diese Ausnahme wuerde der naechste Status-Refresh den Abbruch
    stillschweigend in einen Erfolg umdeuten und die ``error_message``
    loeschen; der Nutzer saehe 'fertig' fuer etwas, das er selbst abgebrochen
    hat, und verloere das Retry-Angebot.

    B-871/B-872: Fuer Artefakte, die bei einer Reanalyse bewusst erhalten
    bleiben, kann ``preserve_reanalysis_status`` einen aktuellen Fehler oder
    laufenden Schritt vor veralteter DB-Evidenz schuetzen. Erfolgreiche Worker
    setzen den Schritt selbst via ``mark_done``.
    """
    key = (media_id, step_key)
    if status_entries is None:
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
            AnalysisStatus.step_key == step_key,
        )
        entry = session.execute(stmt).scalar_one_or_none()
    else:
        entry = status_entries.get(key)

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
        if status_entries is not None:
            status_entries[key] = entry
        logger.info("Inferred status='done' for %s/%d/%s", media_type, media_id, step_key)
    elif (
        entry.status == "error"
        and (
            entry.error_message == CANCELLED_MARKER
            or preserve_reanalysis_status
        )
    ) or (
        entry.status == "running" and preserve_reanalysis_status
    ):
        # B-820/B-871/B-872: User-Cancel, aktueller Reanalysefehler oder
        # laufende Reanalyse bleibt stehen; Artefakte koennen alt sein.
        logger.debug(
            "Kept status=%s for %s/%d/%s (kein Reconcile auf 'done')",
            entry.status,
            media_type,
            media_id,
            step_key,
        )
    elif entry.status != "done":
        entry.status = "done"
        entry.completed_at = datetime.now(timezone.utc)
        entry.value_summary = value_summary
        entry.error_message = None
        logger.info(
            "Reconciled status='done' for %s/%d/%s from DB evidence",
            media_type,
            media_id,
            step_key,
        )

"""Brain V3 project state helpers.

Reads project-local ``brain_v3/state.db`` and resolves current timeline cuts
against the main PB Studio DB for UI feedback and learning previews.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager

from sqlalchemy import select, text  # B-090: column-select statt Blob-Voll-Load

import database
import database.session as db_session_module
from services.brain import paths
from services.brain.schemas.brain_v3_schemas import LearningSampleCut
from services.brain.storage.migration_runner import migrate

logger = logging.getLogger(__name__)


SessionFactory = Callable[[], ContextManager[object]]


@dataclass(frozen=True)
class BrainV3TimelineCutMeta:
    cut_id: int
    clip_id: int
    start_time: float
    confidence: float | None


def default_project_root() -> Path:
    return Path(db_session_module.APP_ROOT)


def state_db_path(project_root: Path | None = None) -> Path:
    return paths.project_state_db_path(Path(project_root or default_project_root()))


def ensure_state_db(project_root: Path | None = None) -> Path:
    db_path = state_db_path(project_root)
    migrations_dir = Path(__file__).resolve().parent / "storage" / "sql_migrations" / "state"
    migrate(db_path, migrations_dir)
    return db_path



# B-781: Achsen-Scores der Entscheidungen des juengsten Pacing-Runs zu genau
# diesem Audio-Track. ``agent_rationale -> brain_v3_scores`` ist die EINZIGE
# Stelle im System, an der echte Sub-Scores pro Bridge-Achse liegen
# (services/pacing/pipeline.py:675, geschrieben vom DecisionRecorder).
# Join ueber ``scenes`` liefert den video_clip, damit ein Treffer nicht nur
# ueber die Zeit, sondern auch ueber den tatsaechlich geschnittenen Clip
# verifiziert ist.
_DECISION_AXIS_SCORES_SQL = text(
    "SELECT d.at_timestamp_sec AS ts, "
    "       s.video_clip_id    AS video_clip_id, "
    "       d.agent_rationale  AS agent_rationale "
    "FROM mem_decision d "
    "LEFT JOIN scenes s ON s.id = d.scene_id "
    "WHERE d.run_id = ("
    "    SELECT id FROM mem_pacing_run WHERE audio_track_id = :aid "
    "    ORDER BY started_at DESC, id DESC LIMIT 1"
    ")"
)


def _load_decision_axis_scores(
    audio_clip_id: int,
    session_factory: SessionFactory | None,
) -> dict[tuple[int, int], dict[str, float]]:
    """B-781: ``{(video_clip_id, start_ms): {achse: score}}`` des juengsten Runs.

    Best-effort: fehlende ``mem_*``-Tabellen (abgespeckte Test-Fixtures),
    DB-Fehler oder ein Projekt ohne Pacing-Run liefern ``{}``. Der Sync faellt
    dann auf den alten Platzhalter zurueck, statt Zahlen zu erfinden.
    """
    from services.brain.feedback_logger import axis_contributions_from_rationale

    sf = session_factory or database.nullpool_session
    try:
        with sf() as session:
            rows = session.execute(
                _DECISION_AXIS_SCORES_SQL, {"aid": int(audio_clip_id)}
            ).mappings().all()
    except Exception as exc:  # broad: Sync darf daran nie scheitern
        logger.info(
            "Brain V3 sync: Achsen-Scores nicht lesbar (%s) — "
            "timeline_cuts behalten den Confidence-Platzhalter.", exc,
        )
        return {}

    out: dict[tuple[int, int], dict[str, float]] = {}
    for row in rows:
        clip_id = row.get("video_clip_id")
        if clip_id is None:
            continue
        rationale = row.get("agent_rationale")
        if isinstance(rationale, str):
            try:
                rationale = json.loads(rationale)
            except (TypeError, ValueError):
                continue
        if not isinstance(rationale, dict):
            continue
        scores = axis_contributions_from_rationale(rationale)
        if not scores:
            continue
        try:
            key = (int(clip_id), _round_ms(float(row.get("ts") or 0.0)))
        except (TypeError, ValueError):
            continue
        out.setdefault(key, scores)
    return out


def sync_current_timeline_from_entries(
    project_root: Path | None,
    entries: list[object],
    session_factory: SessionFactory | None = None,
) -> bool:
    """Create/update Brain-V3 current timeline from main TimelineEntry rows.

    Matching current Brain-V3 timelines are preserved. Stale current timelines
    are kept in the DB but lose ``is_current`` so the UI can map the live
    main timeline to confidence metadata.

    B-781: ``brain_v3_scores_json`` bekommt die ECHTEN Achsen-Sub-Scores der
    Entscheidung hinter dem jeweiligen Cut, sofern eine ``mem_decision``-Zeile
    des juengsten Runs auf (video_clip_id, Timeline-Startzeit) passt. Nur so
    hat der Lern-Dialog ueberhaupt eine Quelle fuer ``axis_contributions``;
    ohne sie verteilt jeder Klick uniformen Credit ueber alle 18 Achsen und
    kann die relative Gewichtung mathematisch nicht veraendern.

    Ohne Treffer (kein Pacing-Run, Reranker lief nicht, Segment wurde nach der
    Entscheidung verschoben/geklemmt) bleibt der alte Platzhalter stehen —
    bewusst, statt Achsenwerte zu erfinden.
    """
    db_path = ensure_state_db(project_root)
    entries = list(entries or [])
    audio_entries = [e for e in entries if getattr(e, "track", None) == "audio"]
    video_entries = [e for e in entries if getattr(e, "track", None) == "video"]
    if not audio_entries or not video_entries:
        return False

    # B-373: change-detection signature must include end_time and clip_start
    # (source offset), not only (media_id, start_time). A change to source
    # offset or duration on the same clip + same timeline start would
    # otherwise be missed and the current timeline never re-synced.
    expected_video_keys = []
    for entry in sorted(video_entries, key=lambda e: float(e.start_time or 0.0)):
        start = float(getattr(entry, "start_time", 0.0) or 0.0)
        end_raw = getattr(entry, "end_time", None)
        end = float(end_raw) if end_raw is not None else start + 1.0
        clip_start = float(getattr(entry, "source_start", 0.0) or 0.0)
        expected_video_keys.append((
            int(getattr(entry, "media_id")),
            _round_ms(start),
            _round_ms(max(end, start)),
            _round_ms(clip_start),
        ))

    with sqlite3.connect(db_path) as conn:
        existing_rows = conn.execute(
            """
            SELECT c.id, c.clip_id, c.start_time, c.end_time, c.clip_start,
                   c.brain_v3_scores_json
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            ORDER BY c.position_idx ASC, c.id ASC
            """
        ).fetchall()
        existing_video_keys = []
        # B-784: Parallel-Liste (Row-ID, Cut-Schluessel, gespeicherte Scores),
        # damit der Score-Refresh unten die Zeile wiederfindet, ohne sich auf
        # die Index-Gleichheit mit ``existing_video_keys`` zu verlassen
        # (unparsbare Zeilen werden dort uebersprungen).
        existing_score_rows: list[tuple[int, tuple[int, int], str | None]] = []
        for row_id, clip_id, start_time, end_time, clip_start, scores_json in existing_rows:
            try:
                key = (
                    int(clip_id),
                    _round_ms(float(start_time or 0.0)),
                    _round_ms(float(end_time or 0.0)),
                    _round_ms(float(clip_start or 0.0)),
                )
                cut_row_id = int(row_id)
            except (TypeError, ValueError):
                continue
            existing_video_keys.append(key)
            existing_score_rows.append((cut_row_id, (key[0], key[1]), scores_json))

        audio_clip_id = int(audio_entries[0].media_id)
        if existing_video_keys == expected_video_keys:
            # B-784 Teil 2: Geometrie unveraendert heisst NICHT "nichts zu tun".
            # Ein erneuter Pacing-Run mit identischem Schnittbild erzeugt neue
            # ``mem_decision``-Zeilen; ohne Nachtrag blieben die Achsen-Scores
            # der Cuts veraltet bzw. leer und der Lern-Dialog im
            # Uniform-Fallback (siehe B-781).
            return _refresh_axis_scores_in_place(
                conn, existing_score_rows, audio_clip_id, session_factory,
            )

        # B-781: echte Achsen-Scores der Entscheidungen nachladen (best-effort).
        axis_scores_by_cut = _load_decision_axis_scores(
            audio_clip_id, session_factory,
        )
        conn.execute("UPDATE timelines SET is_current = 0 WHERE is_current = 1")
        cur = conn.execute(
            "INSERT INTO timelines(name, audio_clip_id, created_at, config_json, is_current) "
            "VALUES (?, ?, ?, ?, 1)",
            (
                "main-timeline-sync",
                audio_clip_id,
                datetime.now(timezone.utc).isoformat(),
                '{"source": "main_timeline"}',
            ),
        )
        timeline_id = int(cur.lastrowid)
        for idx, entry in enumerate(sorted(video_entries, key=lambda e: float(e.start_time or 0.0))):
            start = float(getattr(entry, "start_time", 0.0) or 0.0)
            end_raw = getattr(entry, "end_time", None)
            end = float(end_raw) if end_raw is not None else start + 1.0
            clip_start = float(getattr(entry, "source_start", 0.0) or 0.0)
            # B-781: Achsen-Scores dieser konkreten Entscheidung, falls
            # (Clip, Startzeit) exakt auf eine mem_decision-Zeile passt.
            scores = axis_scores_by_cut.get(
                (int(entry.media_id), _round_ms(start))
            )
            scores_json = (
                json.dumps({"confidence": 0.5, "brain_v3_scores": scores})
                if scores
                else '{"confidence": 0.5}'
            )
            conn.execute(
                """
                INSERT INTO timeline_cuts(
                    timeline_id, position_idx, clip_id, start_time, end_time,
                    clip_start, brain_v3_scores_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timeline_id,
                    idx,
                    str(int(entry.media_id)),
                    start,
                    max(end, start),
                    clip_start,
                    scores_json,
                    '{"brain_v3_confidence": 0.5, "source": "main_timeline_sync"}',
                ),
            )
        conn.commit()
    return True


def _refresh_axis_scores_in_place(
    conn: sqlite3.Connection,
    rows: list[tuple[int, tuple[int, int], str | None]],
    audio_clip_id: int,
    session_factory: SessionFactory | None,
) -> bool:
    """B-784 Teil 2: Achsen-Scores nachtragen, ohne die Timeline neu zu bauen.

    Die Change-Detection von ``sync_current_timeline_from_entries`` verglich bis
    B-784 ausschliesslich die Geometrie. Lief ein zweiter Pacing-Run mit
    identischem Schnittbild, kehrte der Sync mit ``False`` zurueck und die
    frischen ``mem_decision``-Achsenwerte erreichten ``timeline_cuts`` nie.

    Geschrieben wird nur, was sich tatsaechlich unterscheidet — ist alles
    identisch (oder gibt es gar keine Entscheidungen), bleibt die DB
    unangetastet und der Sync meldet weiterhin ``False``.

    Args:
        rows: ``(timeline_cuts.id, (clip_id, start_ms), brain_v3_scores_json)``.
    """
    if not rows:
        return False
    axis_scores_by_cut = _load_decision_axis_scores(audio_clip_id, session_factory)
    if not axis_scores_by_cut:
        return False

    updated = 0
    for row_id, cut_key, scores_json in rows:
        scores = axis_scores_by_cut.get(cut_key)
        if not scores:
            continue
        data = _json_dict(scores_json)
        if data.get("brain_v3_scores") == scores:
            continue
        data["brain_v3_scores"] = scores
        conn.execute(
            "UPDATE timeline_cuts SET brain_v3_scores_json = ? WHERE id = ?",
            (json.dumps(data), row_id),
        )
        updated += 1
    if updated:
        conn.commit()
        logger.info(
            "B-784: %d timeline_cuts mit frischen Achsen-Scores aktualisiert "
            "(Geometrie unveraendert).", updated,
        )
    return bool(updated)


def sync_current_timeline_after_apply(
    project_id: int | None = None,
    project_root: Path | None = None,
    session_factory: SessionFactory | None = None,
) -> bool:
    """B-784: Brain-V3-Lernzustand aus den echten ``TimelineEntry``-Zeilen ziehen.

    Produktions-Einstieg fuer ``sync_current_timeline_from_entries``. Vorher gab
    es ausser Tests keinen Aufrufer — ``timeline_cuts`` blieb in beiden echten
    ``brain_v3/state.db`` leer und ``BrainV3Service.learning_session`` fiel
    immer auf den Weight-Bucket-Sampler ohne Medienpfade zurueck.

    Aufgerufen wird das nach dem Auto-Edit-Apply: dort steht die Timeline
    genau so in der Haupt-DB, wie der Pacing-Run sie erzeugt hat, und die
    passenden ``mem_decision``-Zeilen des juengsten Runs liegen vor.

    Faellt NIE mit einer Exception aus — der Apply darf daran nicht scheitern.

    Returns:
        ``True``, wenn ``state.db`` veraendert wurde.
    """
    try:
        if project_id is None:
            from database import get_active_project_id

            project_id = get_active_project_id()
        if project_id is None:
            logger.info(
                "B-784: kein aktives Projekt — Brain-V3-Timeline-Sync uebersprungen.")
            return False

        sf = session_factory or database.nullpool_session
        with sf() as session:
            # column-select statt ORM-Voll-Load: der Sync liest nur diese
            # fuenf Skalare (Muster B-090).
            entries = list(
                session.execute(
                    select(
                        database.TimelineEntry.track,
                        database.TimelineEntry.media_id,
                        database.TimelineEntry.start_time,
                        database.TimelineEntry.end_time,
                        database.TimelineEntry.source_start,
                    ).where(database.TimelineEntry.project_id == int(project_id))
                ).all()
            )
        return sync_current_timeline_from_entries(
            project_root, entries, session_factory,
        )
    except Exception as exc:  # broad: darf den Apply nie brechen
        logger.warning(
            "B-784: Brain-V3-Timeline-Sync nach Apply fehlgeschlagen: %s",
            exc, exc_info=True,
        )
        return False


def load_learning_preview_samples(
    project_root: Path | None = None,
    session_factory: SessionFactory | None = None,
    n: int = 15,
) -> list[LearningSampleCut]:
    """Resolve current timeline cuts to real audio/video preview paths."""
    db_path = ensure_state_db(project_root)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                c.id, c.clip_id, c.start_time, c.end_time, c.clip_start,
                c.brain_v3_scores_json, c.metadata_json, t.audio_clip_id
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            ORDER BY c.position_idx ASC, c.id ASC
            LIMIT ?
            """,
            (max(0, int(n)),),
        ).fetchall()
    if not rows:
        return []

    sf = session_factory or database.nullpool_session
    audio_ids = sorted({int(r[7]) for r in rows if r[7] is not None})
    video_ids = []
    for r in rows:
        try:
            video_ids.append(int(r[1]))
        except (TypeError, ValueError):
            continue

    with sf() as session:
        audios = (
            {
                # B-636/B-090: column-select (id/file_path) statt Voll-ORM-Load —
                # AudioTrack.beatgrid/waveform_data sind lazy='joined' und wuerden
                # sonst bei jedem Track die JSON-Blobs eager mitziehen, obwohl
                # nur file_path gebraucht wird (Folgecode unten).
                a.id: str(a.file_path) if a.file_path else None
                for a in session.execute(
                    select(database.AudioTrack.id, database.AudioTrack.file_path).where(
                        database.AudioTrack.id.in_(audio_ids),
                        database.AudioTrack.deleted_at.is_(None),
                    )
                ).all()
            }
            if audio_ids
            else {}
        )
        fallback_audio_path = _resolve_timeline_audio_path(
            session=session,
            project_root=project_root,
        )
        videos = (
            {
                # B-090: column-select (id/proxy_path/file_path) statt Voll-ORM-Load
                # mit lazy='joined' scenes-Blob; Folgecode nutzt nur diese Skalare.
                v.id: _existing_media_path(v.proxy_path, v.file_path)
                for v in session.execute(
                    select(
                        database.VideoClip.id,
                        database.VideoClip.proxy_path,
                        database.VideoClip.file_path,
                    ).where(
                        database.VideoClip.id.in_(video_ids),
                        database.VideoClip.deleted_at.is_(None),
                    )
                ).all()
            }
            if video_ids
            else {}
        )

    samples: list[LearningSampleCut] = []
    for r in rows:
        try:
            clip_id = int(r[1])
        except (TypeError, ValueError):
            continue
        audio = audios.get(int(r[7])) or fallback_audio_path
        video = videos.get(clip_id)
        if audio is None or video is None:
            continue
        audio_path = audio
        video_path = video
        confidence = _extract_confidence(r[5], r[6])
        duration = max(0.0, float(r[3] or 0.0) - float(r[2] or 0.0))
        samples.append(
            LearningSampleCut(
                cut_id=int(r[0]),
                audio_position_s=float(r[2] or 0.0),
                video_position_s=float(r[4] or 0.0),
                preview_duration_s=duration,
                clip_id=clip_id,
                audio_preview_path=audio_path,
                video_preview_path=video_path,
                has_preview=bool(audio_path or video_path),
                uncertainty=_confidence_to_uncertainty(confidence),
            )
        )
    return samples


def load_learning_axis_contributions(
    project_root: Path | None = None,
    cut_ids: list[int] | None = None,
) -> dict[int, dict[str, float]]:
    """B-781: Achsen-Beitraege je Lern-Session-Cut aus ``state.db``.

    Quelle ist ``timeline_cuts.brain_v3_scores_json`` — dort schreibt
    ``sync_current_timeline_from_entries`` seit B-781 die echten Sub-Scores
    der Entscheidung (Key ``brain_v3_scores``, identisches Vokabular wie
    ``mem_decision.agent_rationale``). Die Auswertung laeuft deshalb ueber
    denselben ``axis_contributions_from_rationale``-Parser wie der
    Timeline-Pfad — kein zweites Format.

    Bestandszeilen enthalten nur ``{"confidence": 0.5}``. Dafuer gibt es
    keinen Eintrag im Ergebnis; der Aufrufer bleibt dann korrekt im
    Uniform-Fallback statt Achsenwerte zu erfinden.

    Returns:
        ``{cut_id: {achse: score}}`` — nur fuer Cuts mit echten Scores.
    """
    from services.brain.feedback_logger import axis_contributions_from_rationale

    wanted = {int(c) for c in cut_ids} if cut_ids else None

    db_path = ensure_state_db(project_root)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.brain_v3_scores_json
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            ORDER BY c.position_idx ASC, c.id ASC
            """
        ).fetchall()

    out: dict[int, dict[str, float]] = {}
    for row in rows:
        try:
            cut_id = int(row[0])
        except (TypeError, ValueError):
            continue
        if wanted is not None and cut_id not in wanted:
            continue
        contribs = axis_contributions_from_rationale(_json_dict(row[1]))
        if contribs:
            out[cut_id] = contribs
    return out


def load_learning_cut_contexts(
    project_root: Path | None = None,
    session_factory: SessionFactory | None = None,
    cut_ids: list[int] | None = None,
) -> dict[int, "object"]:
    """B-733: echter ``CutContext`` je Lern-Session-Cut.

    Der Lern-Dialog schickte bisher ``CutContext()`` — jedes Feedback landete
    damit auf demselben Default-Backoff-Schluessel und der 6-stufige Backoff
    im WeightStore lief leer.

    Belegte Quellen (alles echte Messwerte, nichts geraten):
      - ``timeline_cuts.start_time``  -> Audio-Position des Cuts (state.db)
      - ``structure_segments``        -> Section-Label + Segment-Energie +
                                         Segment-Grenzen fuer die
                                         Subtrack-Position (Haupt-DB)
      - ``audio_tracks.mood`` / ``.bpm`` -> Mood-Slot und Pace-Klasse

    NICHT belegt und deshalb bewusst auf dem neutralen Default:
      - ``video_motion_class``. In ``state.db`` steht pro Cut kein
        Motion-Wert, und ``timeline_cuts.metadata_json`` fuehrt nur
        ``brain_v3_confidence``/``source`` (siehe
        ``sync_current_timeline_from_entries``). Raten waere hier ein
        falsches Lern-Signal, deshalb bleibt der Slot auf "medium".

    Returns:
        ``{cut_id: CutContext}``. Cuts ohne aufloesbare Section fehlen im
        Ergebnis — der Aufrufer muss den fehlenden Kontext dann ehrlich
        kennzeichnen statt einen Default zu erfinden.
    """
    from services.brain.context_mapping import (
        ContextMappingConfig,
        build_cut_context,
    )
    from services.brain.context_resolver import (
        quantize_subtrack_position,
        quantize_tertile,
    )

    wanted = {int(c) for c in cut_ids} if cut_ids else None

    db_path = ensure_state_db(project_root)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.start_time, c.segment_type, t.audio_clip_id
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            ORDER BY c.position_idx ASC, c.id ASC
            """
        ).fetchall()
    cuts: list[tuple[int, float, str | None, int | None]] = []
    for row in rows:
        try:
            cut_id = int(row[0])
        except (TypeError, ValueError):
            continue
        if wanted is not None and cut_id not in wanted:
            continue
        audio_id: int | None
        try:
            audio_id = int(row[3]) if row[3] is not None else None
        except (TypeError, ValueError):
            audio_id = None
        cuts.append((cut_id, float(row[1] or 0.0), row[2], audio_id))
    if not cuts:
        return {}

    audio_ids = sorted({c[3] for c in cuts if c[3] is not None})
    sf = session_factory or database.nullpool_session
    tracks: dict[int, tuple[str | None, float | None]] = {}
    segments: dict[int, list[tuple[float, float, str, float | None]]] = {}
    if audio_ids:
        with sf() as session:
            for tid, mood, bpm in session.execute(
                select(
                    database.AudioTrack.id,
                    database.AudioTrack.mood,
                    database.AudioTrack.bpm,
                ).where(database.AudioTrack.id.in_(audio_ids))
            ).all():
                tracks[int(tid)] = (mood, bpm)
            for tid, start, end, label, energy in session.execute(
                select(
                    database.StructureSegment.audio_track_id,
                    database.StructureSegment.start_time,
                    database.StructureSegment.end_time,
                    database.StructureSegment.label,
                    database.StructureSegment.energy,
                )
                .where(database.StructureSegment.audio_track_id.in_(audio_ids))
                .order_by(database.StructureSegment.start_time.asc())
            ).all():
                segments.setdefault(int(tid), []).append(
                    (float(start or 0.0), float(end or 0.0), str(label or ""),
                     None if energy is None else float(energy))
                )

    # Tertil-Schwellen aus den ECHTEN Segment-Energien des jeweiligen Tracks.
    # Feste 0.33/0.66 waeren bei einem durchgehend lauten DJ-Mix sinnlos.
    thresholds: dict[int, tuple[float, float]] = {}
    for tid, segs in segments.items():
        energies = sorted(e for _s, _e, _l, e in segs if e is not None)
        if len(energies) >= 3:
            thresholds[tid] = (
                energies[int(len(energies) * 0.33)],
                energies[int(len(energies) * 0.66)],
            )

    cfg = ContextMappingConfig(pace_source="audio_bpm")
    out: dict[int, object] = {}
    for cut_id, position_s, segment_type, audio_id in cuts:
        segs = segments.get(audio_id or -1, [])
        seg = _segment_at(segs, position_s)
        raw_section = (segment_type or (seg[2] if seg else "")).strip()
        if not raw_section:
            continue  # keine Section-Quelle -> keinen Kontext erfinden
        mood, bpm = tracks.get(audio_id or -1, (None, None))
        if seg is not None and seg[3] is not None:
            p33, p66 = thresholds.get(audio_id or -1, (0.33, 0.66))
            energy_level = quantize_tertile(seg[3], p33, p66)
        else:
            energy_level = "medium"
        subpos = (
            quantize_subtrack_position(position_s, seg[0], seg[1])
            if seg is not None else "middle"
        )
        out[cut_id] = build_cut_context(
            raw_section=raw_section,
            raw_mood=str(mood or "neutral"),
            raw_subtrack_position=subpos,
            raw_energy_level=energy_level,
            raw_motion_class="medium",  # keine Quelle in state.db — s. Docstring
            cfg=cfg,
            audio_bpm=bpm,
        )
    return out


def _segment_at(
    segments: list[tuple[float, float, str, float | None]],
    position_s: float,
) -> tuple[float, float, str, float | None] | None:
    """Segment, das ``position_s`` enthaelt; sonst das letzte davor."""
    found = None
    for seg in segments:
        if seg[0] <= position_s < seg[1]:
            return seg
        if seg[0] <= position_s:
            found = seg
    return found


def _resolve_timeline_audio_path(
    session: object,
    project_root: Path | None,
) -> str | None:
    query = (
        session.query(database.AudioTrack.file_path)
        .join(
            database.TimelineEntry,
            database.TimelineEntry.media_id == database.AudioTrack.id,
        )
        .join(
            database.Project,
            database.Project.id == database.TimelineEntry.project_id,
        )
        .filter(
            database.TimelineEntry.track == "audio",
            database.AudioTrack.deleted_at.is_(None),
        )
        .order_by(database.TimelineEntry.id.desc())
    )
    if project_root is not None:
        query = query.filter(database.Project.path == str(project_root))
    row = query.first()
    if row is None or not row[0]:
        return None
    return str(row[0])


def _existing_media_path(*candidates: object) -> str | None:
    fallback: str | None = None
    for raw in candidates:
        if not raw:
            continue
        value = str(raw)
        if fallback is None:
            fallback = value
        try:
            if Path(value).exists():
                return value
        except OSError:
            continue
    return fallback


def _extract_confidence(
    brain_v3_scores_json: str | None,
    metadata_json: str | None,
) -> float | None:
    for raw in (metadata_json, brain_v3_scores_json):
        data = _json_dict(raw)
        for key in ("brain_v3_confidence", "confidence"):
            if key in data:
                try:
                    return max(0.0, min(1.0, float(data[key])))
                except (TypeError, ValueError):
                    return None
    return None


def _confidence_to_uncertainty(confidence: float | None) -> float:
    if confidence is None:
        return 0.5
    return max(0.0, min(1.0, 1.0 - float(confidence)))


def _json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _round_ms(value: float) -> int:
    return int(round(float(value) * 1000.0))

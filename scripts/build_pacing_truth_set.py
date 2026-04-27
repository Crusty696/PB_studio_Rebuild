"""scripts/build_pacing_truth_set.py
=====================================

Exportiert ``mem_decision``-Rows mit ``user_verdict in ('good', 'bad')``
ins JSON-Format fuer ``scripts/tune_pacing_reward.py``.

Output-Schema entspricht ``tests/fixtures/pacing_truth_set.template.json``.

CLI:
    python scripts/build_pacing_truth_set.py
        [--db PATH]               Default: <APP_ROOT>/pb_studio.db
        [--output PATH]           Default: tests/fixtures/pacing_truth_set.json
        [--min-cuts N]            Default: 30 — Warning wenn weniger als N
                                  Verdicts vorhanden
        [--include-neutral]       Default off — auch ``user_verdict=None``
                                  Cuts mitnehmen (als 'neutral')

Workflow:
    1. App mit ``PB_USE_STUDIO_BRAIN_PIPELINE=1`` starten
    2. Auto-Edit ausfuehren -> mem_decision wird gefuellt
    3. Im Studio Brain "Pacing-Explorer" Cuts mit 👍/👎 labeln
    4. Dieses Skript ausfuehren -> tests/fixtures/pacing_truth_set.json
    5. ``python scripts/tune_pacing_reward.py`` -> default_weights.json

Fehlende Felder (Audio-Stem-Energien, Video-Shot-Type) werden aus
``agent_rationale`` (JSON-Column) extrahiert oder mit ``None`` /
sicheren Defaults gefuellt — ``tune_pacing_reward.py`` toleriert
fehlende Felder via ``.get(..., 0.5)``.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Repo-Root in sys.path damit ``database.session`` importierbar ist
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pacing_truth_set.json"


def _resolve_db_path() -> Path:
    """Liefert den Pfad zur aktiven DB (APP_ROOT/pb_studio.db).

    Faellt auf Repo-Root/pb_studio.db zurueck wenn APP_ROOT nicht gesetzt.
    """
    try:
        import database.session as _session
        return _session.APP_ROOT / "pb_studio.db"
    except Exception:
        return Path(__file__).resolve().parent.parent / "pb_studio.db"


def _row_to_truth_entry(row: Any) -> dict:
    """Mapped eine ``mem_decision``-Row aufs Truth-Set-Schema.

    ``row`` ist ein RowMapping mit den Spalten aus mem_decision +
    audio_track.file_path (per JOIN).
    """
    # agent_rationale enthaelt oft Reward-Components als JSON-Dict.
    # Wir versuchen daraus die feinen Audio-/Video-Features zu lesen
    # — fallback None.
    rationale_raw = row["agent_rationale"]
    if isinstance(rationale_raw, str):
        try:
            rationale = json.loads(rationale_raw)
        except (json.JSONDecodeError, TypeError):
            rationale = {}
    elif isinstance(rationale_raw, dict):
        rationale = rationale_raw
    else:
        rationale = {}

    # Audio-Features
    audio_features = {
        "rms": float(row["at_energy"] or 0.5),
        "vocal_energy": float(rationale.get("vocal_energy", 0.5) or 0.5),
        "drum_energy": float(rationale.get("drum_energy", 0.5) or 0.5),
        "bass_energy": float(rationale.get("bass_energy", 0.5) or 0.5),
        "melody_energy": float(rationale.get("melody_energy", 0.5) or 0.5),
        "section_type": (row["at_section_type"] or "verse"),
    }

    # Video-Features
    video_features = {
        "motion_score": float(row["clip_motion_score"] or 0.5),
        # mood_cluster: wir nehmen style_bucket_id als deterministischen
        # Surrogat (1:1-Mapping zwischen Bucket und Mood-Cluster im
        # aktuellen Enrichment).
        "mood_cluster": int(row["clip_style_bucket_id"] or 0),
        "shot_type": rationale.get("shot_type"),  # None wenn nicht da
        "cosine_sim_to_audio_mood": rationale.get("cosine_sim_to_audio_mood"),
    }

    return {
        "run_id": str(row["run_id"]),
        "cut_id": int(row["sequence_idx"]),
        "timestamp_ms": int(float(row["at_timestamp_sec"] or 0.0) * 1000.0),
        "track_id": str(row["track_file_path"] or "unknown"),
        "verdict": row["user_verdict"] or "neutral",
        "audio_features": audio_features,
        "video_features": video_features,
    }


def export_truth_set(
    db_path: Path,
    output_path: Path,
    min_cuts: int = 30,
    include_neutral: bool = False,
) -> int:
    """Liest mem_decision aus der DB und schreibt das Truth-Set-JSON.

    Returns: Anzahl exportierter Rows.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"DB nicht gefunden: {db_path}\n"
            f"Hinweis: Setze APP_ROOT korrekt oder gib --db <pfad>."
        )

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)

    where_clause = (
        "WHERE d.user_verdict IN ('good', 'bad')"
        if not include_neutral
        else "WHERE d.user_verdict IS NOT NULL OR 1=1"
    )

    sql = f"""
        SELECT
            d.id                    AS id,
            d.run_id                AS run_id,
            d.sequence_idx          AS sequence_idx,
            d.at_timestamp_sec      AS at_timestamp_sec,
            d.at_energy             AS at_energy,
            d.at_section_type       AS at_section_type,
            d.scene_id              AS scene_id,
            d.clip_motion_score     AS clip_motion_score,
            d.clip_style_bucket_id  AS clip_style_bucket_id,
            d.agent_rationale       AS agent_rationale,
            d.user_verdict          AS user_verdict,
            r.audio_track_id        AS audio_track_id,
            a.file_path             AS track_file_path
        FROM mem_decision d
        LEFT JOIN mem_pacing_run r ON r.id = d.run_id
        LEFT JOIN audio_tracks a ON a.id = r.audio_track_id
        {where_clause}
        ORDER BY d.run_id ASC, d.sequence_idx ASC
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()

    entries = [_row_to_truth_entry(r) for r in rows]

    # Schema-konformes Output
    payload = {
        "schema_version": "1.0",
        "description": (
            f"Auto-export from {db_path.name} via build_pacing_truth_set.py — "
            f"{len(entries)} cuts. {'Includes neutral' if include_neutral else 'Only good/bad verdicts'}."
        ),
        "instructions": [
            "Exported automatically — re-run after labeling more cuts in Pacing-Explorer.",
            "Feed into scripts/tune_pacing_reward.py for Grid-Search reward-weight tuning.",
        ],
        "data": entries,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return len(entries)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Export mem_decision rows with user_verdict to truth-set JSON."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Pfad zur SQLite-DB (Default: APP_ROOT/pb_studio.db).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output-JSON (Default: {DEFAULT_OUTPUT.relative_to(Path.cwd()) if DEFAULT_OUTPUT.is_relative_to(Path.cwd()) else DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--min-cuts",
        type=int,
        default=30,
        help="Warning wenn weniger als N gelabelte Cuts vorhanden (Default: 30).",
    )
    parser.add_argument(
        "--include-neutral",
        action="store_true",
        help="Auch ungelabelte (user_verdict=NULL) Cuts mitnehmen — "
             "fuer Diagnose, NICHT fuer Reward-Tuning.",
    )
    args = parser.parse_args(argv)

    db_path = args.db or _resolve_db_path()
    print(f"DB:     {db_path}")
    print(f"Output: {args.output}")

    try:
        n = export_truth_set(
            db_path=db_path,
            output_path=args.output,
            min_cuts=args.min_cuts,
            include_neutral=args.include_neutral,
        )
    except FileNotFoundError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2

    print(f"Exportiert: {n} Cuts")

    if n < args.min_cuts and not args.include_neutral:
        print(
            f"WARNUNG: Nur {n} Cuts mit user_verdict — Tuning-Pipeline "
            f"empfiehlt mindestens {args.min_cuts}.",
            file=sys.stderr,
        )
        print(
            "Tipp: Studio Brain -> Tab 'Pacing-Explorer' -> 👍/👎-Buttons "
            "auf weiteren Cuts klicken, dann dieses Skript erneut ausfuehren.",
            file=sys.stderr,
        )
        return 1

    print(
        "Naechster Schritt: python scripts/tune_pacing_reward.py "
        f"--truth-set {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

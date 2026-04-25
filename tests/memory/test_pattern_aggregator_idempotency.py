"""Skeptic-/Regressions-Test fuer BUG-7-b (bug-hunter trial 2026-04-25):

Klage des bug-hunter agents: ``json_extract`` liefert native JSON-Typen
zurueck. Aggregator schreibt ``bpm_bucket`` als JSON-string ("140"),
Migration e670c6bc097c schreibt ihn als JSON-integer (140). Damit soll
die Lookup im ``_upsert_patterns`` SELECT mit ``IS :bpm_bucket``
fehlschlagen, sodass jeder zweite Aggregator-Run einen Duplicate-INSERT
statt UPDATE macht.

**Ergebnis dieses Tests:** Klage ist falsch fuer den Happy Path.
Aggregator-Self-Lookup ueber zwei Runs hinweg matched korrekt
(JSON-string '140' = bound TEXT '140' in SQLite). Keine Duplikate.

Test bleibt als Regressions-Schutz im Repo: falls jemand das
Lookup-SQL aendert, wuerde dieser Test sofort failen.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from services.pacing.pattern_aggregator import PatternAggregator

from tests.memory.test_pattern_aggregator import (
    _build_sqlite,
    _seed_decision,
    _seed_run,
)


def test_second_run_does_not_duplicate_pattern(tmp_path: Path) -> None:
    """Zweiter Aggregator-Run gegen die gleichen Decisions muss UPDATE machen,
    nicht INSERT. Ein zweiter Row mit identischer fingerprint+target waere
    BUG-7-b (Duplicate-Insert)."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    for _ in range(3):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="accept",
        )

    agg = PatternAggregator(session_factory=Session)

    n_first = agg.run()
    assert n_first == 1
    with engine.begin() as conn:
        count_after_first = conn.execute(
            text("SELECT COUNT(*) FROM mem_learned_pattern")
        ).scalar()
    assert count_after_first == 1, (
        f"Erster Run muss genau 1 Pattern erzeugen, gefunden: {count_after_first}"
    )

    n_second = agg.run()
    with engine.begin() as conn:
        count_after_second = conn.execute(
            text("SELECT COUNT(*) FROM mem_learned_pattern")
        ).scalar()

    assert count_after_second == 1, (
        f"BUG-7-b: zweiter Run hat dupliziert. Pattern-Count nach 2. Run: "
        f"{count_after_second} (erwartet: 1). n_second={n_second}."
    )

    # Zusatz-Check: stat_accept_count wurde geupdatet, nicht reset.
    with engine.begin() as conn:
        accept = conn.execute(
            text("SELECT stat_accept_count FROM mem_learned_pattern LIMIT 1")
        ).scalar()
    assert accept == 3, (
        f"UPDATE-Pfad muss accept_count=3 setzen (3 accepts), gefunden: {accept}"
    )

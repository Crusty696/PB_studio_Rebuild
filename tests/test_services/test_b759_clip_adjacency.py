"""B-759: Derselbe Clip darf nicht direkt hintereinander gesetzt werden.

Root Cause (statisch belegt): Der Wiederholungsschutz im Auswahlpfad ist
ausschliesslich ein gewichteter Score-Term (`freshness`, Gewicht 0.15). Ein
Clip mit besserem Mood-Match (Gewicht 0.25) gewinnt trotz `freshness = 0.0`
erneut — auch unmittelbar nach sich selbst.

Diese Tests fixieren die harte Nachbarschaftsregel:
der direkte Vorgaenger ist kein Kandidat, solange eine Alternative existiert.
"""
from __future__ import annotations

import logging

import numpy as np
import pytest

from services.pacing_edit_helpers import (
    _match_video_by_motion,
    _match_video_for_segment,
)

SECTION = "VERSE"


def _video_info() -> dict[int, dict]:
    return {
        1: {"path": "a.mp4", "duration": 60.0},
        2: {"path": "b.mp4", "duration": 60.0},
    }


def _clip_metadata() -> list[dict]:
    return [
        {
            "video_path": "a.mp4",
            "scene_start": 0.0,
            "scene_end": 4.0,
            "motion_score": 0.5,
        },
        {
            "video_path": "b.mp4",
            "scene_start": 0.0,
            "scene_end": 4.0,
            "motion_score": 0.5,
        },
    ]


def _select(used_recently: list[int], available_ids: list[int]):
    """Ruft den Hauptpfad (Fitness-Matrix) deterministisch auf (rng=None)."""
    return _match_video_for_segment(
        seg_start=0.0,
        seg_end=4.0,
        vibe="",
        video_info=_video_info(),
        available_ids=available_ids,
        clip_offsets={1: 0.0, 2: 0.0},
        used_recently=used_recently,
        energy_per_beat=[0.5] * 8,
        beats=[float(i) for i in range(8)],
        section_type=SECTION,
        # Clip 0 (vid=1) hat den perfekten Mood-Match, Clip 1 (vid=2) den
        # schlechtesten. Ohne harte Regel gewinnt vid=1 auch als Wiederholung.
        fitness_matrix={(0, SECTION): 1.0, (1, SECTION): 0.0},
        clip_embeddings=np.zeros((2, 4), dtype=np.float32),
        clip_metadata=_clip_metadata(),
        rng=None,
    )


def test_direct_predecessor_is_not_reused_when_alternative_exists():
    """RED vor dem Fix: vid=1 gewinnt trotz freshness=0.0 durch Mood-Vorsprung."""
    vid, _source_start, _clip_idx = _select(used_recently=[1], available_ids=[1, 2])

    assert vid != 1, (
        "Der direkte Vorgaenger wurde erneut gewaehlt, obwohl eine Alternative "
        "existiert. Die weiche freshness-Strafe (0.15) wird vom Mood-Match "
        "(0.25) ueberstimmt."
    )
    assert vid == 2


def test_three_in_a_row_is_impossible_with_two_clips():
    """Das gemeldete Symptom: dreimal derselbe Clip nacheinander."""
    used: list[int] = []
    picked: list[int] = []
    for _ in range(3):
        vid, _s, _c = _select(used_recently=used, available_ids=[1, 2])
        picked.append(vid)
        used.append(vid)

    assert not any(
        picked[i] == picked[i - 1] for i in range(1, len(picked))
    ), f"Direkte Wiederholung in der Auswahlfolge: {picked}"


def test_single_available_clip_is_still_returned(caplog):
    """Kein Kandidatenmangel-Deadlock: bei genau einem Clip bleibt er gueltig,
    die ausgesetzte Regel muss aber sichtbar geloggt werden."""
    with caplog.at_level(logging.WARNING, logger="services.pacing_edit_helpers"):
        vid, _s, _c = _select(used_recently=[1], available_ids=[1])

    assert vid == 1
    assert any(
        "B-759" in rec.message for rec in caplog.records
    ), "Ausgesetzte Nachbarschaftsregel muss als WARNING sichtbar sein"


def test_empty_history_selects_best_scoring_clip():
    """Ohne Vorgaenger bleibt das bisherige Verhalten unveraendert."""
    vid, _s, _c = _select(used_recently=[], available_ids=[1, 2])
    assert vid == 1, "Ohne Wiederholung muss weiterhin der beste Clip gewinnen"


def test_motion_fallback_logs_when_recency_filter_collapses(caplog):
    """`_match_video_by_motion` kippte still auf die volle Liste zurueck."""
    with caplog.at_level(logging.WARNING, logger="services.pacing_edit_helpers"):
        vid, _source_start = _match_video_by_motion(
            0.5,
            _video_info(),
            [1],
            [1, 1, 1],
        )

    assert vid == 1
    assert any(
        "B-759" in rec.message for rec in caplog.records
    ), "Stiller Recency-Fallback muss als WARNING sichtbar sein"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

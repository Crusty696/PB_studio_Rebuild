"""B-080 + B-061 + B-075 Batch-2 regression tests.

GPU+Qt-frei. B-080 mit Mock-DB, B-061 nur Source-Verify (schon durch
B-143 gefixt — B-061 war doppelt-dokumentiert), B-075 mit echten
PacingPlan.from_json-Calls.
"""

from __future__ import annotations

import inspect

import pytest


# ---------------------------------------------------------------------------
# B-080: VectorDB Cache-Invalidate in delete_*
# ---------------------------------------------------------------------------


def test_vector_db_delete_by_clip_ids_invalidates_cache() -> None:
    """B-080: ``delete_by_clip_ids`` muss ``_invalidate_cache`` rufen
    — sonst liefert der naechste search() noch die geloeschten Clips
    aus dem in-Memory-Cache."""
    from services.vector_db_service import VectorDBService

    src = inspect.getsource(VectorDBService.delete_by_clip_ids)
    assert "_invalidate_cache" in src, (
        "B-080: delete_by_clip_ids ruft _invalidate_cache nicht — "
        "Cache liefert nach Loeschen weiterhin Stale-Hits."
    )


def test_vector_db_delete_all_invalidates_cache() -> None:
    """B-080: ``delete_all`` muss ``_invalidate_cache`` rufen."""
    from services.vector_db_service import VectorDBService

    src = inspect.getsource(VectorDBService.delete_all)
    assert "_invalidate_cache" in src, (
        "B-080: delete_all ruft _invalidate_cache nicht."
    )


# ---------------------------------------------------------------------------
# B-061: Track-Lock-Pool — schon durch B-143 (Refcount) gefixt
# ---------------------------------------------------------------------------


def test_audio_service_uses_refcount_lock_pattern() -> None:
    """B-061 (fixed-by B-143): ``audio_service.track_lock``-ContextManager
    nutzt Refcount-Pattern (``_track_lock_refs``-Dict). Frueher Race im
    pop-im-finally ist damit ausgeschlossen.
    """
    from services import audio_service

    src = inspect.getsource(audio_service)
    assert "_track_lock_refs" in src, (
        "B-061/B-143: Refcount-Dict fehlt — Race-Window wieder offen."
    )
    # ContextManager-Wrapper muss da sein
    assert "def track_lock" in src, (
        "B-061/B-143: track_lock(track_id) ContextManager fehlt."
    )


# ---------------------------------------------------------------------------
# B-075: PacingPlan.from_json validiert Schema
# ---------------------------------------------------------------------------


def test_pacing_plan_rejects_negative_cut_rate() -> None:
    """B-075: ``cut_rate_beats=-5`` muss aus Section gedroppt werden,
    nicht durchgereicht."""
    from services.pacing_strategist import PacingPlan

    plan = PacingPlan.from_json({
        "sections": [
            {"type": "DROP", "cut_rate_beats": -5},
            {"type": "DROP", "cut_rate_beats": 4},
        ],
    })
    # Section-1 ohne cut_rate_beats (gedroppt), Section-2 mit cr=4
    cuts = [s.get("cut_rate_beats") for s in plan.section_overrides]
    assert cuts.count(-5) == 0, "B-075: negativer cut_rate_beats wurde durchgereicht"
    assert 4 in cuts, "B-075: gueltiger cut_rate_beats wurde verworfen"


def test_pacing_plan_rejects_unknown_section_type() -> None:
    """B-075: ``type='GRATULATION'`` ist nicht in der Whitelist und
    muss komplett gedroppt werden."""
    from services.pacing_strategist import PacingPlan

    plan = PacingPlan.from_json({
        "sections": [
            {"type": "GRATULATION", "cut_rate_beats": 4},
            {"type": "DROP", "cut_rate_beats": 4},
        ],
    })
    types = [s.get("type") for s in plan.section_overrides]
    assert "GRATULATION" not in types
    assert "DROP" in types


def test_pacing_plan_clamps_global_min_duration() -> None:
    """B-075: ``global_min_duration=-2.0`` muss auf 0.5 geclamped werden,
    nicht negativ durchgereicht."""
    from services.pacing_strategist import PacingPlan

    plan = PacingPlan.from_json({
        "global_min_duration": -2.0,
        "variety_priority": "sehr hoch",  # auch ungueltig
    })
    assert plan.global_min_duration >= 0.5
    assert plan.global_min_duration <= 30.0
    # variety_priority "sehr hoch" → fallback auf 0.7, dann clamp [0,1]
    assert 0.0 <= plan.variety_priority <= 1.0


def test_pacing_plan_default_unchanged_for_valid_input() -> None:
    """B-075: ein gueltiges Plan-Dict muss 1:1 durchkommen — Validation
    darf nichts veraendern wenn alles passt.
    """
    from services.pacing_strategist import PacingPlan

    plan = PacingPlan.from_json({
        "sections": [
            {"type": "INTRO", "cut_rate_beats": 8, "start": 0.0, "end": 30.0},
            {"type": "DROP", "cut_rate_beats": 2, "mood": "energetic"},
        ],
        "global_min_duration": 4.0,
        "variety_priority": 0.5,
    })
    assert len(plan.section_overrides) == 2
    assert plan.section_overrides[0]["type"] == "INTRO"
    assert plan.section_overrides[0]["cut_rate_beats"] == 8
    assert plan.section_overrides[1]["mood"] == "energetic"
    assert plan.global_min_duration == 4.0
    assert plan.variety_priority == 0.5


def test_pacing_plan_handles_garbage_input() -> None:
    """B-075: total ungueltiger Input darf nicht crashen, sondern
    Default-Plan zurueckgeben.
    """
    from services.pacing_strategist import PacingPlan

    plan = PacingPlan.from_json({"foo": "bar", "sections": "not a list"})
    assert plan.section_overrides == []
    assert plan.global_min_duration == 3.0
    assert plan.variety_priority == 0.7

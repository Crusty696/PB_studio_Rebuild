"""B-613: Export-Crash durch kleine Timeline-Luecke (Projekt 21, 35ms).

Symptom: _validate_video_timeline_gaps warf ValueError bei einer 35ms-Luecke
(vor Video-Segment 728) -> ganzer Export brach vor ffmpeg ab. Ursache: ein
Mini-Segment (<0.2s) wurde im Auto-Edit-Loop geskippt und hinterliess die
Luecke. Fixes: (1) Export schliesst kleine Luecken (<=50ms) statt zu crashen;
(2) Auto-Edit fuehrt zu nahe Cuts vorher zusammen (kein Mini-Segment).
"""
import pytest

from services.export_service import _validate_video_timeline_gaps


def _segs(bounds):
    return [{"start": s, "end": e} for s, e in bounds]


def test_small_gap_is_closed_not_raised():
    # 35ms-Luecke vor dem 2. Segment (exakt der Projekt-21-Fall)
    segs = _segs([(0.0, 2805.845), (2805.880, 2808.460)])
    _validate_video_timeline_gaps(segs)  # darf NICHT werfen
    # Luecke geschlossen: 2. Segment auf voriges Ende zurueckgeschoben,
    # Dauer erhalten.
    assert segs[1]["start"] == pytest.approx(2805.845)
    assert segs[1]["end"] == pytest.approx(2805.845 + (2808.460 - 2805.880))


def test_contiguous_unchanged():
    segs = _segs([(0.0, 2.0), (2.0, 4.0)])
    _validate_video_timeline_gaps(segs)
    assert segs[1]["start"] == pytest.approx(2.0)
    assert segs[1]["end"] == pytest.approx(4.0)


def test_large_gap_still_raises():
    # 0.5s-Luecke = echtes fehlendes Material -> muss weiterhin werfen
    segs = _segs([(0.0, 2.0), (2.5, 4.5)])
    with pytest.raises(ValueError, match="Timeline gap"):
        _validate_video_timeline_gaps(segs)


def test_project21_real_data_passes():
    """Gegenpruefung an den echten Projekt-21-Daten (falls vorhanden).

    Optional: die eigentliche Regressionsabsicherung leisten die Tests oben
    mit synthetischen Segmenten. Dieser Test prueft zusaetzlich gegen einen
    echten Projektbestand, wenn er lokal vorliegt.

    B-673: der Pfad zeigte mit vier ``..`` zwei Ebenen ueber das Repo hinaus
    (``<Repo>/../../outputs/21``) und konnte deshalb nie aufloesen — der Test
    haette selbst bei vorhandenen Daten uebersprungen. Von
    ``tests/test_services/`` sind es zwei Ebenen zum Repo-Root.
    """
    import os
    import sqlite3

    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    db = os.path.join(repo_root, "outputs", "21", "pb_studio.db")
    if not os.path.exists(db):
        pytest.skip(f"Projekt-21-Daten nicht vorhanden ({db})")
    rows = sqlite3.connect(db).execute(
        "SELECT start_time,end_time FROM timeline_entries "
        "WHERE track='video' ORDER BY start_time"
    ).fetchall()
    segs = [{"start": s, "end": e} for s, e in rows]
    _validate_video_timeline_gaps(segs)  # darf nicht werfen (Luecke geschlossen)
    prev = 0.0
    big = 0
    for s in segs:
        if s["start"] - prev > 0.05:
            big += 1
        prev = max(prev, s["end"])
    assert big == 0


def test_cut_dedup_prevents_gap_source_contract():
    """Quelltext-Vertrag: Auto-Edit fuehrt zu nahe Cuts (< 0.2s) zusammen,
    bevor der Segment-Loop laeuft (Ursachen-Fix)."""
    import inspect

    import services.pacing_service as ps
    src = inspect.getsource(ps)
    assert "B-613" in src
    assert "_MIN_SEG" in src

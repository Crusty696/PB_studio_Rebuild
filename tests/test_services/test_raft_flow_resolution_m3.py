"""NEUBAU-VOLLINTEGRATION M3 (D-065): feste Flow-Aufloesung fuer Monolith-Paritaet.

Der GPU-Paritaets-Lauf zeigte: ohne feste Aufloesung driftet Scene.energy
zwischen Engine und Monolith (Clip3 Energy-Diff 0.63), weil der Monolith auf
520x320 skaliert und die Engine auf voller Aufloesung rechnete. Mit
flow_resolution=(320,520) im Produktions-Pfad: Energy-Diff 0.0000 (Clip1+3).

Diese Tests sichern die Verdrahtung (ohne GPU); der numerische Beweis liegt
im Live-Paritaets-Lauf (tests/qa_artifacts/video_engine_parity_*.md).
"""
from services.video_pipeline.stages.raft_motion_service import RaftMotionService


def test_default_has_no_fixed_resolution():
    """Klassen-Default unveraendert (None) — Bestands-Engine-Tests bleiben
    auf dem alten Verhalten."""
    svc = RaftMotionService(variant="raft_small")
    assert svc.flow_resolution is None


def test_fixed_resolution_stored():
    svc = RaftMotionService(variant="raft_small", flow_resolution=(320, 520))
    assert svc.flow_resolution == (320, 520)


def test_build_pipeline_sets_monolith_resolution():
    """Quelltext-Vertrag: der Produktions-Pfad setzt 520x320 wie der
    Monolith (_raft_motion_score)."""
    import inspect

    import services.video_pipeline.app_integration as ai
    src = inspect.getsource(ai.build_pipeline)
    assert "flow_resolution=(320, 520)" in src

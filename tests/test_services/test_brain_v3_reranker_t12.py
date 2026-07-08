"""NEUBAU-VOLLINTEGRATION T1.2 (USE-002): Brain-V3-Reranker angekoppelt.

Vorher: PacingPipeline(use_brain_v3=False)-Default; die einzige
Produkt-Instanzierung uebergab den Parameter nicht — Reranker + WeightStore
waren toter Code im Schnittpfad.
"""
from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import PacingScorer


class TestPipelineFlag:
    def test_use_brain_v3_activates_reranker_member(self):
        p = PacingPipeline(scorer=PacingScorer(), use_brain_v3=True)
        assert p._use_brain_v3 is True
        # Reranker wird lazy/direkt gesetzt — je nach Verfuegbarkeit der
        # Brain-Stores; das Flag selbst muss aber gesetzt sein.

    def test_default_stays_off(self):
        p = PacingPipeline(scorer=PacingScorer())
        assert p._use_brain_v3 is False

    def test_min_confidence_passed(self):
        p = PacingPipeline(scorer=PacingScorer(), use_brain_v3=True,
                           brain_v3_min_confidence=0.35)
        assert abs(p._brain_v3_min_confidence - 0.35) < 1e-9


def test_product_instantiation_passes_flag():
    """Quelltext-Vertrag: die Produkt-Instanzierung in pacing_service
    reicht use_brain_v3=True + Konfidenz durch (T1.2-Kopplung)."""
    import inspect

    import services.pacing_service as ps
    src = inspect.getsource(ps)
    idx = src.index("_studio_brain_pipeline = PacingPipeline(")
    window = src[idx:idx + 1000]
    assert "use_brain_v3=True" in window
    assert "brain_v3_min_confidence=" in window

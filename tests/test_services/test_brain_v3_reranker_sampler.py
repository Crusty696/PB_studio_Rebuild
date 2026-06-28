"""Tests fuer Phase 4 Reranker + Smart-Sampler."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

from services.brain.brain_v3_service import BrainV3Service
from services.brain.context_resolver import CutContext
from services.brain.reranker import BrainV3Reranker, RerankedCandidate
from services.brain.schemas.brain_v3_schemas import FeedbackRequest
from services.brain.smart_sampler import sample_uncertain, SamplePoint
from services.brain.storage.brain_store import BrainStore
from services.brain.weight_store import WeightStore


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


# ---- Adapter helper -----------------------------------------------------
@dataclass(frozen=True)
class _StubClipFeatures:
    clip_id: int
    motion_score: float = 0.5
    embedding: Optional[np.ndarray] = None


@dataclass(frozen=True)
class _StubAudioContext:
    at_section_type: str = "drop"
    at_mood_audio: str = "dramatic"
    at_bpm: float = 128.0
    at_energy: float = 0.7
    at_harmonic_tension: float = 0.3


# ---- Reranker -----------------------------------------------------------
def test_reranker_invalid_brain_weight_raises(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    with pytest.raises(ValueError, match="brain_weight"):
        BrainV3Reranker(ws, brain_weight=1.5)


def test_reranker_returns_sorted_list(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    rr = BrainV3Reranker(ws, brain_weight=1.0)
    scored = [
        (_StubClipFeatures(clip_id=1, motion_score=0.2), 0.4, {}),
        (_StubClipFeatures(clip_id=2, motion_score=0.8), 0.6, {}),
        (_StubClipFeatures(clip_id=3, motion_score=0.5), 0.5, {}),
    ]
    out = rr.rerank(scored, _StubAudioContext(), recent_clip_ids=[10, 11])
    assert len(out) == 3
    assert all(isinstance(c, RerankedCandidate) for c in out)
    # sortiert absteigend
    for i in range(len(out) - 1):
        assert out[i].final_score >= out[i + 1].final_score
    # brain_v3_scores hat alle 17 Achsen
    assert len(out[0].brain_v3_scores) == 17


def test_reranker_brain_weight_zero_keeps_original_order(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    rr = BrainV3Reranker(ws, brain_weight=0.0)
    scored = [
        (_StubClipFeatures(clip_id=1), 0.9, {}),
        (_StubClipFeatures(clip_id=2), 0.5, {}),
        (_StubClipFeatures(clip_id=3), 0.7, {}),
    ]
    out = rr.rerank(scored, _StubAudioContext())
    # brain_weight=0 → final = soft_score → höchster bleibt vorne
    assert out[0].clip_id == 1
    assert out[1].clip_id == 3
    assert out[2].clip_id == 2


def test_reranker_blend_combines_both(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    rr = BrainV3Reranker(ws, brain_weight=0.5)
    scored = [(_StubClipFeatures(clip_id=99), 0.4, {})]
    out = rr.rerank(scored, _StubAudioContext())
    assert len(out) == 1
    expected = 0.5 * out[0].brain_score + 0.5 * 0.4
    assert abs(out[0].final_score - expected) < 1e-6


def test_reranker_handles_empty_input(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    rr = BrainV3Reranker(ws)
    out = rr.rerank([], _StubAudioContext())
    assert out == []


def test_reranker_filters_below_min_confidence(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    scored = [
        (_StubClipFeatures(clip_id=1), 0.9, {}),
        (_StubClipFeatures(clip_id=2), 0.8, {}),
    ]
    baseline = BrainV3Reranker(ws, min_confidence=0.0).rerank(scored, _StubAudioContext())
    assert len(baseline) == 2

    strict = BrainV3Reranker(ws, min_confidence=1.1).rerank(scored, _StubAudioContext())
    assert strict == []


def test_reranker_propagates_brain_v3_scores_per_axis(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    rr = BrainV3Reranker(ws)
    scored = [(_StubClipFeatures(clip_id=42), 0.5, {})]
    out = rr.rerank(scored, _StubAudioContext())
    from services.brain.cold_start import BRIDGE_AXES
    assert set(out[0].brain_v3_scores.keys()) == set(BRIDGE_AXES)


# ---- Smart-Sampler ------------------------------------------------------
def test_sampler_empty_store_returns_empty(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    out = sample_uncertain(ws, n=15)
    assert out == []


def test_sampler_returns_top_n_by_variance(isolated_appdata):
    """Erst Klicks generieren -> dann sample_uncertain liefert Punkte."""
    svc = BrainV3Service()
    # eine Mischung aus perfect + no_match → variance hoch
    for _ in range(3):
        svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    for _ in range(3):
        svc.feedback(FeedbackRequest(cut_id=2, rating="no_match"))
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    out = sample_uncertain(ws, n=10)
    assert len(out) > 0
    assert all(isinstance(p, SamplePoint) for p in out)
    # absteigend sortiert
    for i in range(len(out) - 1):
        assert out[i].variance >= out[i + 1].variance


def test_sampler_n_zero_returns_empty(isolated_appdata):
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    out = sample_uncertain(ws, n=0)
    assert out == []


def test_sampler_min_samples_filter(isolated_appdata):
    """min_samples=100 → bei wenigen Klicks 0 Ergebnisse."""
    svc = BrainV3Service()
    svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    store = BrainStore()
    ws = WeightStore(store.weights_path)
    out = sample_uncertain(ws, n=10, min_samples=100.0)
    assert out == []

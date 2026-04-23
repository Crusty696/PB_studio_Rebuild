import pytest
import numpy as np
from services.pacing.variations_budget import VariationsBudget
from services.pacing.pacing_scorer import PacingScorer
from services.pacing.pacing_pipeline import PacingPipeline

def test_variations_budget():
    budget = VariationsBudget(history_size=10)
    
    # Clip 1 registrieren
    budget.record_usage(1)
    
    # Strafe für Clip 1 sollte 1.0 sein (gerade eben verwendet)
    assert budget.get_penalty(1) == 1.0
    
    # Strafe für Clip 2 sollte 0.0 sein
    assert budget.get_penalty(2) == 0.0
    
    # Weiteren Clip registrieren
    budget.record_usage(2)
    assert budget.get_penalty(2) == 1.0
    # Strafe für Clip 1 sollte sinken
    penalty1 = budget.get_penalty(1)
    assert penalty1 < 1.0
    assert penalty1 > 0.0

def test_pacing_scorer():
    scorer = PacingScorer()
    budget = VariationsBudget()
    
    candidate = {
        "id": 1,
        "motion_score": 0.8,
        "video_clip_id": 101,
        "beat_sync_score": 0.9,
        "fitness_score": 0.7
    }
    
    context = {
        "energy": 0.8,
        "section_type": "DROP",
        "vocal_active": False,
        "memory_bias": 0.5
    }
    
    score = scorer.calculate_score(candidate, context, budget)
    assert 0.0 <= score <= 1.0
    
    # Bei schlechtem Match sollte Score niedriger sein
    context_bad = context.copy()
    context_bad["energy"] = 0.1 # Großer Unterschied zu motion_score 0.8
    score_bad = scorer.calculate_score(candidate, context_bad, budget)
    assert score_bad < score

def test_pacing_pipeline():
    pipeline = PacingPipeline()
    
    candidates = [
        {"id": 1, "video_clip_id": 101, "motion_score": 0.8, "beat_sync_score": 0.9},
        {"id": 2, "video_clip_id": 102, "motion_score": 0.2, "beat_sync_score": 0.5},
    ]
    
    context = {
        "energy": 0.8,
        "section_type": "DROP",
    }
    
    # Sollte Szene 1 wählen (Energie-Match 0.8 vs 0.8)
    best = pipeline.select_best_scene(candidates, context)
    assert best["id"] == 1
    
    # Wenn wir Clip 101 oft verwenden, sollte Budget ihn bestrafen
    for _ in range(5):
        pipeline.budget.record_usage(101)
        
    # Jetzt sollte er Szene 2 bevorzugen (trotz schlechterem Energie-Match),
    # weil 101 im Budget bestraft wird.
    best_new = pipeline.select_best_scene(candidates, context)
    assert best_new["id"] == 2

def test_wilson_integration():
    pipeline = PacingPipeline()
    
    candidates = [
        {"id": 1, "video_clip_id": 101, "motion_score": 0.5, "feedback_ups": 100, "feedback_total": 100},
        {"id": 2, "video_clip_id": 102, "motion_score": 0.5, "feedback_ups": 0, "feedback_total": 100},
    ]
    
    context = {
        "energy": 0.5,
        "section_type": "TRANSITION",
    }
    
    # Clip 1 hat viel besseres Feedback (100/100) -> Wilson Score hoch
    best = pipeline.select_best_scene(candidates, context)
    assert best["id"] == 1

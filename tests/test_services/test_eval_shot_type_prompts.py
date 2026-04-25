"""P3.3: Tests für Confusion-Matrix + Macro-F1 Helper aus eval_shot_type_prompts."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Skript befindet sich in scripts/, nicht im Package
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from eval_shot_type_prompts import confusion_matrix, macro_f1


CLASSES = ["vocal_dominant", "drum_dominant", "melody_dominant", "bass_dominant"]


def test_confusion_matrix_perfect_prediction():
    true_lbl = ["vocal_dominant", "drum_dominant", "melody_dominant", "bass_dominant"]
    pred_lbl = list(true_lbl)
    cm = confusion_matrix(true_lbl, pred_lbl, CLASSES)
    assert cm.shape == (4, 4)
    # Diagonal sollte je 1, off-diag 0
    assert cm.trace() == 4
    assert cm.sum() == 4


def test_confusion_matrix_off_diagonal_for_misclass():
    true_lbl = ["vocal_dominant", "vocal_dominant"]
    pred_lbl = ["vocal_dominant", "drum_dominant"]
    cm = confusion_matrix(true_lbl, pred_lbl, CLASSES)
    assert cm[0, 0] == 1  # 1× richtig vocal
    assert cm[0, 1] == 1  # 1× vocal als drum klassifiziert


def test_macro_f1_perfect_one():
    """Perfekte Diagonal-Confusion-Matrix → F1 = 1.0."""
    cm = np.eye(4, dtype=np.int32) * 10
    assert abs(macro_f1(cm) - 1.0) < 1e-6


def test_macro_f1_all_wrong_zero():
    """Off-Diagonal-only Matrix → F1 = 0.0."""
    cm = np.zeros((4, 4), dtype=np.int32)
    cm[0, 1] = 5
    cm[1, 2] = 5
    cm[2, 3] = 5
    cm[3, 0] = 5
    f1 = macro_f1(cm)
    assert f1 == 0.0


def test_macro_f1_partial():
    """50% Genauigkeit → F1 ≈ 0.5."""
    cm = np.array([
        [5, 5, 0, 0],
        [0, 5, 5, 0],
        [0, 0, 5, 5],
        [5, 0, 0, 5],
    ], dtype=np.int32)
    f1 = macro_f1(cm)
    assert 0.4 < f1 < 0.6


def test_macro_f1_handles_class_with_zero_samples():
    """Class ohne Samples soll nicht crashen — F1=0 für die Klasse."""
    cm = np.zeros((4, 4), dtype=np.int32)
    cm[0, 0] = 10
    # Klasse 1, 2, 3 haben keine Samples
    f1 = macro_f1(cm)
    # f1 = (1 + 0 + 0 + 0) / 4 = 0.25
    assert abs(f1 - 0.25) < 1e-6

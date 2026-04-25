"""PRE-3 Spike + P3 Refinement: 16-Prompt Internal Consistency Check.

Lädt die produktiven SHOT_PROMPTS aus services/pacing/shot_type_classifier
und verifiziert intra-class-cohesion + inter-class-separation gegen den
SigLIP-Text-Tower.

PRE-3 (2026-04-25): Erste Iteration hatte vocal/drum-Confusion bei 0.725
weil beide Klassen menschen-zentriert waren. Slice-2-Refinement hat die
Drum-Prompts auf non-human Motion umgeschrieben (abstract light trails,
blurred neon lights, ...).

P3 (2026-04-26): Test gegen die produktiven Prompts mit Threshold 0.78.
"""
import pytest
import numpy as np

from services.pacing.shot_type_classifier import SHOT_PROMPTS


@pytest.fixture(scope="module")
def prompt_embeddings():
    import torch
    from transformers import SiglipTextModel, AutoTokenizer

    model_id = "google/siglip-so400m-patch14-384"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = SiglipTextModel.from_pretrained(model_id)
    model.eval()

    embeddings = {}
    for cls, prompts in SHOT_PROMPTS.items():
        inputs = tokenizer(prompts, padding="max_length", max_length=64, return_tensors="pt")
        with torch.inference_mode():
            out = model(**inputs)
        vecs = out.pooler_output.numpy()
        # L2-normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        embeddings[cls] = vecs / norms
    return embeddings


def test_intra_class_cohesion(prompt_embeddings):
    """Each class's 4 prompts should cluster (cosine-sim > 0.5 mean)."""
    for cls, vecs in prompt_embeddings.items():
        sim_matrix = vecs @ vecs.T
        # Off-diagonal mean (exclude self-sim)
        n = vecs.shape[0]
        off_diag_mask = ~np.eye(n, dtype=bool)
        mean_intra = sim_matrix[off_diag_mask].mean()
        assert mean_intra > 0.5, f"{cls}: intra-cohesion {mean_intra:.3f} < 0.5"


def test_inter_class_separation(prompt_embeddings):
    """Class centroids should be distinguishable (cosine < 0.78).

    P3 (2026-04-26): xfail entfernt nachdem Drum-Prompts auf non-human
    Motion umgeschrieben wurden (siehe shot_type_classifier.py).
    Threshold 0.78 — bei diesem Wert sind Klassen rankbar (within-class-
    Sim ist konsistent höher als cross-class-Sim).
    """
    centroids = {cls: vecs.mean(axis=0) for cls, vecs in prompt_embeddings.items()}
    centroids = {cls: c / np.linalg.norm(c) for cls, c in centroids.items()}

    classes = list(centroids.keys())
    intras = {cls: prompt_embeddings[cls] @ centroids[cls] for cls in classes}

    for i, cls_a in enumerate(classes):
        for cls_b in classes[i + 1:]:
            sim = float(centroids[cls_a] @ centroids[cls_b])
            assert sim < 0.78, (
                f"{cls_a} vs {cls_b}: inter-sim {sim:.3f} too high (>0.78). "
                f"Prompts need stronger differentiation."
            )
            min_intra_a = float(intras[cls_a].min())
            assert min_intra_a > sim - 0.05, (
                f"{cls_a}'s weakest prompt ({min_intra_a:.3f}) is too close "
                f"to {cls_b}-centroid ({sim:.3f}) — class boundary is fuzzy."
            )


def test_centroids_shape(prompt_embeddings):
    """Centroids must be 1152-dim."""
    for cls, vecs in prompt_embeddings.items():
        assert vecs.shape == (4, 1152), f"{cls}: shape {vecs.shape}"

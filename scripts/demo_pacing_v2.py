"""Final-Demo: zeigt Slice-1..4 + D-023 Stack im Trockendurchlauf.

Verwendet synthetische Daten — kein echter Audio/Video-File-Zugriff,
kein GPU. Das ist der "Headless-End-to-End"-Smoke-Test der gesamten
Pacing-v2-Sprint-Auslieferung.

Aufruf:
    python scripts/demo_pacing_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.pacing.audio_video_curves import compute_curves
from services.pacing.stem_section_aggregator import aggregate, dominant_stem
from services.pacing.cut_snapper import snap_cuts
from services.pacing.vocal_hold_modifier import vocal_hold_spacing_modifier
from services.pacing.cut_density_modulator import (
    apply_drop_burst,
    apply_bpm_adaptation,
)
from services.pacing.energy_match_reward import compute_energy_match_reward
from services.pacing.phrase_boundary_constraint import phrase_boundary_penalty
from services.pacing.shot_type_classifier import classify, SHOT_CLASSES
from services.pacing.stem_class_bonus import compute_stem_class_bonus
from services.pacing.audio_mood_vector import compute_audio_mood_vector
from services.pacing.mood_match_score import compute_mood_match_score
from services.pacing.variety_memory import VarietyMemory
from services.pacing.section_coherence import compute_section_coherence
from services.pacing.rl_reward import RewardComponents, compute_reward
from services.pacing.rl_policy import SectionPolicy
from services.pacing.ab_runner import run_ab
from services.pacing.decision_explainer import explain_decision
from services.pacing.rl_memory_v2 import RLPacingMemoryV2, DecisionRecord
from services.graph.graph_service import GraphService
from services.graph.knn_backend import KnnBackend, pick_backend_strategy
from services.graph.sigma_renderer import render_sigma_html
from services.graph.cockpit_view_model import CockpitViewModel


class _Section:
    def __init__(self, sid, start, end, type_):
        self.id = sid
        self.start = start
        self.start_time = start
        self.end = end
        self.end_time = end
        self.section_type = type_


class _Scene:
    def __init__(self, start, end, motion):
        self.start_time = start
        self.end_time = end
        self.motion_score = motion


def _stub_centroids():
    rng = np.random.default_rng(42)
    out = {}
    for cls in SHOT_CLASSES:
        v = rng.standard_normal(1152).astype(np.float32)
        v /= np.linalg.norm(v)
        out[cls] = v
    return out


def main():
    print("=== PB Studio Pacing-v2 Demo ===\n")

    # ── Foundation: Curves + Stem-Aggregation ──────────────────────────
    sr = 22050
    duration = 8.0
    rng = np.random.default_rng(7)
    audio = rng.standard_normal(int(sr * duration)).astype(np.float32)
    scenes = [_Scene(0.0, 4.0, 0.7), _Scene(4.0, 8.0, 0.4)]
    curves = compute_curves(audio, sr=sr, scene_infos=scenes, duration_sec=duration)
    print(f"[Foundation FR-S0-2] Curves: rms={curves.rms.shape}, motion={curves.motion.shape}")

    stems = {
        "vocals": rng.standard_normal(int(sr * duration)).astype(np.float32) * 0.3,
        "drums": rng.standard_normal(int(sr * duration)).astype(np.float32) * 0.8,
        "bass": rng.standard_normal(int(sr * duration)).astype(np.float32) * 0.5,
        "other": rng.standard_normal(int(sr * duration)).astype(np.float32) * 0.1,
    }
    sections = [_Section("verse", 0.0, 4.0, "verse"), _Section("drop", 4.0, 8.0, "drop")]
    stem_energies = aggregate(stems, sections, sr=sr)
    print(f"[Foundation FR-S0-3] Stem-Energies: {stem_energies}")
    print(f"  Dominant in 'drop' section: {dominant_stem(stem_energies['drop'])}")

    # ── Slice 1 ───────────────────────────────────────────────────────
    cuts = [0.5, 1.0, 1.5, 2.0, 4.0, 4.5, 5.0, 5.5, 6.0]
    snapped = snap_cuts(cuts, onsets=[0.51, 1.02, 4.01, 5.49], max_shift_ms=50)
    print(f"\n[Slice 1 FR-S1-1] Snapped cuts: {snapped}")

    vocal_mod = vocal_hold_spacing_modifier(stem_energies["verse"])
    print(f"[Slice 1 FR-S1-2] Vocal-Hold modifier (verse): {vocal_mod}")

    drop_cuts = apply_drop_burst(snapped, drop_times=[5.0], bpm=128)
    print(f"[Slice 1 FR-S1-3] Drop-Burst cuts: {drop_cuts[:6]}...")

    r_energy = compute_energy_match_reward(curves.rms, curves.motion)
    print(f"[Slice 1 FR-S1-4] r_energy = {r_energy:.3f}")

    pen = phrase_boundary_penalty(beat_idx=16, prev_mood="energetic", candidate_mood="energetic")
    print(f"[Slice 1 FR-S1-5] Phrase-Boundary penalty (same mood): {pen}")

    # ── Slice 2 ───────────────────────────────────────────────────────
    centroids = _stub_centroids()
    clip_emb = rng.standard_normal(1152).astype(np.float32)
    clip_emb /= np.linalg.norm(clip_emb)
    shot_conf = classify(clip_emb, centroids)
    print(f"\n[Slice 2 FR-S2-1] Shot-classification: {shot_conf}")

    bonus = compute_stem_class_bonus("drums", shot_conf)
    print(f"[Slice 2 FR-S2-2] Stem-class bonus (drums): {bonus}")

    bpm_adapted = apply_bpm_adaptation(drop_cuts, sections)
    print(f"[Slice 2 FR-S2-3] BPM-adapted cuts ({len(drop_cuts)} -> {len(bpm_adapted)})")

    # ── Slice 3 ───────────────────────────────────────────────────────
    audio_mood = compute_audio_mood_vector(stem_energies["drop"], "drop", centroids)
    r_mood = compute_mood_match_score(audio_mood, clip_emb)
    print(f"\n[Slice 3 FR-S3-1+2] r_mood = {r_mood:.3f}")

    vm = VarietyMemory(window_sec=30.0)
    vm.record(clip_id=1, t_sec=0.0)
    print(f"[Slice 3 FR-S3-3] Clip 1 recent at t=10s: {vm.is_recent(1, 10.0)} "
          f"(penalty={vm.penalty(1, 10.0):.2f})")

    coh = compute_section_coherence(prev_emb=clip_emb, candidate_emb=clip_emb,
                                     boundary_distance_sec=4.0)
    print(f"[Slice 3 FR-S3-4] Coherence (inside section, same emb): {coh:.3f}")

    # ── Slice 4 ───────────────────────────────────────────────────────
    comps = RewardComponents(
        r_energy=r_energy, r_mood=r_mood, r_stem_class=bonus,
        r_section=coh, r_freshness=1 - vm.penalty(1, 10.0),
        r_collision=0.7, r_user=0.5,
    )
    total = compute_reward(comps)
    print(f"\n[Slice 4 FR-S4-1] Total reward: {total:.3f}")

    pol = SectionPolicy(min_decisions=1)
    for _ in range(10):
        pol.update("drop", ("good",), reward=0.85)
    print(f"[Slice 4 FR-S4-2] Section-Policy(drop, good): {pol.value('drop', ('good',)):.3f}")

    cands = [{"id": i, "r_energy": float(i) / 10} for i in range(10)]
    ab = run_ab(
        cands, ctx={}, weights_a={"r_energy": 1.0}, weights_b={"r_energy": 0.1},
        scorer_factory=lambda w: lambda c, ctx: c["r_energy"] * w.get("r_energy", 0),
        seed=0,
    )
    print(f"[Slice 4 FR-S4-5] A/B picks: A={ab.choice_a['id']}, B={ab.choice_b['id']}")

    expl = explain_decision(comps, top_n=3)
    print(f"[Slice 4 FR-S4-4] Top-3 components: "
          f"{[c['key'] for c in expl['top_components']]}")

    # ── D-023 Graph + Memory ──────────────────────────────────────────
    g = GraphService()
    for i in range(20):
        g.add_node(f"v{i}", "video", f"Clip {i}")
    embeddings = rng.standard_normal((20, 1152)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    n_edges = g.build_similarity_edges([f"v{i}" for i in range(20)],
                                        embeddings, k=3, min_similarity=0.0)
    print(f"\n[D-023 P3] Graph: {g.node_count()} nodes, {g.edge_count()} edges (Backend: "
          f"{pick_backend_strategy(20)})")

    cockpit = CockpitViewModel(graph=g)
    html = cockpit.render_html()
    print(f"[D-023 P1+P4] Sigma-HTML rendered ({len(html)} chars)")

    mem = RLPacingMemoryV2(variety_window_sec=30.0)
    mem.record(DecisionRecord(
        run_id=1, cut_id=1, timestamp_ms=5000, section_type="drop",
        scene_id=42, verdict="good", reward=total, components=comps.as_dict(),
    ))
    print(f"[D-023 P5] RL-Memory v2: {mem.count()} decisions, "
          f"section-acceptance(drop)={mem.section_acceptance_rate('drop'):.2f}")

    print("\n=== Demo complete. All slices + D-023 stack functional. ===")


if __name__ == "__main__":
    main()

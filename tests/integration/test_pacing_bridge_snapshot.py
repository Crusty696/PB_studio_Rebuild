"""P1.2: Snapshot-Sicherheitsnetz für auto_edit_phase3 ↔ Bridge.

Statischer Snapshot der garantiert:
1. `_auto_edit_phase3_inner` enthält den Bridge-Hook (wer ihn entfernt
   merkt es im Test).
2. `_auto_edit_phase3_inner` nutzt die Entscheidung aus dem Outer-Wrapper,
   statt das Environment ein zweites Mal zu lesen.
3. `bridge.maybe_use_studio_brain_pipeline` Default-Off = False bleibt.

Plus: Determinismus-Snapshot der Bridge-Mapping-Outputs auf einer
fixierten Mini-Szenerie. Output wird mit baseline-JSON unter
`tests/integration/baselines/pacing_bridge_snapshot.json` verglichen;
Re-Generation via `scripts/generate_pacing_baseline.py --overwrite`.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from services.pacing import bridge, bridge_mapping
from services.pacing.bridge_mapping import build_audio_context, build_clip_features
from services.pacing.scorer import AudioContext, ClipFeatures

BASELINE_PATH = Path(__file__).parent / "baselines" / "pacing_bridge_snapshot.json"


# ── Kontrakt-Snapshots: Source-Inspektion gegen versehentliche Drift ───────


def test_auto_edit_phase3_inner_has_bridge_hook():
    """Bridge-Hook (`maybe_use_studio_brain_pipeline`) muss im Outer-Wrapper
    aufgerufen werden — sonst greift der Slice-1-Switch nie."""
    from services import pacing_service
    src = inspect.getsource(pacing_service.auto_edit_phase3)
    assert "maybe_use_studio_brain_pipeline" in src, (
        "P1.2: Bridge-Hook entfernt aus auto_edit_phase3 — Slice-1-Wiring "
        "wäre damit blockiert. Verdrahtung wiederherstellen."
    )


def test_auto_edit_phase3_inner_select_best_is_flag_guarded():
    """P0 #1 Cycle 11: select_best darf JETZT aufgerufen werden, aber NUR
    hinter der Bridge-Entscheidung `studio_brain_requested`. Der
    Default-Pfad (Flag=False) bleibt 100% Legacy.
    """
    from services import pacing_service
    src = inspect.getsource(pacing_service._auto_edit_phase3_inner)
    if "select_best" in src:
        assert "studio_brain_requested" in src, (
            "P0 #1: select_best wird aufgerufen, aber nicht hinter der "
            "Bridge-Entscheidung studio_brain_requested. Snapshot-Sicherheit verletzt."
        )
        assert "_studio_brain_pipeline" in src, (
            "P0 #1: select_best ohne Pipeline-Variable — "
            "Bridge-Setup unklar."
        )


def test_bridge_default_off():
    """Default ohne ENV → Bridge gibt False zurück."""
    import os
    if bridge.ENV_VAR in os.environ:
        # Test soll deterministisch sein, ohne die User-Env zu mutieren
        pytest.skip(f"{bridge.ENV_VAR} ist im Env gesetzt — überspringe Default-Test")
    assert bridge.use_studio_brain_pipeline() is False
    assert bridge.maybe_use_studio_brain_pipeline(audio_id=1, video_clip_ids=[]) is False


def test_bridge_mapping_module_symbols_present():
    """Sicher dass die Public-API der Mapping-Helfer stabil bleibt."""
    assert callable(bridge_mapping.build_audio_context)
    assert callable(bridge_mapping.build_clip_features)


# ── Determinismus-Snapshot der Mapping-Outputs ─────────────────────────────


class _FixedAudioTrack:
    id = 1
    bpm = 128.0
    key = "Am"
    key_confidence = 0.9
    mood = "energetic"
    genre = "psytrance"
    sub_genre = "progressive_psy"
    lufs = -8.5
    groove_template = "fotf"
    spectral_hash = "hash_drop"
    harmonic_tension = 0.75


class _FixedScene:
    id = 100
    motion_score = 0.7
    energy = 0.7
    ai_mood = "energetic"
    role = "hero"
    style_bucket_id = 3
    embedding = None


def _build_fixture_outputs() -> dict:
    """Deterministische Mini-Szenerie → 3 Cuts, 2 Clips → 6 (cut, clip) Mappings."""
    audio = _FixedAudioTrack()
    beats = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    energy = [0.1, 0.2, 0.4, 0.6, 0.85, 0.9, 0.7]
    sections = ("intro", "drop", "outro")
    cut_points = [0.5, 2.0, 2.5]
    scenes = [
        _FixedScene(),
        type("_S2", (), {
            "id": 200, "motion_score": 0.4, "energy": 0.4,
            "ai_mood": "calm", "role": "ambient",
            "style_bucket_id": 1, "embedding": None,
        })(),
    ]

    cut_outputs = []
    for sec, t in zip(sections, cut_points):
        ctx = build_audio_context(
            seg_start_sec=t, seg_section_type=sec,
            audio_track=audio, beats=beats, energy_per_beat=energy,
        )
        cut_outputs.append({
            "section": ctx.at_section_type,
            "ts": round(ctx.at_timestamp_sec, 4),
            "beat_idx": ctx.at_beat_idx,
            "energy": round(ctx.at_energy, 4) if ctx.at_energy is not None else None,
            "tension": round(ctx.at_harmonic_tension, 4) if ctx.at_harmonic_tension is not None else None,
            "bpm": ctx.at_bpm,
            "key": ctx.at_key,
            "mood_audio": ctx.at_mood_audio,
            "groove": ctx.at_groove_template,
        })

    clip_outputs = []
    for vid, scene in enumerate(scenes, start=1):
        cf = build_clip_features(video_clip_id=vid, scene=scene)
        clip_outputs.append({
            "clip_id": cf.clip_id,
            "scene_id": cf.scene_id,
            "role": cf.role,
            "mood": cf.mood_refined,
            "bucket": cf.style_bucket_id,
            "motion": round(cf.motion_score, 4),
            "has_emb": cf.embedding is not None,
        })

    return {"cuts": cut_outputs, "clips": clip_outputs}


def test_bridge_mapping_snapshot_matches_baseline():
    """Outputs der Mapping-Helfer auf einer fixen Szenerie müssen
    bit-identisch zu der baseline-JSON sein. Drift = absichtliche
    Änderung → mit `scripts/generate_pacing_baseline.py --overwrite`
    neu erzeugen.
    """
    actual = _build_fixture_outputs()
    if not BASELINE_PATH.exists():
        pytest.skip(
            f"Baseline {BASELINE_PATH} fehlt — "
            "erzeuge sie mit `python scripts/generate_pacing_baseline.py --overwrite`"
        )
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"Bridge-Mapping-Snapshot drifted:\nExpected: {expected}\nActual: {actual}\n"
        "Wenn die Drift gewollt ist → Baseline neu erzeugen."
    )


def test_bridge_mapping_deterministic_across_runs():
    """Zweimal aufgerufen muss derselbe Output rauskommen — schützt vor
    versehentlichen RNG-Lecks oder Datums-Komponenten in den Helfern."""
    a = _build_fixture_outputs()
    b = _build_fixture_outputs()
    assert a == b

from __future__ import annotations


def test_nvenc_conflict_spike_measures_serializer_wait():
    from scripts.spike_brain_v3_nvenc_conflict import measure_serializer_conflict

    result = measure_serializer_conflict(hold_seconds=0.15)

    assert result["brain_holder"] == "clap_embed_mix"
    assert result["render_holder"] == "render"
    assert result["serialized"] is True
    assert result["render_wait_s"] >= 0.10


def test_nvenc_conflict_spike_measures_legacy_gpu_lock_wait():
    from scripts.spike_brain_v3_nvenc_conflict import measure_legacy_gpu_lock_conflict

    result = measure_legacy_gpu_lock_conflict(hold_seconds=0.15)

    assert result["legacy_holder"] == "demucs_or_raft"
    assert result["render_holder"] == "render"
    assert result["serialized"] is True
    assert result["render_wait_s"] >= 0.10

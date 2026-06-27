from __future__ import annotations


def test_performance_profile_collects_pacing_samples():
    from scripts.spike_brain_v3_performance_profile import run_pacing_profile

    result = run_pacing_profile(iterations=1)

    assert result["iterations"] == 1
    assert len(result["samples"]) == 1
    assert result["pacing_overhead_ms"]["p95"] < 800.0
    assert result["learning_session_ms"]["p95"] < 5000.0


def test_performance_profile_collects_embedding_queue_metrics():
    from scripts.spike_brain_v3_performance_profile import run_embedding_queue_profile

    result = run_embedding_queue_profile(n_jobs=3, fake_work_seconds=0.01)

    assert result["submitted"] == 3
    assert result["completed"] == 3
    assert result["throughput_jobs_per_s"] > 0
    assert result["p95_latency_ms"] > 0

from __future__ import annotations


def test_knn_ann_eval_detects_missing_ann_module():
    from scripts.spike_brain_v3_knn_ann_eval import detect_ann_support

    result = detect_ann_support(
        vec_version="v0.1.9",
        module_names=["vec0", "fts5", "rtree"],
    )

    assert result["status"] == "blocked-no-ann-module"
    assert result["ann_module_available"] is False


def test_knn_ann_eval_detects_available_hnsw_module():
    from scripts.spike_brain_v3_knn_ann_eval import detect_ann_support

    result = detect_ann_support(
        vec_version="v0.1.9",
        module_names=["vec0", "vec_hnsw"],
    )

    assert result["status"] == "ready"
    assert result["ann_module_available"] is True


def test_knn_ann_eval_writes_result(tmp_path):
    from scripts.spike_brain_v3_knn_ann_eval import run

    result = run(tmp_path, n_vectors=32, dim=8, n_queries=2)

    assert result["status"] in {
        "ready",
        "blocked-no-ann-module",
        "ready-external-vectorlite",
    }
    assert result["vec0_smoke"]["inserted"] == 32
    assert result["vec0_smoke"]["queries"] == 2
    assert (tmp_path / result["out_dir_name"] / "results.json").exists()


def test_vectorlite_ann_eval_can_report_unavailable(monkeypatch):
    from scripts import spike_brain_v3_knn_ann_eval as mod

    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda _name: None)

    result = mod.detect_vectorlite_support()

    assert result["available"] is False

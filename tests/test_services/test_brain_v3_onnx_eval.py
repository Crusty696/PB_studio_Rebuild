from __future__ import annotations


def test_onnx_eval_blocks_when_onnx_package_missing():
    from services.brain.onnx_export import evaluate_onnx_environment

    result = evaluate_onnx_environment(
        find_spec=lambda name: None if name == "onnx" else object(),
        provider_getter=lambda: ["CPUExecutionProvider"],
    )

    assert result["status"] == "blocked"
    assert "onnx package missing" in result["blockers"]


def test_onnx_eval_ready_when_export_and_cuda_provider_available():
    from services.brain.onnx_export import evaluate_onnx_environment

    result = evaluate_onnx_environment(
        find_spec=lambda _name: object(),
        provider_getter=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
    )

    assert result["status"] == "ready"
    assert result["blockers"] == []
    assert result["cuda_execution_provider"] is True


def test_onnx_eval_script_writes_machine_readable_result(tmp_path):
    from scripts.spike_brain_v3_onnx_eval import run

    result = run(tmp_path)

    assert result["status"] in {"ready", "blocked"}
    assert result["out_dir"]
    assert (tmp_path / result["out_dir_name"] / "results.json").exists()


def test_onnx_cuda_smoke_reports_skipped_without_cuda_provider():
    from services.brain.onnx_export import run_onnx_cuda_smoke

    result = run_onnx_cuda_smoke(providers=["CPUExecutionProvider"])

    assert result["status"] == "skipped"
    assert "CUDAExecutionProvider" in result["reason"]

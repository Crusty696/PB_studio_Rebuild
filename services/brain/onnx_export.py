"""ONNX export feasibility checks for Brain V3 CLAP/SigLIP-2.

This module does not export models unless the required ONNX stack is present.
Phase 6 asks for an eval before implementation; on GTX 1060 the CUDA provider
is mandatory for a useful native-vs-ONNX latency comparison.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import time
from pathlib import Path
from typing import Any, Callable

from services.brain.audio.audio_embedder import CLAP_MODEL_ID
from services.brain.video.video_embedder import SIGLIP2_MODEL_ID


FindSpec = Callable[[str], object | None]
ProviderGetter = Callable[[], list[str]]


def _default_provider_getter() -> list[str]:
    try:
        import onnxruntime as ort  # type: ignore
    except Exception:
        return []
    try:
        return list(ort.get_available_providers())
    except Exception:
        return []


def model_export_targets() -> list[dict[str, str]]:
    return [
        {
            "name": "clap_audio",
            "model_id": CLAP_MODEL_ID,
            "purpose": "audio embedding",
            "expected_dim": "512",
        },
        {
            "name": "siglip2_vision",
            "model_id": SIGLIP2_MODEL_ID,
            "purpose": "video embedding",
            "expected_dim": "768",
        },
    ]


def evaluate_onnx_environment(
    find_spec: FindSpec | None = None,
    provider_getter: ProviderGetter | None = None,
) -> dict[str, Any]:
    find_spec = find_spec or importlib.util.find_spec
    provider_getter = provider_getter or _default_provider_getter

    packages = {
        "onnx": find_spec("onnx") is not None,
        "onnxruntime": find_spec("onnxruntime") is not None,
        "torch": find_spec("torch") is not None,
        "transformers": find_spec("transformers") is not None,
    }
    providers = provider_getter() if packages["onnxruntime"] else []
    cuda_provider = "CUDAExecutionProvider" in providers
    blockers: list[str] = []

    if not packages["onnx"]:
        blockers.append("onnx package missing")
    if not packages["onnxruntime"]:
        blockers.append("onnxruntime package missing")
    if not cuda_provider:
        blockers.append("onnxruntime CUDAExecutionProvider missing")
    if not packages["torch"]:
        blockers.append("torch package missing")
    if not packages["transformers"]:
        blockers.append("transformers package missing")

    return {
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "packages": packages,
        "onnxruntime_providers": providers,
        "cuda_execution_provider": cuda_provider,
        "targets": model_export_targets(),
        "hardware_note": (
            "GTX 1060/Pascal has no Tensor Cores; FP16 ONNX speedup is not "
            "expected. Eval must compare FP32 native CUDA vs ONNX CUDA."
        ),
        "python": platform.python_version(),
    }


def run_onnx_cuda_smoke(providers: list[str] | None = None) -> dict[str, Any]:
    providers = providers or _default_provider_getter()
    if "CUDAExecutionProvider" not in providers:
        return {
            "status": "skipped",
            "reason": "CUDAExecutionProvider not available",
            "providers": providers,
        }
    try:
        import numpy as np
        import onnx
        import onnxruntime as ort  # type: ignore
        import torch  # type: ignore
        from onnx import TensorProto, helper
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"ONNX imports failed: {exc}",
            "providers": providers,
        }
    dll_dir = Path(torch.__file__).resolve().parent / "lib"
    dll_handle = None
    if dll_dir.exists() and hasattr(os, "add_dll_directory"):
        dll_handle = os.add_dll_directory(str(dll_dir))

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    node = helper.make_node("Add", ["x", "x"], ["y"])
    graph = helper.make_graph([node], "brain_v3_cuda_smoke", [x], [y])
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 13)],
        producer_name="pb-studio-brain-v3",
    )
    model.ir_version = 9
    try:
        start = time.perf_counter()
        session = ort.InferenceSession(
            model.SerializeToString(),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        used = session.get_providers()
        out = session.run(None, {"x": np.ones((1, 4), dtype=np.float32)})[0]
        elapsed_ms = (time.perf_counter() - start) * 1000.0
    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "providers": providers,
        }
    finally:
        if dll_handle is not None:
            dll_handle.close()
    return {
        "status": "ok" if "CUDAExecutionProvider" in used else "failed",
        "providers": providers,
        "session_providers": used,
        "elapsed_ms": elapsed_ms,
        "output_sum": float(out.sum()),
        "preloaded_dll_dir": str(dll_dir),
        "onnx_version": onnx.__version__,
        "ort_version": ort.__version__,
    }


def recommended_next_step(result: dict[str, Any]) -> str:
    if result["status"] == "ready":
        return "Run native-vs-ONNX latency spike for CLAP and SigLIP-2."
    return (
        "Skip ONNX export implementation for now or install a CUDA-capable "
        "ONNX stack intentionally, then rerun this eval."
    )

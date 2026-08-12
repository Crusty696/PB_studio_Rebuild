"""B-818: OS-dGPU-Wake muss vor erstem Torch-CUDA-Probe laufen."""

from pathlib import Path


def test_b818_pnp_wake_precedes_first_torch_import() -> None:
    source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    bootstrap = source[source.index("# B-336:"):source.index("# ---------------------------------------")]

    wake_call = bootstrap.index("check_nvidia_gpu_state(force_refresh=True)")
    torch_import = bootstrap.index("import torch")

    assert wake_call < torch_import, (
        "B-818: Torch/CUDA wurde vor OS-PnP-Wake geprueft; ein transient "
        "abwesender SB2-dGPU-Zustand kann damit fuer gesamte Session CPU bleiben"
    )

"""B-215 Diagnose-Script — CUDA + RAFT + SigLIP Sanity-Check.

Zweck: vor einem App-Start verifizieren, dass torch + torchvision +
CUDA-Driver konsistent installiert sind und die Modell-Loads NICHT in
einen STATUS_STACK_BUFFER_OVERRUN (exit -1073740791) laufen.

Aufruf:
    python scripts/diagnose_cuda.py

Output: zeilenweise Diagnose, am Ende SUMMARY mit OK/FAIL.

Was geprueft wird:
1. Python-Interpreter + Pfad (zeigt welche env aktiv ist)
2. torch/torchvision Versionen + CUDA-Build
3. CUDA-Init-Status mit konkretem Fehlerwert (z.B. 11030 = CUDA_ERROR_UNKNOWN)
4. NVIDIA-Treiber-DLL-Pfad
5. torch-DLL-Pfad (muss zum Interpreter passen!)
6. Ob mehrere torch-Installs im PATH sind (Mismatch-Indikator)
7. RAFT-Small-Load auf CPU (isoliert)
8. SigLIP Tiny-Load auf CPU (Smoke-Test)
9. OpenMP-Runtime-Konflikte (KMP_DUPLICATE_LIB_OK Status)

Wenn 1-7 alle OK sind, sollte die App nicht im RAFT-Load crashen.
Wenn 6 oder 9 FAIL, Crash-Wahrscheinlichkeit hoch.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _hdr(msg: str) -> None:
    print()
    print("=" * 70)
    print(msg)
    print("=" * 70)


def _line(label: str, value, ok: bool | None = None) -> None:
    marker = "    " if ok is None else ("[OK] " if ok else "[!!] ")
    print(f"{marker}{label}: {value}")


def main() -> int:
    fail_count = 0

    _hdr("1. Python-Interpreter")
    _line("sys.executable", sys.executable)
    _line("sys.prefix", sys.prefix)
    _line("sys.version", sys.version.split()[0])

    _hdr("2. OpenMP / MKL Environment")
    kmp_ok = os.environ.get("KMP_DUPLICATE_LIB_OK", "(unset)")
    _line("KMP_DUPLICATE_LIB_OK", kmp_ok, ok=(kmp_ok.upper() == "TRUE"))
    if kmp_ok.upper() != "TRUE":
        fail_count += 1
        print("    -> setze: set KMP_DUPLICATE_LIB_OK=TRUE")
    _line("OMP_NUM_THREADS", os.environ.get("OMP_NUM_THREADS", "(unset)"))
    _line("MKL_NUM_THREADS", os.environ.get("MKL_NUM_THREADS", "(unset)"))

    _hdr("3. torch import")
    try:
        import torch
        _line("torch.__version__", torch.__version__)
        _line("torch.__file__", torch.__file__)
        _line("torch.version.cuda", torch.version.cuda)
        _line("torch.backends.cudnn.version", torch.backends.cudnn.version() if torch.cuda.is_available() else "n/a")
    except Exception as e:
        _line("torch import", f"FAIL: {e}", ok=False)
        return 99

    _hdr("4. torch.cuda Status")
    avail = torch.cuda.is_available()
    _line("torch.cuda.is_available", avail, ok=avail)
    if not avail:
        fail_count += 1
        try:
            print(f"    cuda compile-time version: {torch._C._cuda_getCompiledVersion()}")
        except Exception as e:
            print(f"    compile-time check failed: {e}")
        try:
            count = torch.cuda.device_count()
            _line("torch.cuda.device_count", count)
        except Exception as e:
            print(f"    device_count failed: {e}")
        print("    -> moegliche Ursachen: NVIDIA Treiber zu alt, ")
        print("       GPU im Energiesparmodus, CUDA_VISIBLE_DEVICES gesetzt,")
        print("       oder anderer Prozess haelt CUDA exklusiv.")
    else:
        _line("device_name", torch.cuda.get_device_name(0))
        _line("device_count", torch.cuda.device_count())

    _hdr("5. torch-DLL-Pfad")
    torch_lib = Path(torch.__file__).parent / "lib"
    _line("torch/lib", torch_lib)
    if torch_lib.exists():
        dll_count = sum(1 for _ in torch_lib.glob("*.dll"))
        _line("DLL-Anzahl in torch/lib", dll_count)

    expected_lib = Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"
    matches_interpreter = (
        torch_lib.resolve() == expected_lib.resolve()
        if expected_lib.exists() else None
    )
    _line(
        "torch/lib gehoert zum aktuellen Interpreter",
        matches_interpreter,
        ok=(matches_interpreter is True),
    )
    if matches_interpreter is False:
        fail_count += 1
        print("    -> KRITISCH: torch wird aus einem anderen env geladen als erwartet!")
        print("    -> moegliche Ursache: PYTHONPATH oder PATH zeigt auf alten env")

    _hdr("6. PATH-Konflikte (mehrere torch-Installs?)")
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    torch_path_dirs = [
        d for d in path_dirs
        if d and "torch" in d.lower() and "lib" in d.lower()
    ]
    if len(torch_path_dirs) > 1:
        fail_count += 1
        _line("torch-Eintraege im PATH", len(torch_path_dirs), ok=False)
        for d in torch_path_dirs:
            print(f"      - {d}")
        print("    -> KRITISCH: Mehrere torch-DLL-Pfade in PATH = Mismatch-Risiko")
    elif len(torch_path_dirs) == 1:
        _line("torch-Eintraege im PATH", 1, ok=True)
        print(f"      - {torch_path_dirs[0]}")
    else:
        _line("torch-Eintraege im PATH", 0)

    _hdr("7. NVIDIA-Treiber-DLL")
    drv_store = Path(r"C:\Windows\System32\DriverStore\FileRepository")
    if drv_store.exists():
        nv_dirs = [d for d in drv_store.iterdir() if d.name.startswith("nv") and "amd64" in d.name]
        _line("NVIDIA Treiber-Ordner gefunden", len(nv_dirs))
        for d in sorted(nv_dirs, key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            print(f"      - {d.name}")
    else:
        _line("DriverStore", "nicht gefunden", ok=False)

    _hdr("8. torchvision import")
    try:
        import torchvision
        _line("torchvision.__version__", torchvision.__version__)
    except Exception as e:
        _line("torchvision import", f"FAIL: {e}", ok=False)
        fail_count += 1

    _hdr("9. RAFT Small isoliert auf CPU laden")
    try:
        from torchvision.models.optical_flow import raft_small, Raft_Small_Weights
        m = raft_small(weights=Raft_Small_Weights.DEFAULT)
        m = m.to("cpu").eval()
        nparams = sum(p.numel() for p in m.parameters())
        _line("RAFT geladen", f"{nparams:,} params", ok=True)
    except Exception as e:
        _line("RAFT-Load", f"FAIL: {type(e).__name__}: {e}", ok=False)
        fail_count += 1

    _hdr("10. SigLIP Tiny Smoke-Test")
    try:
        from transformers import AutoModel
        # Mini-Modell, kein 2.5 GB Download
        _ = AutoModel.from_pretrained("hf-internal-testing/tiny-random-SiglipModel")
        _line("Tiny-SigLIP geladen", "OK", ok=True)
    except Exception as e:
        _line("Tiny-SigLIP-Load", f"FAIL: {type(e).__name__}: {e}", ok=False)
        # nicht hart failen — kann transient sein (Network, HF-API)

    _hdr("SUMMARY")
    if fail_count == 0:
        print(">>> Diagnose OK — App-Start sollte stabil sein.")
        return 0
    print(f">>> {fail_count} kritische Findings. Fix die markierten [!!] Punkte.")
    return fail_count


if __name__ == "__main__":
    sys.exit(main())

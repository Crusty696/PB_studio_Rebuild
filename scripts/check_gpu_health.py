"""PB Studio — GPU & CUDA Health Check.

Vollstaendige Diagnose: Treiber, CUDA-Version, PyTorch-Kompatibilitaet,
ctranslate2, und klare Reparatur-Anweisungen.
"""

import os
import subprocess
import sys
from pathlib import Path


# ── Mindest-Treiber fuer CUDA-Versionen (Windows) ──────────────────────
MIN_DRIVER = {
    "12.8": 570.0,
    "12.6": 560.0,
    "12.4": 550.0,
    "12.1": 530.0,
    "11.8": 522.0,
    "11.7": 516.0,
    "11.6": 510.0,
}

# Ziel-Konfiguration fuer PB Studio
TARGET_CUDA = "12.4"
TARGET_TORCH = "2.5.1+cu124"
TARGET_MIN_DRIVER = 550.0


def _run_ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _get_driver_info() -> tuple[str, str, float]:
    """Returns (gpu_name, driver_version_str, driver_version_float)."""
    raw = _run_ps(
        "Get-CimInstance Win32_VideoController "
        "| Where-Object { $_.Name -match 'NVIDIA' } "
        "| Select-Object -First 1 Name, DriverVersion "
        "| Format-List"
    )
    gpu_name = ""
    driver_str = ""
    driver_num = 0.0
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("Name"):
            gpu_name = line.split(":", 1)[-1].strip()
        elif line.startswith("DriverVersion"):
            wv = line.split(":", 1)[-1].strip()
            parts = wv.split(".")
            if len(parts) >= 4:
                combined = parts[-2] + parts[-1]
                if len(combined) >= 5:
                    driver_str = combined[-5:-2] + "." + combined[-2:]
                    try:
                        driver_num = float(driver_str)
                    except ValueError:
                        pass
    return gpu_name, driver_str, driver_num


def check():
    W = 62
    print("=" * W)
    print("   PB STUDIO — GPU & CUDA VOLLDIAGNOSE")
    print("=" * W)
    issues = []

    # ── 1. GPU & Treiber ────────────────────────────────────────────────
    print("\n[1/5] NVIDIA GPU & Treiber...")
    gpu_name, driver_str, driver_num = _get_driver_info()
    if gpu_name:
        print(f"  GPU:     {gpu_name}")
        print(f"  Treiber: {driver_str}")
        if driver_num < TARGET_MIN_DRIVER:
            print(f"  FEHLER:  Treiber {driver_str} ist ZU ALT!")
            print(f"           Mindestens {TARGET_MIN_DRIVER:.0f}+ benoetigt fuer CUDA {TARGET_CUDA}")
            print(f"           Download: https://www.nvidia.com/drivers/")
            issues.append("driver_old")
        else:
            print(f"  OK:      Treiber {driver_str} >= {TARGET_MIN_DRIVER:.0f} (CUDA {TARGET_CUDA} kompatibel)")
    else:
        print("  FEHLER: Keine NVIDIA GPU erkannt!")
        print("          PB Studio benoetigt eine NVIDIA GPU fuer KI-Features.")
        issues.append("no_gpu")

    # ── 2. PyTorch & CUDA ───────────────────────────────────────────────
    print("\n[2/5] PyTorch Installation...")
    try:
        import torch
        torch_ver = torch.__version__
        torch_cuda = getattr(torch.version, "cuda", None) or "NONE"
        print(f"  PyTorch:    {torch_ver}")
        print(f"  CUDA built: {torch_cuda}")

        # Pruefe ob richtige CUDA-Version
        if "+cu124" in torch_ver:
            print(f"  OK:         Korrekte CUDA 12.4 Version")
        elif "+cu" in torch_ver:
            actual_cu = torch_ver.split("+")[1] if "+" in torch_ver else "?"
            print(f"  FEHLER:     Falsche CUDA-Version! Installiert: {actual_cu}, erwartet: cu124")
            print(f"              Reparatur: python scripts/fix_gpu_setup.py")
            issues.append("wrong_cuda")
        elif "+cpu" in torch_ver:
            print(f"  FEHLER:     CPU-only PyTorch installiert! Keine GPU-Beschleunigung.")
            print(f"              Reparatur: python scripts/fix_gpu_setup.py")
            issues.append("cpu_only")
        else:
            print(f"  WARNUNG:    Unbekanntes PyTorch-Build: {torch_ver}")
            issues.append("unknown_torch")

        # torchaudio / torchvision
        try:
            import torchaudio
            print(f"  torchaudio: {torchaudio.__version__}")
        except ImportError:
            print(f"  torchaudio: NICHT INSTALLIERT")
            issues.append("no_torchaudio")
        try:
            import torchvision
            print(f"  torchvision: {torchvision.__version__}")
        except ImportError:
            print(f"  torchvision: NICHT INSTALLIERT")
            issues.append("no_torchvision")

    except ImportError:
        print("  FEHLER: PyTorch nicht installiert!")
        issues.append("no_torch")

    # ── 3. CUDA Initialisierung ─────────────────────────────────────────
    print("\n[3/5] CUDA Initialisierung...")
    try:
        import torch
        if torch.cuda.is_available():
            dev = torch.cuda.get_device_name(0)
            cap = torch.cuda.get_device_capability(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024**3)
            print(f"  CUDA:     AKTIV")
            print(f"  Device:   {dev}")
            print(f"  Compute:  {cap[0]}.{cap[1]}")
            print(f"  VRAM:     {vram_gb:.1f} GB")
            free, total = torch.cuda.mem_get_info(0)
            print(f"  Frei:     {free / (1024**3):.1f} / {total / (1024**3):.1f} GB")
        else:
            print("  FEHLER: torch.cuda.is_available() = False")
            if "driver_old" in issues:
                print("           Ursache: NVIDIA-Treiber zu alt (siehe oben)")
            elif "wrong_cuda" in issues:
                print("           Ursache: Falsche PyTorch-CUDA-Version (siehe oben)")
            else:
                print("           Reparatur: python scripts/fix_gpu_setup.py")
            issues.append("cuda_unavailable")
    except ImportError:
        print("  Uebersprungen (kein PyTorch)")
    except Exception as e:
        print(f"  FEHLER: {e}")
        issues.append("cuda_init_error")

    # ── 4. ctranslate2 (faster-whisper Backend) ─────────────────────────
    print("\n[4/5] ctranslate2 (Whisper Backend)...")
    try:
        import ctranslate2
        print(f"  Version:  {ctranslate2.__version__}")
        try:
            n = ctranslate2.get_cuda_device_count()
            if n > 0:
                types = ctranslate2.get_supported_compute_types("cuda")
                print(f"  CUDA:     {n} Device(s), Typen: {', '.join(types)}")
            else:
                print(f"  CUDA:     Keine Devices (Treiber-Problem?)")
                issues.append("ct2_no_cuda")
        except RuntimeError as e:
            print(f"  CUDA:     FEHLER — {e}")
            issues.append("ct2_cuda_error")
    except ImportError:
        print("  NICHT INSTALLIERT")
        issues.append("no_ct2")

    # ── 5. Umgebungs-Variablen ──────────────────────────────────────────
    print("\n[5/5] Umgebung...")
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "<nicht gesetzt>")
    print(f"  CUDA_VISIBLE_DEVICES: {cuda_visible}")
    if cuda_visible not in ("<nicht gesetzt>", "", "0"):
        print(f"  WARNUNG: CUDA_VISIBLE_DEVICES={cuda_visible} koennte GPU blockieren!")
        issues.append("cuda_env")
    hf_token = "gesetzt" if os.environ.get("HF_TOKEN") else "NICHT gesetzt"
    print(f"  HF_TOKEN: {hf_token}")
    if hf_token == "NICHT gesetzt":
        print("  HINWEIS: HF_TOKEN setzen fuer schnellere Model-Downloads")

    # ── Zusammenfassung ─────────────────────────────────────────────────
    print("\n" + "=" * W)
    if not issues:
        print("  ALLES OK — GPU-Setup ist korrekt konfiguriert.")
    else:
        print("  PROBLEME GEFUNDEN:")
        if "no_gpu" in issues:
            print("  - Keine NVIDIA GPU erkannt")
        if "driver_old" in issues:
            print(f"  - NVIDIA-Treiber {driver_str} zu alt (min. {TARGET_MIN_DRIVER:.0f})")
            print(f"    FIX: https://www.nvidia.com/drivers/ -> Treiber {TARGET_MIN_DRIVER:.0f}+ installieren, PC neustarten")
        if "wrong_cuda" in issues or "cpu_only" in issues or "unknown_torch" in issues:
            print(f"  - Falsche PyTorch-Version installiert")
            print(f"    FIX: python scripts/fix_gpu_setup.py")
        if "cuda_unavailable" in issues and "driver_old" not in issues and "wrong_cuda" not in issues:
            print(f"  - CUDA nicht verfuegbar (unbekannter Grund)")
            print(f"    FIX: python scripts/fix_gpu_setup.py")

        print("\n  EMPFOHLENE REIHENFOLGE:")
        if "driver_old" in issues or "no_gpu" in issues:
            print("  1. NVIDIA-Treiber aktualisieren (Version 560+)")
            print("     https://www.nvidia.com/drivers/")
        print("  2. python scripts/fix_gpu_setup.py   (PyTorch reparieren)")
        print("  3. PC neustarten")
    print("=" * W)

    return len(issues) == 0


if __name__ == "__main__":
    ok = check()
    sys.exit(0 if ok else 1)

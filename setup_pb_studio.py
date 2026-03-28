#!/usr/bin/env python3
"""
PB Studio Rebuild - Setup Script
=================================
Erstellt ein Python 3.11 venv und installiert alle Dependencies automatisch.
Funktioniert autonom ohne manuelle Eingriffe.

Voraussetzung: Python 3.11 muss installiert sein.

Flags:
  --repair    Nur fehlende Packages nachinstallieren (kein venv-Neuaufbau)
"""

import os
import sys
import subprocess
import shutil
import time as _time
from pathlib import Path

# -- Konfiguration ----------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"

# Python 3.11 Suchpfade (Windows)
PY311_CANDIDATES = [
    Path(r"C:\Users") / os.environ.get("USERNAME", "david")
    / r"AppData\Local\Programs\Python\Python311\python.exe",
    Path(r"C:\Python311\python.exe"),
    Path(r"C:\Program Files\Python311\python.exe"),
    Path(r"C:\Program Files (x86)\Python311\python.exe"),
]

# PyTorch CUDA Index (cu124 — passend zu pyproject.toml)
PYTORCH_INDEX = "https://download.pytorch.org/whl/cu124"

# Packages die VOR dem Rest installiert werden muessen (mit CUDA)
TORCH_PACKAGES = [
    "torch==2.6.0+cu124",
    "torchaudio==2.6.0+cu124",
    "torchvision==0.21.0+cu124",
]

# beat-this Git-Installation (spezieller Commit)
BEAT_THIS_URL = (
    "git+https://github.com/CPJKU/beat_this.git"
    "@c8c320e84f1a4e5b291327debe754734ea802afc"
)

# Kritische Imports fuer Verifikation
CRITICAL_IMPORTS = [
    ("PySide6", "PySide6"),
    ("torch", "PyTorch"),
    ("torchaudio", "torchaudio"),
    ("librosa", "librosa"),
    ("demucs", "Demucs"),
    ("cv2", "OpenCV"),
    ("sqlalchemy", "SQLAlchemy"),
    ("transformers", "Transformers"),
    ("sounddevice", "sounddevice"),
    ("soundfile", "soundfile"),
]


# -- Hilfsfunktionen --------------------------------------------------------

def _print_header(text: str):
    w = max(60, len(text) + 6)
    print(f"\n{'=' * w}")
    print(f"   {text}")
    print(f"{'=' * w}\n")


def _print_step(num: int, total: int, text: str):
    bar_len = 30
    filled = int(bar_len * num / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"  [{bar}] Schritt {num}/{total}: {text}")


def _run(cmd: list[str], desc: str, cwd=None, env=None,
         check=True) -> subprocess.CompletedProcess:
    """Fuehrt einen Befehl aus und zeigt Fortschritt mit Zeitmessung."""
    print(f"  > {desc}...")
    t0 = _time.time()
    result = subprocess.run(
        cmd,
        cwd=cwd or str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = _time.time() - t0
    if check and result.returncode != 0:
        print(f"  [FAIL] FEHLER bei: {desc} ({elapsed:.0f}s)")
        print(f"    Command: {' '.join(cmd[:5])}...")
        if result.stderr:
            lines = result.stderr.strip().split("\n")
            for line in lines[-15:]:
                print(f"    {line}")
        return result
    print(f"  [OK] {desc} ({elapsed:.0f}s)")
    return result


# -- Python 3.11 finden -----------------------------------------------------

def find_python311() -> Path | None:
    """Sucht Python 3.11 auf dem System."""
    # 1. Bekannte Pfade pruefen
    for candidate in PY311_CANDIDATES:
        if candidate.exists():
            result = subprocess.run(
                [str(candidate), "--version"],
                capture_output=True, text=True,
            )
            if result.returncode == 0 and "3.11" in result.stdout:
                return candidate

    # 2. py launcher (Windows)
    try:
        result = subprocess.run(
            ["py", "-3.11", "--version"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and "3.11" in result.stdout:
            result2 = subprocess.run(
                ["py", "-3.11", "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True,
            )
            if result2.returncode == 0:
                return Path(result2.stdout.strip())
    except FileNotFoundError:
        pass

    # 3. PATH durchsuchen
    for name in ["python3.11", "python3", "python"]:
        path = shutil.which(name)
        if path:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True,
            )
            if result.returncode == 0 and "3.11" in result.stdout:
                return Path(path)

    return None


# -- NVIDIA/CUDA Vorab-Pruefung ----------------------------------------------

def check_nvidia() -> bool:
    """Prueft ob NVIDIA-Treiber und CUDA verfuegbar sind."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_info = result.stdout.strip()
            print(f"  [OK] NVIDIA GPU erkannt: {gpu_info}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("  [WARN] Kein NVIDIA-Treiber gefunden - CUDA wird nicht verfuegbar sein!")
    return False


# -- venv erstellen ----------------------------------------------------------

def create_venv(py311: Path) -> bool:
    """Erstellt das .venv Verzeichnis."""
    if VENV_PYTHON.exists():
        result = subprocess.run(
            [str(VENV_PYTHON), "--version"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and "3.11" in result.stdout:
            print(f"  [OK] Bestehendes venv gefunden: {VENV_DIR}")
            return True
        else:
            print("  [WARN] Bestehendes venv hat falsche Python-Version - wird neu erstellt...")
            shutil.rmtree(VENV_DIR, ignore_errors=True)

    result = _run(
        [str(py311), "-m", "venv", str(VENV_DIR)],
        f"Erstelle venv mit Python 3.11 in {VENV_DIR.name}/",
    )
    if result.returncode != 0:
        return False

    _run(
        [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
        "pip upgraden",
    )
    return VENV_PYTHON.exists()


# -- Installations-Schritte --------------------------------------------------

def install_torch() -> bool:
    """Installiert PyTorch + CUDA separat (braucht extra-index-url)."""
    cmd = [
        str(VENV_PIP), "install",
        "--extra-index-url", PYTORCH_INDEX,
    ] + TORCH_PACKAGES
    result = _run(cmd, f"PyTorch + CUDA installieren ({', '.join(TORCH_PACKAGES)})")
    return result.returncode == 0


def install_requirements() -> bool:
    """Installiert alle anderen Dependencies aus requirements.txt."""
    req_file = PROJECT_DIR / "requirements.txt"
    if not req_file.exists():
        print("  [FAIL] requirements.txt nicht gefunden!")
        return False
    result = _run(
        [str(VENV_PIP), "install", "-r", str(req_file)],
        "Alle Dependencies aus requirements.txt installieren",
    )
    return result.returncode == 0


def install_beat_this() -> bool:
    """Installiert beat-this von Git (spezieller Commit)."""
    result = _run(
        [str(VENV_PIP), "install", BEAT_THIS_URL],
        "beat-this (Git Commit) installieren",
    )
    return result.returncode == 0


def install_dev_deps() -> bool:
    """Installiert Dev-Dependencies (pytest)."""
    result = _run(
        [str(VENV_PIP), "install", "pytest>=9.0.2"],
        "pytest installieren",
    )
    return result.returncode == 0


# -- Verifikation -----------------------------------------------------------

def verify_installation() -> tuple[bool, list[str]]:
    """Verifiziert dass alle kritischen Packages importierbar sind.

    Returns: (all_ok, list_of_failed_packages)
    """
    print("\n  Verifikation - kritische Imports:")
    all_ok = True
    failed = []
    for module, name in CRITICAL_IMPORTS:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c",
             f"import {module}; print(getattr({module}, '__version__', 'OK'))"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"    [OK] {name}: {version}")
        else:
            print(f"    [FAIL] {name}: IMPORT FEHLER")
            all_ok = False
            failed.append(module)

    # CUDA Check
    result = subprocess.run(
        [str(VENV_PYTHON), "-c",
         "import torch; print(f'CUDA: {torch.cuda.is_available()}, "
         "Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"    [OK] {result.stdout.strip()}")
    else:
        print("    [WARN] CUDA-Check fehlgeschlagen")

    return all_ok, failed


# -- Repair-Modus -----------------------------------------------------------

def repair_mode():
    """Nur fehlende Packages nachinstallieren."""
    _print_header("PB Studio Rebuild - Repair")

    if not VENV_PYTHON.exists():
        print("  [FAIL] Kein .venv gefunden - bitte volles Setup ausfuehren.")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)

    print("  Pruefe installierte Packages...")
    all_ok, failed = verify_installation()

    if all_ok:
        print("\n  [OK] Alle Packages sind korrekt installiert. Nichts zu tun.")
        input("\nDruecke Enter zum Beenden...")
        return

    print(f"\n  {len(failed)} fehlende Packages gefunden. Repariere...")

    # Versuche fehlende Packages via pip nachzuinstallieren
    for module in failed:
        _run(
            [str(VENV_PIP), "install", module],
            f"Nachinstallation: {module}",
            check=False,
        )

    # Nochmals pruefen
    all_ok, still_failed = verify_installation()
    if all_ok:
        _print_header("Repair ERFOLGREICH")
    else:
        _print_header("Repair TEILWEISE (einige Packages fehlen noch)")
        print(f"  Fehlend: {', '.join(still_failed)}")

    input("\nDruecke Enter zum Beenden...")


# -- Hauptprogramm ----------------------------------------------------------

def main():
    # Repair-Modus?
    if "--repair" in sys.argv:
        repair_mode()
        return

    t_start = _time.time()
    _print_header("PB Studio Rebuild - Setup")
    print(f"  Projektverzeichnis: {PROJECT_DIR}")
    print(f"  Ziel-venv:          {VENV_DIR}")

    total_steps = 8

    # -- Schritt 1: NVIDIA/CUDA pruefen --
    _print_step(1, total_steps, "NVIDIA/CUDA pruefen")
    has_nvidia = check_nvidia()

    # -- Schritt 2: Python 3.11 finden --
    _print_step(2, total_steps, "Python 3.11 suchen")
    py311 = find_python311()
    if not py311:
        print("\n  [FAIL] FATAL: Python 3.11 wurde nicht gefunden!")
        print("    Bitte installiere Python 3.11 von:")
        print("    https://www.python.org/downloads/release/python-3110/")
        print("    und starte dieses Skript erneut.")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)
    print(f"  [OK] Python 3.11 gefunden: {py311}")

    # -- Schritt 3: venv erstellen --
    _print_step(3, total_steps, "Virtual Environment erstellen")
    if not create_venv(py311):
        print("\n  [FAIL] FATAL: venv konnte nicht erstellt werden!")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)

    # -- Schritt 4: PyTorch + CUDA --
    _print_step(4, total_steps, "PyTorch + CUDA installieren")
    if not install_torch():
        print("\n  [WARN] PyTorch-Installation fehlgeschlagen - versuche weiter...")

    # -- Schritt 5: requirements.txt --
    _print_step(5, total_steps, "Dependencies installieren")
    if not install_requirements():
        print("\n  [WARN] Einige Dependencies fehlgeschlagen - versuche weiter...")

    # -- Schritt 6: beat-this (Git) --
    _print_step(6, total_steps, "beat-this (Git) installieren")
    if not install_beat_this():
        print("\n  [WARN] beat-this Installation fehlgeschlagen (Git erforderlich)")

    # -- Schritt 7: Dev-Dependencies --
    _print_step(7, total_steps, "Dev-Dependencies installieren")
    install_dev_deps()

    # -- Schritt 8: Verifikation --
    _print_step(8, total_steps, "Installation verifizieren")
    all_ok, failed = verify_installation()

    elapsed_total = _time.time() - t_start
    minutes = int(elapsed_total // 60)
    seconds = int(elapsed_total % 60)

    if all_ok:
        _print_header("Setup ERFOLGREICH abgeschlossen")
        print(f"  venv:    {VENV_DIR}")
        print(f"  Python:  {VENV_PYTHON}")
        print(f"  Dauer:   {minutes}m {seconds}s")
        if not has_nvidia:
            print("\n  [WARN] NVIDIA nicht erkannt - GPU-Features deaktiviert.")
        print(f"\n  Starte die App mit:  start_pb_studio.bat")
        print(f"  Oder manuell:        .venv\\Scripts\\python.exe main.py")
        print(f"  Repair-Modus:        setup_pb_studio.py --repair")
    else:
        _print_header("Setup ABGESCHLOSSEN (mit Warnungen)")
        print(f"  Fehlende Packages: {', '.join(failed)}")
        print(f"  Dauer: {minutes}m {seconds}s")
        print(f"\n  Versuche Repair:  setup_pb_studio.py --repair")
        print(f"  Oder manuell:     {VENV_PIP} install <package-name>")

    input("\nDruecke Enter zum Beenden...")


if __name__ == "__main__":
    main()

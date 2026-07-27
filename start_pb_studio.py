#!/usr/bin/env python3
"""
PB Studio Rebuild - Start Script
==================================
Startet die App mit conda-env pb-studio. Fallback: .venv310, dann .venv.
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()

def resolve_venv_paths() -> tuple[Path, Path]:
    """Ermittelt dynamisch die bevorzugte Python-Umgebung."""
    conda_pb = Path.home() / "miniconda3" / "envs" / "pb-studio"
    if not (conda_pb / "python.exe").exists():
        conda_pb = Path.home() / "anaconda3" / "envs" / "pb-studio"
    
    if (conda_pb / "python.exe").exists():
        venv_dir = conda_pb
        venv_python = venv_dir / "python.exe"
    else:
        venv_dir = PROJECT_DIR / ".venv310"
        if not (venv_dir / "Scripts" / "python.exe").exists():
            venv_dir = PROJECT_DIR / ".venv"
        venv_python = venv_dir / "Scripts" / "python.exe"
        
    return venv_dir, venv_python

VENV_DIR, VENV_PYTHON = resolve_venv_paths()
MAIN_PY = PROJECT_DIR / "main.py"
CRASH_LOG = PROJECT_DIR / "logs" / "crash.log"

def _cleanup_pycache():
    """Loescht alle __pycache__ Verzeichnisse (verhindert Probleme nach Updates)."""
    project_root = PROJECT_DIR.resolve()
    for cache_dir in PROJECT_DIR.rglob("__pycache__"):
        try:
            resolved_cache = cache_dir.resolve()
        except OSError:
            continue
        if project_root != resolved_cache and project_root not in resolved_cache.parents:
            continue
        if ".venv" not in str(resolved_cache):
            shutil.rmtree(cache_dir, ignore_errors=True)

def main():
    global VENV_DIR, VENV_PYTHON
    print("=" * 50)
    print("  PB Studio Rebuild - Starter")
    print("=" * 50)

    # 1. Pruefen ob main.py existiert
    if not MAIN_PY.exists():
        print(f"\n  FEHLER: {MAIN_PY} nicht gefunden!")
        print(f"  Bist du im richtigen Verzeichnis? ({PROJECT_DIR})")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)

    # 2. Pruefen ob bevorzugte Python-Umgebung existiert
    if not VENV_PYTHON.exists():
        print(f"\n  Python-Umgebung nicht gefunden in: {VENV_DIR}")
        print("  Starte automatisches Setup...\n")

        setup_script = PROJECT_DIR / "setup_pb_studio.py"
        if setup_script.exists():
            result = subprocess.run(
                [sys.executable, str(setup_script)],
                cwd=str(PROJECT_DIR),
            )
            
            # Pfade nach dem Setup neu ermitteln
            VENV_DIR, VENV_PYTHON = resolve_venv_paths()
            
            if result.returncode != 0 or not VENV_PYTHON.exists():
                print("\n  FEHLER: Setup fehlgeschlagen!")
                print(f"  Bitte fuehre manuell aus: python {setup_script}")
                input("\nDruecke Enter zum Beenden...")
                sys.exit(1)
        else:
            print(f"  FEHLER: {setup_script.name} nicht gefunden!")
            print("  Bitte erstelle zuerst die conda-Umgebung:")
            print("    conda env create -f environment.yml")
            input("\nDruecke Enter zum Beenden...")
            sys.exit(1)

    # 3. Python-Version im venv pruefen
    result = subprocess.run(
        [str(VENV_PYTHON), "--version"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        py_version = result.stdout.strip()
        print(f"\n  Python: {py_version}")
    else:
        print("\n  WARNUNG: Konnte Python-Version nicht lesen")

    # 4. __pycache__ aufraeumen
    _cleanup_pycache()

    # 5. App starten
    print(f"  Starte: {MAIN_PY.name}")
    print("  " + "-" * 40)

    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env["PATH"] = str(VENV_DIR / "Scripts") + os.pathsep + env.get("PATH", "")
    
    # B-711: Laufzeit-Invarianten identisch zu start_pb_studio.bat (kanonisch).
    # NVIDIA GTX 1060 Fix: Lazy Loading für CUDA Module
    env["CUDA_MODULE_LOADING"] = "LAZY"
    # DG-001 / Surface Book 2: Video-Encode muss NVENC nutzen.
    # Kein libx264-CPU-Fallback bei Proxy/Export/Convert.
    env["PB_REQUIRE_NVENC"] = "1"
    # B-215 Fix: OpenMP/MKL Doppel-Init verhindern (STATUS_STACK_BUFFER_OVERRUN).
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["OMP_NUM_THREADS"] = "4"
    env["MKL_NUM_THREADS"] = "4"

    # stderr live in Datei schreiben (wie die .bat), statt erst nach Prozessende
    # aus einer PIPE lesbar zu sein.
    err_log = PROJECT_DIR / "outputs" / f"app_run_{datetime.now():%Y-%m-%d_%H%M%S}_err.log"
    err_log.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Err-Log: {err_log}")

    try:
        with open(err_log, "w", encoding="utf-8", errors="replace") as err_handle:
            result = subprocess.run(
                [str(VENV_PYTHON), str(MAIN_PY)],
                cwd=str(PROJECT_DIR),
                env=env,
                stderr=err_handle,
            )
        if result.returncode != 0:
            print(f"\n  App beendet mit Exit-Code: {result.returncode}")
            # Crash-Log schreiben
            try:
                stderr_text = err_log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                stderr_text = ""
            if stderr_text:
                CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
                with open(CRASH_LOG, "w", encoding="utf-8") as f:
                    f.write(f"Exit-Code: {result.returncode}\n\n")
                    f.write(stderr_text)
                print(f"  Crash-Log: {CRASH_LOG}")
                # Letzte 10 Zeilen stderr anzeigen
                lines = stderr_text.strip().split("\n")
                for line in lines[-10:]:
                    print(f"  {line}")
            # B-712: Exit-Code der App durchreichen, damit Crashes fuer
            # Automatisierung/CI sichtbar sind.
            sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n  App durch Benutzer beendet.")
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        print(f"\n  FEHLER: {e}")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)


if __name__ == "__main__":
    main()

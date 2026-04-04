#!/usr/bin/env python3
"""
PB Studio Rebuild - Start Script
==================================
Startet die App im lokalen .venv. Erstellt das venv automatisch falls noetig.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
MAIN_PY = PROJECT_DIR / "main.py"
CRASH_LOG = PROJECT_DIR / "logs" / "crash.log"


def _cleanup_pycache():
    """Loescht alle __pycache__ Verzeichnisse (verhindert Probleme nach Updates)."""
    for cache_dir in PROJECT_DIR.rglob("__pycache__"):
        if ".venv" not in str(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)


def main():
    print("=" * 50)
    print("  PB Studio Rebuild - Starter")
    print("=" * 50)

    # 1. Pruefen ob main.py existiert
    if not MAIN_PY.exists():
        print(f"\n  FEHLER: {MAIN_PY} nicht gefunden!")
        print(f"  Bist du im richtigen Verzeichnis? ({PROJECT_DIR})")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)

    # 2. Pruefen ob .venv existiert
    if not VENV_PYTHON.exists():
        print(f"\n  .venv nicht gefunden in: {VENV_DIR}")
        print("  Starte automatisches Setup...\n")

        setup_script = PROJECT_DIR / "setup_pb_studio.py"
        if setup_script.exists():
            result = subprocess.run(
                [sys.executable, str(setup_script)],
                cwd=str(PROJECT_DIR),
            )
            if result.returncode != 0 or not VENV_PYTHON.exists():
                print("\n  FEHLER: Setup fehlgeschlagen!")
                print(f"  Bitte fuehre manuell aus: python {setup_script}")
                input("\nDruecke Enter zum Beenden...")
                sys.exit(1)
        else:
            print(f"  FEHLER: {setup_script.name} nicht gefunden!")
            print("  Bitte erstelle zuerst das venv:")
            print(f'    py -3.11 -m venv "{VENV_DIR}"')
            print(f'    "{VENV_DIR}\\Scripts\\pip.exe" install -r requirements.txt')
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

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(MAIN_PY)],
            cwd=str(PROJECT_DIR),
            env=env,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print(f"\n  App beendet mit Exit-Code: {result.returncode}")
            # Crash-Log schreiben
            if result.stderr:
                CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
                with open(CRASH_LOG, "w", encoding="utf-8") as f:
                    f.write(f"Exit-Code: {result.returncode}\n\n")
                    f.write(result.stderr)
                print(f"  Crash-Log: {CRASH_LOG}")
                # Letzte 10 Zeilen stderr anzeigen
                lines = result.stderr.strip().split("\n")
                for line in lines[-10:]:
                    print(f"  {line}")
    except KeyboardInterrupt:
        print("\n  App durch Benutzer beendet.")
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        print(f"\n  FEHLER: {e}")
        input("\nDruecke Enter zum Beenden...")
        sys.exit(1)


if __name__ == "__main__":
    main()

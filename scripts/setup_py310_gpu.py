"""PB Studio - Komplett-Setup (Python 3.10 + CUDA 11.3).

Ablauf:
  Phase A - INVENTUR: Was ist bereits auf dem System?
  Phase B - INSTALL:  Nur fehlende Komponenten werden nachgezogen.

Geprueft / installiert:
  - Python 3.10
  - venv (.venv310)
  - torch 1.12.1+cu113 (kompat. NVIDIA Treiber 461.40)
  - Alle Pakete aus requirements-py310-cu113.txt
  - beat_this (vendor/beat_this)
  - Ollama + gemma4:e4b
  - FFmpeg in bin/
  - HuggingFace-Modelle: htdemucs, siglip, moondream2

Voraussetzung: Python 3.10
Download: https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe

Ausfuehrung:
    python scripts/setup_py310_gpu.py
    python scripts/setup_py310_gpu.py --check-only     (nur Inventur)
    python scripts/setup_py310_gpu.py --skip-models    (keine HF-Modelle laden)
    python scripts/setup_py310_gpu.py --skip-ollama    (kein Ollama-Check)
    python scripts/setup_py310_gpu.py --force-recreate (venv komplett neu bauen)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_ROOT / ".venv310"
REQUIREMENTS = PROJECT_ROOT / "requirements-py310-cu113.txt"
BEAT_THIS_DIR = PROJECT_ROOT / "vendor" / "beat_this"
FFMPEG_BIN = PROJECT_ROOT / "bin" / "ffmpeg.exe"
FFPROBE_BIN = PROJECT_ROOT / "bin" / "ffprobe.exe"

OLLAMA_MODEL = "gemma4:e4b"

HF_MODELS = [
    ("google/siglip-so400m-patch14-384", "SigLIP (Visual Embeddings)"),
    ("vikhyatk/moondream2", "Moondream2 (Vision LLM)"),
]
# Hinweis: Demucs (htdemucs_ft) liegt NICHT auf HuggingFace. Das Modell wird
# beim ersten Aufruf automatisch via torch.hub von dl.fbaipublicfiles.com geladen
# und in %USERPROFILE%\.cache\torch\hub\checkpoints\ abgelegt. Kein Pre-Cache noetig.

PY310_CANDIDATES = [
    r"C:\Python310\python.exe",
    r"C:\Python3.10\python.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Python\Python310\python.exe"),
    r"C:\Program Files\Python310\python.exe",
    r"C:\Program Files (x86)\Python310\python.exe",
]

OLLAMA_CANDIDATES = [
    os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
    os.path.expanduser(r"~\AppData\Local\Ollama\ollama.exe"),
    r"C:\Program Files\Ollama\ollama.exe",
]

HF_CACHE_ROOT = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def _run(cmd, check=True, capture=False, timeout=None):
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, timeout=timeout)


# ---------- Phase A: Inventur ----------

@dataclass
class Inventory:
    py310_path: str | None = None
    venv_python: str | None = None
    venv_pip: str | None = None
    torch_ok: bool = False
    cuda_ok: bool = False
    gpu_name: str = ""
    req_total: int = 0
    missing_requirements: list[str] = field(default_factory=list)
    beat_this_ok: bool = False
    ollama_path: str | None = None
    ollama_model_ok: bool = False
    ffmpeg_ok: bool = False
    hf_models_missing: list[tuple[str, str]] = field(default_factory=list)

    def everything_ok(self, skip_models: bool, skip_ollama: bool) -> bool:
        if not self.venv_python or not self.torch_ok or self.missing_requirements:
            return False
        if not self.beat_this_ok or not self.ffmpeg_ok:
            return False
        if not skip_ollama and (not self.ollama_path or not self.ollama_model_ok):
            return False
        if not skip_models and self.hf_models_missing:
            return False
        return True


def find_python310() -> str | None:
    try:
        r = _run(["py", "-3.10", "-c", "import sys; print(sys.executable)"],
                 check=False, capture=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    for p in PY310_CANDIDATES:
        if os.path.isfile(p):
            try:
                r = _run([p, "--version"], check=False, capture=True, timeout=5)
                if "3.10" in r.stdout:
                    return p
            except (OSError, subprocess.TimeoutExpired):
                pass
    return None


def find_ollama() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    for c in OLLAMA_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def parse_requirements() -> list[tuple[str, str | None]]:
    out = []
    if not REQUIREMENTS.exists():
        return out
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("--"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|<|>)\s*([A-Za-z0-9_.\-+]+)", line)
        if m:
            out.append((m.group(1).lower().replace("_", "-"), m.group(3)))
        else:
            m2 = re.match(r"^([A-Za-z0-9_.\-]+)", line)
            if m2:
                out.append((m2.group(1).lower().replace("_", "-"), None))
    return out


def check_venv_and_packages(inv: Inventory) -> None:
    if not VENV_DIR.exists():
        return
    python = VENV_DIR / "Scripts" / "python.exe"
    pip = VENV_DIR / "Scripts" / "pip.exe"
    if not python.exists() or not pip.exists():
        return
    inv.venv_python = str(python)
    inv.venv_pip = str(pip)

    r = _run([str(python), "-c",
              "import torch; print('V='+torch.__version__); "
              "print('C='+str(torch.cuda.is_available())); "
              "print('G='+(torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''))"],
             check=False, capture=True, timeout=60)
    if r.returncode == 0:
        inv.torch_ok = "1.12.1+cu113" in r.stdout
        inv.cuda_ok = "C=True" in r.stdout
        for line in r.stdout.splitlines():
            if line.startswith("G="):
                inv.gpu_name = line[2:].strip()

    r = _run([str(pip), "list", "--format=freeze"], check=False, capture=True, timeout=60)
    installed = {}
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            if "==" in line:
                n, v = line.split("==", 1)
                installed[n.lower().replace("_", "-")] = v.strip()

    reqs = parse_requirements()
    inv.req_total = len(reqs)
    for pkg, ver in reqs:
        if pkg not in installed:
            inv.missing_requirements.append(pkg if ver is None else f"{pkg}=={ver}")

    inv.beat_this_ok = "beat-this" in installed or "beat_this" in installed


def check_ollama(inv: Inventory) -> None:
    inv.ollama_path = find_ollama()
    if not inv.ollama_path:
        return
    r = _run([inv.ollama_path, "list"], check=False, capture=True, timeout=30)
    if r.returncode == 0 and OLLAMA_MODEL.split(":")[0] in r.stdout:
        inv.ollama_model_ok = True


def check_ffmpeg(inv: Inventory) -> None:
    inv.ffmpeg_ok = FFMPEG_BIN.exists() and FFPROBE_BIN.exists()


def check_hf_models(inv: Inventory) -> None:
    for repo, desc in HF_MODELS:
        cache_name = "models--" + repo.replace("/", "--")
        cache_path = HF_CACHE_ROOT / cache_name
        has_snapshot = cache_path.exists() and any(
            f.is_file() for f in cache_path.rglob("*") if "snapshots" in f.parts
        )
        if not has_snapshot:
            inv.hf_models_missing.append((repo, desc))


def run_inventory() -> Inventory:
    inv = Inventory()
    inv.py310_path = find_python310()
    check_venv_and_packages(inv)
    check_ollama(inv)
    check_ffmpeg(inv)
    check_hf_models(inv)
    return inv


def print_inventory(inv: Inventory) -> None:
    def mark(ok: bool) -> str:
        return "[OK]" if ok else "[--]"

    print("  Python 3.10      " + mark(bool(inv.py310_path)) + f"  {inv.py310_path or 'NICHT GEFUNDEN'}")
    print("  venv .venv310    " + mark(bool(inv.venv_python)))
    print("  torch 1.12+cu113 " + mark(inv.torch_ok))
    cuda_line = "  CUDA verfuegbar  " + mark(inv.cuda_ok)
    if inv.gpu_name:
        cuda_line += f"  ({inv.gpu_name})"
    print(cuda_line)
    if inv.venv_python:
        ok = inv.req_total - len(inv.missing_requirements)
        print("  requirements     " + mark(not inv.missing_requirements) +
              f"  {ok}/{inv.req_total} installiert")
        if inv.missing_requirements and len(inv.missing_requirements) <= 10:
            for p in inv.missing_requirements:
                print(f"                         - fehlt: {p}")
        elif inv.missing_requirements:
            print(f"                         ({len(inv.missing_requirements)} fehlen)")
    print("  beat_this        " + mark(inv.beat_this_ok))
    print("  Ollama           " + mark(bool(inv.ollama_path)) + f"  {inv.ollama_path or ''}")
    print(f"  Ollama {OLLAMA_MODEL.ljust(10)}" + mark(inv.ollama_model_ok))
    print("  FFmpeg (bin/)    " + mark(inv.ffmpeg_ok))
    total_hf = len(HF_MODELS)
    missing_hf = len(inv.hf_models_missing)
    print("  HF-Modelle       " + mark(missing_hf == 0) + f"  {total_hf - missing_hf}/{total_hf} gecacht")
    for repo, desc in inv.hf_models_missing:
        print(f"                         - fehlt: {desc} ({repo})")


# ---------- Phase B: Install (nur fehlendes) ----------

def ensure_venv(py310: str, force: bool) -> tuple[str, str]:
    if VENV_DIR.exists() and not force:
        print("  venv vorhanden - reuse.")
    else:
        if VENV_DIR.exists():
            print(f"  entferne altes venv: {VENV_DIR}")
            shutil.rmtree(VENV_DIR)
        print(f"  erstelle venv: {VENV_DIR}")
        _run([py310, "-m", "venv", str(VENV_DIR)])
    python = str(VENV_DIR / "Scripts" / "python.exe")
    pip = str(VENV_DIR / "Scripts" / "pip.exe")
    print("  aktualisiere pip/setuptools/wheel...")
    _run([python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], capture=True)
    return python, pip


def install_torch(pip: str) -> None:
    print("  installiere torch 1.12.1+cu113 / torchaudio / torchvision...")
    _run([pip, "install",
          "--extra-index-url", "https://download.pytorch.org/whl/cu113",
          "torch==1.12.1+cu113",
          "torchaudio==0.12.1+cu113",
          "torchvision==0.13.1+cu113"], timeout=1800)


def install_requirements(pip: str) -> None:
    print("  installiere App-Abhaengigkeiten...")
    _run([pip, "install", "-r", str(REQUIREMENTS),
          "--extra-index-url", "https://download.pytorch.org/whl/cu113"], timeout=1800)


def install_beat_this(pip: str) -> None:
    if not BEAT_THIS_DIR.exists():
        print(f"  WARNUNG: {BEAT_THIS_DIR} fehlt - uebersprungen.")
        return
    print("  installiere beat_this aus vendor/...")
    _run([pip, "install", str(BEAT_THIS_DIR), "--no-deps"], timeout=300)


def pull_ollama_model(ollama: str) -> None:
    print(f"  pulle {OLLAMA_MODEL} (~10 GB - kann dauern)...")
    try:
        _run([ollama, "pull", OLLAMA_MODEL], timeout=3600)
    except subprocess.TimeoutExpired:
        print("  WARNUNG: Ollama-Pull Timeout - manuell nachholen.")


def precache_hf(python: str, missing: list[tuple[str, str]]) -> None:
    token = os.environ.get("HUGGINGFACE_API_TOKEN") or os.environ.get("HF_TOKEN") or ""
    code = (
        "from huggingface_hub import snapshot_download\n"
        f"token = {token!r} or None\n"
        f"for repo, desc in {missing!r}:\n"
        "    print(f'  -> {desc} ({repo})')\n"
        "    try:\n"
        "        snapshot_download(repo_id=repo, token=token, resume_download=True)\n"
        "    except Exception as e:\n"
        "        print(f'     WARNUNG: {e}')\n"
    )
    _run([python, "-c", code], timeout=3600)


def smoke_test(python: str) -> bool:
    code = (
        "mods = ['PySide6.QtWidgets','torch','transformers','demucs','librosa','cv2',"
        "'scenedetect','sqlalchemy','alembic','opentimelineio','beat_this',"
        "'numpy','scipy','sklearn','numba','thefuzz','httpx','requests','dotenv',"
        "'yaml','PIL','onnxruntime','einops','rotary_embedding_torch',"
        "'huggingface_hub','accelerate','tokenizers','safetensors']\n"
        "fails = []\n"
        "for m in mods:\n"
        "    try: __import__(m)\n"
        "    except Exception as e: fails.append(f'{m}: {e}')\n"
        "print('OK' if not fails else 'FAIL: ' + ', '.join(fails))\n"
    )
    r = _run([python, "-c", code], capture=True, timeout=120)
    print(f"  {r.stdout.strip()}")
    return "OK" in r.stdout and "FAIL" not in r.stdout


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="PB Studio Komplett-Setup mit System-Inventur")
    parser.add_argument("--check-only", action="store_true",
                        help="Nur Inventur anzeigen, nichts installieren")
    parser.add_argument("--skip-models", action="store_true", help="HF-Modelle ueberspringen")
    parser.add_argument("--skip-ollama", action="store_true", help="Ollama-Check ueberspringen")
    parser.add_argument("--force-recreate", action="store_true", help="venv neu bauen")
    args = parser.parse_args()

    print("=" * 64)
    print("   PB STUDIO - Komplett-Setup (Py 3.10 + CUDA 11.3)")
    print("=" * 64)

    # Phase A
    print("\n--- PHASE A: System-Inventur ---")
    inv = run_inventory()
    print_inventory(inv)

    if not inv.py310_path:
        print("\nFEHLER: Python 3.10 muss zuerst installiert werden.")
        print("Download: https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe")
        sys.exit(1)

    if inv.everything_ok(args.skip_models, args.skip_ollama) and not args.force_recreate:
        print("\nAlles vorhanden - nichts zu tun.")
        if not args.check_only and inv.venv_python:
            print("\n--- Smoke-Test ---")
            smoke_test(inv.venv_python)
        print("\nApp starten:  start_pb_studio.bat")
        return

    if args.check_only:
        print("\n--check-only: es fehlen Komponenten (siehe oben). Ende.")
        sys.exit(2)

    # Phase B
    print("\n--- PHASE B: fehlende Komponenten installieren ---")

    need_full_install = False
    if not inv.venv_python or args.force_recreate:
        print("\n[venv]")
        python, pip = ensure_venv(inv.py310_path, args.force_recreate)
        need_full_install = True  # neues venv -> alles installieren
    else:
        python, pip = inv.venv_python, inv.venv_pip
        print("\n[venv] uebersprungen - bereits vorhanden.")

    if need_full_install or not inv.torch_ok:
        print("\n[torch]")
        install_torch(pip)
    else:
        print("\n[torch] uebersprungen - bereits installiert.")

    if need_full_install or inv.missing_requirements:
        print("\n[requirements]")
        install_requirements(pip)
    else:
        print("\n[requirements] uebersprungen - alle Pakete installiert.")

    if need_full_install or not inv.beat_this_ok:
        print("\n[beat_this]")
        install_beat_this(pip)
    else:
        print("\n[beat_this] uebersprungen - bereits installiert.")

    if not args.skip_ollama:
        if not inv.ollama_path:
            print("\n[ollama] nicht gefunden.")
            print("  Installieren: https://ollama.com/download/windows")
            print(f"  Dann:         ollama pull {OLLAMA_MODEL}")
        elif not inv.ollama_model_ok:
            print(f"\n[ollama] Modell {OLLAMA_MODEL} fehlt")
            pull_ollama_model(inv.ollama_path)
        else:
            print(f"\n[ollama] uebersprungen - {OLLAMA_MODEL} bereits gecacht.")

    if not inv.ffmpeg_ok:
        print("\n[ffmpeg] WARNUNG: bin/ffmpeg.exe oder bin/ffprobe.exe fehlt.")
        print("  Download: https://www.gyan.dev/ffmpeg/builds/  (shared build)")
    else:
        print("\n[ffmpeg] OK.")

    if not args.skip_models and inv.hf_models_missing:
        print(f"\n[hf-models] {len(inv.hf_models_missing)} fehlen - lade nach...")
        precache_hf(python, inv.hf_models_missing)
    else:
        print("\n[hf-models] uebersprungen - alle gecacht.")

    print("\n--- Smoke-Test ---")
    ok = smoke_test(python)

    print()
    print("=" * 64)
    print("   SETUP ERFOLGREICH" if ok else "   SETUP UNVOLLSTAENDIG - siehe Warnungen oben")
    print()
    print("   App starten:  start_pb_studio.bat")
    print("=" * 64)
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nFEHLER: Befehl fehlgeschlagen (exit={e.returncode}): {e.cmd}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(130)

# installer/hooks/runtime_hook_torch.py
# PyInstaller runtime hook — runs BEFORE main.py at app startup.
#
# Fixes torch CUDA discovery inside a frozen PyInstaller bundle:
# - Sets CUDA_PATH so torch finds cuDNN / cublas DLLs in _MEIPASS
# - Adds the bundle root to PATH so bundled DLLs are discoverable
# - Disables torch's online version check (network call at import time)

import os
import sys

if getattr(sys, 'frozen', False):
    # We are running inside a PyInstaller bundle
    bundle_dir = sys._MEIPASS  # noqa: SIM117

    # 1. Add bundled DLL directories to PATH. PyInstaller may place CUDA/Torch
    # DLLs either at bundle root or in package-local folders after pruning.
    dll_dirs = [
        bundle_dir,
        os.path.join(bundle_dir, 'torch', 'lib'),
        os.path.join(bundle_dir, 'torch', 'bin'),
        os.path.join(bundle_dir, 'torchvision'),
        os.path.join(bundle_dir, 'PySide6'),
    ]
    existing_dll_dirs = [p for p in dll_dirs if os.path.isdir(p)]
    os.environ['PATH'] = os.pathsep.join(existing_dll_dirs + [os.environ.get('PATH', '')])

    # 2. Point CUDA_PATH to the bundle so torch finds cudart/cublas/cudnn
    os.environ['CUDA_PATH'] = bundle_dir
    os.environ['CUDA_HOME'] = bundle_dir

    # 3. Disable torch update nag / telemetry
    os.environ['PYTORCH_DISABLE_TELEMETRY'] = '1'
    os.environ['TORCH_WARN_ALWAYS'] = '0'

    # 4. Set default model cache to a user-writable directory
    #    (models are NOT bundled — downloaded on first use)
    user_data = os.path.join(os.path.expanduser('~'), '.pbstudio', 'models')
    os.makedirs(user_data, exist_ok=True)
    os.environ.setdefault('TRANSFORMERS_CACHE', user_data)
    os.environ.setdefault('HF_HOME', user_data)
    os.environ.setdefault('TORCH_HOME', user_data)

    # 4b. Numba/umap JIT-Disk-Cache in ein beschreibbares Verzeichnis (B-618).
    #     Im Frozen liegen pynndescents .py im PYZ (kein beschreibbarer Pfad) —
    #     ohne dies kann numba den @njit(cache=True)-Cache nicht persistieren und
    #     JITet bei JEDEM Start kalt neu. Der PB_WARMUP_UMAP-Kindprozess schreibt
    #     hierhin, Eltern- und Folge-Starts lesen denselben warmen Cache.
    numba_cache = os.path.join(os.path.expanduser('~'), '.pbstudio', 'numba_cache')
    os.makedirs(numba_cache, exist_ok=True)
    os.environ.setdefault('NUMBA_CACHE_DIR', numba_cache)

    # 5. PySide6/Qt plugin path — tell Qt where to find platform plugins
    qt_plugin_path = os.path.join(bundle_dir, 'PySide6', 'plugins')
    if os.path.isdir(qt_plugin_path):
        os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qt_plugin_path, 'platforms')

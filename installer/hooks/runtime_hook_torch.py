# installer/hooks/runtime_hook_torch.py
# PyInstaller runtime hook — runs BEFORE main.py at app startup.
#
# Fixes torch CUDA discovery inside a frozen PyInstaller bundle:
# - Sets CUDA_PATH so torch finds cuDNN / cublas DLLs in _MEIPASS
# - Adds the bundle root to PATH so ctranslate2 finds its DLLs
# - Disables torch's online version check (network call at import time)

import os
import sys

if getattr(sys, 'frozen', False):
    # We are running inside a PyInstaller bundle
    bundle_dir = sys._MEIPASS  # noqa: SIM117

    # 1. Add bundle root to PATH so all bundled DLLs are found
    os.environ['PATH'] = bundle_dir + os.pathsep + os.environ.get('PATH', '')

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

    # 5. PySide6/Qt plugin path — tell Qt where to find platform plugins
    qt_plugin_path = os.path.join(bundle_dir, 'PySide6', 'plugins')
    if os.path.isdir(qt_plugin_path):
        os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qt_plugin_path, 'platforms')

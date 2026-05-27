# -*- mode: python ; coding: utf-8 -*-
# pb_studio.spec — PyInstaller build spec for PB Studio Rebuild v0.5.0
#
# Usage:
#   poetry run pyinstaller pb_studio.spec
#
# Prerequisites:
#   pip install pyinstaller
#
# Output:
#   dist/pb_studio/          <- app folder (pass to NSIS)
#   dist/pb_studio.exe       <- single launcher (optional)
#
# NOTE: Full CUDA build is ~15-20 GB. Use --onedir (default here), not --onefile.
# Models (Demucs, SigLIP) are NOT bundled — downloaded to %USERPROFILE%\.cache on first use.

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None
ROOT = Path(SPEC).parent  # project root

# ---------------------------------------------------------------------------
# Import packaging hooks directly from pb_packaging
# ---------------------------------------------------------------------------
try:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from pb_packaging.bundle_hooks import hiddenimports as pkg_hidden, datas as pkg_datas
except Exception as e:
    pkg_hidden, pkg_datas = [], []

# ---------------------------------------------------------------------------
# Heavy packages — collect all binaries + data (CUDA DLLs live here)
# ---------------------------------------------------------------------------
torch_datas,       torch_bins,       torch_hidden       = collect_all('torch')
torchaudio_datas,  torchaudio_bins,  torchaudio_hidden  = collect_all('torchaudio')
torchvision_datas, torchvision_bins, torchvision_hidden = collect_all('torchvision')
pyside6_datas,     pyside6_bins,     pyside6_hidden     = collect_all('PySide6')

# ---------------------------------------------------------------------------
# Project asset data (resources, styles, knowledge)
# ---------------------------------------------------------------------------
project_datas = [
    (str(ROOT / 'resources'),  'resources'),
    (str(ROOT / 'styles'),     'styles'),
    (str(ROOT / 'knowledge'),  'knowledge'),
    (str(ROOT / 'translations'), 'translations'),
    (str(ROOT / 'config'),     'config'),
    (str(ROOT / 'database' / 'alembic'), 'database/alembic'),
    (str(ROOT / 'services' / 'brain_v3' / 'storage' / 'sql_migrations'), 'services/brain_v3/storage/sql_migrations'),
    (str(ROOT / 'bin' / 'ffmpeg.exe'), 'bin'),
    (str(ROOT / 'bin' / 'ffprobe.exe'), 'bin'),
]

all_datas    = project_datas + torch_datas + torchaudio_datas + torchvision_datas + pyside6_datas + [(str(ROOT / src), dest) for src, dest in pkg_datas]
all_binaries = torch_bins + torchaudio_bins + torchvision_bins + pyside6_bins

# ---------------------------------------------------------------------------
# Hidden imports — packages that PyInstaller can't auto-detect
# ---------------------------------------------------------------------------
all_hidden = list(set([
    # SQLAlchemy
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.orm',
    'sqlalchemy.event',
    'sqlalchemy.pool',
    # DB package
    'database',
    'database.models',
    'database.session',
    'database.migrations',
    # Services
    'services',
    'services.actions',
    'services.actions.ai_actions',
    'services.actions.audio_actions',
    'services.actions.edit_actions',
    'services.actions.video_actions',
    # Workers
    'workers',
    'workers.analysis',
    'workers.audio',
    'workers.audio_analysis',
    'workers.base',
    'workers.debug',
    'workers.edit',
    'workers.import_export',
    'workers.registry',
    'workers.video',
    # UI
    'ui',
    'ui.theme',
    'ui.timeline',
    'ui.waveform_item',
    'ui.chat_dock',
    'ui.workspaces',
    'ui.widgets',
    'ui.dialogs',
    'ui.controllers',
    # Audio/ML
    'librosa',
    'librosa.core',
    'librosa.feature',
    'librosa.effects',
    'soundfile',
    'sounddevice',
    'scipy',
    'scipy.signal',
    'scipy.fft',
    'scipy.io',
    'scipy.io.wavfile',
    'demucs',
    'demucs.pretrained',
    'demucs.apply',
    'beat_this',
    # Vision
    'cv2',
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    # Misc
    'opentimelineio',
    'pyarrow',
    'thefuzz',
    'thefuzz.fuzz',
    'click',
    'dotenv',
    'einops',
    'accelerate',
    'transformers',
    'transformers.models',
    'scenedetect',
    *torch_hidden,
    *torchaudio_hidden,
    *torchvision_hidden,
    *pyside6_hidden,
    *collect_submodules('librosa'),
    *collect_submodules('demucs'),
    *pkg_hidden,
]))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[str(ROOT / 'installer' / 'hooks')],
    hooksconfig={},
    runtime_hooks=[str(ROOT / 'installer' / 'hooks' / 'runtime_hook_torch.py')],
    excludes=[
        # Dev/notebook bloat — not needed at runtime
        'matplotlib',
        'notebook',
        'ipython',
        'IPython',
        'jupyter',
        'jupyterlab',
        'pytest',
        'sphinx',
        # Large unused torch backends
        'torch.distributed',
        'torch.utils.tensorboard',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# PYZ — pure-Python archive
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# EXE — launcher stub
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir mode
    name='pb_studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,                    # don't strip on Windows
    upx=True,                       # compress with UPX if available
    console=False,                  # no console window (windowed app)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'resources' / 'pb_studio.ico') if (ROOT / 'resources' / 'pb_studio.ico').exists() else None,
    version=str(ROOT / 'installer' / 'version_info.txt') if (ROOT / 'installer' / 'version_info.txt').exists() else None,
)

# ---------------------------------------------------------------------------
# COLLECT — gather everything into dist/pb_studio/
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        # Never compress these — UPX breaks them on Windows
        'vcruntime140.dll',
        'vcruntime140_1.dll',
        'msvcp140.dll',
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
        'cudart64_12.dll',
        'cublas64_12.dll',
        'cudnn64_9.dll',
        'torch_cuda.dll',
        '_C.pyd',
    ],
    name='pb_studio',
)

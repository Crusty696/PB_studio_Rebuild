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
def _filter_known_unused_hidden(hiddenimports):
    """Drop collected hidden imports that are explicitly unused by PB Studio."""
    blocked_exact = {
        'workers.debug',
    }
    blocked_prefixes = (
        'torch.distributed',
        'torch.testing',
        'torch.utils.benchmark',
        'torch.utils.tensorboard',
        'pyqtgraph.opengl',
        'PySide6.scripts.deploy_lib',
    )
    return [
        item for item in hiddenimports
        if item not in blocked_exact
        and not any(item.startswith(prefix) for prefix in blocked_prefixes)
    ]


def _keep_known_used_submodule(name):
    return _filter_known_unused_hidden([name]) == [name]


def _filter_known_unused_toc(entries):
    blocked_names = {
        'onnxruntime_providers_tensorrt.dll',
        'qsqlmimer.dll',
        'qsqlpsql.dll',
        'tbbpool.cp310-win_amd64.pyd',
        '_torchaudio_ffmpeg.pyd',
        'libtorchaudio_ffmpeg.pyd',
    }
    blocked_parts = (
        'PySide6/qml/QtWebView/',
        'PySide6\\qml\\QtWebView\\',
    )
    result = []
    for entry in entries:
        src = str(entry[0])
        normalized = src.replace('\\', '/')
        if Path(src).name in blocked_names:
            continue
        if any(part.replace('\\', '/') in normalized for part in blocked_parts):
            continue
        result.append(entry)
    return result


torch_datas,       torch_bins,       torch_hidden       = collect_all('torch', filter_submodules=_keep_known_used_submodule)
torchaudio_datas,  torchaudio_bins,  torchaudio_hidden  = collect_all('torchaudio')
torchvision_datas, torchvision_bins, torchvision_hidden = collect_all('torchvision')
pyside6_datas,     pyside6_bins,     pyside6_hidden     = collect_all('PySide6', filter_submodules=_keep_known_used_submodule)

torch_hidden = _filter_known_unused_hidden(torch_hidden)
pyside6_hidden = _filter_known_unused_hidden(pyside6_hidden)
pyside6_datas = _filter_known_unused_toc(pyside6_datas)
pyside6_bins = _filter_known_unused_toc(pyside6_bins)

# ---------------------------------------------------------------------------
# Project asset data (resources, styles, knowledge)
# ---------------------------------------------------------------------------
project_datas = [
    (str(ROOT / 'resources'),  'resources'),
    # B-SPEC-styles: 'styles'-Ordner wurde bei Repo-Bereinigung (146d0f4) entfernt;
    # Theme kommt jetzt aus ui/theme.py (get_stylesheet). Stale Referenz brach den
    # PyInstaller-Build ("Unable to find ...\\styles"). STYLE_DIR in main.py:174 ist tot.
    # (str(ROOT / 'styles'),     'styles'),
    (str(ROOT / 'knowledge'),  'knowledge'),
    (str(ROOT / 'translations'), 'translations'),
    (str(ROOT / 'config'),     'config'),
    (str(ROOT / 'database' / 'alembic'), 'database/alembic'),
    (str(ROOT / 'services' / 'brain' / 'storage' / 'sql_migrations'), 'services/brain/storage/sql_migrations'),
    (str(ROOT / 'bin' / 'ffmpeg.exe'), 'bin'),
    (str(ROOT / 'bin' / 'ffprobe.exe'), 'bin'),
    # Bundled Ollama (GPU/CUDA) — services/ollama_service.py:95 sucht im frozen
    # Bundle nach {sys._MEIPASS}/redist/ollama.exe. lib/ollama/ enthaelt die
    # CUDA-Runner (cuda_v12 fuer GTX 1060) + ggml-DLLs; Ollama laedt sie relativ
    # zur EXE (redist/lib/ollama/). Ohne dieses Bundle faellt die App auf ein
    # systemweit installiertes Ollama zurueck (ollama_service.py:101).
    (str(ROOT / 'redist' / 'ollama.exe'), 'redist'),
    (str(ROOT / 'redist' / 'lib'), 'redist/lib'),
]

all_datas    = project_datas + torch_datas + torchaudio_datas + torchvision_datas + pyside6_datas + [(str(ROOT / src), dest) for src, dest in pkg_datas]
vc_runtime_bins = []
for dll_name in (
    'vcruntime140.dll',
    'vcruntime140_1.dll',
    'msvcp140.dll',
    'msvcp140_1.dll',
    'msvcp140_2.dll',
    'concrt140.dll',
    'zlib.dll',
):
    dll_path = Path(sys.prefix) / dll_name
    if dll_path.exists():
        vc_runtime_bins.append((str(dll_path), '.'))

all_binaries = _filter_known_unused_toc(torch_bins + torchaudio_bins + torchvision_bins + pyside6_bins + vc_runtime_bins)

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
    'workers.edit',
    'workers.import_export',
    'workers.brain_v3_hashing',
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
all_hidden = _filter_known_unused_hidden(all_hidden)

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
        'torch.testing',
        'torch.utils.benchmark',
        'torch.utils.tensorboard',
        'pyqtgraph.opengl',
        'PySide6.scripts.deploy_lib',
        'pycparser.lextab',
        'pycparser.yacctab',
        'tzdata',
        'scipy.special._cdflib',
        'pysqlite2',
        'MySQLdb',
        'PySide6.QtSql',
        'PySide6.QtWebView',
        'onnxruntime.capi.onnxruntime_providers_tensorrt',
        'numba.np.ufunc.tbbpool',
        'torchaudio._torchaudio_ffmpeg',
        'torchaudio.lib.libtorchaudio_ffmpeg',
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
        # Active GTX-1060 runtime: torch 1.12.1+cu113.
        'cudart64_110.dll',
        'cublas64_11.dll',
        'cublasLt64_11.dll',
        'cudnn64_8.dll',
        'cudnn_adv_infer64_8.dll',
        'cudnn_adv_train64_8.dll',
        'cudnn_cnn_infer64_8.dll',
        'cudnn_cnn_train64_8.dll',
        'cudnn_ops_infer64_8.dll',
        'cudnn_ops_train64_8.dll',
        'c10_cuda.dll',
        'torch_cuda_cpp.dll',
        'torch_cuda_cu.dll',
        'cudart64_12.dll',
        'cublas64_12.dll',
        'cudnn64_9.dll',
        'torch_cuda.dll',
        '_C.pyd',
    ],
    name='pb_studio',
)

# installer/hooks/hook-torchaudio.py
# PB Studio uses torchaudio with the soundfile backend plus managed FFmpeg CLI fallback.

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


_FFMPEG_EXTENSIONS = {
    '_torchaudio_ffmpeg.pyd',
    'libtorchaudio_ffmpeg.pyd',
}


def _keep_runtime_submodule(name):
    blocked = (
        'torchaudio._torchaudio_ffmpeg',
        'torchaudio.lib.libtorchaudio_ffmpeg',
    )
    return name not in blocked


binaries = [
    entry for entry in collect_dynamic_libs('torchaudio')
    if Path(str(entry[0])).name not in _FFMPEG_EXTENSIONS
]
hiddenimports = collect_submodules('torchaudio.lib', filter=_keep_runtime_submodule)

module_collection_mode = 'pyz+py'

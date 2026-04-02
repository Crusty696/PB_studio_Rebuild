# installer/hooks/hook-ctranslate2.py
# Ensures ctranslate2 CUDA DLLs (cudnn64_9.dll, libiomp5md.dll, etc.) are bundled.

from PyInstaller.utils.hooks import collect_all, logger

datas, binaries, hiddenimports = collect_all('ctranslate2')

try:
    import ctranslate2
    from pathlib import Path

    ct2_root = Path(ctranslate2.__file__).parent
    for dll in ct2_root.glob('*.dll'):
        binaries.append((str(dll), '.'))
        logger.info(f'hook-ctranslate2: added {dll.name}')

except Exception as e:
    logger.warning(f'hook-ctranslate2: {e}')

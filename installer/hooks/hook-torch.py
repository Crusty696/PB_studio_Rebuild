# installer/hooks/hook-torch.py
# PyInstaller analysis hook for torch — supplements the built-in hook.
#
# Ensures torch's lazy-loaded CUDA extension DLLs are picked up even if
# collect_all() misses them (happens with torch >= 2.4 on Windows).

from PyInstaller.utils.hooks import collect_all, collect_data_files, logger

datas, binaries, hiddenimports = collect_all('torch')

# Explicitly add torch.libs / torch.lib directory if present
try:
    import torch
    import os
    from pathlib import Path

    torch_root = Path(torch.__file__).parent
    lib_dir = torch_root / 'lib'

    if lib_dir.is_dir():
        for dll in lib_dir.glob('*.dll'):
            binaries.append((str(dll), '.'))
            logger.info(f'hook-torch: added {dll.name}')

    # torch/_C extensions
    for pyd in torch_root.rglob('*.pyd'):
        binaries.append((str(pyd), str(pyd.parent.relative_to(torch_root.parent))))

except Exception as e:
    logger.warning(f'hook-torch: {e}')

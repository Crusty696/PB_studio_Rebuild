# installer/hooks/hook-pyqtgraph.py
# PyInstaller analysis hook for PB Studio's pyqtgraph usage.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def _keep_runtime_submodule(name):
    blocked_prefixes = (
        'pyqtgraph.examples',
        'pyqtgraph.jupyter',
        'pyqtgraph.opengl',
    )
    return name not in blocked_prefixes and not any(
        name.startswith(prefix + '.') for prefix in blocked_prefixes
    )


datas = collect_data_files('pyqtgraph', excludes=['**/examples/*'])
all_imports = collect_submodules('pyqtgraph', filter=_keep_runtime_submodule)
hiddenimports = [name for name in all_imports if 'Template' in name]
hiddenimports += ['pyqtgraph.multiprocess.bootstrap']

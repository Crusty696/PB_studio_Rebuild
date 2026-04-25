"""D-023 P6: Bundle-Hooks Sanity-Check.

Stellt sicher, dass alle in packaging.bundle_hooks gelisteten Module
auch tatsächlich existieren — sonst läuft pyinstaller --collect-all
zwar durch, aber zur Laufzeit fehlen Imports.
"""
import importlib

from pb_packaging.bundle_hooks import hiddenimports


def test_all_hidden_imports_resolvable():
    failed = []
    for mod in hiddenimports:
        try:
            importlib.import_module(mod)
        except ImportError as e:
            failed.append((mod, str(e)))
    assert not failed, f"Bundle-Hook-Module nicht importierbar: {failed}"


def test_hidden_imports_unique():
    assert len(hiddenimports) == len(set(hiddenimports))

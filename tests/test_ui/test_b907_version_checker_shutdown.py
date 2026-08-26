from types import SimpleNamespace

import shiboken6
from PySide6.QtCore import QThread

from main import PBWindow


def test_shutdown_ignores_already_deleted_version_checker() -> None:
    checker = QThread()
    shiboken6.delete(checker)
    assert not shiboken6.isValid(checker)

    owner = SimpleNamespace(_version_checker=checker)
    PBWindow._stop_version_checker(owner)

    assert owner._version_checker is None

"""B-138 regression test: OpenProjectDialog must validate SQLite magic.

Cycle-3 tester flagged: ``_check_path`` only verified file existence.
A 0-byte or text file named pb_studio.db produced "found" but the
subsequent open_project crashed with "file is not a database".
"""

from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui.dialogs.project_dialog import OpenProjectDialog


def test_check_path_validates_sqlite_magic_header() -> None:
    src = inspect.getsource(OpenProjectDialog._check_path)
    # Must read the file and check for the SQLite-3 magic header.
    has_magic_check = (
        b"SQLite format 3" in src.encode("utf-8")
        or "SQLite format 3" in src
    )
    assert has_magic_check, (
        "BUG-138 regression: _check_path still only checks .exists() "
        "without verifying the SQLite magic header. Read the first "
        "16 bytes and assert they start with b'SQLite format 3\\x00'."
    )


# --------------------------------------------------------------------------
# B-352: manueller Accept-Pfad muss denselben SQLite-Magic-Check machen.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def _make_dialog(_qapp, monkeypatch):
    """Erzeugt einen OpenProjectDialog und faengt accept()/warning() ab."""
    from PySide6.QtWidgets import QMessageBox

    dlg = OpenProjectDialog()
    accepted = {"n": 0}
    monkeypatch.setattr(dlg, "accept", lambda: accepted.__setitem__("n", accepted["n"] + 1))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    return dlg, accepted


def test_validate_and_accept_rejects_non_sqlite_db(_qapp, monkeypatch, tmp_path):
    """B-352: eine pb_studio.db ohne SQLite-Header darf NICHT akzeptiert werden."""
    (tmp_path / "pb_studio.db").write_text("not a database")
    dlg, accepted = _make_dialog(_qapp, monkeypatch)
    try:
        dlg.path_input.setText(str(tmp_path))
        dlg._validate_and_accept()
        assert accepted["n"] == 0, "Korrupte pb_studio.db wurde faelschlich akzeptiert"
    finally:
        dlg.deleteLater()


def test_validate_and_accept_rejects_empty_db(_qapp, monkeypatch, tmp_path):
    """B-352: eine 0-Byte pb_studio.db darf NICHT akzeptiert werden."""
    (tmp_path / "pb_studio.db").write_bytes(b"")
    dlg, accepted = _make_dialog(_qapp, monkeypatch)
    try:
        dlg.path_input.setText(str(tmp_path))
        dlg._validate_and_accept()
        assert accepted["n"] == 0, "Leere pb_studio.db wurde faelschlich akzeptiert"
    finally:
        dlg.deleteLater()


def test_validate_and_accept_accepts_valid_sqlite(_qapp, monkeypatch, tmp_path):
    """B-352: eine echte SQLite-Datei wird weiterhin akzeptiert."""
    import sqlite3

    db_path = tmp_path / "pb_studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()

    dlg, accepted = _make_dialog(_qapp, monkeypatch)
    try:
        dlg.path_input.setText(str(tmp_path))
        dlg._validate_and_accept()
        assert accepted["n"] == 1, "Gueltige SQLite-pb_studio.db wurde nicht akzeptiert"
    finally:
        dlg.deleteLater()

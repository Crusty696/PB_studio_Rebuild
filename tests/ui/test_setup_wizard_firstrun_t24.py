"""NEUBAU-VOLLINTEGRATION T2.4 (WIRE-001/DEAD-002): SetupWizard beim First-Run.

Vorher: ui/dialogs/setup_wizard.py (inkl. Download-Worker, intern korrekt)
wurde nirgends im Produkt aufgerufen — 868 Zeilen toter Einstieg.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


class _WizardSpy:
    instances = []

    def __init__(self):
        self.exec_called = False
        _WizardSpy.instances.append(self)

    def exec(self):
        self.exec_called = True
        return 1


class _Splash:
    def __init__(self):
        self.hidden = False
        self.shown = False

    def hide(self):
        self.hidden = True

    def show(self):
        self.shown = True


def test_wizard_runs_on_first_run(monkeypatch):
    _qapp()
    import main as main_mod
    import ui.dialogs.setup_wizard as sw
    _WizardSpy.instances.clear()
    monkeypatch.setattr(sw, "is_setup_complete", lambda: False)
    monkeypatch.setattr(sw, "SetupWizard", _WizardSpy)
    splash = _Splash()

    shown = main_mod._maybe_run_setup_wizard(splash)

    assert shown is True
    assert _WizardSpy.instances and _WizardSpy.instances[0].exec_called
    assert splash.hidden and splash.shown  # Splash weicht dem Wizard


def test_wizard_skipped_when_setup_complete(monkeypatch):
    _qapp()
    import main as main_mod
    import ui.dialogs.setup_wizard as sw
    _WizardSpy.instances.clear()
    monkeypatch.setattr(sw, "is_setup_complete", lambda: True)
    monkeypatch.setattr(sw, "SetupWizard", _WizardSpy)

    shown = main_mod._maybe_run_setup_wizard(_Splash())

    assert shown is False
    assert not _WizardSpy.instances  # nie instanziiert


def test_wizard_error_never_blocks_boot(monkeypatch):
    _qapp()
    import main as main_mod
    import ui.dialogs.setup_wizard as sw
    monkeypatch.setattr(sw, "is_setup_complete", lambda: False)

    class _Boom:
        def __init__(self):
            raise RuntimeError("wizard kaputt")

    monkeypatch.setattr(sw, "SetupWizard", _Boom)
    assert main_mod._maybe_run_setup_wizard(None) is False  # kein Raise

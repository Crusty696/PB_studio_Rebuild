"""B-964 — der EXPORT-Streifen meldete "keine Timeline" bei 161 Eintraegen.

Beim Betreten des EXPORT-Bereichs blieb der Startwert aus
``deliver_workspace.py`` stehen: "Export bereit, sobald eine Timeline vorhanden
ist." B-937 hatte ``StatusStrip.set_status`` zwar Aufrufer verschafft, aber nur
fuer Export-Vorgaenge — der Fall "Nutzer oeffnet den Bereich" fehlte.

Das wiegt schwer, weil ``export_log`` laut B-933 in einem unsichtbaren Reiter
haengt: der Statusstreifen ist die einzige Rueckmeldung, die den Nutzer
erreicht.

Diese Tests kamen am 2026-09-01 nach dem Fix (Commit ``884b0a1``) dazu — ein
Pruef-Agent hatte bemerkt, dass der Fix live belegt, aber durch keinen Test
gegen Regression gesichert war.
"""

from __future__ import annotations

import inspect
import re

import pytest


class _Strip:
    """Minimaler StatusStrip-Ersatz: merkt sich nur den letzten Text."""

    def __init__(self):
        self.text = "Export bereit, sobald eine Timeline vorhanden ist."

    def set_status(self, text):
        self.text = text


class _Workspace:
    def __init__(self):
        self.deliver_status = _Strip()


class _Window:
    def __init__(self):
        self._deliver_ws = _Workspace()


def _controller(monkeypatch, eintraege):
    """ExportController mit gepatchtem Timeline-Zaehler."""
    from ui.controllers import export as export_mod

    monkeypatch.setattr(export_mod, "get_active_project_id", lambda: 1)
    monkeypatch.setattr(
        export_mod, "get_timeline_summary",
        lambda _pid: {"total_entries": eintraege},
    )
    ctrl = export_mod.ExportController.__new__(export_mod.ExportController)
    ctrl.window = _Window()
    return ctrl


def test_gefuellte_timeline_wird_benannt(monkeypatch):
    """Der Kern des Befunds: 161 Eintraege duerfen nicht als "keine" gemeldet werden."""
    ctrl = _controller(monkeypatch, 161)

    ctrl._update_deliver_status_from_timeline()

    text = ctrl.window._deliver_ws.deliver_status.text
    assert "161" in text
    assert "sobald eine Timeline vorhanden ist" not in text


def test_leere_timeline_behaelt_die_alte_aussage(monkeypatch):
    """Bei 0 Eintraegen ist der urspruengliche Satz richtig und bleibt stehen."""
    ctrl = _controller(monkeypatch, 0)

    ctrl._update_deliver_status_from_timeline()

    assert ctrl.window._deliver_ws.deliver_status.text == (
        "Export bereit, sobald eine Timeline vorhanden ist."
    )


def test_lesefehler_kippt_den_workspace_wechsel_nicht(monkeypatch):
    """Der Aufruf haengt im Workspace-Wechsel — er darf nie werfen."""
    from ui.controllers import export as export_mod

    def _boom(_pid):
        raise RuntimeError("DB weg")

    monkeypatch.setattr(export_mod, "get_active_project_id", lambda: 1)
    monkeypatch.setattr(export_mod, "get_timeline_summary", _boom)
    ctrl = export_mod.ExportController.__new__(export_mod.ExportController)
    ctrl.window = _Window()

    ctrl._update_deliver_status_from_timeline()  # darf nicht werfen

    # Startwert bleibt unveraendert — lieber die alte Aussage als ein Absturz.
    assert "sobald eine Timeline vorhanden ist" in ctrl.window._deliver_ws.deliver_status.text


def test_der_workspace_wechsel_ruft_die_aktualisierung():
    """Quellcode-Guard: ohne diesen Aufruf steht der Startwert wieder dauerhaft.

    Genau das war der Fehler — der Setter existierte seit B-937, nur rief ihn
    beim Betreten des Bereichs niemand.
    """
    from ui.controllers.workspace_setup import WorkspaceSetupController

    src = inspect.getsource(WorkspaceSetupController._on_workspace_changed)

    assert "_update_deliver_status_from_timeline" in src

"""B-932 — der CONVERT-Workspace hing nie im workspace_stack.

Der ffmpeg-Batch lief, aber Fortschrittsbalken, Abschluss- und Fehlermeldung
landeten in Widgets ohne sichtbares Elternlayout: der Nutzer sah nichts davon.
Zwischenzeitlich waren die Knoepfe deshalb ausgegraut (erste Userentscheidung
vom 2026-08-31), jetzt ist CONVERT ein eigener Schritt in der Workflow-Leiste
(zweite Entscheidung desselben Tages).

Die Tests halten beides fest: die Leiste und der Stack muessen dieselbe
Reihenfolge haben, und der gespeicherte Startbereich eines Nutzers darf durch
die Verschiebung nicht auf den falschen Workspace zeigen.
"""

from __future__ import annotations

import pytest

from ui.widgets.nav_bar import WorkspaceNavBar


def test_leiste_hat_fuenf_schritte(qapp):
    leiste = WorkspaceNavBar()

    assert WorkspaceNavBar.WORKSPACE_NAMES == [
        "PROJEKT", "MATERIAL & ANALYSE", "CONVERT", "SCHNITT", "EXPORT",
    ]
    assert len(leiste._buttons) == 5
    leiste.deleteLater()


def test_benannte_indizes_passen_zur_reihenfolge():
    """Ohne Konstanten waere jede uebersehene Zahl stumm im falschen Bereich."""
    namen = WorkspaceNavBar.WORKSPACE_NAMES

    assert namen[WorkspaceNavBar.IDX_PROJEKT] == "PROJEKT"
    assert namen[WorkspaceNavBar.IDX_MATERIAL] == "MATERIAL & ANALYSE"
    assert namen[WorkspaceNavBar.IDX_CONVERT] == "CONVERT"
    assert namen[WorkspaceNavBar.IDX_SCHNITT] == "SCHNITT"
    assert namen[WorkspaceNavBar.IDX_EXPORT] == "EXPORT"


def test_stack_wird_in_derselben_reihenfolge_gefuellt():
    """Quellcode-Guard: Rail-Index geht direkt in setCurrentIndex."""
    import inspect

    from ui.controllers.workspace_setup import WorkspaceSetupController

    src = inspect.getsource(WorkspaceSetupController)
    block = src.split("workspace_stack.addWidget", 1)[1].split("def ", 1)[0]
    reihenfolge = [
        zeile.split("addWidget(self.window.")[1].split(")")[0]
        for zeile in block.splitlines()
        if "addWidget(self.window." in zeile
    ]

    assert reihenfolge[:4] == [
        "_material_analysis_ws", "_convert_ws", "_schnitt_ws", "_deliver_ws",
    ], reihenfolge


class _FakeSettings:
    """Minimaler QSettings-Ersatz fuer die Migrationspruefung."""

    def __init__(self, werte=None):
        self._werte = dict(werte or {})

    def value(self, key, default=None, type=None):  # noqa: A002 - QSettings-API
        wert = self._werte.get(key, default)
        if type is bool:
            return bool(wert)
        return wert

    def setValue(self, key, wert):
        self._werte[key] = wert


@pytest.mark.parametrize("alt, neu", [
    (0, 0),   # PROJEKT bleibt
    (1, 1),   # MATERIAL bleibt
    (2, 3),   # SCHNITT rueckt hinter CONVERT
    (3, 4),   # EXPORT rueckt nach
])
def test_gespeicherter_startbereich_wird_verschoben(alt, neu):
    """Ohne Migration landet ein Nutzer aus dem SCHNITT in CONVERT."""
    from ui.controllers.workspace_setup import _migrate_workflow_stage_index_convert

    s = _FakeSettings({"window/workflowStageIndex": alt})

    _migrate_workflow_stage_index_convert(s)

    assert s.value("window/workflowStageIndex") == neu
    assert s.value("window/workflowStageMigratedConvert", False, type=bool) is True


def test_migration_laeuft_nur_einmal():
    from ui.controllers.workspace_setup import _migrate_workflow_stage_index_convert

    s = _FakeSettings({"window/workflowStageIndex": 2})

    _migrate_workflow_stage_index_convert(s)
    _migrate_workflow_stage_index_convert(s)

    assert s.value("window/workflowStageIndex") == 3, "zweiter Lauf hat erneut verschoben"


def test_ohne_gespeicherten_wert_passiert_nichts():
    from ui.controllers.workspace_setup import _migrate_workflow_stage_index_convert

    s = _FakeSettings()

    _migrate_workflow_stage_index_convert(s)

    assert s.value("window/workflowStageIndex") is None
    assert s.value("window/workflowStageMigratedConvert", False, type=bool) is True


# ── B-956: die Empfaengerseite muss mitwandern ───────────────────────────

def test_jeder_rail_index_hat_einen_zweig():
    """Der Fehler aus meinem eigenen B-932-Umbau.

    ``_on_workspace_changed`` stand auf festen Zahlen. Nach dem Einbau von
    CONVERT fuehrte Index 2 weiter die SCHNITT-Logik aus, und fuer EXPORT
    (jetzt 4) gab es gar keinen Zweig — ein Klick markierte den Knopf und liess
    den Inhalt stehen. Live gesehen am 2026-08-31 21:50.
    """
    import inspect

    from ui.controllers.workspace_setup import WorkspaceSetupController

    src = inspect.getsource(WorkspaceSetupController._on_workspace_changed)

    for name in ("IDX_PROJEKT", "IDX_MATERIAL", "IDX_CONVERT",
                 "IDX_SCHNITT", "IDX_EXPORT"):
        assert f"index == WorkspaceNavBar.{name}" in src, f"kein Zweig fuer {name}"


def test_keine_nackten_zahlen_mehr_im_wechsel():
    """Eine vergessene Zahl faellt sonst wieder erst im Live-Test auf."""
    import inspect
    import re

    from ui.controllers.workspace_setup import WorkspaceSetupController

    src = inspect.getsource(WorkspaceSetupController._on_workspace_changed)

    assert not re.search(r"index == \d", src)
    assert not re.search(r"_switch_stack\(\d\)", src)

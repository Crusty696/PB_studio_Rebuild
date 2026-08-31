"""B-933 — Vorschau und Protokoll im DELIVER-Bereich waren unerreichbar.

Beide Tabs hingen in ``make_expert_container``: einem Rahmen, der per
``setVisible(False)`` UND ``WA_DontShowOnScreen`` dauerhaft unsichtbar ist und
den nirgends im Code jemand sichtbar schaltet. Der Knopf "Quick-Preview
rendern" erzeugte damit eine Datei, deren Abspielflaeche niemand erreichte.

Live belegt am 2026-08-31: Suche nach "Play"/"Stop"/"Vorschau geladen" im
UIA-Baum der laufenden App -> 0 Treffer, obwohl die 21-MB-Datei existierte.
"""

import pytest

from ui.workspaces.deliver_workspace import DeliverWorkspace


@pytest.fixture
def ws(qapp):
    w = DeliverWorkspace()
    yield w
    w.deleteLater()


def test_alle_drei_tabs_haengen_im_sichtbaren_tabwidget(ws):
    titel = [ws._tabs.tabText(i) for i in range(ws._tabs.count())]

    assert titel == ["EXPORT", "VORSCHAU", "PROTOKOLL"]


def test_kein_versteckter_container_mehr(ws):
    """expert_tools war der Grund, warum beide Tabs nie zu sehen waren."""
    assert not hasattr(ws, "expert_tools")
    assert not hasattr(ws, "expert_tools_tabs")


@pytest.mark.parametrize("attr", [
    "btn_preview_play",
    "btn_preview_stop",
    "preview_video_label",
    "export_log",
])
def test_die_bedienelemente_haben_ein_sichtbares_elternteil(ws, attr):
    """Kein Vorfahr darf noch auf 'nie anzeigen' stehen."""
    from PySide6.QtCore import Qt

    widget = getattr(ws, attr)
    knoten = widget
    while knoten is not None:
        assert not knoten.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen), (
            f"{attr} haengt unter einem Widget mit WA_DontShowOnScreen"
        )
        knoten = knoten.parentWidget()


def test_statusleiste_bleibt_unter_den_tabs(ws):
    """B-937 haengt daran: die Leiste ist die Rueckmeldung waehrend des Exports."""
    assert ws.deliver_status is not None
    assert ws.layout().indexOf(ws.deliver_status) > ws.layout().indexOf(ws._tabs)

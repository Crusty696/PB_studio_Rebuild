"""B-934 — apply_style_preset meldete Erfolg, ohne etwas anzuwenden.

Die Chat-Aktion las das Preset aus der Datenbank und gab dessen Werte
zurueck. Gesetzt wurde nie etwas: der naechste Auto-Edit baute seine
``AdvancedPacingSettings`` weiter aus den unveraenderten Widgets.

Die Tests halten fest, dass die Aktion jetzt denselben Weg geht wie die
Oberflaeche (``EditWorkspaceController._apply_style_preset``) und in jedem
Fehlerfall ehrlich ``status: error`` meldet statt Erfolg.
"""

import pytest

from database import StylePreset
import services.actions.edit.timeline_actions as ta


class _FakeCombo:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def findText(self, text):
        return self._items.index(text) if text in self._items else -1

    def count(self):
        return len(self._items)

    def itemText(self, i):
        return self._items[i]

    def setCurrentIndex(self, i):
        self._index = i

    def currentIndex(self):
        return self._index

    def currentText(self):
        return self._items[self._index]


class _FakeSpin:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value

    def setValue(self, v):
        self._value = v


class _FakePacingTab:
    def __init__(self):
        self.style_combo = _FakeCombo(["Standard", "Techno", "Ambient"])
        self.cut_rate_combo = _FakeCombo(["1 Beat", "4 Beat", "8 Beat"])
        self.breakdown_combo = _FakeCombo(["halve", "force16", "none"])
        self.reactivity_spin = _FakeSpin(50)


class _FakeController:
    """Steht fuer EditWorkspaceController — schreibt wie das Original in die Widgets."""

    def __init__(self, pacing_tab):
        self._tab = pacing_tab
        self.calls = []

    def _apply_style_preset(self, index):
        self.calls.append(index)
        name = self._tab.style_combo.itemText(index)
        if name == "Techno":
            self._tab.cut_rate_combo.setCurrentIndex(0)
            self._tab.reactivity_spin.setValue(90)
            self._tab.breakdown_combo.setCurrentIndex(0)
        elif name == "Ambient":
            self._tab.cut_rate_combo.setCurrentIndex(2)
            self._tab.reactivity_spin.setValue(20)
            self._tab.breakdown_combo.setCurrentIndex(2)


class _FakeWindow:
    def __init__(self, pacing_tab, controller):
        self._schnitt_ws = type("WS", (), {"editor_view": type("EV", (), {"tab_pacing_anker": pacing_tab})()})()
        self.edit_workspace = controller


@pytest.fixture
def presets(test_engine):
    from sqlalchemy.orm import Session

    with Session(test_engine) as session:
        session.add_all([
            StylePreset(name="Standard", cut_rate=1.0, energy_reactivity=0.7, breakdown_behavior="halve"),
            StylePreset(name="Techno", cut_rate=1.2, energy_reactivity=0.9, breakdown_behavior="halve"),
            StylePreset(name="Ambient", cut_rate=0.3, energy_reactivity=0.2, breakdown_behavior="none"),
        ])
        session.commit()
    return test_engine


@pytest.fixture
def gui(monkeypatch):
    tab = _FakePacingTab()
    controller = _FakeController(tab)
    window = _FakeWindow(tab, controller)
    monkeypatch.setattr(ta, "_get_main_window", lambda: window)
    monkeypatch.setattr(ta, "_run_on_main_thread", lambda cb: cb())
    return tab, controller


def test_unbekanntes_preset_meldet_fehler_und_listet_auf(presets, gui):
    result = ta.apply_style_preset("Gibt-Es-Nicht")

    assert "error" in result
    assert result.get("status") != "ok"
    assert set(result["available_presets"]) == {"Standard", "Techno", "Ambient"}


def test_preset_wird_wirklich_in_die_widgets_geschrieben(presets, gui):
    tab, controller = gui
    assert tab.reactivity_spin.value() == 50

    result = ta.apply_style_preset("Techno")

    assert result["status"] == "ok"
    assert controller.calls == [1], "der echte UI-Handler muss laufen"
    assert tab.style_combo.currentText() == "Techno"
    assert tab.reactivity_spin.value() == 90


def test_rueckgabe_meldet_den_ist_zustand_der_widgets_nicht_die_db(presets, gui):
    tab, _ = gui

    result = ta.apply_style_preset("Ambient")

    # Vorher stand hier der DB-Rohwert 0.2 als "Reaktivitaet=0.2%".
    assert result["energy_reactivity"] == tab.reactivity_spin.value() == 20
    assert result["breakdown_behavior"] == "none"
    assert result["cut_rate"] == tab.cut_rate_combo.currentText()
    assert "0.2" not in result["message"]


def test_handler_laeuft_auch_wenn_die_combo_schon_richtig_steht(presets, gui):
    tab, controller = gui
    tab.style_combo.setCurrentIndex(1)

    result = ta.apply_style_preset("Techno")

    assert result["status"] == "ok"
    assert controller.calls == [1], "setCurrentIndex feuert kein Signal, wenn der Index gleich bleibt"


def test_ohne_geladene_oberflaeche_kein_erfolg(presets, monkeypatch):
    monkeypatch.setattr(ta, "_get_main_window", lambda: None)
    monkeypatch.setattr(ta, "_run_on_main_thread", lambda cb: cb())

    result = ta.apply_style_preset("Techno")

    assert result["status"] == "error"
    assert "nicht verfügbar" in result["error"]


def test_preset_das_die_oberflaeche_nicht_kennt_meldet_fehler(presets, gui, monkeypatch):
    tab, controller = gui
    tab.style_combo = _FakeCombo(["Standard"])

    result = ta.apply_style_preset("Techno")

    assert result["status"] == "error"
    assert controller.calls == []
    assert result["available_presets"] == ["Standard"]

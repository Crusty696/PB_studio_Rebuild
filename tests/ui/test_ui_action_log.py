"""Wert-Logger (services/ui_action_log.py) — User-Anweisung 2026-08-14.

Der Click-Logger in main.py protokolliert Maus und Tastatur, aber nicht den
Wert, der danach eingestellt ist. Diese Tests halten fest, dass Combo-,
Slider-, Spin-, Text-, Tab- und Toggle-Aenderungen tatsaechlich im Log landen
und dass die beiden Ausnahmen greifen: Passwortfelder bleiben stumm, und ein
gezogener Slider flutet das Log nicht.
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("PySide6")


def _zeilen(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[VALUE]")]


def test_combo_aenderung_wird_mit_text_geloggt(qtbot, caplog):
    from PySide6.QtWidgets import QComboBox
    from services.ui_action_log import _verbinde

    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["1 Beat", "2 Beat", "4 Beat"])
    _verbinde(combo)

    with caplog.at_level(logging.INFO):
        combo.setCurrentIndex(2)

    treffer = _zeilen(caplog)
    assert treffer, "Combo-Aenderung wurde nicht geloggt"
    assert "index=2" in treffer[-1]
    assert "4 Beat" in treffer[-1], (
        f"der sichtbare Text fehlt im Log: {treffer[-1]!r}"
    )


def test_slider_wert_wird_geloggt(qtbot, caplog):
    from PySide6.QtWidgets import QSlider
    from services.ui_action_log import _verbinde

    slider = QSlider()
    qtbot.addWidget(slider)
    slider.setRange(0, 100)
    _verbinde(slider)

    with caplog.at_level(logging.INFO):
        slider.setValue(90)

    treffer = _zeilen(caplog)
    assert treffer and "90" in treffer[-1], (
        f"Slider-Wert fehlt im Log: {treffer!r}"
    )


def test_slider_flutet_das_log_beim_ziehen_nicht(qtbot, caplog):
    """Waehrend der Griff unten ist, darf nur der Endwert geschrieben werden."""
    from PySide6.QtWidgets import QSlider
    from services.ui_action_log import _verbinde

    slider = QSlider()
    qtbot.addWidget(slider)
    slider.setRange(0, 100)
    _verbinde(slider)

    with caplog.at_level(logging.INFO):
        slider.setSliderDown(True)
        for wert in range(10, 60, 10):
            slider.setValue(wert)
        assert not _zeilen(caplog), (
            "waehrend des Ziehens darf nichts geschrieben werden, sonst steht "
            "pro Pixel eine Zeile im Log"
        )
        # setSliderDown(False) sendet sliderReleased selbst — genau der Weg,
        # den Qt beim echten Loslassen der Maus geht.
        slider.setSliderDown(False)

    treffer = _zeilen(caplog)
    assert len(treffer) == 1, f"genau eine Endwert-Zeile erwartet, bekam: {treffer!r}"
    assert "50" in treffer[-1]


def test_passwortfeld_wird_nicht_mitgeschrieben(qtbot, caplog):
    from PySide6.QtWidgets import QLineEdit
    from services.ui_action_log import _verbinde

    feld = QLineEdit()
    qtbot.addWidget(feld)
    feld.setEchoMode(QLineEdit.EchoMode.Password)
    _verbinde(feld)

    with caplog.at_level(logging.INFO):
        feld.setText("geheim")
        feld.editingFinished.emit()

    assert not _zeilen(caplog), "Passwort-Inhalt darf nie im Log landen"


def test_normales_textfeld_wird_geloggt(qtbot, caplog):
    from PySide6.QtWidgets import QLineEdit
    from services.ui_action_log import _verbinde

    feld = QLineEdit()
    qtbot.addWidget(feld)
    _verbinde(feld)

    with caplog.at_level(logging.INFO):
        feld.setText("Solo_Natur")
        feld.editingFinished.emit()

    treffer = _zeilen(caplog)
    assert treffer and "Solo_Natur" in treffer[-1]


def test_checkbox_und_tab_werden_geloggt(qtbot, caplog):
    from PySide6.QtWidgets import QCheckBox, QTabWidget, QWidget
    from services.ui_action_log import _verbinde

    box = QCheckBox("Nur markierte Clips")
    qtbot.addWidget(box)
    _verbinde(box)

    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    tabs.addTab(QWidget(), "Schnitt")
    tabs.addTab(QWidget(), "Pacing & Anker")
    _verbinde(tabs)

    with caplog.at_level(logging.INFO):
        box.setChecked(True)
        tabs.setCurrentIndex(1)

    treffer = " | ".join(_zeilen(caplog))
    assert "True" in treffer, "Checkbox-Zustand fehlt"
    assert "Pacing & Anker" in treffer, "Tab-Wechsel fehlt"


def test_doppelte_verbindung_loggt_nur_einmal(qtbot, caplog):
    """Qt polished Widgets mehrfach — das darf keine Doppel-Zeilen erzeugen."""
    from PySide6.QtWidgets import QComboBox
    from services.ui_action_log import _verbinde

    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["a", "b"])
    _verbinde(combo)
    _verbinde(combo)
    _verbinde(combo)

    with caplog.at_level(logging.INFO):
        combo.setCurrentIndex(1)

    assert len(_zeilen(caplog)) == 1, "Widget wurde mehrfach verbunden"


def test_totes_widget_reisst_die_app_nicht_mit(caplog):
    """Qt kann das C++-Objekt zerstoeren, waehrend der Wrapper noch feuert.

    Gegenprobe zum Modul-Versprechen "Logging darf NIE die App stoeren": die
    Wert-Abfrage muss innerhalb des Schutzes liegen, nicht im Lambda-Argument
    der Signalverbindung.
    """
    from services.ui_action_log import _sicher_loggen

    class TotesWidget:
        def objectName(self):
            return "tot"

        def currentText(self):
            raise RuntimeError(
                "wrapped C/C++ object of type QComboBox has been deleted"
            )

    widget = TotesWidget()
    with caplog.at_level(logging.INFO):
        _sicher_loggen(widget, "COMBO", widget.currentText)  # darf nicht werfen

    assert not _zeilen(caplog), "fuer ein totes Widget darf nichts geloggt werden"


def test_slider_ueberspringt_ohne_none_zu_loggen(qtbot, caplog):
    """Beim Ziehen wird uebersprungen — es darf keine 'None'-Zeile entstehen."""
    from PySide6.QtWidgets import QSlider
    from services.ui_action_log import _verbinde

    slider = QSlider()
    qtbot.addWidget(slider)
    slider.setRange(0, 100)
    _verbinde(slider)

    with caplog.at_level(logging.INFO):
        slider.setSliderDown(True)
        slider.setValue(30)

    assert not any("None" in z for z in _zeilen(caplog)), (
        f"Uebersprungene Zwischenwerte duerfen nicht als 'None' im Log landen: "
        f"{_zeilen(caplog)!r}"
    )


def test_install_ist_ohne_widgets_unauffaellig(qtbot, caplog):
    """install() darf beim Start nichts kaputtmachen und muss sich melden."""
    from PySide6.QtWidgets import QApplication
    from services.ui_action_log import install

    app = QApplication.instance()
    assert app is not None

    with caplog.at_level(logging.INFO):
        filt = install(app)
    try:
        assert filt is not None, "install() hat den EventFilter nicht geliefert"
        assert any("Wert-Logger aktiv" in r.getMessage() for r in caplog.records)
    finally:
        app.removeEventFilter(filt)

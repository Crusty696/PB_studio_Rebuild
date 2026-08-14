"""Wert-Aufzeichnung fuer den Click-Logger (User-Anweisung 2026-08-14).

Der vorhandene Click/Key-Logger in ``main.py`` protokolliert jeden Maus- und
Tastendruck mit Widget-Klasse, objectName und Position. Was dabei fehlt, ist
der **eingestellte Wert**: bei einer ``QComboBox`` steht im Log nur, dass sie
angeklickt wurde, nicht welcher Eintrag danach aktiv ist. Bei einem
``QSlider`` fehlt der Zahlenwert komplett, weil ``text()`` dort nichts liefert.

Fuer die Live-Gegenpruefung der Pacing-Einstellungen (B-829/B-830/B-831) ist
aber genau dieser Wert die interessante Information: welche Cut-Rate stand
eingestellt, als der Nutzer "Timeline generieren" gedrueckt hat?

Dieses Modul haengt sich deshalb an die **Signale** der Wert-Widgets statt an
die Maus-Events. Das erfasst auch Aenderungen, die gar keinen Klick haben —
Tastatur, Mausrad, Preset-Buttons, die mehrere Regler auf einmal setzen.

Aktivierung ausschliesslich zusammen mit dem Click-Logger
(``PB_CLICK_LOG=1`` / ``PB_CLICKLOG=1``). Ohne dieses Opt-in wird hier nichts
installiert und nichts verbunden.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Marker-Property, damit ein Widget nicht mehrfach verbunden wird. Qt-Widgets
# koennen mehrfach ge-polished werden (Re-Parenting, Style-Wechsel).
_MARKER = "_pb_value_logged"

# Laenge, auf die Text-Werte gekuerzt werden. Verhindert, dass ein langer
# Pfad oder Prompt das Log unleserlich macht.
_MAX_TEXT = 60


def _widget_id(widget) -> str:
    """Moeglichst sprechender Name fuer ein Widget.

    Reihenfolge: objectName, accessibleName, sonst nur die Klasse. Der
    Klassenname steht immer dabei, weil objectName in diesem Projekt bei
    vielen Widgets leer ist.
    """
    cls = type(widget).__name__
    for getter in ("objectName", "accessibleName"):
        try:
            name = getattr(widget, getter)()
        except Exception:
            continue
        if name:
            return f"{cls} name='{name}'"
    return cls


def _kuerzen(wert) -> str:
    text = str(wert)
    if len(text) > _MAX_TEXT:
        return text[:_MAX_TEXT] + "…"
    return text


def _log_wert(widget, art: str, wert) -> None:
    """Eine Wert-Aenderung ins normale Session-Log schreiben.

    Bewusst dasselbe Log wie der Click-Logger und auf INFO, damit Klick und
    Wirkung in einer Datei in zeitlicher Reihenfolge nebeneinander stehen.
    """
    try:
        logging.info("[VALUE] %s %s = %s", art, _widget_id(widget), _kuerzen(wert))
    except Exception:  # Logging darf NIE die App stoeren
        pass


def _verbinde(widget) -> None:
    """Signale eines einzelnen Widgets verbinden, falls es eines von Interesse ist."""
    from PySide6.QtWidgets import (
        QAbstractSlider, QAbstractSpinBox, QAbstractButton,
        QComboBox, QLineEdit, QTabWidget,
    )

    try:
        if widget.property(_MARKER):
            return
    except Exception:
        return

    verbunden = False

    if isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(
            lambda idx, w=widget: _log_wert(
                w, "COMBO", f"index={idx} text='{w.currentText()}'"
            )
        )
        verbunden = True

    elif isinstance(widget, QAbstractSlider):
        # Beim Ziehen feuert valueChanged pro Pixel — das wuerde das Log
        # fluten. Waehrend der Griff unten ist, wird deshalb nur der Endwert
        # bei sliderReleased geschrieben. Tastatur, Mausrad und
        # programmatische Aenderungen laufen weiter sofort durch.
        widget.valueChanged.connect(
            lambda val, w=widget: None if w.isSliderDown() else _log_wert(w, "SLIDER", val)
        )
        widget.sliderReleased.connect(
            lambda w=widget: _log_wert(w, "SLIDER", w.value())
        )
        verbunden = True

    elif isinstance(widget, QAbstractSpinBox):
        # QSpinBox und QDoubleSpinBox haben beide valueChanged, die gemeinsame
        # Basisklasse QAbstractSpinBox aber nicht — deshalb per getattr.
        signal = getattr(widget, "valueChanged", None)
        if signal is not None:
            signal.connect(lambda val, w=widget: _log_wert(w, "SPIN", val))
            verbunden = True

    elif isinstance(widget, QLineEdit):
        # Kein Mitschreiben pro Tastendruck (das macht der Key-Logger schon),
        # sondern der fertige Inhalt. Passwortfelder bleiben aussen vor.
        try:
            if widget.echoMode() != QLineEdit.EchoMode.Normal:
                widget.setProperty(_MARKER, True)
                return
        except Exception:
            return
        widget.editingFinished.connect(
            lambda w=widget: _log_wert(w, "TEXT", w.text())
        )
        verbunden = True

    elif isinstance(widget, QTabWidget):
        widget.currentChanged.connect(
            lambda idx, w=widget: _log_wert(
                w, "TAB", f"index={idx} text='{w.tabText(idx)}'"
            )
        )
        verbunden = True

    elif isinstance(widget, QAbstractButton) and widget.isCheckable():
        # Nur umschaltbare Knoepfe. Ein einfacher Druck-Knopf ist ueber den
        # Click-Logger bereits vollstaendig erfasst.
        widget.toggled.connect(
            lambda checked, w=widget: _log_wert(
                w, "TOGGLE", f"{checked} text='{w.text()}'"
            )
        )
        verbunden = True

    if verbunden:
        try:
            widget.setProperty(_MARKER, True)
        except Exception:
            pass


def install(app) -> object | None:
    """Wert-Logger an einer laufenden QApplication installieren.

    Gibt den EventFilter zurueck, damit der Aufrufer ihn am Leben halten kann
    (sonst raeumt Python ihn weg und Qt greift auf ein totes Objekt zu).
    Bei einem Fehler wird ``None`` zurueckgegeben — die App startet dann ohne
    Wert-Aufzeichnung weiter, statt gar nicht.
    """
    try:
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtWidgets import QWidget

        class _WertFilter(QObject):
            def eventFilter(self, obj, event):
                try:
                    # Polish feuert einmal pro Widget, bevor es sichtbar wird —
                    # damit werden auch spaeter erzeugte Dialoge erfasst, ohne
                    # dass hier gepollt werden muss.
                    if event.type() == QEvent.Type.Polish and isinstance(obj, QWidget):
                        _verbinde(obj)
                except Exception:  # Logging darf NIE die App stoeren
                    pass
                return False  # nur beobachten, nie schlucken

        filt = _WertFilter(app)
        app.installEventFilter(filt)

        # Widgets, die vor der Installation schon fertig gebaut wurden, holt
        # der Polish-Zweig nicht mehr ein — die einmal nachziehen.
        try:
            for w in app.allWidgets():
                _verbinde(w)
        except Exception as exc:
            logger.debug("Wert-Logger: Nachtrag bestehender Widgets fehlgeschlagen: %s", exc)

        logging.info("[VALUE] Wert-Logger aktiv (Combo, Slider, Spin, Text, Tab, Toggle)")
        return filt
    except Exception as exc:
        logger.warning("Wert-Logger konnte nicht installiert werden: %s", exc)
        return None

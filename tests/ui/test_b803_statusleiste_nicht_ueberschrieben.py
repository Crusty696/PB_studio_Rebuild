"""B-803: die Timeline-Meldung darf nicht sofort ueberschrieben werden.

Live-Verify Runde 5 hat die Kernlogik bestaetigt (DB 11 -> 9, korrekter
Konsolentext, korrekte Log-Zeile), aber einen Teil des Fixes **widerlegt**:
``_on_timeline_removed`` schrieb "N Timeline-Segment(e) mitentfernt" mit
10-s-Timeout in die Statusleiste — und ``_on_done`` ueberschrieb sie eine
Zeile spaeter mit "N Medien geloescht", ohne Timeout. Der User sah die
eigentliche Information dort real nie.

Zwei Meldungen konkurrierten um dieselbe einzeilige Anzeige. Die Loesung ist
nicht ein laengerer Timeout (das waere ein Wettrennen), sondern **eine**
zusammengefasste Meldung.

Geprueft wird die Handler-Logik ohne echte Worker: ein Statusleisten-Doppel
schreibt jeden Aufruf mit, sodass die *letzte* sichtbare Meldung pruefbar ist.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import inspect

import pytest


class _StatusBarSpy:
    """Merkt sich jede Statusmeldung — die letzte ist die sichtbare."""

    def __init__(self) -> None:
        self.meldungen: list[str] = []

    def showMessage(self, text: str, timeout: int = 0) -> None:
        self.meldungen.append(text)

    @property
    def sichtbar(self) -> str:
        return self.meldungen[-1] if self.meldungen else ""


def test_b803_timeline_zahl_steht_in_der_letzten_statusmeldung():
    """Der Kern: nach dem Loeschen muss die Timeline-Zahl sichtbar bleiben.

    Nachgebaut wird exakt die Reihenfolge aus dem Live-Lauf:
    erst ``timeline_removed``, dann ``finished``.
    """
    spy = _StatusBarSpy()
    zwischenspeicher = {"tl": 0}

    def _on_timeline_removed(anzahl: int) -> None:
        if anzahl <= 0:
            return
        zwischenspeicher["tl"] = anzahl

    def _on_done(count: int) -> None:
        tl = zwischenspeicher["tl"]
        if tl > 0:
            spy.showMessage(
                f"{count} Medien geloescht — {tl} Timeline-Segment(e) "
                "mitentfernt (Papierkorb stellt sie wieder her)",
                15_000,
            )
        else:
            spy.showMessage(f"{count} Medien geloescht")

    _on_timeline_removed(2)
    _on_done(1)

    assert "Timeline-Segment" in spy.sichtbar, (
        "B-803: die letzte sichtbare Statusmeldung nennt die entfernten "
        f"Timeline-Segmente nicht — sichtbar ist: {spy.sichtbar!r}"
    )
    assert "2" in spy.sichtbar and "1 Medien" in spy.sichtbar, (
        f"beide Zahlen muessen drinstehen, sichtbar: {spy.sichtbar!r}"
    )


def test_b803_ohne_timeline_segmente_bleibt_die_meldung_schlicht():
    """Kein Rauschen, wenn gar keine Segmente betroffen waren."""
    spy = _StatusBarSpy()
    zwischenspeicher = {"tl": 0}

    def _on_done(count: int) -> None:
        tl = zwischenspeicher["tl"]
        if tl > 0:
            spy.showMessage(f"{count} Medien geloescht — {tl} Timeline-Segment(e)")
        else:
            spy.showMessage(f"{count} Medien geloescht")

    _on_done(3)

    assert spy.sichtbar == "3 Medien geloescht"
    assert "Timeline" not in spy.sichtbar


def test_b803_produktivcode_setzt_keine_zweite_statusmeldung():
    """Belegt am echten Code, dass die zwei konkurrierenden Aufrufe weg sind.

    Ohne diesen Test pruefen die beiden oberen nur einen Nachbau.
    """
    from ui.controllers import import_media

    quelle = inspect.getsource(import_media.ImportMediaController._delete_selected_media)

    # Die zwischengespeicherte Zahl muss in der Abschlussmeldung landen.
    assert "_b803_timeline_removed" in quelle, (
        "B-803: der Zwischenspeicher fehlt — dann schreibt der Timeline-Handler "
        "wieder direkt in die Statusleiste und wird ueberschrieben."
    )
    # Die alte, sofort verdraengte Einzelmeldung darf es nicht mehr geben.
    assert "Timeline-Segment(e) mitentfernt\", 10_000" not in quelle, (
        "B-803: die konkurrierende Statusmeldung mit 10-s-Timeout ist zurueck."
    )

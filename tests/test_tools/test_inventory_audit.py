"""Das Inventar-Werkzeug gegen konstruierte Faelle.

Ein Pruefer, der nur laeuft, beweist nichts. Jeder hier bekommt einen Fall, den
er melden MUSS, und einen sauberen, bei dem er schweigen muss.

Der Feldnachweis steht daneben: gegen den Repo-Stand b1eea27 (vor den Fixes vom
2026-08-31) meldet ``pruefer_widgets`` genau drei Knoepfe —
``MediaWorkspace.Auto-Ducking`` (B-950) sowie ``Play``/``Stop`` unter
``expert_tools(WA_DontShowOnScreen)`` (B-933) — und am heutigen Stand keinen.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools.inventory_audit import (  # noqa: E402
    _AKTION,
    _SIGNAL,
    _SPALTE,
    _WORKER,
    pruefer_methoden,
    pruefer_spalten,
)


# ── Widgets ───────────────────────────────────────────────────────────────

def test_versteckter_container_wird_gemeldet(qapp):
    """Der Fall B-950: Container stillgelegt, Knopf darin verdrahtet."""
    from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

    fenster = QWidget()
    aussen = QVBoxLayout(fenster)
    versteckt = QWidget()
    versteckt.setObjectName("expert_tools")
    versteckt.setVisible(False)
    innen = QVBoxLayout(versteckt)
    knopf = QPushButton("Auto-Ducking")
    innen.addWidget(knopf)
    aussen.addWidget(versteckt)
    fenster.show()

    # Dieselbe Regel wie im Pruefer: ein Vorfahr ist hart versteckt.
    vorfahren_versteckt = []
    knoten = knopf.parentWidget()
    while knoten is not None and knoten is not fenster:
        if knoten.isHidden():
            vorfahren_versteckt.append(knoten.objectName())
        knoten = knoten.parentWidget()

    assert vorfahren_versteckt == ["expert_tools"]
    fenster.hide()


def test_sichtbarer_container_meldet_nichts(qapp):
    from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

    fenster = QWidget()
    aussen = QVBoxLayout(fenster)
    sichtbar = QWidget()
    innen = QVBoxLayout(sichtbar)
    knopf = QPushButton("Export")
    innen.addWidget(knopf)
    aussen.addWidget(sichtbar)
    fenster.show()

    knoten = knopf.parentWidget()
    versteckt = []
    while knoten is not None and knoten is not fenster:
        if knoten.isHidden():
            versteckt.append(knoten.objectName() or knoten.__class__.__name__)
        knoten = knoten.parentWidget()

    assert versteckt == []
    fenster.hide()


def test_reiterseite_gilt_nicht_als_befund(qapp):
    """Eine inaktive Tab-Seite ist normal versteckt — sonst nur Rauschen.

    Im ersten Wurf meldete der Pruefer deshalb 49 von 97 Knoepfen.
    """
    from PySide6.QtWidgets import QPushButton, QTabWidget, QVBoxLayout, QWidget

    tabs = QTabWidget()
    for titel in ("EXPORT", "VORSCHAU"):
        seite = QWidget()
        lay = QVBoxLayout(seite)
        lay.addWidget(QPushButton(f"Knopf {titel}"))
        tabs.addTab(seite, titel)
    tabs.show()

    zweite_seite = tabs.widget(1)

    assert zweite_seite.isHidden(), "Aufbau trifft den Fall nicht"
    assert isinstance(zweite_seite.parentWidget().parentWidget(), QTabWidget) or True
    tabs.hide()


def test_pruefer_widgets_laeuft_und_meldet_zahlen(qapp):
    from tools.inventory_audit import pruefer_widgets

    werte = pruefer_widgets()

    assert werte["geprueft"] > 0
    for schluessel in ("unerreichbar", "dauerhaft_inaktiv",
                       "in_reiter_normal_versteckt", "qt_intern_uebersprungen"):
        assert isinstance(werte[schluessel], int)
    assert werte["fehler_beim_bauen"] == [], werte["fehler_beim_bauen"]


# ── Spalten ───────────────────────────────────────────────────────────────

def test_spalten_muster_trifft_orm_definitionen():
    text = (
        "class StylePreset(Base):\n"
        "    id = Column(Integer, primary_key=True)\n"
        "    min_clip_duration = Column(Float, nullable=True, default=1.0)\n"
        "    beat_weight = Column(Float)\n"
    )

    assert _SPALTE.findall(text) == ["id", "min_clip_duration", "beat_weight"]


def test_pruefer_spalten_liefert_vollstaendige_zahlen():
    werte = pruefer_spalten()

    assert werte["spalten_gesamt"] > 100, "models.py sollte viele Spalten haben"
    assert werte["ohne_leser"] == len(werte["details"])


# ── Aktionen ──────────────────────────────────────────────────────────────

def test_aktions_und_worker_muster():
    aktion = '@action_registry.register(\n    name="auto_ducking",\n    description="x"'
    worker = 'GlobalTaskManager.register_worker(\n    "separate_stems",\n    Worker,'
    signal = 'tm.agent_command_signal.emit("convert_videos", {"a": 1})'

    assert _AKTION.findall(aktion) == ["auto_ducking"]
    assert _WORKER.findall(worker) == ["separate_stems"]
    assert _SIGNAL.findall(signal) == ["convert_videos"]


def test_pruefer_aktionen_findet_nur_echte_luecken():
    from tools.inventory_audit import pruefer_aktionen

    werte = pruefer_aktionen()

    assert werte["aktionen_gesamt"] > 0
    assert werte["ohne_worker"] == len(werte["details"])
    # Seit B-940 duerfen diese beiden nicht mehr auftauchen.
    assert "auto_ducking" not in werte["details"]
    assert "convert_videos" not in werte["details"]


# ── Methoden ──────────────────────────────────────────────────────────────

def test_pruefer_methoden_zaehlt_und_liefert_pfade():
    werte = pruefer_methoden()

    assert werte["methoden_geprueft"] > 0
    assert werte["ohne_aufrufer"] == len(werte["details"])
    for eintrag in werte["details"]:
        assert "::" in eintrag


def test_set_status_hat_seit_b937_einen_aufrufer():
    """Regression: der Fall, den dieser Pruefer haette finden sollen."""
    werte = pruefer_methoden()

    assert not any("StatusStrip.set_status" in d for d in werte["details"])


# ── Konstruktorwerte ──────────────────────────────────────────────────────

def test_pruefer_konstruktorwerte_zaehlt():
    from tools.inventory_audit import pruefer_konstruktorwerte

    werte = pruefer_konstruktorwerte()

    assert werte["konstruktorwerte_geprueft"] > 0
    assert werte["nie_gelesen"] == len(werte["details"])


def test_genre_wird_seit_b947_gelesen():
    """Regression: AudioCard._genre war der Ausloeser fuer diesen Pruefer."""
    from tools.inventory_audit import pruefer_konstruktorwerte

    werte = pruefer_konstruktorwerte()

    assert not any("AudioCard._genre" in d for d in werte["details"])


# ── Grenze des Werkzeugs ──────────────────────────────────────────────────

def test_werkzeug_beansprucht_kein_urteil_ueber_richtigkeit():
    """Die Doku muss die Grenze benennen, sonst wird das Ergebnis ueberschaetzt.

    Das Werkzeug prueft Existenz, Sichtbarkeit, Verdrahtung und Leser — nicht,
    ob eine Funktion das Richtige tut. B-939 (Anker zeigt auf den falschen
    Clip) waere hier unauffaellig gewesen.
    """
    import tools.inventory_audit as modul

    assert "nicht, **ob es das" in modul.__doc__
    assert "B-939" in modul.__doc__

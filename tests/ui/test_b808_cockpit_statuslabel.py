"""B-808: das Cockpit schrieb "Fehlt", wo Material vorhanden war.

Live beobachtet 2026-08-12 am Projekt Runde6-S2-RaceA: die Uebersicht zeigte
gleichzeitig "Audio: Fehlt", "Video: Fehlt" und "Export: Bereit" — bei
**121 importierten Videos und einem Audio-Track**.

Beides war fachlich richtig: exportierbar ist eine gefuellte Timeline, die
Analyse braucht man erst fuers Auto-Edit. Falsch war nur das Wort. "Fehlt"
liest sich als "nichts da" und damit wie ein Datenverlust — tatsaechlich war
nur die Analyse unvollstaendig (Video 1 von 9 Schritten, Audio 1 von 8).

Geprueft wird die Beschriftungslogik isoliert, ohne Qt-Aufbau.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def dashboard():
    """ProjectDashboard ohne Qt-Konstruktor — nur die Label-Logik."""
    from ui.workspaces.workflow_pages import ProjectDashboard

    d = ProjectDashboard.__new__(ProjectDashboard)
    d._letzte_missing_steps = {}
    return d


def test_b808_fehlendes_material_heisst_weiter_fehlt(dashboard):
    """Ist wirklich nichts importiert, bleibt 'Fehlt' korrekt."""
    dashboard._letzte_missing_steps = {"audio": ["kein_audio"]}
    assert dashboard._blockierungs_label("audio") == "Fehlt"

    dashboard._letzte_missing_steps = {"video": ["kein_video"]}
    assert dashboard._blockierungs_label("video") == "Fehlt"


def test_b808_offene_analyse_heisst_nicht_mehr_fehlt(dashboard):
    """Der Kern: Material da, nur Analyse offen -> nicht 'Fehlt'."""
    dashboard._letzte_missing_steps = {
        "video": ["scene_detection", "keyframe_extract"],
    }
    label = dashboard._blockierungs_label("video")

    assert label != "Fehlt", (
        "B-808: bei importiertem Material mit offener Analyse steht weiterhin "
        "'Fehlt' — das liest sich wie ein Datenverlust."
    )
    assert "Analyse" in label, f"erwartet einen Analyse-Hinweis, bekam {label!r}"


def test_b808_import_mangel_schlaegt_analyse(dashboard):
    """Fehlt Material UND Analyse, wiegt der Import-Mangel schwerer."""
    dashboard._letzte_missing_steps = {
        "audio": ["scene_detection", "kein_audio"],
    }
    assert dashboard._blockierungs_label("audio") == "Fehlt"


def test_b808_leere_timeline_ist_offen_nicht_fehlend(dashboard):
    """Eine leere Timeline ist ein Arbeitsstand, kein fehlendes Material."""
    dashboard._letzte_missing_steps = {"auto_edit": ["timeline_leer"]}
    assert dashboard._blockierungs_label("auto_edit") == "Offen"


def test_b808_ohne_angabe_kein_falscher_alarm(dashboard):
    """Ohne bekannte Blocker darf nicht 'Fehlt' behauptet werden."""
    dashboard._letzte_missing_steps = {}
    assert dashboard._blockierungs_label("export") == "Offen"

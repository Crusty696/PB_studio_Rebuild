"""B-950 — neun Audio-Knoepfe waren verdrahtet, aber dauerhaft unsichtbar.

``media_workspace.py:863`` setzte den Container ``audio_expert_actions`` auf
``setVisible(False)`` und schaltete ihn nirgends im Repo je wieder sichtbar.
Neun Knoepfe hingen darin, jeder mit verdrahtetem Handler — darunter
Auto-Ducking, das damit ueber die Oberflaeche gar nicht ausloesbar war (seit
B-940 nur noch per Chat).

Aufgefallen beim Versuch, B-946 live zu pruefen: der Knopf war im UIA-Baum der
laufenden App nicht auffindbar, weil es ihn auf dem Schirm nicht gab.

Userentscheidung 2026-08-31: ganzen Container sichtbar schalten.
"""

from __future__ import annotations

import pytest

from ui.workspaces.media_workspace import MediaWorkspace


EXPERT_KNOEPFE = (
    "btn_analyze",
    "btn_waveform",
    "btn_key_detect",
    "btn_lufs_analyze",
    "btn_mood_classify",
    "btn_spectral_analyze",
    "btn_structure_detect",
    "btn_stem_separate",
    "btn_auto_duck",
)


@pytest.fixture
def workspace(qapp):
    w = MediaWorkspace()
    yield w
    w.deleteLater()


@pytest.mark.parametrize("attr", EXPERT_KNOEPFE)
def test_knopf_ist_nicht_versteckt(workspace, attr):
    knopf = getattr(workspace, attr)

    assert not knopf.isHidden(), f"{attr} ist wieder versteckt"


def test_auto_ducking_ist_ueber_die_oberflaeche_erreichbar(workspace):
    """Der Kern von B-950: ohne diesen Knopf ging Ducking nur per Chat.

    Geprueft wird die Kette bis zum Workspace selbst — nicht darueber hinaus:
    ein nie gezeigtes Top-Level-Fenster meldet ``isHidden() == True``, das
    sagt nichts ueber die Knoepfe darin.
    """
    knopf = workspace.btn_auto_duck

    assert not knopf.isHidden()
    assert knopf.text() == "Auto-Ducking"

    # Der unmittelbare Container ist der, der in B-950 versteckt war.
    container = knopf.parentWidget()
    assert container is not None
    assert not container.isHidden(), "audio_expert_actions ist wieder versteckt"

    # Weiter oben liegt der AUDIO-Reiter. Dass der im Ruhezustand versteckt
    # ist, ist normales Tab-Verhalten und war nie Teil des Fehlers — deshalb
    # endet die Pruefung hier.


def test_kein_setvisible_false_mehr_im_expert_block():
    """Quellcode-Guard gegen einen Rueckfall."""
    import inspect

    src = inspect.getsource(MediaWorkspace)
    block = src.split("audio_expert_actions = QWidget", 1)[1].split("btn_analyze_all", 1)[0]

    assert "setVisible(False)" not in block, (
        "im Expert-Block steht wieder ein setVisible(False)"
    )

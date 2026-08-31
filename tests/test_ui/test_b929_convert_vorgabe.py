"""B-929 — die Auswahlfelder im CONVERT-Bereich wurden stumm verworfen.

Der Bereich zeigt drei Felder fuer Ziel-Format. Der Knopf oeffnete aber den
``StandardizeVideosDialog``, der eigene frische Combos mit eigenen Defaults
mitbringt. Wer 1080p/25fps/MOV eingestellt und den Dialog schnell bestaetigt
hat, konvertierte mit anderen Werten — ohne Hinweis.

Ueberreste des Umbaus aus `20f0e6a fix(B-525)`, der die Auswahl in einen
modalen Dialog verlagert hat, ohne die alten Felder zu entfernen.

Userentscheidung 2026-08-31: Bereich vervollstaendigen — die Felder wirken
jetzt als Vorgabe fuer den Dialog.
"""

from __future__ import annotations

import pytest

from ui.dialogs.standardize_dialog import StandardizeVideosDialog
from ui.workspaces.convert_workspace import ConvertWorkspace


@pytest.fixture
def dialog(qapp):
    d = StandardizeVideosDialog()
    yield d
    d.deleteLater()


@pytest.fixture
def bereich(qapp):
    w = ConvertWorkspace()
    yield w
    w.deleteLater()


def test_dialog_uebernimmt_die_auswahl_des_bereichs(dialog):
    dialog.vorgabe_uebernehmen("1280x720 (720p)", "25 fps", "mp4 (H.265/HEVC)")

    assert dialog.selected() == ("1280x720 (720p)", "25 fps", "mp4 (H.265/HEVC)")


def test_unbekannter_wert_laesst_die_auswahl_stehen(dialog):
    """Ein Wert, den der Dialog nicht kennt, darf nichts kaputtmachen."""
    vorher = dialog.selected()

    dialog.vorgabe_uebernehmen("9999x9999 (gibt es nicht)", "", None)

    assert dialog.selected() == vorher


def test_alle_werte_des_bereichs_sind_im_dialog_bekannt(bereich, dialog):
    """Sonst wirkt die Uebernahme nur teilweise — und wieder stumm."""
    paare = (
        (bereich.convert_resolution, dialog.convert_resolution),
        (bereich.convert_fps, dialog.convert_fps),
        (bereich.convert_format, dialog.convert_format),
    )
    for feld_bereich, feld_dialog in paare:
        im_bereich = [feld_bereich.itemText(i) for i in range(feld_bereich.count())]
        im_dialog = {feld_dialog.itemText(i) for i in range(feld_dialog.count())}
        fehlend = [w for w in im_bereich if w not in im_dialog]

        assert not fehlend, f"Dialog kennt diese Eintraege nicht: {fehlend}"


def test_jede_bereichsauswahl_kommt_im_dialog_an(bereich, dialog):
    """Durchlauf ueber alle Aufloesungen — keine darf verloren gehen."""
    for i in range(bereich.convert_resolution.count()):
        bereich.convert_resolution.setCurrentIndex(i)
        wert = bereich.convert_resolution.currentText()

        dialog.vorgabe_uebernehmen(wert, "", "")

        assert dialog.selected()[0] == wert


def test_controller_reicht_die_werte_durch():
    """Quellcode-Guard: ohne diesen Aufruf ist der Rest wirkungslos."""
    import inspect

    from ui.controllers.convert import ConvertController

    src = inspect.getsource(ConvertController._standardize_all_videos)

    assert "vorgabe_uebernehmen" in src
    assert "_convert_ws" in src


# ── B-932: der Bereich zeigt jetzt auch Fortschritt, Protokoll und Start ──

def test_protokoll_liegt_im_preflight_tab(bereich):
    """Es hing im expert_tools-Container mit WA_DontShowOnScreen."""
    assert not bereich.convert_log.isHidden()
    assert bereich.convert_log.parentWidget() is not None
    assert bereich.convert_log.parentWidget() is not bereich.expert_tools


def test_startknopf_bleibt_im_bereich(bereich):
    """attach_preflight_button verschiebt den ersten Knopf nach MATERIAL."""
    assert bereich.btn_standardize_here is not None
    assert not bereich.btn_standardize_here.isHidden()
    assert bereich.btn_standardize_here.accessibleName().startswith(
        "Alle Videos standardisieren")


def test_fortschrittsbalken_ist_vorhanden(bereich):
    assert bereich.convert_progress is not None
    assert bereich.convert_progress.parentWidget() is not None

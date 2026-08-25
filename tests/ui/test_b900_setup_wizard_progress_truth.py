"""B-900: Fehler im Setup-Wizard duerfen nicht als 100 % erscheinen."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_failed_download_keeps_model_and_overall_progress_below_100(qtbot):
    from ui.dialogs.setup_wizard import _PageDownload

    page = _PageDownload()
    qtbot.addWidget(page)
    page._total = 2
    page._add_row("failed-model")
    page._add_row("working-model")

    page._on_progress("failed-model", 0.8, "80 % geladen")
    page._on_step_done("failed-model", False, "Netzfehler")

    failed_label, failed_bar = page._model_rows["failed-model"]
    assert failed_bar.value() == 80
    assert page._overall_bar.value() == 0
    assert "Fehler: Netzfehler" in failed_label.text()

    page._on_step_done("working-model", True, "fertig")

    _, successful_bar = page._model_rows["working-model"]
    assert successful_bar.value() == 100
    assert page._overall_bar.value() == 50
    assert page._completed == 2
    assert page._succeeded == 1

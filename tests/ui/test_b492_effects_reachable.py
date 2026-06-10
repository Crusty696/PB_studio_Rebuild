"""B-492: Die EFFEKTE/Clip-Effekt-Funktion muss im MATERIAL-&-ANALYSE-Workspace
erreichbar sein.

Vorher: ConvertWorkspace wurde erzeugt, aber MaterialAnalysisWorkspace fuegte das
convert_widget nie ins Layout — nur Preflight-Button/Format wurden in den
Media-Bereich injiziert. Die EFFEKTE-Controls (Clip-Combo, Helligkeit/Kontrast/
Crossfade, Vorschau) waren dadurch unerreichbar.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_b492_convert_widget_in_material_layout_effects_only():
    _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace
    from ui.workspaces.media_workspace import MediaWorkspace
    from ui.workspaces.workflow_pages import MaterialAnalysisWorkspace

    media = MediaWorkspace()
    convert = ConvertWorkspace()
    assert convert._tabs.count() == 2  # PREFLIGHT + EFFEKTE vor dem Einbau

    ws = MaterialAnalysisWorkspace(media, convert)

    # convert_widget ist jetzt im Layout des Material-Workspace
    layout = ws.layout()
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert convert in widgets, "convert_widget nicht im MaterialAnalysisWorkspace-Layout"

    # nur noch der EFFEKTE-Tab (leerer PREFLIGHT entfernt)
    assert convert._tabs.count() == 1
    assert convert._tabs.tabText(0).upper() == "EFFEKTE"

    # EFFEKTE-Controls existieren weiterhin
    assert hasattr(convert, "effects_preview")
    assert hasattr(convert, "effects_clip_combo")
    assert hasattr(convert, "btn_apply_effects")

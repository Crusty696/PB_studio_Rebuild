"""EFFEKTE-Platzierung im MATERIAL-&-ANALYSE-Workspace.

Historie:
- B-492 mountete das ConvertWorkspace (EFFEKTE) bewusst in den Material-Workspace,
  damit die Clip-Effekte erreichbar sind.
- UI-Ueberholung 2026-06-13 (User-Entscheidung "EFFEKTE ganz raus aus Material"):
  Das EFFEKTE-Widget wird NICHT mehr in Material gemountet — die leere 360px-
  Vorschau fraß den unteren Material-Bereich als toten Platz. Per-Clip-Effekte
  (Helligkeit/Kontrast/Crossfade) sind im SCHNITT Clip-Inspector verfuegbar; der
  "Videos standardisieren…"-Button bleibt als Trigger im Material-Bereich.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_convert_widget_not_mounted_in_material_but_standardize_reachable():
    _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace
    from ui.workspaces.media_workspace import MediaWorkspace
    from ui.workspaces.workflow_pages import MaterialAnalysisWorkspace

    media = MediaWorkspace()
    convert = ConvertWorkspace()

    ws = MaterialAnalysisWorkspace(media, convert)

    # UI-Ueberholung 2026-06-13: convert_widget (EFFEKTE) ist NICHT (mehr) im
    # Material-Layout -> kein toter Vorschau-Platz mehr.
    layout = ws.layout()
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert convert not in widgets

    # Der Standardisieren-Button wurde aber in den Media-Bereich attached und
    # bleibt damit als Trigger (oeffnet den Ziel-Format-Dialog) erreichbar.
    assert convert.btn_standardize_all.parentWidget() is media._video_preflight_panel

    # EFFEKTE-Controls existieren weiterhin am convert_widget (Controller/Dialog
    # referenzieren sie); sie sind nur nicht in Material gemountet.
    assert hasattr(convert, "effects_clip_combo")
    assert hasattr(convert, "btn_apply_effects")

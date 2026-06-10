"""B-351: Import-Funktion muss auch ueber das Tools-Menue erreichbar sein.

Vorher gab es Import nur ueber die Buttons im MATERIAL-&-ANALYSE-Workspace,
nicht im Tools-Menue. Fix: ein 'Medien importieren'-Submenue im Tools-Menue,
das denselben Import-Flow (ImportMediaController) ruft.
"""

from __future__ import annotations

import inspect


def test_b351_tools_menu_has_import_submenu():
    from ui.controllers.workspace_setup import WorkspaceSetupController
    src = inspect.getsource(WorkspaceSetupController._build_top_bar)
    assert 'addMenu("Medien importieren")' in src
    assert "import_media._import_video" in src
    assert "import_media._import_audio" in src
    assert "import_media._import_folder" in src

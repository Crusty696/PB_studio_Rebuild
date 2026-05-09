# Phase 10 — Navigation + Integration

**Ziel:** `nav_bar` auf 4 Tabs reduzieren, `workspace_setup` re-mappen, `cockpit_orchestrator` zusammenführen, QSettings-Migration.

---

## Task 10.1: `WORKSPACE_NAMES` reduzieren

**Files:**
- Modify: `ui/widgets/nav_bar.py:40-99`
- Test: aktualisiere `tests/ui/test_frontend_rebuild_contract.py:24-34` (Phase 11) — hier nur Implementation.

- [ ] **Step 1: Datei umbauen**

```python
# ui/widgets/nav_bar.py — Klasse WorkspaceNavBar
WORKSPACE_NAMES = ["PROJEKT", "MATERIAL & ANALYSE", "SCHNITT", "EXPORT"]
```

Tooltips, accessible_names, status_tips ebenfalls auf vier Einträge:

```python
tooltips = [
    "Projekt: Status, letzte Projekte und nächster Schritt",
    "Material & Analyse: Medien auswählen und analysieren",
    "Schnitt: Auto-Edit, Pacing, Anker, Audio-Mixer und Notes — alles in einem Workspace",
    "Export: Preview und finales Video rendern",
]
accessible_names = [
    "Projekt Workflow",
    "Material und Analyse Workflow",
    "Schnitt Workflow",
    "Export Workflow",
]
status_tips = [
    "Projektstatus und Startpunkt",
    "Medienpool und Analyse",
    "Schnitt: Auto-Edit + Review in einem Tab",
    "Finales Video exportieren",
]
```

`min_width` für „MATERIAL & ANALYSE" bleibt 154; alle anderen 110.

- [ ] **Step 2: Smoke-Test (manuell)**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -c "from PySide6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from ui.widgets.nav_bar import WorkspaceNavBar; w = WorkspaceNavBar(); print(w.WORKSPACE_NAMES); print(len(w._buttons))"
```

Erwartet: `['PROJEKT', 'MATERIAL & ANALYSE', 'SCHNITT', 'EXPORT']` und `4`.

- [ ] **Step 3: Commit**

```bash
git add ui/widgets/nav_bar.py
git commit -m "feat(schnitt): nav bar reduced to 4 tabs"
```

- [ ] **Step 4: Vault-Update.**

---

## Task 10.2: `workspace_setup._create_workspaces` re-mappen

**Files:**
- Modify: `ui/controllers/workspace_setup.py` (Methode `_create_workspaces`, `_handle_cockpit_action`, `_on_workspace_changed`)
- Test: `tests/ui/test_workspace_setup_four_tabs.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_workspace_setup_four_tabs.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_main_window_has_four_stack_widgets_and_schnitt():
    _qapp()
    from main import PBWindow
    win = PBWindow(app_version="test")
    assert win.workspace_stack.count() == 4
    assert hasattr(win, "_schnitt_ws")
    assert win._schnitt_ws is not None
    win.close()
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Workspace-Erstellung umbauen**

In `ui/controllers/workspace_setup.py`:

- Import oben: `from ui.workspaces.schnitt_workspace import SchnittWorkspace`.
- In `_create_workspaces` ersetze die `_edit_ws`-Erzeugung durch `_schnitt_ws`:

```python
self.window._schnitt_ws = SchnittWorkspace()
```

- Alle bisherigen Direkt-Promotions (`self.window.video_preview = self.window._edit_ws.video_preview` usw.) werden gestrichen oder auf das neue Sub-Tab umgeleitet:

```python
self.window.video_preview = self.window._schnitt_ws.editor_view.tab_schnitt.video_preview
self.window.btn_preview_play = self.window._schnitt_ws.editor_view.tab_schnitt.btn_play
self.window.btn_preview_stop = self.window._schnitt_ws.editor_view.tab_schnitt.btn_stop
self.window.timeline_view = self.window._schnitt_ws.editor_view.tab_schnitt.timeline_view
self.window.cut_info_label = self.window._schnitt_ws.editor_view.tab_schnitt.cut_info_label
self.window.inspector_panel = self.window._schnitt_ws.editor_view.inspector_panel
self.window.audio_combo = ...  # Neu: Combo lebt jetzt im Sub-Tab Pacing & Anker oder als Header.
```

Falls `audio_combo`/`video_combo` bisher in `_build_pacing_tab` lebten, im neuen Layout einen schmalen Header oben in `tab_pacing_anker` ergänzen — alternativ als Property auf `SchnittWorkspace` exposen. Pflicht: alle Konsumenten in `ui/controllers/edit_workspace.py` müssen weiter zugreifen können.

- Stack-Adds:

```python
self.window.workspace_stack.addWidget(self.window._project_dashboard)        # 0
self.window.workspace_stack.addWidget(self.window._material_analysis_ws)     # 1
self.window.workspace_stack.addWidget(self.window._schnitt_ws)               # 2
self.window.workspace_stack.addWidget(self.window._deliver_ws)               # 3
```

- [ ] **Step 4: `_handle_cockpit_action` zusammenführen**

```python
def _handle_cockpit_action(self, action_key: str):
    if action_key == "open_project":
        self.window.project_management._open_project()
        return
    if action_key == "open_material_analysis":
        self.window.nav_bar.set_workspace(1)
        return
    if action_key == "run_audio_complete":
        self.window.nav_bar.set_workspace(1)
        if hasattr(self.window._media_ws, "switch_to_audio"):
            self.window._media_ws.switch_to_audio()
        self.window.audio_analysis._analyze_all_sequential()
        return
    if action_key == "run_video_pipeline":
        self.window.nav_bar.set_workspace(1)
        if hasattr(self.window._media_ws, "switch_to_video"):
            self.window._media_ws.switch_to_video()
        self.window.video_analysis._start_video_pipeline()
        return
    if action_key in ("open_schnitt", "open_auto_edit", "open_review"):
        # Backward-Compat-Aliasse: alle wandern in SCHNITT
        self.window.nav_bar.set_workspace(2)
        return
    if action_key == "open_export":
        self.window.nav_bar.set_workspace(3)
        return
    self.logger.warning("Unbekannte Cockpit-Aktion: %s", action_key)
```

- [ ] **Step 5: `_on_workspace_changed` reduzieren**

```python
def _on_workspace_changed(self, index: int):
    self._update_workflow_gates()
    if index == 0:
        self.window.workspace_stack.setCurrentIndex(0)
        self._refresh_project_dashboard()
        return
    if index == 1:
        self.window.workspace_stack.setCurrentIndex(1)
        if hasattr(self.window, 'convert'):
            self.window.convert._refresh_effects_combos()
        return
    if index == 2:
        self.window.workspace_stack.setCurrentIndex(2)
        self.window._schnitt_ws.refresh_state_from_db()
        return
    if index == 3:
        self.window.workspace_stack.setCurrentIndex(3)
        if hasattr(self.window, 'export'):
            self.window.export._refresh_production_info()
        return
```

- [ ] **Step 6: Pass bestätigen.**

- [ ] **Step 7: Commit**

```bash
git add ui/controllers/workspace_setup.py tests/ui/test_workspace_setup_four_tabs.py
git commit -m "feat(schnitt): workspace_setup remap to 4 tabs"
```

- [ ] **Step 8: Vault-Update.**

---

## Task 10.3: `cockpit_orchestrator` `open_schnitt`

**Files:**
- Modify: `services/cockpit_orchestrator.py:97-104, 275-277`
- Test: `tests/test_services/test_cockpit_open_schnitt.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_cockpit_open_schnitt.py
from services.cockpit_orchestrator import ACTIONS


def test_open_schnitt_action_exists():
    assert "open_schnitt" in ACTIONS
    a = ACTIONS["open_schnitt"]
    assert a.key == "open_schnitt"
    assert a.label


def test_legacy_keys_alias_to_schnitt():
    assert ACTIONS["open_auto_edit"].key in ("open_schnitt", "open_auto_edit")
    assert ACTIONS["open_review"].key in ("open_schnitt", "open_review")
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# services/cockpit_orchestrator.py — neue Action zwischen open_auto_edit / open_review
ACTIONS["open_schnitt"] = CockpitAction(
    key="open_schnitt",
    label="Schnitt öffnen",
    description="Auto-Edit starten oder Timeline prüfen.",
    enabled=True,
)
# Legacy-Alias-Targets: einfach umbiegen
ACTIONS["open_auto_edit"] = CockpitAction(
    key="open_schnitt",
    label="Schnitt öffnen (Auto-Edit)",
    description="Auto-Edit-Lauf in SCHNITT.",
    enabled=True,
)
ACTIONS["open_review"] = CockpitAction(
    key="open_schnitt",
    label="Schnitt öffnen (Review)",
    description="Timeline prüfen / feinjustieren.",
    enabled=True,
)
```

In der Logik die `compute_next_action`/`get_cockpit_readiness` (Zeile ~275) gibt jetzt `ACTIONS["open_schnitt"]` zurück, wo zuvor `open_auto_edit` oder `open_review`.

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add services/cockpit_orchestrator.py tests/test_services/test_cockpit_open_schnitt.py
git commit -m "feat(schnitt): cockpit open_schnitt action + legacy aliases"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 10.4: QSettings-Migration alter Tab-Indizes

**Files:**
- Modify: `ui/controllers/workspace_setup.py` (`_restore_window_state`)
- Test: `tests/ui/test_qsettings_migration.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_qsettings_migration.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings, QCoreApplication
from PySide6.QtWidgets import QApplication
from ui.controllers.workspace_setup import _migrate_workflow_stage_index


def _qapp():
    QCoreApplication.setOrganizationName("PBStudio")
    QCoreApplication.setApplicationName("PBStudioApp")
    return QApplication.instance() or QApplication([])


def test_migrates_3_to_2():
    _qapp()
    s = QSettings("PBStudio", "PBStudioApp")
    s.setValue("window/workflowStageIndex", 3)
    s.remove("window/workflowStageMigratedV2")
    _migrate_workflow_stage_index(s)
    assert int(s.value("window/workflowStageIndex")) == 2
    assert s.value("window/workflowStageMigratedV2", False, type=bool) is True


def test_migrates_4_to_3():
    _qapp()
    s = QSettings("PBStudio", "PBStudioApp")
    s.setValue("window/workflowStageIndex", 4)
    s.remove("window/workflowStageMigratedV2")
    _migrate_workflow_stage_index(s)
    assert int(s.value("window/workflowStageIndex")) == 3


def test_idempotent_when_already_migrated():
    _qapp()
    s = QSettings("PBStudio", "PBStudioApp")
    s.setValue("window/workflowStageIndex", 2)
    s.setValue("window/workflowStageMigratedV2", True)
    _migrate_workflow_stage_index(s)
    assert int(s.value("window/workflowStageIndex")) == 2
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Migration-Funktion**

```python
# ui/controllers/workspace_setup.py — am Ende des File auf Modul-Ebene
def _migrate_workflow_stage_index(settings) -> None:
    """SCHNITT-Redesign 2026-05-09: alte 5-Tab-Indizes auf 4-Tab-Layout mappen."""
    if settings.value("window/workflowStageMigratedV2", False, type=bool):
        return
    raw = settings.value("window/workflowStageIndex")
    if raw is None:
        settings.setValue("window/workflowStageMigratedV2", True)
        return
    try:
        old = int(raw)
    except (TypeError, ValueError):
        old = 0
    mapping = {0: 0, 1: 1, 2: 2, 3: 2, 4: 3}
    settings.setValue("window/workflowStageIndex", mapping.get(old, 0))
    settings.setValue("window/workflowStageMigratedV2", True)
```

In `_restore_window_state` als allererste Zeile aufrufen:

```python
_migrate_workflow_stage_index(settings)
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/controllers/workspace_setup.py tests/ui/test_qsettings_migration.py
git commit -m "feat(schnitt): QSettings workflow stage migration v2"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 10.5: e2e_render_test Index fixen

**Files:**
- Modify: `e2e_render_test.py:141`

- [ ] **Step 1: Anpassung**

```python
# e2e_render_test.py:141
window.workspace_stack.setCurrentIndex(3)  # EXPORT (4 Tabs gesamt)
```

- [ ] **Step 2: Smoke-Run** (sofern lauffähig).

- [ ] **Step 3: Commit**

```bash
git add e2e_render_test.py
git commit -m "fix(schnitt): e2e_render_test export tab index"
```

- [ ] **Step 4: Vault-Update.**

---

## Phasen-Abschluss

Phase 10 fertig. Navigation, Stack, Cockpit-Action und QSettings konsistent auf 4 Tabs.

Nächste Phase: [11_TESTS.md](11_TESTS.md).

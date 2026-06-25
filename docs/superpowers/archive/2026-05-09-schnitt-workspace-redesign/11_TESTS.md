# Phase 11 — Tests anpassen + ergänzen

**Ziel:** Bestehende Tests, die auf 5 Tabs / `set_workflow_stage` pinnen, anpassen. Neue Tests, die in den Sub-Phasen evtl. übersprungen wurden, auffangen.

---

## Task 11.1: `test_frontend_rebuild_contract` aktualisieren

**Files:**
- Modify: `tests/ui/test_frontend_rebuild_contract.py:24-34`

- [ ] **Step 1: Anpassen**

```python
def test_workflow_navigation_names_are_final():
    _ensure_qapp()
    from ui.widgets.nav_bar import WorkspaceNavBar

    assert WorkspaceNavBar.WORKSPACE_NAMES == [
        "PROJEKT",
        "MATERIAL & ANALYSE",
        "SCHNITT",
        "EXPORT",
    ]
```

- [ ] **Step 2: Test laufen lassen, Pass bestätigen.**

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_frontend_rebuild_contract.py
git commit -m "test(schnitt): nav names assert 4 tabs"
```

- [ ] **Step 4: Vault-Update.**

---

## Task 11.2: `test_workspaces_smoke` aktualisieren

**Files:**
- Modify: `tests/ui/test_workspaces_smoke.py:137,142` (sowie ggf. umliegende Test-Funktionen)

- [ ] **Step 1: Lokalisieren**

Lese `tests/ui/test_workspaces_smoke.py` rund um Zeile 137. Identifiziere die Testfunktionen, die `set_workflow_stage` oder die alten Tab-Texte „AUTO-SCHNITT" / „REVIEW" prüfen.

- [ ] **Step 2: Anpassung**

Ersetze die Asserts durch:

```python
def test_schnitt_initial_state_when_empty():
    _ensure_qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    ws = SchnittWorkspace()
    ws.set_active_project(None)
    assert ws.current_state() == STATE_EMPTY


def test_schnitt_editor_subtabs_have_correct_titles():
    _ensure_qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    titles = [ws.editor_view.sub_tabs.tabText(i)
              for i in range(ws.editor_view.sub_tabs.count())]
    assert titles == ["Schnitt", "Pacing & Anker", "Audio", "RL & Notes"]
```

Entferne die alten `set_workflow_stage`-Tests komplett (oder markiere sie mit `@pytest.mark.skip(reason="Replaced by SchnittWorkspace state tests")` wenn dependency-relevant).

- [ ] **Step 3: Pass bestätigen.**

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_workspaces_smoke.py
git commit -m "test(schnitt): replace set_workflow_stage asserts with state tests"
```

- [ ] **Step 5: Vault-Update.**

---

## Task 11.3: Komplette Test-Suite einmal grün bekommen

- [ ] **Step 1: Run**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/ -v --tb=short -m "not gui and not e2e and not slow" --ignore=tests/e2e_real_test.py --ignore=tests/visual_e2e_test.py --ignore=tests/e2e_full_render.py --ignore=tests/e2e_stresstest.py --ignore=tests/gui_e2e_autonomous.py --ignore=tests/gui_e2e_dj_mix_pipeline.py --ignore=tests/smoke_test_app.py --ignore=tests/test_ollama_chat_dock_e2e.py --ignore=tests/verify_ai_stack_final.py
```

- [ ] **Step 2: Bei Fehlern**

Liste die roten Tests im Vault unter neuer Section in der Living-Plan-Datei. **Nicht** Fehler stillschweigend ignorieren oder mit `@pytest.skip` zudecken — Root-Cause analysieren, dokumentieren, fixen oder dem User vorlegen.

- [ ] **Step 3: Bei Pass: Commit `chore(schnitt): tests green after redesign`** (falls noch unverbuchte Test-Anpassungen offen).

- [ ] **Step 4: Vault-Update.**

---

## Phasen-Abschluss

Phase 11 fertig. Test-Suite ist konsistent mit 4-Tab-Architektur.

Nächste Phase: [12_CLEANUP_AND_VERIFY.md](12_CLEANUP_AND_VERIFY.md).

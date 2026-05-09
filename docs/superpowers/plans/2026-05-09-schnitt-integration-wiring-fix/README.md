# SCHNITT Integration-Wiring Fix — Implementation Plan

**Datum:** 2026-05-09 (Nachmittag)
**Branch:** `feat/schnitt-redesign-2026-05-09` (weiter)
**Vorgeschichte:** Audit 2026-05-09 nach Tier 1–6 Hardening hat drei Integrations-Layer-Bugs aufgedeckt: [`B-284`](../../../../../C:/Brain-Bug/projects/pb-studio/wiki/bugs/B-284-schnitt-controller-not-instantiated.md) (P0), `B-285` (P0), `B-286` (P1). 131/131 SCHNITT-Tests grün, aber SCHNITT-Tab in Production unbrauchbar — Controller nirgendwo instanziiert, `set_active_project` nie gerufen, Re-Generate ohne Lock-Confirm.

**Ziel:** Pipeline-Wiring zwischen `MainWindow` ↔ `SchnittWorkspace` ↔ `SchnittController` ↔ Workern ↔ DB-Lifecycle vollständig herstellen, mit echter Production-Pfad-Verifikation und harten Regeln gegen Wiederholung der Integrations-Lücke.

**Out of scope:** keine neuen Features, keine Spec-Änderungen, keine LOCKED-Architektur-Touches. Reines Wiring + Lifecycle + Schutz-Tests.

---

## ⛔ HARTE REGELN — gelten für jede Sub-Task

Diese Regeln sind nicht verhandelbar. Verstoß → Phase-Abbruch + Vault-Eintrag + Plan-Rework. Sie existieren weil Tier 1–6 trotz „Wiring"-Label am Production-Boot vorbeigetestet hat.

### R-1 — „Tests grün ≠ Done"

`pytest` grün ist **notwendig, nicht hinreichend**. Eine Phase ist erst dann „abschließbar", wenn:

- (a) Alle relevanten Unit-Tests grün, **und**
- (b) **Production-Boot-Smoke-Test** (siehe R-3) den Code-Pfad tatsächlich durchläuft, **und**
- (c) Manuell-Walk durch das Feature im laufenden GUI mit Test-Datensatz (Solo_Natur + Crusty Progressive Psy Set2.mp3).

Phase-Status `done` wird nicht vom Agent gesetzt. Phase-Agent setzt nur `code-fix-pending-live-verification`. Final-`done` setzt der User.

### R-2 — Kein Controller ohne Production-Instanziierung

Wenn eine Klasse mit Controller-/Service-/Manager-Charakter neu angelegt wird, MUSS vor dem nächsten Commit ein Grep beweisen, dass sie außerhalb von Tests instanziiert wird:

```bash
# Pflicht-Check vor jedem Phase-Commit (verbatim ausführen, Output anhängen)
grep -rn "ClassName(" --include="*.py" -- . | grep -v "tests/" | grep -v "__pycache__"
```

Treffer == 0 → Commit blockiert, Tasks neu planen.

### R-3 — Production-Boot-Smoke-Test ist Pflicht

Jede Phase, die Wiring berührt, fügt mindestens einen Test hinzu, der **die echte `_create_workspaces`-Methode** (oder ihren Lifecycle-Hook) ausführt und prüft, dass Klick → Worker-Start passiert. Stub den Worker, nicht den Controller. Stub die DB, nicht das UI.

Test-Skeleton (Pflichtform):

```python
def test_schnitt_preset_click_triggers_worker(qapp, monkeypatch, test_engine):
    # 1. echte WorkspaceSetupController._create_workspaces durchlaufen
    window = _build_real_main_window(monkeypatch, test_engine)
    # 2. echtes UI-Element finden, echten Klick simulieren
    btn = window._schnitt_ws.empty_view.findChild(QPushButton, "preset_techno")
    captured = []
    monkeypatch.setattr(window.edit_workspace, "_on_schnitt_auto_edit_request",
                        lambda profile: captured.append(profile))
    btn.click()
    # 3. Slot wurde wirklich gerufen
    assert len(captured) == 1
    assert captured[0].cut_rate is not None
```

### R-4 — Doppel-Verdrahtung verboten

Wenn ein Klick durch den Controller-Pfad geht, darf `workspace_setup.py` denselben Klick **nicht** parallel auf den alten Pfad mappen. Pre-Commit-Grep:

```bash
grep -n "btn_regenerate.clicked.connect\|preset_selected.connect" ui/controllers/workspace_setup.py
```

Treffer in `workspace_setup.py` muss **null** sein für Buttons, die der Controller besitzt. Treffer ≠ null → entfernen, neu committen.

### R-5 — Lifecycle-Vollständigkeit (Triple-Hook-Pflicht)

Jeder Workspace mit `set_active_project(pid)` muss an **drei** Stellen aufgerufen werden:

1. `WorkspaceSetupController._on_workspace_changed(idx)` (Tab-Wechsel),
2. `WorkspaceSetupController._handle_cockpit_action("open_schnitt")` (Cockpit-Sprung),
3. Project-Open-Hook (`ProjectManager` oder `project_management._open_project` Post-Open-Callback).

Plan-Phase-B Checkliste enthält alle drei. Fehlt einer → Phase nicht fertig.

### R-6 — Vault-Pflicht pro Sub-Task

`C:\Brain-Bug\projects\pb-studio\` wird **pro Commit** aktualisiert: Living-Plan-Status, `log.md`-Eintrag, Bug-File-Status auf `code-fix-pending-live-verification` (nie `fixed`), `index.md > Aktiver Handoff` aktuell halten. Repo-Synthese unter `docs/superpowers/synthesis/` nicht ausreichend — Vault muss separat gepflegt sein.

### R-7 — Conventional Commits, atomar, deutsch

Subject ≤ 50 Zeichen. Conventional-Commits-Prefix. Ein Commit = ein Sub-Task. Co-Author-Trailer wie projektüblich. Beispiel:

```
fix(schnitt): SchnittController in workspace_setup instanziieren (B-284)
```

### R-8 — Conda-Env hart

Alle pytest-Aufrufe ausschließlich mit:

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest <pfad> -v --tb=short
```

Kein `.venv`, kein System-Python, keine Abkürzungen.

### R-9 — Stop-and-Ask bei Unklarheit

Wenn ein Slot-Name, ein Lifecycle-Hook, eine DB-Spalte oder ein Test-Pfad nicht eindeutig ist: **stop, frag User**. Nicht raten, nicht „pragmatisch entscheiden", nicht improvisieren. Vorbeugend gegen die nächste Selbsttäuschung.

### R-10 — Audit-Schluss-Verifikation

Nach Phase E (Live-Verify) macht der Agent **einen letzten Audit-Pass** mit denselben Greps wie der initiale Audit (B-284/285/286-Reproduktion):

```bash
grep -rn "SchnittController" --include="*.py" -- . | grep -v tests | grep -v __pycache__
grep -rn "_schnitt_ws.set_active_project\|tab_rl_notes.set_active_project" --include="*.py" -- .
grep -n "btn_regenerate.clicked.connect" ui/controllers/workspace_setup.py
```

Erwartete Treffer-Counts in Phase-E-Definition-of-Done dokumentiert. Abweichung → Plan-Rework.

---

## Phasen-Übersicht

| # | Phase | Zweck | Geschätzt | Bugs |
|---|---|---|---|---|
| A | Controller-Boot | `SchnittController` in `_create_workspaces` instanziieren, Signal-Bridges anlegen, Doppel-Verdrahtung entfernen. | 30–45 min | B-284, B-286 |
| B | Project-Lifecycle | `set_active_project` an Triple-Hook (Tab-Wechsel, Cockpit, Project-Open) für `_schnitt_ws` + `tab_rl_notes`. | 30 min | B-285 |
| C | Worker-Bridge | `attach_worker(worker)` in `_auto_edit_to_beat` und `_generate_timeline_impl` anbinden, Progress-Stage-Texte real propagieren. | 30 min | B-284 (Teil) |
| D | Integration-Smoke-Tests | Drei Production-Boot-Smoke-Tests anlegen (Preset-Klick, Project-Open-State, Worker-Progress-Roundtrip). | 30 min | Schutz |
| E | Live-Verify durch User | App starten, 16-Schritt-Klick aus `12_LIVE_VERIFY_USER_GUIDE.md` durchlaufen. **Nur User vergibt `status: fixed`.** | User-Zeit | Abnahme |

Total Agent-Aufwand: ~2 h. Live-Verify-Zeit User: ~10 min.

---

## Phase A — Controller-Boot (B-284, B-286 Teil)

**Ziel:** `SchnittController` läuft im echten App-Boot mit, Signale sind an `edit_workspace`-Adapter-Slots gebunden, Empty-State-Klicks und Cancel werden bedient, Re-Generate-ConfirmDialog erscheint.

### A.1 — Adapter-Slots in `edit_workspace.py` anlegen

Datei: `ui/controllers/edit_workspace.py`.

Zwei neue Methoden ergänzen, die `PacingProfile`-Objekte konsumieren und auf bestehende Pfade mappen:

```python
def _on_schnitt_auto_edit_request(self, profile) -> None:
    """SchnittController: empty-state preset → start auto-edit.
    profile is services.pacing_profile.PacingProfile (immutable).
    """
    self._apply_profile_to_widgets(profile)   # neu, A.1.b
    self._auto_edit_to_beat()

def _on_schnitt_regenerate_request(self, profile) -> None:
    """SchnittController: pacing-tab regenerate (post-confirm)."""
    self._apply_profile_to_widgets(profile)
    self._generate_timeline_impl()

def _apply_profile_to_widgets(self, profile) -> None:
    """Spiegelt PacingProfile-Werte zurück in audio_combo/video_combo/cut_rate_combo/...
    damit _auto_edit_to_beat / _generate_timeline_impl mit konsistentem UI-Stand laufen.
    Implementation: idx-Lookup für Combo-IDs, setValue für Slider/Spin, setText für vibe.
    """
    ...
```

**Pflicht-Check (R-9):** Bevor A.1 beginnt — feststellen welche Profile-Felder welche Widgets befüllen. Falls eines nicht eindeutig ist → User fragen, nicht raten.

### A.2 — `SchnittController` in `_create_workspaces` instanziieren

Datei: `ui/controllers/workspace_setup.py`, nach Zeile 276 (`self.window._schnitt_ws = SchnittWorkspace()`):

```python
from ui.controllers.schnitt_controller import SchnittController
self.window._schnitt_ctrl = SchnittController(
    self.window._schnitt_ws,
    parent=self.window,
)
self.window._schnitt_ctrl.request_auto_edit_with_profile.connect(
    self.window.edit_workspace._on_schnitt_auto_edit_request
)
self.window._schnitt_ctrl.request_regenerate.connect(
    self.window.edit_workspace._on_schnitt_regenerate_request
)
self.window._schnitt_ctrl.request_open_settings.connect(
    self.window.project_management._show_settings
)
```

### A.3 — Doppel-Verdrahtung entfernen (R-4)

Datei: `ui/controllers/workspace_setup.py`, Zeile 333:

```python
# ENTFERNEN — Controller besitzt diesen Klick (Plan A13 Confirm-Dialog).
_schnitt_tab_pacing.btn_regenerate.clicked.connect(self.window.edit_workspace._generate_timeline)
```

Empty-State-Buttons (`preset_selected`, `custom_clicked`) sind ohnehin nicht in `workspace_setup.py` doppelt verdrahtet — Controller hat sie alleine.

### A.4 — Pre-Commit-Grep (R-2 + R-4)

```bash
grep -rn "SchnittController(" --include="*.py" -- . | grep -v "tests/" | grep -v __pycache__
# Erwartung: ≥ 1 Treffer (workspace_setup.py)

grep -n "btn_regenerate.clicked.connect" ui/controllers/workspace_setup.py
# Erwartung: 0 Treffer
```

Treffer-Counts in Commit-Body dokumentieren.

### A.5 — Test-Lauf

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/ui/test_schnitt_controller_wiring.py tests/ui/test_schnitt_controller_loading_hook.py tests/ui/test_workspaces_smoke.py -v --tb=short
```

Erwartung: alle grün, keine Regression.

### A.6 — Vault-Update + Commit (R-6, R-7)

- `wiki/synthesis/schnitt-workspace-redesign-2026-05-09.md`: Phase-A-Block mit Commit-Hash.
- `wiki/bugs/B-284-...md`: Status auf `code-fix-pending-live-verification`.
- `wiki/bugs/B-286-...md`: dito.
- `log.md`: dated entry.
- Commit: `fix(schnitt): SchnittController boot + signal bridges (B-284,B-286)`.

### A — Definition of Done

- [ ] `SchnittController` in Production grep > 0.
- [ ] `btn_regenerate.clicked.connect` in `workspace_setup.py` == 0.
- [ ] Bestehende SCHNITT-Tests weiterhin alle grün.
- [ ] Vault-Update committet.
- [ ] Bug-Files B-284, B-286 auf `code-fix-pending-live-verification`.

---

## Phase B — Project-Lifecycle (B-285)

**Ziel:** SchnittWorkspace und tab_rl_notes erfahren bei jedem Project-Open / Tab-Wechsel / Cockpit-Sprung das aktive Projekt. STATE_EMPTY ist nur noch sichtbar, wenn keine Timeline existiert — nicht weil `_project_id is None`.

### B.1 — Helper für aktiven PID

Datei: `ui/controllers/workspace_setup.py`. Privater Helper:

```python
def _push_active_project_to_schnitt(self) -> None:
    """Triple-Hook (R-5): Tab-Wechsel, Cockpit, Project-Open rufen alle hier durch."""
    try:
        from database import get_active_project_id
        pid = get_active_project_id()
    except Exception as exc:
        self.logger.debug("active project id unavailable: %s", exc)
        pid = None
    # Schnitt-Workspace: Controller-protected um Loading nicht zu killen
    ctrl = getattr(self.window, "_schnitt_ctrl", None)
    if ctrl is not None:
        ctrl.set_active_project_protected(pid)
    else:
        self.window._schnitt_ws.set_active_project(pid)
    # RL-Notes-Subtab eigenständig
    self.window._schnitt_ws.editor_view.tab_rl_notes.set_active_project(pid)
```

### B.2 — Hook 1: Tab-Wechsel

Datei: `ui/controllers/workspace_setup.py`, in `_on_workspace_changed(2)` vor `refresh_state_from_db`:

```python
self._push_active_project_to_schnitt()
```

### B.3 — Hook 2: Cockpit-Action

Datei: `ui/controllers/workspace_setup.py`, in `_handle_cockpit_action` bei Branches `open_schnitt` / `open_auto_edit` / `open_review` (vor oder nach `nav_bar.set_workspace(2)`):

```python
self._push_active_project_to_schnitt()
```

### B.4 — Hook 3: Project-Open

Drei Wege (alle drei prüfen, Treffer durchziehen):

- `services/project_manager.py`: existiert ein Post-Open-Signal? Falls ja → an Helper binden.
- `ui/controllers/project_management.py::_open_project`: nach erfolgreichem `manager.open_project(...)` Helper-Call ergänzen.
- `ui/controllers/workspace_setup.py::_open_recent_project`: nach erfolgreichem `manager.open_project(...)` Helper-Call ergänzen.

**R-9-Pflicht:** Vor B.4 — Project-Manager-Code lesen, herausfinden welcher der drei Pfade kanonisch ist. Falls Project-Manager Signal `project_opened` o.ä. emittiert, dieses bevorzugen, statt jede UI-Stelle einzeln zu pflegen. Wenn unklar → User fragen.

### B.5 — Pre-Commit-Grep (R-5)

```bash
grep -rn "_push_active_project_to_schnitt\|_schnitt_ws.set_active_project\|tab_rl_notes.set_active_project" --include="*.py" -- . | grep -v tests | grep -v __pycache__
```

Erwartung: mindestens drei Treffer in Production-Code (Tab-Wechsel, Cockpit, Project-Open).

### B.6 — Test-Lauf

```text
"...python.exe" -m pytest tests/ui/test_schnitt_workspace_states.py tests/ui/test_subtab_rl_notes.py tests/ui/test_workspaces_smoke.py -v --tb=short
```

### B.7 — Vault + Commit

- Living-Plan Phase-B-Block.
- B-285 auf `code-fix-pending-live-verification`.
- Commit: `fix(schnitt): triple-hook set_active_project (B-285)`.

### B — Definition of Done

- [ ] Helper `_push_active_project_to_schnitt` existiert und wird **dreimal** in Production-Code gerufen.
- [ ] Bestehende Workspace-State-Tests grün.
- [ ] Bug-File B-285 auf `code-fix-pending-live-verification`.

---

## Phase C — Worker-Bridge

**Ziel:** Wenn ein SCHNITT-driving Worker startet, propagieren `progress` / `done` / `failed` an die Loading-View und an `refresh_state_from_db`. Damit erst sind die rotierenden Stage-Texte und die Editor-Rückkehr keine tote UI mehr.

### C.1 — Worker-Inventur

Vor jedem Code-Change: Liste der relevanten Worker mit Datei + Klasse + Signal-Namen. Plan kennt:

- `_auto_edit_to_beat` → vermutlich `AutoEditWorker` (Datei aus Phase 09).
- `_generate_timeline_impl` → `_CutsWorker` (Datei aus Phase 09).

**R-9-Pflicht:** Lesen, nicht raten. Beide Worker-Files öffnen, Signal-Schema (`progress`, `done`, `failed`, ggf. überladen) verifizieren. Falls Signal-Namen abweichen → vor Code-Change User fragen.

### C.2 — Worker an Controller anhängen

In `ui/controllers/edit_workspace.py`, an jedem Worker-Konstruktor / `start()`:

```python
worker = AutoEditWorker(...)
ctrl = getattr(self.window, "_schnitt_ctrl", None)
if ctrl is not None:
    ctrl.attach_worker(worker)
worker.start()
```

`SchnittController.attach_worker` ist bereits implementiert — keine Änderung dort nötig.

### C.3 — Loading-State-Eintritt synchronisieren

Empty-State-Preset-Klick triggert `enter_loading()` über den Controller (existiert in `_on_preset_selected`). Re-Generate triggert es über `_on_regenerate_clicked`. Aber: Wenn der User den Editor-Header-Button `btn_generate` direkt klickt (Editor-State, nicht Empty-State), umgeht er den Controller. Entscheidung:

- **Variante 1 (empfohlen):** `btn_generate.clicked` zusätzlich an Controller-Slot binden, der `enter_loading()` ruft und dann an Worker-Pfad delegiert.
- **Variante 2:** akzeptieren, dass Editor-Header-Generate ohne Loading-Overlay läuft (Spec verlangt es nicht explizit).

**R-9-Pflicht:** vor Phase C entscheiden. Ich (Agent) tendiere zu Variante 1 für Konsistenz; falls User Variante 2 will → Plan-Abweichung dokumentieren.

### C.4 — Test-Lauf

```text
"...python.exe" -m pytest tests/ui/test_schnitt_controller_loading_hook.py tests/ui/test_schnitt_workspace_states.py -v --tb=short
```

### C.5 — Vault + Commit

- Living-Plan Phase-C-Block.
- B-284 Commentary: Worker-Bridge Teil von B-284 jetzt fertig.
- Commit: `fix(schnitt): attach_worker hookup for progress bridge (B-284)`.

### C — Definition of Done

- [ ] Jeder SCHNITT-driving Worker geht durch `ctrl.attach_worker(...)` bevor `start()`.
- [ ] Loading-View Stage-Text propagiert nachweislich (siehe Phase-D-Smoke-Test).
- [ ] Variante 1 vs 2 entschieden + dokumentiert.

---

## Phase D — Integration-Smoke-Tests (Schutz, R-3)

**Ziel:** Drei Tests, die genau diese Klasse von Bugs in Zukunft abfangen. Datei: `tests/ui/test_schnitt_integration_boot.py` (neu).

### D.1 — Test 1: Preset-Klick → Worker-Start

Skeleton:

```python
def test_preset_click_triggers_auto_edit_request(qapp, monkeypatch, test_engine, real_main_window):
    """B-284-Regression: Empty-State-Klick erreicht edit_workspace-Slot."""
    captured = []
    monkeypatch.setattr(
        real_main_window.edit_workspace,
        "_on_schnitt_auto_edit_request",
        lambda profile: captured.append(profile),
    )
    btn = real_main_window._schnitt_ws.empty_view.findChild(QPushButton, "preset_techno")
    btn.click()
    assert len(captured) == 1
    assert captured[0].cut_rate is not None
```

### D.2 — Test 2: Project-Open → STATE_EDITOR (wenn Timeline existiert)

```python
def test_project_open_with_timeline_lands_in_editor(qapp, test_engine, real_main_window):
    """B-285-Regression: Triple-Hook set_active_project + refresh."""
    pid = _seed_project_with_timeline_entries(test_engine)
    real_main_window.workspace_setup_controller._push_active_project_to_schnitt()
    real_main_window.nav_bar.set_workspace(2)
    assert real_main_window._schnitt_ws.current_state() == 2  # STATE_EDITOR
```

### D.3 — Test 3: Worker-Progress-Roundtrip

```python
def test_worker_progress_propagates_to_loading_view(qapp, real_main_window, fake_worker):
    """B-284-Regression: attach_worker bridge greift wirklich."""
    real_main_window._schnitt_ctrl.attach_worker(fake_worker)
    real_main_window._schnitt_ws.enter_loading()
    fake_worker.progress.emit("audio_load", 0.5)
    assert real_main_window._schnitt_ws.loading_view.progress_bar.value() == 50
```

`real_main_window`-Fixture in `tests/conftest.py` hinzufügen — durchläuft `WorkspaceSetupController._create_workspaces` echt, mit gestubbten DB-Sessions.

### D — Definition of Done

- [ ] Drei neue Tests grün.
- [ ] `real_main_window`-Fixture wiederverwendbar.
- [ ] Tests bewusst so geschrieben, dass sie B-284/285/286 in Zukunft abfangen — Test-Docstring referenziert die Bug-IDs.

---

## Phase E — Live-Verify durch User

**Ziel:** App starten, manuell durch echten Workflow klicken, beweisen dass Pipeline durchgeht.

### E.1 — Pre-Flight Audit-Reproduktion (R-10)

Agent läuft die drei Audit-Greps nochmal:

```bash
grep -rn "SchnittController(" --include="*.py" -- . | grep -v tests | grep -v __pycache__   # ≥ 1
grep -rn "_schnitt_ws.set_active_project\|tab_rl_notes.set_active_project" --include="*.py" -- . | grep -v tests   # ≥ 3
grep -n "btn_regenerate.clicked.connect" ui/controllers/workspace_setup.py   # 0
```

Output ins Vault als Beleg. Abweichung → Phase-Rework, kein User-Live-Verify.

### E.2 — User-Walkthrough

User-Klicks aus `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/12_LIVE_VERIFY_USER_GUIDE.md` (16 Schritte). Test-Datensatz: Solo_Natur (103 Videos) + Crusty Progressive Psy Set2.mp3.

Pflicht-Beobachtungen:

1. SCHNITT-Tab nach Project-Open: zeigt Editor-State, **nicht** Empty-State (sofern Timeline existiert).
2. Klick auf „Techno"-Preset im Empty-State (frisches Projekt): Loading-View erscheint, rotierender Stage-Text läuft, ProgressBar bewegt sich.
3. Loading endet → Editor-State mit allen 4 Sub-Tabs + Inspector.
4. Lock-Icon-Klick auf einem Clip → Lock-Status sichtbar.
5. „Mit neuem Pacing generieren" → ConfirmDialog mit Lock-Count + Diff-Preview erscheint.
6. ConfirmDialog bestätigen → Loading → neuer Editor-State, gesperrter Clip überlebt.
7. RL & Notes Sub-Tab: Note tippen, Projekt schließen, neu öffnen → Note wieder da.

Jeder Schritt: ✅ oder ❌ + Screenshot bei ❌.

### E.3 — Status-Vergabe

Nur bei 7/7 ✅: User vergibt `status: fixed` für B-284, B-285, B-286, sowie für Living-Plan (`schnitt-workspace-redesign-2026-05-09.md`).

Bei ≥ 1 ❌: Bug bleibt offen, neuer Bug-File falls Symptom anders als B-284/285/286, Plan-Rework.

---

## Globaler Erfolgs-Test

Identisch zu `2026-05-09-schnitt-workspace-redesign/README.md` Globaler Erfolgs-Test, **plus**:

> User klickt nach Phase E den Workflow durch und kann an keiner Stelle behaupten „SCHNITT ist tot / Pipeline reicht Daten nicht weiter / unbrauchbar".

---

## Risiken & Trade-Offs

| ID | Risiko | Gegenmaßnahme |
|---|---|---|
| W-1 | `_apply_profile_to_widgets` (A.1.b) verfehlt ein Feld → Re-Generate läuft mit falschen Werten | Inventur der Profile-Felder vor A.1, R-9-Stop bei Unklarheit |
| W-2 | Project-Manager hat kein Post-Open-Signal → drei manuelle Hook-Punkte | B.4 dokumentiert; falls Signal später kommt: Refactor-Folge-Plan |
| W-3 | `attach_worker` Signal-Namen weichen ab (`progress` vs `progressChanged`) | Worker-Inventur vor C.2 |
| W-4 | Variante-1 vs Variante-2 in C.3 → Spec bleibt offen | User-Entscheidung vor C.3 |
| W-5 | Live-Verify findet andere Bugs (z. B. tab_audio Stems-Mixer kaputt) → Plan-Scope-Drift | Strikt im Scope bleiben, neue Bugs als eigene B-XXX, separate Plans |

---

## Anti-Patterns (Verbot)

- **Verboten:** „ich denke das passt", „sollte funktionieren", „pragmatisch entschieden". → R-9.
- **Verboten:** Tests grün → Phase auf `done`. → R-1.
- **Verboten:** mehrere Sub-Tasks in einem Commit. → R-7.
- **Verboten:** SCHNITT-Code anfassen ohne vorherigen Audit-Grep. → R-2/R-4/R-10.
- **Verboten:** Vault-Update am Ende einer ganzen Phase statt pro Commit. → R-6.
- **Verboten:** `status: fixed` durch Agent. → R-1.
- **Verboten:** Force-Push, `git reset --hard`, Branch-Wechsel ohne User-Freigabe.

---

## Plan-Anker

- Spec-Authority: `docs/superpowers/specs/2026-05-09-schnitt-workspace-redesign.md` (unverändert).
- Vorgänger-Plan: `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/` (Phasen 01–12 + Tier 1–6).
- Living-Plan: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md` (wird mit Phase-A/B/C/D/E-Blöcken erweitert).
- Bug-Files: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-284-...md`, `B-285-...md`, `B-286-...md`.
- Test-Datensatz: Solo_Natur (103 Videos) + Crusty Progressive Psy Set2.mp3 (149 MB).
- Conda-Env: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`.

---

## Freigabe

Plan-Status: **draft, awaiting user approval**.

Agent darf erst mit Phase A starten, nachdem User explizit „Plan freigegeben" / „start Phase A" o.ä. sagt. Bis dahin: keine Code-Änderung, kein Commit.

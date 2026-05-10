# Checkbox + SCHNITT + Workflow Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Audio-Multi-Select via Checkbox funktioniert, SCHNITT-Empty-State-Preset-Klick startet wirklich Pipeline, Cutliste sichtbar, MEDIA-Workflow strukturiert mit Sub-Sektionen + Onboarding-Banner.

**Architecture:** TDD pro Bug. Audio-Helper symmetrisch zu Video. SCHNITT-Adapter ruft Auto-Fill-Helper vor Worker. CutListPanel als neues Widget rechts oder unter Timeline im Schnitt-Sub-Tab. MEDIA-Workspace-Layout in 3 visuelle Sektionen mit Banner. ProjectDashboard-Card-Klick navigiert zu Tab+Sektion.

**Tech Stack:** PySide6 (Qt 6) · SQLAlchemy + SQLite WAL · pytest mit `QT_QPA_PLATFORM=offscreen` · conda-env `pb-studio` (`C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`).

**Plan-Wurzel:** `docs/superpowers/plans/2026-05-11-checkbox-schnitt-workflow-fix/`. Regelwerk: [`README.md`](./README.md) mit R-1..R-15.

---

## File Structure

| Datei | Verantwortlichkeit | Phasen |
|---|---|---|
| `ui/controllers/audio_analysis.py` | `_get_selected_audio_track` (Single) + `_get_selected_audio_tracks` (Plural) checkbox-first. | A |
| `ui/controllers/stems.py` | `_start_stem_separation` + `_start_auto_ducking` nutzen neuen Single-Helper. | B |
| `ui/controllers/edit_workspace.py` | `_ensure_combos_filled_from_project` Helper + `_on_schnitt_auto_edit_request`/`_on_schnitt_regenerate_request` Pre-Flight. | C |
| `ui/widgets/cut_list_panel.py` | NEU: `CutListPanel` (QTableWidget) — Spalten Zeit/Quelle/Stärke/Lock/Action. | D |
| `ui/workspaces/schnitt/tab_schnitt.py` | CutListPanel einhängen rechts neben Inspector oder unter Timeline. | D |
| `services/timeline_service.py` | `get_cut_list(project_id)` Helper für CutListPanel-Refresh. | D |
| `ui/workspaces/media_workspace.py` | Layout in 3 Sub-Sektionen (Import / Analyse / Convert). Doppel-Buttons entweder weg oder gestylt. | E |
| `ui/controllers/workspace_setup.py` | Doppel-Connects für `_start_video_pipeline` entfernen oder dokumentieren. | E |
| `ui/workspaces/workflow_pages.py` | `ProjectDashboard`-Card-Klick navigiert via `nav_bar.set_workspace(N)` + Sub-Sektion. | E |
| `ui/widgets/onboarding_banner.py` | NEU: `OnboardingBanner` Widget, dismissable, QSettings-persistent pro Projekt. | F |
| `ui/workspaces/media_workspace.py` | OnboardingBanner einhängen oben im Layout. | F |
| `tests/ui/test_audio_checkbox_wiring.py` | NEU: source-inspection + behavior für Helper. | A |
| `tests/ui/test_schnitt_empty_state_preset_runs_pipeline.py` | NEU: Preset-Klick mit Auto-Fill. | C |
| `tests/ui/test_cut_list_panel.py` | NEU: CutListPanel Render + Refresh. | D |
| `tests/ui/test_media_workspace_layout.py` | NEU: Sub-Sektionen + Doppel-Button-Audit. | E |
| `tests/ui/test_onboarding_banner.py` | NEU: Banner-Anzeige + Dismiss. | F |
| `tests/ui/test_checkbox_workflow_smoke.py` | NEU: Audit-Greps R-13/R-14/R-15. | G |
| `scripts/phase_h_workflow_smoke.py` | NEU: Live-Boot mit echtem PBWindow + Workflow-Walk. | G |

---

## Conventions

- **Conda-Env Pflicht** für jeden pytest-Aufruf: `"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest <pfad> -v --tb=short` (kürzer `<PY>`).
- **Conventional Commits**, Subject ≤ 50 Zeichen, Co-Author-Trailer `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- **Vault-Pflicht pro Sub-Task** — Bug-File-Status `code-fix-pending-live-verification`, log.md-Eintrag.
- **`status: fixed`** vergibt nur der User nach Phase H.

---

## ⛔ Zwangs-Regeln R-16..R-25 (User-Forderung 2026-05-11)

Gelten **pro Task**, nicht nur pro Phase. Implementer-Subagenten **müssen** sich an folgenden Workflow halten — kein Skip, kein DONE_WITH_CONCERNS, kein "fix später":

### Task-Lifecycle (Pflicht-Reihenfolge)

```
1. Soll-Snapshot         [R-16]  — schreibe was geplant ist
2. Pre-Git-Status        [R-21]  — git status --porcelain Vor-Snapshot
3. Pre-Flight-Reads      [R-9]   — Pflicht-Lektüre der zu ändernden Files
4. Failing Test          [TDD]   — Test schreiben + RED beobachten
5. Implementation        [Plan]  — exakt was Soll-Snapshot sagt
6. Test GREEN beobachten [TDD]
7. Selbst-Validation     [R-17]  — Soll-Punkt vs Ist-Code, Tabelle ✓/✗
8. Drei-Pass-Verify      [R-18]  — Source / Behavior / Live-Boot
9. Pre-Commit Greps      [R-22]  — Audit-Greps müssen Soll-Werte erreichen
10. Post-Git-Status      [R-21]  — nur erwartete Files in git status
11. Anti-Skip-Checkliste [R-20]  — alle 10 Punkte abgehakt
12. Vault-Update         [R-7]
13. Commit               [R-8]   — mit Audit-Tabellen im Body
14. Report DONE          [R-19]  — nur DONE oder BLOCKED, nichts dazwischen
```

### Bei Abweichung (Schritt 7 hat `✗`)

**Auto-Correct-Schleife** (R-17):

```
Iteration 1: ✗ erkannt → fix → re-validate
Iteration 2: noch ✗ → fix → re-validate
Iteration 3: noch ✗ → BLOCKED, eskaliere an Controller
```

**Niemals DONE bei `✗`.** Niemals "wird in Phase X gefixt". Niemals "Reviewer entscheidet".

### Bei Reviewer-Findings (R-23)

- **Critical/Important/Minor**: alle MUST-FIX vor DONE des Tasks. Implementer (gleicher Subagent) fixt, Reviewer re-reviewt, Loop bis ✓.
- Nur **Info**-Findings dürfen unbehandelt durchgehen.

### Status-Werte (R-19)

- **DONE** — alle 14 Lifecycle-Punkte abgehakt, alle ✓.
- **BLOCKED** — 3-Iterations-Limit erreicht oder externe Sache.
- **NEEDS_CONTEXT** — Plan-Text unklar, frag Controller.

`DONE_WITH_CONCERNS` ist verboten. Wird vom Controller mit Re-Dispatch beantwortet.

### Pflicht-Block in jedem DONE-Report

```markdown
## R-16 Soll-Snapshot
<text>

## R-17 Spec-Compliance-Check
| Plan-Punkt | Soll | Ist | OK? |
|---|---|---|---|
... 100% ✓ erforderlich.

## R-18 Drei-Pass
- Pass 1 Source: <Grep-Output>
- Pass 2 Behavior: <pytest-Output>
- Pass 3 Live-Boot: <Smoke-Output oder N/A wenn nicht UI/Worker>

## R-20 Checkliste
- [x] Test geschrieben
- [x] Test RED beobachtet
- [x] Implementation
- [x] Test GREEN beobachtet
- [x] Regression-Sweep gruen
- [x] Vault-Update
- [x] log.md
- [x] Commit
- [x] R-18 alle drei Pass gruen
- [x] R-17 100% ✓

## R-21 Git-Status-Audit
| File | Soll | Ist |
|---|---|---|
...

## R-22 Audit-Greps
- <grep1>: PASS
- <grep2>: PASS

## R-23 Reviewer-Findings
- 0 offen (alle gefixt vor DONE).
```

**Implementer-Report ohne diese Sektionen wird sofort re-dispatched mit Hinweis "R-19 incomplete".**

---

---

## Phase A — Audio-Checkbox-Helper (B-293)

**Files:** `tests/ui/test_audio_checkbox_wiring.py` (new), `ui/controllers/audio_analysis.py`.

### Task A.1 — Pre-Flight (R-9)

- [ ] Read `ui/controllers/audio_analysis.py` Z.1-50 (full `_get_selected_audio_track`).
- [ ] Read `ui/controllers/video_analysis.py` Z.30-80 (`_analyze_selected_video` für Symmetrie-Vorbild).
- [ ] Identify audio_pool_model — has `get_checked_ids` method? Grep `class MediaTableModel.*get_checked_ids`. If no, STOP and report (model API gap).

### Task A.2 — Failing test

- [ ] Create `tests/ui/test_audio_checkbox_wiring.py`:

```python
"""B-293: Audio-Pool Checkbox + Alle-Button werden von jeder Audio-Analyse
respektiert. Symmetrisch zu Video-Helper."""
from __future__ import annotations

import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    """AST-strict slot body extraction."""
    import ast
    src = (REPO / file_rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == slot_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None
            return seg
    raise AssertionError(f"Slot {slot_name} nicht gefunden in {file_rel}")


def test_b293_audio_selected_track_uses_get_checked_ids():
    """R-13: Audio-Helper muss get_checked_ids referenzieren BEVOR selectionModel."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_track")
    assert "get_checked_ids" in body, (
        "B-293: _get_selected_audio_track ignoriert Checkbox — "
        "Audio-Multi-Select tot."
    )
    pos_checked = body.find("get_checked_ids")
    pos_selmodel = body.find("selectionModel")
    if pos_selmodel > 0:
        assert pos_checked < pos_selmodel, (
            "B-293: get_checked_ids muss VOR selectionModel-Fallback stehen."
        )


def test_b293_audio_selected_tracks_plural_exists():
    """B-293: Plural-Variante fuer Batch-Funktionen."""
    src = (REPO / "ui/controllers/audio_analysis.py").read_text(encoding="utf-8")
    assert "def _get_selected_audio_tracks(" in src, (
        "B-293: _get_selected_audio_tracks (Plural) fehlt."
    )


def test_b293_audio_selected_tracks_plural_uses_checked_ids():
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_tracks")
    assert "get_checked_ids" in body
    assert "list" in body or "[" in body  # returns iterable
```

- [ ] Run, expect FAIL (Plural-Methode existiert nicht, Single-Helper hat kein `get_checked_ids`):

```text
<PY> tests/ui/test_audio_checkbox_wiring.py -v --tb=short
```

### Task A.3 — Implementation Single-Variante

- [ ] Edit `ui/controllers/audio_analysis.py`. Replace `_get_selected_audio_track` body Z.19-46 with:

```python
    def _get_selected_audio_track(self):
        """B-293: Checkbox-first, Maus-Selection-Fallback. Symmetrisch zu Video-Helper."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession

        view = self.window.audio_pool_table
        model = view.model()

        # 1) Checkbox-Selection (Multi-Select via "Alle"-Button oder einzelne Haken).
        audio_id = None
        if hasattr(model, "get_checked_ids"):
            checked = list(model.get_checked_ids() or [])
            if checked:
                try:
                    audio_id = int(checked[0])
                except (ValueError, TypeError):
                    audio_id = None

        # 2) Fallback: Maus-Selection.
        if audio_id is None:
            indexes = view.selectionModel().selectedRows()
            if indexes:
                val = model.index(indexes[0].row(), 1).data()
                if val and str(val).isdigit():
                    audio_id = int(val)

        if audio_id is None:
            self.window.console_text.append(
                "[Warnung] Kein Audio-Track ausgewaehlt (weder Checkbox noch Maus-Selection)."
            )
            return None

        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                self.window.console_text.append("[Warnung] Audio-Track nicht in DB gefunden.")
                return None
            return (track.id, track.file_path, track.title or "Unbekannt", track.bpm)
```

### Task A.4 — Implementation Plural-Variante

- [ ] Same file, add directly after `_get_selected_audio_track`:

```python
    def _get_selected_audio_tracks(self) -> list[int]:
        """B-293 Batch-Variante. Liefert Track-IDs aller selektierten Audios.
        Checkbox first, Maus-Selection fallback."""
        view = self.window.audio_pool_table
        model = view.model()

        if hasattr(model, "get_checked_ids"):
            checked = list(model.get_checked_ids() or [])
            if checked:
                return [int(x) for x in checked if str(x).isdigit()]

        indexes = view.selectionModel().selectedRows()
        ids: list[int] = []
        for idx in indexes:
            val = model.index(idx.row(), 1).data()
            if val and str(val).isdigit():
                ids.append(int(val))
        return ids
```

### Task A.5 — Verify

```text
<PY> tests/ui/test_audio_checkbox_wiring.py -v --tb=short
```

Expected: 3/3 PASS.

### Task A.6 — Vault + Commit

- [ ] B-293 frontmatter `status: code-fix-pending-live-verification`, `updated: 2026-05-11 phase-A`.
- [ ] log.md phase-A-Eintrag.
- [ ] Commit:

```bash
git add tests/ui/test_audio_checkbox_wiring.py ui/controllers/audio_analysis.py
git commit -m "$(cat <<'COMMITEOF'
fix(audio): checkbox-first selection helpers (B-293)

_get_selected_audio_track nutzte nur selectionModel — Checkbox +
Alle-Button im Audio-Pool wurden komplett ignoriert. Symmetrisch
zum Video-Helper (R-13) umgebaut: get_checked_ids first, Maus-
Selection fallback.

Plus neue Plural-Variante _get_selected_audio_tracks fuer Batch-
Funktionen (sequenzielle Komplett-Analyse, Stems-Batch).

Tests test_audio_checkbox_wiring 3/3 gruen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

### A — Definition of Done

- [ ] Single + Plural Helper checkbox-first.
- [ ] Tests grün.
- [ ] B-293 auf `code-fix-pending-live-verification`.

---

## Phase B — Audio-Slots umstellen (B-293)

**Files:** `ui/controllers/audio_analysis.py` (Konsumenten der Helpers), `ui/controllers/stems.py`.

### Task B.1 — Inventur

- [ ] Grep alle `_get_selected_audio_track()`-Aufrufe in audio_analysis.py + stems.py. Erwartung: ~10 Stellen.
- [ ] Pro Aufruf: ist Single oder Batch sinnvoll? (Single-Funktionen `_detect_key`, `_analyze_lufs` etc. bleiben single. Sequential `_analyze_all_sequential` und Stems-Batch sollten Plural.)

### Task B.2 — Sequential Audio Analyse auf Plural umstellen

- [ ] Read `_analyze_all_sequential` (audio_analysis.py Z.357+) — wie iteriert es aktuell? Vermutlich über Pool-Model-rowCount() (alle Tracks unabhängig von Selection).
- [ ] Wenn ja: nur dann auf Plural umstellen wenn User-Erwartung "nur ausgewählte". Falls Plural-Liste leer ist, fallback auf "alle in Pool" mit Konsolen-Hinweis "Keine Checkbox aktiv — analysiere alle Tracks im Pool".

Konkreter Code-Diff:

```python
    def _analyze_all_sequential(self):
        # B-293: Batch-Auswahl checkbox-first, fallback "alle im Pool".
        track_ids = self._get_selected_audio_tracks()
        if not track_ids:
            # Fallback: ALL tracks in pool
            model = self.window.audio_pool_table.model()
            for row in range(model.rowCount()):
                val = model.index(row, 1).data()
                if val and str(val).isdigit():
                    track_ids.append(int(val))
            if track_ids:
                self.window.console_text.append(
                    f"[Komplett-Analyse] Keine Checkbox aktiv — analysiere alle {len(track_ids)} Tracks im Pool."
                )
        if not track_ids:
            self.window.console_text.append("[Komplett-Analyse] Keine Audio-Tracks im Pool.")
            return
        # ... rest wie bisher, aber iteriert über track_ids
```

(Bestehende Logik adaptieren — der Plan bleibt bewusst flexibel, weil Z.357+ noch nicht gelesen ist. Pre-flight Read first, dann genauer Edit.)

### Task B.3 — Stems-Batch (R-9 Decision)

- [ ] Lesen: `stems._start_stem_separation` Z.78-105. Heute Single-Track. User-Erwartung: bei Checkbox "Alle" alle Audios Demucs durchlaufen?
- [ ] **R-10 Stop-and-Ask** an User: Stems sequenziell für alle gecheckten Tracks ODER nur erster gecheckter? Demucs ist 5+ min pro Track — Batch könnte 100 min dauern bei 20 Tracks.

(Im Plan: bis User entscheidet, Stems bleibt Single — nimmt jetzt aber `_get_selected_audio_tracks()[0]` falls Checkbox da, sonst Single-Helper-Fallback.)

### Task B.4 — Failing test

- [ ] Append to `tests/ui/test_audio_checkbox_wiring.py`:

```python
def test_b293_sequential_analyse_uses_plural_helper():
    """B-293: _analyze_all_sequential ruft _get_selected_audio_tracks."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_analyze_all_sequential")
    assert "_get_selected_audio_tracks" in body, (
        "B-293: _analyze_all_sequential ignoriert Plural-Checkbox-Helper."
    )
```

- [ ] Run, expect FAIL.

### Task B.5 — Implementation

- [ ] Edit `_analyze_all_sequential` per Task B.2 Skizze (echte Anpassung nach Pre-Flight).
- [ ] Stems-Calls per Task B.3 Decision.

### Task B.6 — Verify

```text
<PY> tests/ui/test_audio_checkbox_wiring.py -v --tb=short
```

Expected: 4/4 PASS.

### Task B.7 — Vault + Commit

- [ ] log.md phase-B.
- [ ] Commit:

```bash
git add tests/ui/test_audio_checkbox_wiring.py ui/controllers/audio_analysis.py ui/controllers/stems.py
git commit -m "$(cat <<'COMMITEOF'
fix(audio): wire sequential + stems to checkbox-aware helpers (B-293)

_analyze_all_sequential nutzt jetzt _get_selected_audio_tracks
(Plural), fallback "alle Tracks im Pool" wenn Checkbox leer.
Stems verwenden weiter Single-Helper (Batch-Decision deferred —
Demucs ist 5+min pro Track; User-Frage pending).

Tests test_audio_checkbox_wiring 4/4 gruen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

### B — Definition of Done

- [ ] Sequential nutzt Plural-Helper.
- [ ] Stems-Batch-Frage geklärt oder dokumentiert.
- [ ] Tests grün.

---

## Phase C — SCHNITT Empty-State Recovery (B-294)

**Files:** `ui/controllers/edit_workspace.py`, `tests/ui/test_schnitt_empty_state_preset_runs_pipeline.py` (new).

### Task C.1 — Pre-Flight

- [ ] Read `ui/controllers/edit_workspace.py` Z.209-274 (`_auto_edit_to_beat`) — wie genau wird audio_combo gelesen?
- [ ] Read Z.700+ — der Phase-A Adapter `_on_schnitt_auto_edit_request`.
- [ ] Read `media_table_controller._refresh_director_combos` — befüllt der die Combos automatisch beim Project-Open? Grep.

### Task C.2 — Failing test

- [ ] Create `tests/ui/test_schnitt_empty_state_preset_runs_pipeline.py`:

```python
"""B-294: SCHNITT Empty-State Preset-Klick muss Pipeline starten, nicht silent return."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from ui.controllers.edit_workspace import EditWorkspaceController


def test_b294_ensure_combos_filled_helper_exists():
    """B-294: Helper für Auto-Fill der Combos aus Project-DB muss existieren."""
    assert hasattr(EditWorkspaceController, "_ensure_combos_filled_from_project")


def test_b294_adapter_calls_ensure_combos(qapp, project, audio_track, video_clip, test_engine):
    """B-294: _on_schnitt_auto_edit_request füllt leere Combos automatisch."""
    # Wenn Combos leer sind und Project hat Audio + Video, Adapter fuellt sie.
    # Test braucht echtes PBWindow → integration-style. Falls zu schwer:
    # Source-inspection dass _ensure_combos_filled_from_project gerufen wird.
    import inspect
    src = inspect.getsource(EditWorkspaceController._on_schnitt_auto_edit_request)
    assert "_ensure_combos_filled_from_project" in src, (
        "B-294: Adapter ruft Auto-Fill-Helper nicht — silent return Risiko bleibt."
    )
```

- [ ] Run, expect FAIL.

### Task C.3 — Implementation Helper

- [ ] Edit `ui/controllers/edit_workspace.py`. Add new method (place near top of class, after `_on_audio_combo_changed`):

```python
    def _ensure_combos_filled_from_project(self) -> bool:
        """B-294: Wenn audio_combo/video_combo leer, erstes Audio + erstes Video
        aus Project-DB ziehen. Returnt True wenn beide befuellt sind."""
        from database import engine, AudioTrack, VideoClip, get_active_project_id
        from sqlalchemy.orm import Session as DBSession

        pid = get_active_project_id()
        if pid is None:
            return False
        try:
            with DBSession(engine) as s:
                if self.window.audio_combo.currentData() is None:
                    first_audio = (
                        s.query(AudioTrack)
                        .filter_by(project_id=pid)
                        .filter(AudioTrack.deleted_at.is_(None))
                        .order_by(AudioTrack.id)
                        .first()
                    )
                    if first_audio is not None:
                        idx = self.window.audio_combo.findData(first_audio.id)
                        if idx >= 0:
                            self.window.audio_combo.setCurrentIndex(idx)
                if self.window.video_combo.currentData() is None:
                    first_video = (
                        s.query(VideoClip)
                        .filter_by(project_id=pid)
                        .filter(VideoClip.deleted_at.is_(None))
                        .order_by(VideoClip.id)
                        .first()
                    )
                    if first_video is not None:
                        idx = self.window.video_combo.findData(first_video.id)
                        if idx >= 0:
                            self.window.video_combo.setCurrentIndex(idx)
        except Exception as exc:
            logger.warning("B-294 _ensure_combos_filled_from_project failed: %s", exc)
            return False
        return (
            self.window.audio_combo.currentData() is not None
            and self.window.video_combo.currentData() is not None
        )
```

### Task C.4 — Implementation Adapter-Pre-Flight (R-14)

- [ ] Edit existing `_on_schnitt_auto_edit_request` (and analog `_on_schnitt_regenerate_request`) to call the helper:

```python
    def _on_schnitt_auto_edit_request(self, profile) -> None:
        # B-294/R-14: kein silent return — wenn Combos leer, Auto-Fill aus DB,
        # sonst klare User-Nachricht.
        if not self._ensure_combos_filled_from_project():
            self.window.console_text.append(
                "[SCHNITT] Auto-Edit braucht mind. 1 Audio + 1 Video im Projekt. "
                "Importiere Material in MATERIAL & ANALYSE."
            )
            try:
                ws = getattr(self.window, "_schnitt_ws", None)
                if ws is not None:
                    ws.refresh_state_from_db()
            except Exception:
                pass
            return
        self._auto_edit_to_beat()

    def _on_schnitt_regenerate_request(self, profile) -> None:
        if not self._ensure_combos_filled_from_project():
            self.window.console_text.append(
                "[SCHNITT] Re-Generate braucht mind. 1 Audio + 1 Video."
            )
            try:
                ws = getattr(self.window, "_schnitt_ws", None)
                if ws is not None:
                    ws.refresh_state_from_db()
            except Exception:
                pass
            return
        self._generate_timeline_impl()
```

### Task C.5 — Verify

```text
<PY> tests/ui/test_schnitt_empty_state_preset_runs_pipeline.py tests/ui/test_schnitt_integration_boot.py tests/ui/test_pipeline_progress_wiring.py -v --tb=short
```

Expected: alle grün.

### Task C.6 — Vault + Commit

- [ ] B-294 frontmatter update.
- [ ] log.md phase-C.
- [ ] Commit:

```bash
git add tests/ui/test_schnitt_empty_state_preset_runs_pipeline.py ui/controllers/edit_workspace.py
git commit -m "$(cat <<'COMMITEOF'
fix(schnitt): empty-state preset auto-fills combos (B-294)

Empty-State Preset-Klick endete silent in _auto_edit_to_beat weil
audio_combo/video_combo unsichtbar im Empty-State. Henne-Ei-Bug:
Editor-State erwartete bereits Timeline.

_ensure_combos_filled_from_project zieht erstes Audio + erstes
Video aus Project-DB. Adapter-Slots _on_schnitt_auto_edit_request
und _on_schnitt_regenerate_request rufen Helper vor Worker-Start
(R-14: kein silent return; klare Konsolen-Message wenn Material
fehlt).

Tests test_schnitt_empty_state_preset_runs_pipeline gruen,
SCHNITT-Sweep unverändert gruen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

### C — Definition of Done

- [ ] Helper existiert.
- [ ] Adapter rufen Helper vor `_auto_edit_to_beat`/`_generate_timeline_impl`.
- [ ] R-14-Pflicht erfüllt: kein silent return.

---

## Phase D — Cutliste-Widget (B-295)

**Files:** `ui/widgets/cut_list_panel.py` (new), `ui/workspaces/schnitt/tab_schnitt.py`, `services/timeline_service.py`, `tests/ui/test_cut_list_panel.py` (new).

### Task D.1 — Pre-Flight

- [ ] Read `ui/workspaces/schnitt/tab_schnitt.py` voll — wie ist Layout? Wo Inspector?
- [ ] Read `services/timeline_service.py` — existiert eine API die alle Cuts/Segments für ein Projekt liefert?
- [ ] Read `database/models.py` — TimelineEntry/Scene/CutPoint Schema.

### Task D.2 — Service-Helper

- [ ] Edit `services/timeline_service.py`. Append:

```python
def get_cut_list(project_id: int) -> list[dict]:
    """B-295: Liefert Cutliste eines Projekts als sortierte Liste von dicts.

    Format:
        [
            {"index": 0, "time": 0.0, "duration": 2.5, "source": "beat",
             "strength": 0.9, "locked": False, "clip_id": 17, "title": "clip.mp4"},
            ...
        ]
    """
    from database import nullpool_session, TimelineEntry, VideoClip
    rows: list[dict] = []
    with nullpool_session() as s:
        entries = (
            s.query(TimelineEntry)
            .filter_by(project_id=project_id, track="video")
            .order_by(TimelineEntry.start)
            .all()
        )
        for idx, e in enumerate(entries):
            clip = s.get(VideoClip, e.media_id) if e.media_id else None
            rows.append({
                "index": idx,
                "time": float(e.start or 0.0),
                "duration": float((e.end or 0.0) - (e.start or 0.0)),
                "source": getattr(e, "cut_source", "") or "",
                "strength": float(getattr(e, "cut_strength", 0.0) or 0.0),
                "locked": bool(getattr(e, "locked", False)),
                "clip_id": e.media_id,
                "title": (clip.title if clip else f"Clip {e.media_id}") or "Unbekannt",
            })
    return rows
```

(Falls TimelineEntry-Felder anders heißen: Pre-Flight-Read anpassen. R-9.)

### Task D.3 — Widget

- [ ] Create `ui/widgets/cut_list_panel.py`:

```python
"""CutListPanel — textuelle Cutliste fuer das SCHNITT-Sub-Tab (B-295)."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton,
)
from PySide6.QtGui import QBrush, QColor

logger = logging.getLogger(__name__)

_SOURCE_COLORS = {
    "beat": QColor(74, 222, 128),
    "scene": QColor(96, 165, 250),
    "energy": QColor(251, 191, 36),
    "drum": QColor(248, 113, 113),
    "transition": QColor(167, 139, 250),
    "drop": QColor(244, 114, 182),
    "anchor": QColor(212, 164, 74),
}


class CutListPanel(QWidget):
    """Zeigt Cutliste eines Projekts als sortierte Tabelle.

    Spalten: # / Zeit / Dauer / Quelle / Stärke / Lock / Clip.
    Klick auf Row → emittiert cut_selected(time:float).
    """

    cut_selected = Signal(float)
    cut_lock_toggled = Signal(int, bool)  # entry_index, new_lock_state

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Cutliste")
        title.setStyleSheet(
            "color: #d4a44a; font-weight: 700; font-size: 12px; "
            "letter-spacing: 1.5px; text-transform: uppercase;"
        )
        header.addWidget(title)
        header.addStretch()
        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.setFixedHeight(22)
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            ["#", "Zeit", "Dauer", "Quelle", "Stärke", "Lock", "Clip"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

        self.info_label = QLabel("Noch keine Timeline.")
        self.info_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        layout.addWidget(self.info_label)

    def set_project(self, project_id: Optional[int]) -> None:
        """B-295: Public-API."""
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            self._render_empty("Kein Projekt aktiv.")
            return
        try:
            from services.timeline_service import get_cut_list
            cuts = get_cut_list(self._project_id)
        except Exception as exc:
            logger.warning("CutListPanel.refresh failed: %s", exc)
            self._render_empty(f"Fehler: {exc}")
            return
        self._render_cuts(cuts)

    def _render_empty(self, msg: str) -> None:
        self.table.setRowCount(0)
        self.info_label.setText(msg)

    def _render_cuts(self, cuts: list[dict]) -> None:
        self.table.setRowCount(len(cuts))
        for row, cut in enumerate(cuts):
            self.table.setItem(row, 0, QTableWidgetItem(str(cut["index"])))
            self.table.setItem(row, 1, QTableWidgetItem(f"{cut['time']:.2f}s"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{cut['duration']:.2f}s"))
            src_item = QTableWidgetItem(cut.get("source", ""))
            color = _SOURCE_COLORS.get(cut.get("source", ""), None)
            if color is not None:
                src_item.setForeground(QBrush(color))
            self.table.setItem(row, 3, src_item)
            self.table.setItem(row, 4, QTableWidgetItem(f"{cut.get('strength', 0.0):.2f}"))
            lock_item = QTableWidgetItem("🔒" if cut.get("locked") else "")
            self.table.setItem(row, 5, lock_item)
            self.table.setItem(row, 6, QTableWidgetItem(cut.get("title", "")))
        self.info_label.setText(f"{len(cuts)} Cuts.")

    def _on_cell_clicked(self, row: int, column: int) -> None:
        time_item = self.table.item(row, 1)
        if time_item is None:
            return
        try:
            t = float(time_item.text().rstrip("s"))
            self.cut_selected.emit(t)
        except ValueError:
            pass

    def rendered_row_count(self) -> int:
        """Testaffordance."""
        return self.table.rowCount()
```

### Task D.4 — Failing test

- [ ] Create `tests/ui/test_cut_list_panel.py`:

```python
"""B-295: CutListPanel renders cuts from get_cut_list."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from ui.widgets.cut_list_panel import CutListPanel


def test_b295_cut_list_panel_renders_empty(qapp):
    panel = CutListPanel()
    panel.set_project(None)
    assert panel.rendered_row_count() == 0


def test_b295_cut_list_panel_renders_cuts(qapp, monkeypatch):
    import services.timeline_service as ts

    def fake_get_cut_list(pid):
        return [
            {"index": 0, "time": 0.0, "duration": 2.5, "source": "beat",
             "strength": 0.9, "locked": False, "clip_id": 1, "title": "clip_a"},
            {"index": 1, "time": 2.5, "duration": 1.5, "source": "anchor",
             "strength": 0.7, "locked": True, "clip_id": 2, "title": "clip_b"},
        ]
    monkeypatch.setattr(ts, "get_cut_list", fake_get_cut_list)

    panel = CutListPanel()
    panel.set_project(42)
    assert panel.rendered_row_count() == 2
```

- [ ] Run, expect FAIL (Widget existiert noch nicht / Helper existiert noch nicht).

### Task D.5 — Integration in `tab_schnitt.py`

- [ ] Read existing `tab_schnitt.py` first (Pre-Flight). Layout: vermutlich VBox mit Preview oben, Timeline unten.
- [ ] Add CutListPanel als Drittes Element unter Timeline ODER rechts daneben (Decision pending). Default: unter Timeline mit Splitter:

```python
        from ui.widgets.cut_list_panel import CutListPanel
        self.cut_list_panel = CutListPanel(self)
        # Layout-Erweiterung: Splitter mit Timeline oben, CutListPanel unten.
        # ... (genau nach Pre-Flight)
```

### Task D.6 — Refresh-Bridge

- [ ] CutListPanel.refresh muss bei jedem Auto-Edit-Done feuern. In `edit_workspace._on_auto_edit_finished` ergänzen:

```python
        try:
            tab_schnitt = self.window._schnitt_ws.editor_view.tab_schnitt
            if hasattr(tab_schnitt, "cut_list_panel"):
                tab_schnitt.cut_list_panel.set_project(get_active_project_id())
        except Exception as exc:
            logger.debug("cut_list_panel refresh failed: %s", exc)
```

Plus: bei `_on_cuts_done` (Re-Generate-Worker fertig) dieselbe Bridge.

Plus: bei Tab-Wechsel zu SCHNITT (in `workspace_setup._on_workspace_changed(2)`) initiales refresh.

### Task D.7 — Cut-Click → Timeline-Playhead

- [ ] In `tab_schnitt.py`: `self.cut_list_panel.cut_selected.connect(self.timeline_view.set_playhead_time)`.
- [ ] Test ergänzen für Signal-Roundtrip.

### Task D.8 — Verify + Commit

```text
<PY> tests/ui/test_cut_list_panel.py tests/ui/test_schnitt_workspace_states.py -v --tb=short
```

```bash
git add ui/widgets/cut_list_panel.py services/timeline_service.py ui/workspaces/schnitt/tab_schnitt.py ui/controllers/edit_workspace.py tests/ui/test_cut_list_panel.py
git commit -m "$(cat <<'COMMITEOF'
feat(schnitt): CutListPanel — textuelle Cutliste (B-295)

Cuts sind in der InteractiveTimeline nur visuell. Neu:
CutListPanel rendert Cutliste als Tabelle mit Spalten
#/Zeit/Dauer/Quelle/Staerke/Lock/Clip.

- ui/widgets/cut_list_panel.py: Widget (~150 LOC).
- services/timeline_service.py: get_cut_list(project_id).
- tab_schnitt einhaengen unter Timeline (Splitter).
- Refresh-Bridge an Auto-Edit-Done und Re-Generate-Done.
- Cut-Click -> Timeline-Playhead.

Tests test_cut_list_panel 2/2 gruen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

### D — Definition of Done

- [ ] CutListPanel rendert nach Auto-Edit.
- [ ] Cut-Click springt Playhead.
- [ ] Lock-Status sichtbar.

---

## Phase E — Workflow-Struktur MEDIA-Layout + Cockpit-Navigation (B-296)

**Files:** `ui/workspaces/media_workspace.py`, `ui/controllers/workspace_setup.py`, `ui/workspaces/workflow_pages.py`, `tests/ui/test_media_workspace_layout.py` (new).

### Task E.1 — Pre-Flight

- [ ] Read `ui/workspaces/media_workspace.py` voll (Layout, Button-Erstellung).
- [ ] Identify: gibt es bereits `QGroupBox` oder `QFrame` für visuelle Sektionen? Falls ja: nur Labels anpassen. Falls nein: 3 `QGroupBox` einführen.
- [ ] Read `workspace_setup.py` Z.270-280: `_start_video_pipeline` Doppel-Connects.

### Task E.2 — Doppel-Buttons aufräumen (R-15)

Decision (R-10 Stop-and-Ask falls unklar):
- Option A: `btn_motion_analysis` + `btn_siglip_embeddings` ENTFERNEN (Vorhanden in `_media_ws` aus historischen Gründen).
- Option B: Buttons behalten, visuell als "Sub-Step" stylen + Tooltip "Wird vom Pipeline-Button mit erledigt".

Empfehlung: Option A — Aliase entfernen, einen klaren Pipeline-Button behalten.

Code-Change in `media_workspace.py`: btn_motion_analysis + btn_siglip_embeddings nicht mehr ins Layout aufnehmen. In `workspace_setup.py`: die zwei `if hasattr(...).clicked.connect(...)`-Blocks (Z.277-280) entfernen.

### Task E.3 — Sub-Sektionen

Layout MEDIA Video-Tab:

```
[Banner: "Schritt 2: Material analysieren"]
┌────────────────────────────────────────┐
│ 1. IMPORT                              │
│  [Video importieren] [Folder] [Clear]  │
└────────────────────────────────────────┘
┌────────────────────────────────────────┐
│ 2. ANALYSE                             │
│  [Video-Pipeline (Szenen + KI)]  ⬅ Primär
│  Optional: Einzelschritte               │
└────────────────────────────────────────┘
┌────────────────────────────────────────┐
│ 3. STANDARDISIERUNG                    │
│  [Standardize all]                     │
└────────────────────────────────────────┘
```

Layout MEDIA Audio-Tab: analog.

### Task E.4 — Cockpit-Card-Klick → Navigation

- [ ] Read `ui/workspaces/workflow_pages.py::ProjectDashboard`. Welches Signal hat eine Card? `action_requested(str)`-Signal (laut bestehendem Code) ist da.
- [ ] Empfehlung: Cards bekommen einen klickbaren Bereich. Bei Klick → `nav_bar.set_workspace(N)` + optional Scroll/Highlight des Sub-Bereichs.

In `workspace_setup._handle_cockpit_action`: existiert schon. Cards müssen nur `action_requested` auf Klick emittieren — falls noch nicht.

### Task E.5 — Failing test

- [ ] `tests/ui/test_media_workspace_layout.py`:

```python
"""B-296: MEDIA-Workspace hat Sub-Sektionen + Doppel-Buttons entfernt."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")

from ui.workspaces.media_workspace import MediaWorkspace


def test_b296_no_motion_analysis_button(qapp):
    ws = MediaWorkspace()
    assert not hasattr(ws, "btn_motion_analysis"), (
        "B-296/R-15: btn_motion_analysis ist Alias auf _start_video_pipeline — sollte weg sein."
    )


def test_b296_no_siglip_embeddings_button(qapp):
    ws = MediaWorkspace()
    assert not hasattr(ws, "btn_siglip_embeddings"), (
        "B-296/R-15: btn_siglip_embeddings ist Alias — sollte weg sein."
    )


def test_b296_video_pipeline_button_remains(qapp):
    ws = MediaWorkspace()
    assert hasattr(ws, "btn_video_pipeline"), (
        "B-296: Primary-Pipeline-Button bleibt."
    )
```

- [ ] Run, expect FAIL.

### Task E.6 — Implementation

- [ ] media_workspace.py Edits per E.2 + E.3.
- [ ] workspace_setup.py Edits per E.2 (Doppel-Connects raus).
- [ ] workflow_pages.py Edits per E.4.

### Task E.7 — Verify + Commit

```text
<PY> tests/ui/test_media_workspace_layout.py tests/ui/test_workspaces_smoke.py -v --tb=short
```

```bash
git add tests/ui/test_media_workspace_layout.py ui/workspaces/media_workspace.py ui/controllers/workspace_setup.py ui/workspaces/workflow_pages.py
git commit -m "$(cat <<'COMMITEOF'
fix(ui): MEDIA sub-sections + remove duplicate alias buttons (B-296)

User-Live-Test 2026-05-10: 3 Buttons (btn_motion_analysis,
btn_siglip_embeddings, btn_video_pipeline) auf demselben Handler
verwirren User. Plus keine sichtbare Step-Reihenfolge.

- Aliase btn_motion_analysis + btn_siglip_embeddings entfernt
  (R-15: Doppel-Aliase-Verbot).
- MEDIA-Workspace in 3 Sub-Sektionen 1. Import / 2. Analyse
  / 3. Standardisierung via QGroupBox.
- ProjectDashboard-Cards: action_requested triggert
  _handle_cockpit_action -> nav_bar.set_workspace fuer Tab-Sprung.

Tests test_media_workspace_layout 3/3 gruen, workspaces_smoke
ohne Regression.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

### E — Definition of Done

- [ ] Aliase entfernt.
- [ ] 3 Sub-Sektionen visuell sichtbar.
- [ ] Cockpit-Card-Klick navigiert.

---

## Phase F — Onboarding-Banner (B-296)

**Files:** `ui/widgets/onboarding_banner.py` (new), `ui/workspaces/media_workspace.py`, `tests/ui/test_onboarding_banner.py` (new).

### Task F.1 — Widget

```python
"""OnboardingBanner — schmaler Hinweis-Banner oben in einem Workspace.

Dismissable, persistiert pro Projekt via QSettings (Key:
window/onboarding/<workspace_id>/<step_id>).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame


class OnboardingBanner(QFrame):
    dismissed = Signal()

    def __init__(self, banner_id: str, message: str, parent=None):
        super().__init__(parent)
        self._banner_id = banner_id
        self.setObjectName("onboarding_banner")
        self.setStyleSheet(
            "QFrame#onboarding_banner { background: rgba(212,164,74,0.15); "
            "border: 1px solid #d4a44a; border-radius: 3px; }"
        )
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        self.lbl = QLabel(message)
        self.lbl.setStyleSheet("color: #f0c866; font-size: 11px; font-weight: 500;")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl, stretch=1)
        self.btn_dismiss = QPushButton("Verstanden")
        self.btn_dismiss.setFixedHeight(22)
        self.btn_dismiss.setStyleSheet(
            "QPushButton { background: rgba(212,164,74,0.3); border: 1px solid #d4a44a; "
            "color: #f0c866; padding: 2px 10px; font-size: 10px; }"
        )
        self.btn_dismiss.clicked.connect(self._on_dismiss)
        lay.addWidget(self.btn_dismiss)
        self._restore_state()

    def set_message(self, message: str) -> None:
        self.lbl.setText(message)

    def _on_dismiss(self) -> None:
        s = QSettings("PBStudio", "PBStudioApp")
        s.setValue(f"window/onboarding/{self._banner_id}", True)
        self.hide()
        self.dismissed.emit()

    def _restore_state(self) -> None:
        s = QSettings("PBStudio", "PBStudioApp")
        if s.value(f"window/onboarding/{self._banner_id}", False, type=bool):
            self.hide()
```

### F.2 — Test + Einhängen + Commit

(Test prüft default-visible, dismiss-hidden, persistence-key.)

Einhängen oben in `media_workspace.py` mit kontextueller Message:
- Audio-Tab: "Schritt 2a: Audio analysieren — wähle Tracks oder 'Alle' und klicke 'Komplett-Analyse'."
- Video-Tab: "Schritt 2b: Video analysieren — 'Video-Pipeline' macht alle 9 Schritte automatisch."

Commit-Subject: `feat(ui): onboarding banner per workspace (B-296)`.

---

## Phase G — Smoke + Audit-Greps

**Files:** `tests/ui/test_checkbox_workflow_smoke.py` (new), `scripts/phase_h_workflow_smoke.py` (new).

### G.1 — Source-Inspection

```python
def test_audit_reproduction_r13_helper_symmetry():
    """R-13: Audio-Helper haben get_checked_ids first."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_track")
    assert "get_checked_ids" in body

def test_audit_reproduction_r14_no_silent_return_in_adapter():
    """R-14: SchnittController-Adapter ruft _ensure_combos_filled_from_project."""
    body = _slot_body("ui/controllers/edit_workspace.py", "_on_schnitt_auto_edit_request")
    assert "_ensure_combos_filled_from_project" in body

def test_audit_reproduction_r15_no_duplicate_alias_connect():
    """R-15: btn_motion_analysis/btn_siglip_embeddings NICHT mehr in workspace_setup verdrahtet."""
    src = (REPO / "ui/controllers/workspace_setup.py").read_text(encoding="utf-8")
    assert "btn_motion_analysis.clicked.connect" not in src
    assert "btn_siglip_embeddings.clicked.connect" not in src
```

### G.2 — Live-Smoke

`scripts/phase_h_workflow_smoke.py`: PBWindow hochfahren, prüfen:
- `window._media_ws.btn_motion_analysis` darf nicht existieren.
- `window.audio_analysis._get_selected_audio_tracks` ist callable.
- `window.edit_workspace._ensure_combos_filled_from_project` ist callable.
- `window._schnitt_ws.editor_view.tab_schnitt.cut_list_panel` ist instance von CutListPanel.
- OnboardingBanner ist im MediaWorkspace findChild zu finden.

`os._exit(rc)` analog Phase-E des Vorgängerplans.

---

## Phase H — User-Live-Verify (10 Punkte)

(Siehe README.md "Globaler Erfolgs-Test".)

---

## Self-Review

**Spec coverage:**
- B-293 → Phase A + B ✓
- B-294 → Phase C ✓
- B-295 → Phase D ✓
- B-296 → Phase E + F ✓

**Placeholder scan:** keine TBD/TODO. Pre-Flight-R-9-Reads sind in Tasks dokumentiert.

**Type consistency:** `_get_selected_audio_tracks() -> list[int]`. `_ensure_combos_filled_from_project() -> bool`. `get_cut_list(project_id) -> list[dict]`. `CutListPanel.set_project(project_id)`. `cut_selected = Signal(float)`. Konsistent über Phasen.

---

## Plan-Anker

- Regelwerk: [README.md](./README.md) R-1..R-15.
- Bug-Files: `wiki/bugs/B-293..B-296*.md`.
- Vorgänger: `2026-05-10-pipeline-progress-wiring-fix/`.
- Conda-Env: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`.
- Test-Datensatz: Solo_Natur + Crusty Progressive Psy Set2.mp3.

---

## Freigabe

Plan-Status: **draft, awaiting user approval**.

Agent rührt keinen Code an bis "start Phase A" / "Plan freigegeben".

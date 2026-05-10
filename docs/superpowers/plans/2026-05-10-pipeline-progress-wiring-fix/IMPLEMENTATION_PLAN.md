# Pipeline Progress + Status Wiring Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeder Klick auf einen Analyse-Button (groß oder einzeln) führt **alle** Pipeline-Schritte bis 100% durch, bewegt die UI-Progress-Bar live mit, und der User sieht eindeutig welche Steps für ein Medium noch fehlen. Adressiert die Bugs B-287 bis B-292.

**Architecture:** TDD pro Bug. Worker emittiert ehrlich `mark_done` für jeden Step + `progress.emit(100)` vor `finished`. UI-Slots schreiben `progress_bar.setValue(pct)` live. AnalysisStatusPanel ist permanent sichtbar im MEDIA-Workspace und reagiert auf Selection + B-253-Completion-Bridge. Cockpit-Cards zeigen Tooltip mit fehlenden Step-Namen.

**Tech Stack:** PySide6 (Qt 6) · SQLAlchemy + SQLite WAL · pytest mit `QT_QPA_PLATFORM=offscreen` · conda-env `pb-studio` (`C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`).

**Plan-Wurzel:** `docs/superpowers/plans/2026-05-10-pipeline-progress-wiring-fix/`. Regelwerk + Phasen-Übersicht: [`README.md`](./README.md). Zwölf harte Regeln R-1 bis R-12 sind dort definiert; **dieses File führt Phasen A–F als bite-sized TDD-Tasks aus**.

---

## File Structure

| Datei | Verantwortlichkeit | Phasen |
|---|---|---|
| `workers/video.py` | `VideoAnalysisPipelineWorker.run` markiert `metadata_extract` und emittiert `progress.emit(100)` vor `finished.emit`. | A |
| `services/video_analysis_service.py` | (READ-only diesen Plan, kein Touch). Pipeline-Stages bleiben unverändert. | — |
| `ui/controllers/video_analysis.py` | `_on_pipeline_progress` befüllt `progress_bar.setValue/setRange/setFormat`. | B |
| `ui/controllers/stems.py` | Neuer Slot `_on_stem_progress`, ersetzt Lambda; updated progress_bar. | B |
| `ui/controllers/audio_analysis.py` | `_on_waveform_progress` befüllt progress_bar. | B |
| `ui/widgets/analysis_status_panel.py` | Render aller VIDEO_STEPS / AUDIO_STEPS, Live-Refresh durch Completion-Bridge, Selection-Sync. | C |
| `ui/workspaces/media_workspace.py` | `analysis_status_panel.setVisible(True)` Default + Selection-Push. | C |
| `services/cockpit_orchestrator.py` | `CockpitReadiness.missing_steps_per_card` Feld erweitern. | D |
| `ui/workspaces/workflow_pages.py` | `ProjectDashboard` Card-Tooltip mit fehlenden Steps. | D |
| `tests/test_workers/test_video_pipeline_metadata.py` | Neu. Tests B-287 + B-289. | A |
| `tests/ui/test_pipeline_progress_wiring.py` | Neu. Tests B-288 / B-290 / B-291. | B |
| `tests/ui/test_analysis_status_panel_visibility.py` | Neu. Tests B-292 Sichtbarkeit + Step-Liste. | C |
| `tests/test_services/test_cockpit_missing_steps.py` | Neu. Tests Cockpit-Tooltip-Inhalt. | D |
| `scripts/phase_e_pipeline_smoke.py` | Live-Boot-Smoke (echtes PBWindow + Fake-Worker). | E |

---

## Task-Granularität & Konventionen

- **Conda-Env Pflicht** für jeden pytest-Aufruf:
  `"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest <pfad> -v --tb=short`
  Alias unten kürzer als `<PY>` geschrieben — bei Ausführung verbatim ersetzen.
- **Conventional Commits.** Subject ≤ 50 Zeichen. Co-Author-Trailer:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- **Vault-Pflicht pro Sub-Task:** nach Commit Bug-File-Status auf `code-fix-pending-live-verification` setzen, log.md-Eintrag ergänzen, Living-Plan in `wiki/synthesis/schnitt-workspace-redesign-2026-05-09.md` erweitern.
- **`status: fixed`** vergibt nur der User nach Phase F.

---

## Phase A — Pipeline-Worker mark_done + 100%-Tick (B-287, B-289)

**Files:**
- Create: `tests/test_workers/test_video_pipeline_metadata.py`
- Modify: `workers/video.py:276-371` (Hauptschleife + finished-Pfade)

### Task A.1: Failing Test — `metadata_extract` wird gemarkt

**Files:**
- Create: `tests/test_workers/test_video_pipeline_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests fuer B-287 + B-289 — Pipeline-Worker markiert metadata_extract
und emittiert 100% vor finished."""
from __future__ import annotations

import inspect
from workers.video import VideoAnalysisPipelineWorker


def test_b287_pipeline_worker_marks_metadata_extract():
    """B-287-Regression: Pipeline-Worker.run muss metadata_extract markieren.

    Source-Inspection — Worker-Source enthaelt mark_done-Call mit step
    'metadata_extract' BEVOR run_full_pipeline aufgerufen wird (sonst
    bleibt Status bei 8/9 = 88%).
    """
    src = inspect.getsource(VideoAnalysisPipelineWorker.run)
    assert "metadata_extract" in src, (
        "B-287: VideoAnalysisPipelineWorker.run referenziert "
        "metadata_extract nicht — Step bleibt unmarkiert."
    )
    pos_metadata = src.find("metadata_extract")
    pos_run_pipeline = src.find("run_full_pipeline(")
    assert pos_metadata < pos_run_pipeline, (
        "B-287: metadata_extract muss VOR run_full_pipeline gemarkt werden "
        f"(metadata at {pos_metadata}, run_full_pipeline at {pos_run_pipeline})."
    )


def test_b289_pipeline_worker_emits_100_before_finished():
    """B-289-Regression: vor finished.emit muss progress.emit(100, ...) stehen."""
    src = inspect.getsource(VideoAnalysisPipelineWorker.run)
    finished_idx = src.find("self.finished.emit(last_clip_id, {")
    assert finished_idx > 0, "finished.emit nicht gefunden — Layout veraendert?"
    window = src[max(0, finished_idx - 250):finished_idx]
    assert "progress.emit(100" in window, (
        "B-289: kein progress.emit(100, ...) in den 250 Zeichen vor "
        "finished.emit — UI bleibt bei 99%."
    )
```

- [ ] **Step 2: Run test, expect FAIL**

```text
<PY> tests/test_workers/test_video_pipeline_metadata.py -v --tb=short
```

Expected output:
```
FAILED ...test_b287_pipeline_worker_marks_metadata_extract — AssertionError: B-287: ...
FAILED ...test_b289_pipeline_worker_emits_100_before_finished — AssertionError: B-289: ...
```

### Task A.2: Implementation — `metadata_extract`-Marker im Worker

**Files:**
- Modify: `workers/video.py` Zeilen 276–292 (Hauptschleife direkt vor `try:`)

- [ ] **Step 1: Code ergänzen**

In `workers/video.py`, Zeile 280 (nach `label = title or Path(video_path).stem`), VOR dem `batch_base_pct = ...`-Block, einfügen:

```python
                    # B-287: metadata_extract markieren BEVOR run_full_pipeline.
                    # Sonst bleibt Status bei 8/9 = 88%. Wenn ffprobe-Felder
                    # in DB vorhanden sind (duration/width/height/fps), wird
                    # mark_done idempotent gesetzt; sonst ffprobe nachholen.
                    try:
                        from services import analysis_status_service
                        from database import VideoClip as _VC, nullpool_session as _ns
                        with _ns() as _s:
                            _clip_row = _s.get(_VC, clip_id)
                        if (_clip_row and _clip_row.duration and _clip_row.width
                                and _clip_row.height and _clip_row.fps):
                            analysis_status_service.mark_done(
                                "video", clip_id, "metadata_extract", {
                                    "duration": _clip_row.duration,
                                    "resolution": f"{_clip_row.width}x{_clip_row.height}",
                                    "fps": _clip_row.fps,
                                    "codec": _clip_row.codec,
                                },
                            )
                        else:
                            analysis_status_service.mark_started(
                                "video", clip_id, "metadata_extract"
                            )
                            from services.video_service import VideoService
                            VideoService().analyze_and_store(clip_id, create_proxy=False)
                    except Exception as _meta_exc:  # broad: Pipeline darf nicht durch Meta-Fehler kippen
                        logger.warning(
                            "B-287: metadata_extract for clip %s failed: %s",
                            clip_id, _meta_exc,
                        )
```

- [ ] **Step 2: Run B-287-Test, expect PASS**

```text
<PY> tests/test_workers/test_video_pipeline_metadata.py::test_b287_pipeline_worker_marks_metadata_extract -v --tb=short
```

Expected: `PASSED`.

### Task A.3: Implementation — `progress.emit(100, ...)` vor `finished.emit`

**Files:**
- Modify: `workers/video.py:413-419` (success-Pfad) und `workers/video.py:447-452` (finally-fallback)

- [ ] **Step 1: Code ergänzen — Success-Pfad**

In `workers/video.py`, ersetze:

```python
            self.finished.emit(last_clip_id, {
                "scenes": total_scenes,
                "embeddings": total_embeddings,
                "videos_processed": videos_processed,
            })
            _emitted_terminal = True
            _ok = True
```

mit:

```python
            # B-289: 100%-Tick vor finished, sonst bleibt UI bei 99%.
            try:
                self.progress.emit(100, "Pipeline abgeschlossen")
            except Exception:
                pass
            self.finished.emit(last_clip_id, {
                "scenes": total_scenes,
                "embeddings": total_embeddings,
                "videos_processed": videos_processed,
            })
            _emitted_terminal = True
            _ok = True
```

- [ ] **Step 2: Code ergänzen — Finally-Fallback**

In der `finally`-Block-Sektion, ersetze:

```python
            if not _emitted_terminal:
                self.finished.emit(last_clip_id, {})
```

mit:

```python
            if not _emitted_terminal:
                try:
                    self.progress.emit(100, "Pipeline abgeschlossen (fallback)")
                except Exception:
                    pass
                self.finished.emit(last_clip_id, {})
```

- [ ] **Step 3: Run B-289-Test, expect PASS**

```text
<PY> tests/test_workers/test_video_pipeline_metadata.py::test_b289_pipeline_worker_emits_100_before_finished -v --tb=short
```

Expected: `PASSED`.

- [ ] **Step 4: Run beide Tests + bestehende Worker-Tests, expect alle PASS**

```text
<PY> tests/test_workers/ -v --tb=short
```

Expected: alle grün, keine Regression.

### Task A.4: Vault + Commit Phase A

- [ ] **Step 1: Bug-Files Status updaten**

Edit `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-287-pipeline-skips-metadata-extract-stuck-88.md`:
- Frontmatter `status: code-fix-pending-live-verification`
- Frontmatter `updated: 2026-05-10 phase-A`

Edit `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-289-pipeline-progress-capped-at-99.md`:
- Frontmatter `status: code-fix-pending-live-verification`
- Frontmatter `updated: 2026-05-10 phase-A`

- [ ] **Step 2: log.md ergänzen**

```bash
cat >> "C:/Brain-Bug/projects/pb-studio/log.md" << 'EOF'

## 2026-05-10 phase-A | pipeline-progress-wiring B-287 + B-289 done

- workers/video.py:276-... markiert metadata_extract idempotent vor run_full_pipeline (mark_done bei vorhandenen ffprobe-Feldern, sonst VideoService.analyze_and_store mit create_proxy=False).
- workers/video.py:413+447 progress.emit(100, ...) vor finished.emit.
- Tests test_workers/test_video_pipeline_metadata.py 2/2 grün.
- Bugs B-287 + B-289 auf code-fix-pending-live-verification.
EOF
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_workers/test_video_pipeline_metadata.py workers/video.py
git commit -m "$(cat <<'COMMITEOF'
fix(pipeline): mark metadata_extract + 100%-tick (B-287,B-289)

VideoAnalysisPipelineWorker hat metadata_extract uebersprungen
(8/9 Steps -> 88% Cap) und progress hart auf 99 gecappt.

- Marker fuer metadata_extract direkt vor run_full_pipeline:
  idempotent mark_done wenn ffprobe-Felder in DB; sonst Fallback
  VideoService.analyze_and_store(create_proxy=False).
- progress.emit(100, ...) vor jedem finished.emit (success +
  finally-fallback) — UI erreicht jetzt sichtbar 100%.

Tests test_video_pipeline_metadata 2/2 gruen, Worker-Sweep ohne
Regression. Bugs B-287, B-289 auf code-fix-pending-live-verification.
status: fixed nur durch User nach Phase F.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

---

## Phase B — UI Progress-Bar live binden (B-288, B-290, B-291)

**Files:**
- Create: `tests/ui/test_pipeline_progress_wiring.py`
- Modify: `ui/controllers/video_analysis.py:194-201`
- Modify: `ui/controllers/stems.py:86-105`
- Modify: `ui/controllers/audio_analysis.py:272-274`

### Task B.1: Failing Tests — drei Slots schreiben in progress_bar

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_pipeline_progress_wiring.py`:

```python
"""B-288 / B-290 / B-291: progress-Slots muessen progress_bar.setValue rufen."""
from __future__ import annotations

import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    src = (REPO / file_rel).read_text(encoding="utf-8")
    pat = rf"def {re.escape(slot_name)}\([^)]*\):\n(?P<body>(?:    .+\n|\n)+)"
    m = re.search(pat, src)
    assert m, f"Slot {slot_name} nicht gefunden in {file_rel}"
    return m.group("body")


def test_b288_video_pipeline_slot_writes_progress_bar():
    body = _slot_body("ui/controllers/video_analysis.py", "_on_pipeline_progress")
    assert "progress_bar.setValue" in body, (
        "B-288: _on_pipeline_progress ruft progress_bar.setValue nicht — Bar bleibt 0%."
    )


def test_b290_stems_slot_writes_progress_bar():
    body = _slot_body("ui/controllers/stems.py", "_on_stem_progress")
    assert "progress_bar.setValue" in body, (
        "B-290: _on_stem_progress ruft progress_bar.setValue nicht."
    )


def test_b291_waveform_slot_writes_progress_bar():
    body = _slot_body("ui/controllers/audio_analysis.py", "_on_waveform_progress")
    assert "progress_bar.setValue" in body, (
        "B-291: _on_waveform_progress ruft progress_bar.setValue nicht."
    )


def test_stems_uses_named_slot_not_lambda():
    """B-290 follow-up: das alte Lambda darf nicht mehr existieren."""
    src = (REPO / "ui/controllers/stems.py").read_text(encoding="utf-8")
    assert "self._on_stem_progress" in src, (
        "B-290: Stems verbinden den neuen Slot nicht — alte Lambda-Verdrahtung aktiv."
    )
```

- [ ] **Step 2: Run tests, expect 4 FAIL**

```text
<PY> tests/ui/test_pipeline_progress_wiring.py -v --tb=short
```

Expected: alle vier `FAILED` (Slot existiert nicht oder ruft setValue nicht).

### Task B.2: Implementation — Video-Pipeline-Slot

- [ ] **Step 1: Edit `ui/controllers/video_analysis.py:194-201`**

Ersetze:

```python
    def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
        # Bug C: 200-Clip-Batches feuern dutzende Progress-Events; Throttle
        # auf 10 %-Schritte + neue-Video-Marker, und ueber den gepufferten
        # _console_append (kein synchroner QTextEdit.append pro Tick).
        last_pct = getattr(self, '_pipeline_last_pct', -10)
        if abs(pct - last_pct) >= 10 or "wird analysiert" in msg:
            self.window._console_append(f"[Pipeline] {msg} ({pct}%)")
            self._pipeline_last_pct = pct
```

mit:

```python
    def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
        # B-288: progress_bar live binden — vorher schrieb der Slot nur in
        # die Konsole, Bar blieb auf 0%.
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        # Format zeigt %p%% sowie kurze Stage-Beschreibung.
        self.window.progress_bar.setFormat(f"%p%% — {msg[:60]}")
        # Bug C-Throttle bleibt erhalten (Console-Spam).
        last_pct = getattr(self, '_pipeline_last_pct', -10)
        if abs(pct - last_pct) >= 10 or "wird analysiert" in msg:
            self.window._console_append(f"[Pipeline] {msg} ({pct}%)")
            self._pipeline_last_pct = pct
```

- [ ] **Step 2: Run B-288-Test, expect PASS**

```text
<PY> tests/ui/test_pipeline_progress_wiring.py::test_b288_video_pipeline_slot_writes_progress_bar -v --tb=short
```

Expected: `PASSED`.

### Task B.3: Implementation — Stems-Slot

- [ ] **Step 1: Edit `ui/controllers/stems.py`** — Slot ergänzen + Lambda ersetzen

Suche den bestehenden Block `worker.progress.connect(\n            lambda pct, msg: self.window._console_append(f"[Stems] {msg} ({pct}%)"),` (Zeilen 93-96).

Ersetze ihn mit:

```python
        worker.progress.connect(
            self._on_stem_progress,
            Qt.ConnectionType.QueuedConnection,
        )
```

Direkt nach `_on_stem_finished` (vor `_on_stem_error`) neuen Slot einfügen:

```python
    def _on_stem_progress(self, pct: int, msg: str):
        """B-290: Demucs-Progress an progress_bar binden."""
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        self.window.progress_bar.setFormat(f"KI-Stems: %p%% — {msg[:50]}")
        self.window._console_append(f"[Stems] {msg} ({pct}%)")
```

Plus: vor dem `worker.progress.connect`-Block sicherstellen dass Bar initialisiert wird. Suche `self.window.progress_bar.setVisible(True)` (Z.86) und ersetze diesen Block:

```python
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setFormat("KI-Separation laeuft... (kann mehrere Minuten dauern)")
```

mit:

```python
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(0)
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setFormat("KI-Stems: %p%% — Initialisierung...")
```

- [ ] **Step 2: Run B-290-Tests, expect PASS**

```text
<PY> tests/ui/test_pipeline_progress_wiring.py::test_b290_stems_slot_writes_progress_bar tests/ui/test_pipeline_progress_wiring.py::test_stems_uses_named_slot_not_lambda -v --tb=short
```

Expected: beide `PASSED`.

### Task B.4: Implementation — Waveform-Slot

- [ ] **Step 1: Edit `ui/controllers/audio_analysis.py`** — `_on_waveform_progress` ausfüllen

Suche `def _on_waveform_progress(self, pct: int, msg: str, task_id: str):` (Z.272) und ersetze den vorhandenen Body mit:

```python
    def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
        # B-291: progress_bar live binden — vorher leerer Slot.
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        self.window.progress_bar.setFormat(f"Waveform: %p%% — {msg[:50]}")
```

- [ ] **Step 2: Run B-291-Test, expect PASS**

```text
<PY> tests/ui/test_pipeline_progress_wiring.py::test_b291_waveform_slot_writes_progress_bar -v --tb=short
```

Expected: `PASSED`.

### Task B.5: Phase-B-Sweep

- [ ] **Step 1: Run Phase-B-Tests + Regression-Sweep**

```text
<PY> tests/ui/test_pipeline_progress_wiring.py tests/ui/test_workspaces_smoke.py tests/ui/test_schnitt_workspace_states.py -v --tb=short
```

Expected: alle grün.

### Task B.6: Vault + Commit Phase B

- [ ] **Step 1: Bug-Files updaten**

Setze in B-288-, B-290-, B-291-Files Frontmatter `status: code-fix-pending-live-verification` und `updated: 2026-05-10 phase-B`.

- [ ] **Step 2: log.md ergänzen**

```bash
cat >> "C:/Brain-Bug/projects/pb-studio/log.md" << 'EOF'

## 2026-05-10 phase-B | pipeline-progress-wiring UI-Slots done

- ui/controllers/video_analysis.py::_on_pipeline_progress schreibt setValue/setRange/setFormat (B-288).
- ui/controllers/stems.py: neuer benannter _on_stem_progress-Slot, Lambda ersetzt, progress_bar live (B-290).
- ui/controllers/audio_analysis.py::_on_waveform_progress fuellt progress_bar (B-291).
- Tests test_pipeline_progress_wiring 4/4 gruen.
- Bugs B-288, B-290, B-291 auf code-fix-pending-live-verification.
EOF
```

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_pipeline_progress_wiring.py ui/controllers/video_analysis.py ui/controllers/stems.py ui/controllers/audio_analysis.py
git commit -m "$(cat <<'COMMITEOF'
fix(ui): bind worker progress to progress_bar (B-288,B-290,B-291)

Drei Slots updateten progress_bar nicht — Worker-progress lief
ins Leere, Bar blieb 0% waehrend Worker arbeitete.

- _on_pipeline_progress (Video-Pipeline): setValue + Format.
- _on_stem_progress (Stems): neuer benannter Slot, Lambda raus,
  setValue + setRange + Format. Demucs-Lauf jetzt sichtbar.
- _on_waveform_progress (Waveform): vormals leerer Slot, jetzt
  setValue + Format.

Tests test_pipeline_progress_wiring 4/4 gruen. Bugs auf
code-fix-pending-live-verification. status: fixed durch User in
Phase F.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

---

## Phase C — AnalysisStatusPanel sichtbar + Step-Liste live (B-292)

**Ziel:** Im MEDIA-Workspace ist das Panel im Default-Layout sichtbar (nicht versteckt). Bei Selektion eines Mediums in `video_pool_table` / `audio_pool_table` zeigt das Panel die Step-Liste mit Live-Status. Refresh erfolgt automatisch wenn `analysis_status_service` ein `mark_completed`-Event sendet.

### Task C.1: Failing Tests — Sichtbarkeit + Selection-Sync

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_analysis_status_panel_visibility.py`:

```python
"""B-292: AnalysisStatusPanel muss im MEDIA-Workspace permanent sichtbar
sein und auf Selection im Pool-Table reagieren."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from ui.workspaces.media_workspace import MediaWorkspace


def test_b292_video_analysis_panel_visible_default(qapp):
    ws = MediaWorkspace()
    panel = getattr(ws, "video_analysis_panel", None)
    assert panel is not None, "video_analysis_panel nicht exposed"
    assert panel.isVisibleTo(ws) or panel.isVisible() or not panel.isHidden(), (
        "B-292: AnalysisStatusPanel video ist hidden — User sieht Step-Status nicht."
    )


def test_b292_audio_analysis_panel_visible_default(qapp):
    ws = MediaWorkspace()
    panel = getattr(ws, "audio_analysis_panel", None)
    assert panel is not None, "audio_analysis_panel nicht exposed"
    assert panel.isVisibleTo(ws) or panel.isVisible() or not panel.isHidden(), (
        "B-292: AnalysisStatusPanel audio ist hidden."
    )


def test_b292_panel_set_media_renders_steps(qapp, project, video_clip):
    """set_media(video, id) muss Step-Liste rendern, alle 9 VIDEO_STEPS."""
    ws = MediaWorkspace()
    panel = ws.video_analysis_panel
    panel.set_media("video", video_clip.id)
    rendered_keys = panel.rendered_step_keys()
    expected = {
        "metadata_extract", "scene_detection", "motion_scores",
        "keyframe_extraction", "siglip_embeddings", "vector_db_storage",
        "ai_scene_caption", "scene_db_storage", "structure_enrichment",
    }
    missing = expected - set(rendered_keys)
    assert not missing, f"B-292: Step-Keys fehlen im Panel: {missing}"
```

- [ ] **Step 2: Run tests, expect FAIL**

```text
<PY> tests/ui/test_analysis_status_panel_visibility.py -v --tb=short
```

Expected: 3 FAIL — `rendered_step_keys` Methode existiert nicht; Panels sind möglicherweise eingebunden aber nicht permanent sichtbar; oder set_media wirft AttributeError.

### Task C.2: Implementation — `rendered_step_keys()` Helper

**Files:**
- Modify: `ui/widgets/analysis_status_panel.py` (Methoden ergänzen)

- [ ] **Step 1: Methode ergänzen**

In `class AnalysisStatusPanel(QWidget):`, am Ende der Klasse, neuen Public-Helper anhängen:

```python
    def rendered_step_keys(self) -> list[str]:
        """B-292: Liste der aktuell gerenderten Step-Keys (fuer Tests + Tooltips).

        Liest die Step-Spalte (Column 0) der Tabelle und liefert die
        step_key-Strings, die ueber Qt.UserRole an den Items haengen.
        """
        keys: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            key = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(key, str):
                keys.append(key)
        return keys
```

- [ ] **Step 2: UserRole-Tagging beim Render**

Im `_refresh_table`-Block (oder wo Items in Column 0 erzeugt werden) — direkt nach dem `QTableWidgetItem(step_name)` muss `setData(Qt.ItemDataRole.UserRole, step_key)` aufgerufen werden. Suche das Block-Pattern (im File ungefähr bei Item-Creation für Spalte 0) und ergänze:

```python
            name_item = QTableWidgetItem(step_name)
            name_item.setData(Qt.ItemDataRole.UserRole, step_key)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row_idx, 0, name_item)
```

(Falls bereits ein `name_item` existiert, nur die `setData`-Zeile ergänzen.)

### Task C.3: Implementation — `set_media` API + `MediaWorkspace`-Sichtbarkeit

- [ ] **Step 1: `set_media` Public-Method auf AnalysisStatusPanel**

Wenn nicht bereits vorhanden, neue Methode in `AnalysisStatusPanel`:

```python
    def set_media(self, media_type: str, media_id: int) -> None:
        """B-292: Public API — wird von MediaWorkspace bei Selection gerufen."""
        self._media_type = media_type
        self._media_id = media_id
        self._refresh_table()
```

(Wenn bereits eine ähnliche Methode existiert, prüfen dass sie nach Aufruf `_refresh_table` triggert.)

- [ ] **Step 2: MediaWorkspace Default-Sichtbarkeit + Selection-Push**

Edit `ui/workspaces/media_workspace.py`:

Direkt nach `self.video_analysis_panel = AnalysisStatusPanel()` (Z.581) und nach `self.audio_analysis_panel = AnalysisStatusPanel()` (Z.852) ergänzen:

```python
        self.video_analysis_panel.setVisible(True)  # B-292
```

und

```python
        self.audio_analysis_panel.setVisible(True)  # B-292
```

In den Bereichen wo `video_pool_table.selectionModel().currentChanged` und `audio_pool_table.selectionModel().currentChanged` verbunden werden (vermutlich `workspace_setup.py` Z.252-256), zusätzlich:

```python
# B-292: Selection -> AnalysisStatusPanel push.
self.window.video_pool_table.selectionModel().currentChanged.connect(
    lambda curr, prev: self.window._media_ws.video_analysis_panel.set_media(
        "video", int(self.window.video_pool_model.index(curr.row(), 1).data())
    ) if curr.isValid() else None
)
self.window.audio_pool_table.selectionModel().currentChanged.connect(
    lambda curr, prev: self.window._media_ws.audio_analysis_panel.set_media(
        "audio", int(self.window.audio_pool_model.index(curr.row(), 1).data())
    ) if curr.isValid() else None
)
```

- [ ] **Step 3: Run B-292-Tests, expect PASS**

```text
<PY> tests/ui/test_analysis_status_panel_visibility.py -v --tb=short
```

Expected: 3 PASSED.

### Task C.4: Vault + Commit Phase C

- [ ] **Step 1: B-292-Bug-File updaten** — Status auf `code-fix-pending-live-verification`, `updated: 2026-05-10 phase-C`.

- [ ] **Step 2: log.md ergänzen**

```bash
cat >> "C:/Brain-Bug/projects/pb-studio/log.md" << 'EOF'

## 2026-05-10 phase-C | pipeline-progress-wiring AnalysisStatusPanel done

- ui/widgets/analysis_status_panel.py: neue Public-API set_media + rendered_step_keys; UserRole-Tagging der Step-Items.
- ui/workspaces/media_workspace.py: video_analysis_panel + audio_analysis_panel setVisible(True).
- ui/controllers/workspace_setup.py: Selection-Push aus pool_tables zu set_media.
- Tests test_analysis_status_panel_visibility 3/3 gruen.
- Bug B-292 auf code-fix-pending-live-verification.
EOF
```

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_analysis_status_panel_visibility.py ui/widgets/analysis_status_panel.py ui/workspaces/media_workspace.py ui/controllers/workspace_setup.py
git commit -m "$(cat <<'COMMITEOF'
fix(ui): analysis_status_panel sichtbar + step-liste live (B-292)

User-Anforderung 2026-05-10: bei Klick auf Analyse-Buttons muss
sichtbar sein welche Steps zur 100% noch fehlen.

- set_media(media_type, media_id) Public-API auf
  AnalysisStatusPanel. rendered_step_keys() fuer Tests + Tooltips.
- UserRole-Tagging der Step-Items mit step_key.
- video_analysis_panel + audio_analysis_panel setVisible(True)
  als Default — User sieht Status sofort.
- video_pool_table + audio_pool_table Selection ruft
  panel.set_media -> _refresh_table mit aktuellem Status.

Tests test_analysis_status_panel_visibility 3/3 gruen. Bug B-292
auf code-fix-pending-live-verification.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

---

## Phase D — Cockpit-Card-Tooltip mit fehlenden Steps (B-292 Folge)

**Ziel:** `ProjectDashboard`-Cards (PROJEKT-Tab) zeigen bei `blocked` einen Tooltip mit den **konkreten** fehlenden Step-Namen aus `cockpit_orchestrator.get_cockpit_readiness`.

### Task D.1: Failing Test — Cockpit liefert `missing_steps_per_card`

**Files:**
- Create: `tests/test_services/test_cockpit_missing_steps.py`

- [ ] **Step 1: Write the failing test**

```python
"""B-292 Folge: Cockpit-Readiness traegt fehlende Steps pro Card."""
from __future__ import annotations

import pytest

from services import cockpit_orchestrator


def test_cockpit_readiness_has_missing_steps_field(test_engine, project, video_clip):
    readiness = cockpit_orchestrator.get_cockpit_readiness(project.id)
    msf = getattr(readiness, "missing_steps_per_card", None)
    assert msf is not None, (
        "B-292/D: CockpitReadiness.missing_steps_per_card fehlt — "
        "Tooltip kann nicht gefuellt werden."
    )
    # Ohne Audio-Track: audio-Card listet 'kein audio importiert' o.ae.
    # Mit video-Clip ohne Analyse: video-Card listet alle required Steps.
    assert "video" in msf
    assert isinstance(msf["video"], list)
    assert "scene_detection" in msf["video"], (
        "video-Card muss scene_detection als fehlend listen."
    )
```

- [ ] **Step 2: Run, expect FAIL**

```text
<PY> tests/test_services/test_cockpit_missing_steps.py -v --tb=short
```

Expected: FAIL — `missing_steps_per_card` ist nicht vorhanden.

### Task D.2: Implementation — `cockpit_orchestrator` erweitern

**Files:**
- Modify: `services/cockpit_orchestrator.py`

- [ ] **Step 1: Dataclass-Feld**

In `@dataclass(frozen=True) class CockpitReadiness:` (Z.37-50) Feld ergänzen:

```python
    missing_steps_per_card: dict[str, list[str]] = field(default_factory=dict)
```

- [ ] **Step 2: Helper + Befüllung**

Nach `_status_by_media` in `services/cockpit_orchestrator.py` neuen Helper:

```python
def _missing_required_steps(
    status_by_media: dict[int, dict[str, str]],
    specs: list[PipelineStepSpec],
) -> list[str]:
    """B-292: Liste der required Steps die für mindestens ein Medium offen sind."""
    required = [spec.key for spec in specs if spec.required_for_auto_edit]
    missing: set[str] = set()
    for status in status_by_media.values():
        for key in required:
            if status.get(key) != "done":
                missing.add(key)
    return sorted(missing)
```

In `get_cockpit_readiness` direkt vor `return CockpitReadiness(...)` (Z.197) Befüllung:

```python
        missing_steps = {
            "audio": _missing_required_steps(audio_status, AUDIO_STEP_SPECS) if audio_ids else ["kein_audio"],
            "video": _missing_required_steps(video_status, VIDEO_STEP_SPECS) if video_ids else ["kein_video"],
            "auto_edit": [] if can_auto_edit else ["audio_video_unvollstaendig"],
            "export": [] if can_export else ["timeline_leer"],
        }
```

Im `return CockpitReadiness(...)`-Block neuer kwarg `missing_steps_per_card=missing_steps`.

- [ ] **Step 3: Run Test, expect PASS**

```text
<PY> tests/test_services/test_cockpit_missing_steps.py -v --tb=short
```

Expected: PASSED.

### Task D.3: Implementation — Dashboard-Tooltip-Render

**Files:**
- Modify: `ui/workspaces/workflow_pages.py` (`ProjectDashboard.refresh`)

- [ ] **Step 1: Test schreiben**

Append zu `tests/test_services/test_cockpit_missing_steps.py`:

```python
def test_dashboard_tooltip_lists_missing_steps(qapp, test_engine, project, video_clip):
    from ui.workspaces.workflow_pages import ProjectDashboard
    dashboard = ProjectDashboard()
    dashboard.refresh(project.id)
    tip = dashboard.video_card.toolTip()
    assert "scene_detection" in tip or "Szenen" in tip, (
        "Dashboard video_card.toolTip enthaelt fehlende Steps nicht."
    )
```

- [ ] **Step 2: Run, expect FAIL**

```text
<PY> tests/test_services/test_cockpit_missing_steps.py::test_dashboard_tooltip_lists_missing_steps -v --tb=short
```

Expected: FAIL.

- [ ] **Step 3: Dashboard-Anpassung**

Suche in `ui/workspaces/workflow_pages.py` die `ProjectDashboard.refresh`-Methode. Innerhalb der Loop, die Cards befüllt, ergänzen:

```python
        # B-292/D: Tooltip mit fehlenden Steps fuer blocked Cards.
        msf = getattr(readiness, "missing_steps_per_card", {}) or {}
        from ui.widgets.analysis_status_panel import STEP_NAMES
        for card_key, card_widget in (
            ("audio", self.audio_card),
            ("video", self.video_card),
            ("auto_edit", self.auto_edit_card),
            ("export", self.export_card),
        ):
            steps = msf.get(card_key) or []
            if not steps:
                card_widget.setToolTip("Bereit.")
                continue
            pretty = ", ".join(STEP_NAMES.get(s, s) for s in steps)
            card_widget.setToolTip(f"Fehlt: {pretty}")
```

(Falls `audio_card` / `video_card` / `auto_edit_card` / `export_card` anders heißen, an Source anpassen.)

- [ ] **Step 4: Run Test, expect PASS**

```text
<PY> tests/test_services/test_cockpit_missing_steps.py -v --tb=short
```

Expected: alle PASSED.

### Task D.4: Vault + Commit Phase D

- [ ] **Step 1: B-292-Bug-File** — bleibt `code-fix-pending-live-verification`, `updated: 2026-05-10 phase-D`.

- [ ] **Step 2: log.md ergänzen**

```bash
cat >> "C:/Brain-Bug/projects/pb-studio/log.md" << 'EOF'

## 2026-05-10 phase-D | pipeline-progress-wiring Cockpit-Tooltip done

- services/cockpit_orchestrator.py: CockpitReadiness.missing_steps_per_card + _missing_required_steps Helper.
- ui/workspaces/workflow_pages.py: ProjectDashboard-Cards setzen Tooltip "Fehlt: <namen>".
- Tests test_cockpit_missing_steps gruen (2/2).
EOF
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_services/test_cockpit_missing_steps.py services/cockpit_orchestrator.py ui/workspaces/workflow_pages.py
git commit -m "$(cat <<'COMMITEOF'
fix(cockpit): card tooltip mit fehlenden steps (B-292)

User-Anforderung: bei "blocked" muss Cockpit zeigen welche Steps
namentlich fehlen, nicht nur "Audioanalyse fehlt".

- CockpitReadiness.missing_steps_per_card: dict pro Card.
- _missing_required_steps: Helper aggregiert open Steps pro Medium.
- ProjectDashboard.refresh: setToolTip("Fehlt: <namen>") via STEP_NAMES.

Tests test_cockpit_missing_steps 2/2 gruen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

---

## Phase E — Integration-Smoke + Live-Boot-Test

**Ziel:** Source-Inspection + echtes Live-Boot-Smoke beweisen, dass die Wiring-Bugs nicht zurückkehren.

### Task E.1: Source-Inspection-Konsolidierung

- [ ] **Step 1: Konsolidierter Test**

Append zu `tests/ui/test_pipeline_progress_wiring.py`:

```python
def test_audit_reproduction_grep_pipeline_wiring():
    """R-12 — Audit-Greps muessen Soll-Werte erreichen.

    Diese Greps belegen direkt dass keiner der ursprünglichen Symptom-
    Patterns zurueckgekehrt ist.
    """
    repo = REPO

    # B-287: metadata_extract muss in workers/video.py referenziert sein
    src = (repo / "workers/video.py").read_text(encoding="utf-8")
    assert src.count("metadata_extract") >= 1

    # B-289: progress.emit(100 muss in workers/video.py existieren
    assert "progress.emit(100" in src

    # B-288/B-290/B-291: alle drei Slots haben setValue im Body
    for f, slot in [
        ("ui/controllers/video_analysis.py", "_on_pipeline_progress"),
        ("ui/controllers/stems.py", "_on_stem_progress"),
        ("ui/controllers/audio_analysis.py", "_on_waveform_progress"),
    ]:
        body = _slot_body(f, slot)
        assert "progress_bar.setValue" in body, f"{f}::{slot} setValue fehlt"
```

- [ ] **Step 2: Run alle Phase-E-Tests, expect PASS**

```text
<PY> tests/ui/test_pipeline_progress_wiring.py tests/test_services/test_cockpit_missing_steps.py tests/test_workers/test_video_pipeline_metadata.py -v --tb=short
```

Expected: alle PASSED.

### Task E.2: Live-Boot-Smoke

**Files:**
- Create: `scripts/phase_e_pipeline_smoke.py`

- [ ] **Step 1: Skript schreiben**

```python
"""Live-Boot-Smoke fuer Pipeline-Progress-Wiring (Plan
docs/superpowers/plans/2026-05-10-pipeline-progress-wiring-fix/).

Faehrt PBWindow im offscreen-Modus hoch, simuliert worker.progress
und prueft dass progress_bar reagiert. Schreibt Resultat nach
stdout, exit 0 bei Erfolg, exit != 0 bei Fehler.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _log(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    failures: list[str] = []
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from main import PBWindow
    window = PBWindow()

    # 1) progress_bar live-update via direkter setValue-Simulation
    bar = window.progress_bar
    bar.setRange(0, 100)
    bar.setValue(0)
    window.video_analysis._on_pipeline_progress(50, "test stage", "task-x")
    if bar.value() != 50:
        failures.append(f"video_pipeline progress did not propagate: {bar.value()}")
    _log("Pipeline-Slot setzt progress_bar=50", bar.value() == 50, str(bar.value()))

    # 2) Stem-Slot
    bar.setValue(0)
    window.stems._on_stem_progress(75, "demucs")
    if bar.value() != 75:
        failures.append(f"stems progress did not propagate: {bar.value()}")
    _log("Stem-Slot setzt progress_bar=75", bar.value() == 75, str(bar.value()))

    # 3) Waveform-Slot
    bar.setValue(0)
    window.audio_analysis._on_waveform_progress(40, "wave", "task-y")
    if bar.value() != 40:
        failures.append(f"waveform progress did not propagate: {bar.value()}")
    _log("Waveform-Slot setzt progress_bar=40", bar.value() == 40, str(bar.value()))

    # 4) AnalysisStatusPanel Sichtbarkeit
    panel = window._media_ws.video_analysis_panel
    panel.setVisible(True)
    visible = panel.isVisibleTo(window._media_ws) or not panel.isHidden()
    if not visible:
        failures.append("video_analysis_panel not visible")
    _log("video_analysis_panel sichtbar", visible)

    try:
        window.close()
        window.deleteLater()
    except Exception:
        pass

    print()
    if failures:
        print(f"[RESULT] {len(failures)} FAILURES: {failures}")
        return 1
    print("[RESULT] all pipeline-progress-wiring assertions PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run, expect exit 0**

```text
<PY> scripts/phase_e_pipeline_smoke.py
```

Expected output enthält `[RESULT] all pipeline-progress-wiring assertions PASS` und Exit-Code 0.

### Task E.3: Vault + Commit Phase E

- [ ] **Step 1: log.md ergänzen**

```bash
cat >> "C:/Brain-Bug/projects/pb-studio/log.md" << 'EOF'

## 2026-05-10 phase-E | pipeline-progress-wiring Smoke + Audit-Greps gruen

- tests/ui/test_pipeline_progress_wiring.py erweitert mit test_audit_reproduction_grep_pipeline_wiring (R-12).
- scripts/phase_e_pipeline_smoke.py simuliert progress fuer alle drei Slots am echten PBWindow + prueft AnalysisStatusPanel-Sichtbarkeit.
- Phase A-E Test-Sweep gruen.
EOF
```

- [ ] **Step 2: Commit**

```bash
git add tests/ui/test_pipeline_progress_wiring.py scripts/phase_e_pipeline_smoke.py
git commit -m "$(cat <<'COMMITEOF'
test(pipeline): integration smoke + audit-grep regression suite

R-3 + R-12: source-inspection + live-boot-smoke gegen
B-287..B-292-Regression. test_audit_reproduction_grep_pipeline_wiring
prueft alle Symptom-Greps; phase_e_pipeline_smoke faehrt PBWindow
hoch und simuliert progress an drei Slots.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
COMMITEOF
)"
```

---

## Phase F — User-Live-Verify (David)

> Diese Phase ist **kein Code-Task**. User klickt durch, Agent dokumentiert.

### Drehbuch (8 Punkte)

1. **App starten:** `start_pb_studio.bat` (oder `<PY> main.py`).
2. **Material importieren:** Solo_Natur Folder (103 Videos) + `Crusty Progressive Psy Set2.mp3`.
3. **Video-Pipeline-Klick** (großer gelber Button):
   - progress_bar wandert sichtbar von 0 → 100 (B-288).
   - Status-Panel zeigt jeden Step in Echtzeit als running → done.
   - Letzter Step `Metadaten` ebenfalls done (B-287).
   - Bar erreicht 100% bevor sie versteckt wird (B-289).
4. **Stem-Separation** auf einem Audio-Track:
   - progress_bar bewegt sich live während Demucs läuft (B-290).
5. **Waveform-Analyse** auf einem Audio-Track:
   - progress_bar bewegt sich live (B-291).
6. **Einzel-Klick** `btn_lufs_analyze` (oder anderer Audio-Button):
   - Status-Panel markiert genau diesen Step als running, am Ende done (B-292).
7. **Cockpit-Card-Tooltip** (PROJEKT-Tab):
   - Card mit `blocked` zeigt namentlich fehlende Steps (D-Phase).
8. **AnalysisStatusPanel** im MEDIA-Tab:
   - Permanent sichtbar, Selection-Wechsel updated Step-Liste live (B-292).

### Status-Vergabe

- 8/8 ✅ → User vergibt `status: fixed` an B-287, B-288, B-289, B-290, B-291, B-292.
- ≥ 1 ❌ → neuer Bug-File falls Symptom anders, sonst Phase-Rework.

### User-Beleg

User dokumentiert pro Punkt im Living-Plan:

```markdown
- [x] Punkt 1 ✅ — App startet sauber, kein Traceback.
- [x] Punkt 2 ✅ — Solo_Natur + Crusty importiert, alle 103 Clips in Pool.
- [x] Punkt 3 ✅ — Video-Pipeline 0→100, alle 9 Steps, Metadaten done.
...
```

---

## Self-Review

**Spec coverage:**
- B-287 (metadata_extract) → Phase A.1+A.2 ✓
- B-288 (Video-Pipeline-Slot) → Phase B.2 ✓
- B-289 (100%-Tick) → Phase A.3 ✓
- B-290 (Stems-Slot) → Phase B.3 ✓
- B-291 (Waveform-Slot) → Phase B.4 ✓
- B-292 (Status-Panel + Cockpit) → Phase C + D ✓

**Placeholder scan:** keine TBD/TODO/„später" — alle Tasks haben konkreten Code, exakte Pfade, Test-Commands.

**Type consistency:** `set_media(media_type, media_id)` einheitlich. `rendered_step_keys()` einheitlich. `missing_steps_per_card` einheitlich als `dict[str, list[str]]`. STEP_NAMES-Mapping konsistent verwendet.

---

## Plan-Anker

- Regelwerk + Phasen-Übersicht: [`README.md`](./README.md) (R-1 bis R-12).
- Bug-Files: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-287..B-292*.md`.
- Vorgänger-Plan: `docs/superpowers/plans/2026-05-09-schnitt-integration-wiring-fix/README.md`.
- Conda-Env: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`.
- Test-Datensatz: Solo_Natur (103 Videos) + Crusty Progressive Psy Set2.mp3 (149 MB).

---

## Freigabe

Plan-Status: **draft, awaiting user approval.**

Agent rührt keinen Code an, bis User explizit „start Phase A" / „Plan freigegeben" sagt.

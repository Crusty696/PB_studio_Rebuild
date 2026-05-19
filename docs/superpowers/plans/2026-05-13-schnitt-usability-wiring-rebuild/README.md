# SCHNITT Usability + Wiring Rebuild Implementation Plan

> **Cross-Plan-Awareness — 3 neue Plaene 2026-05-19 (aktualisiert 2026-05-19):**
>
> Drei neue Plaene laufen parallel:
> 1. `VIDEO-PIPELINE-ENGINE-2026-05-19` (Plan A) — Video-Analyse + Proxy + Cross-Modal. **SCHNITT-Timeline kann spaeter Proxy + Cut-Plan anzeigen** (optional, Plan-A Phase 42). Mirror `wiki/synthesis/plan-video-pipeline-engine-2026-05-19.md` · Decision `D-045`.
> 2. `LLM-BACKEND-PLATFORM-2026-05-19` (Plan B) — Embedded Ollama. **Keine neuen Direkt-Calls** auf `services/ollama_service.py` / `ollama_client.py` einfuegen — werden in Plan-B Phase 41/42 durch `services/llm/` ersetzt. SCHNITT-Wiring-Calls werden mitmigriert. Mirror `wiki/synthesis/plan-llm-backend-platform-2026-05-19.md` · Decision `D-044`.
> 3. `GLOBAL-STORAGE-PROVENANCE-2026-05-19` (Plan C) — Content-Address-Storage + Provenance + Adapter. **SCHNITT-Audio-Subtab Backward-compat via Junction**, kein Code-Touch. Mirror `wiki/synthesis/plan-global-storage-provenance-2026-05-19.md` · Decision `D-046`.
>
> **Konkret fuer SCHNITT-Usability-Wiring:** Stems-Pfade nicht aendern. Neue LLM-Aufrufe ueber Plan B. Cut-Plan-Anzeige optional.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SCHNITT wird wiring-first nutzbar: Audio/Stems/Waveform/Timeline/Actions laufen ueber klare Binder statt halb verdrahtete globale Promotions.

**Architecture:** Neue `SchnittCoordinator`-Schicht sammelt Projekt-/Audio-/Video-/Timeline-Kontext und verteilt ihn an fokussierte Binder. Bestehende Kernlogik wie `InteractiveTimeline`, `AutoEditWorker`, `StemWorkspace`, `timeline_service` und `pacing_service` bleibt erhalten; sichtbare SCHNITT-Shell, Datenbinder und Action-Gating werden neu aufgebaut.

**Tech Stack:** PySide6, SQLAlchemy, pytest (`QT_QPA_PLATFORM=offscreen`), bestehende PB-Studio Services, conda-env `pb-studio`.

---

## Scope

Autorisiert durch User am 2026-05-13 als Folgearbeit zu B-310.

Plan-Regel: Wenn alter SCHNITT-Code nur Skeleton oder halb verdrahteter Adapter ist, darf er ersetzt werden. Services/DB bleiben, solange sie echte Logik tragen.

## Definition Of Done

- B-310 hat Status hoechstens `code-fix-pending-live-verification`, erst nach Live-Lauf `fixed`.
- Kein aktiver SCHNITT-Control ohne Slot.
- Kein aktiver SCHNITT-Control ohne Tooltip/AccessibleName.
- SCHNITT-Audio-Subtab bekommt echte Stems/Waveform/Beatgrid/Structure/LUFS/Key.
- Timeline hat sichtbare Zoom-/Fit-/Status-/Legende-Shell.
- Preconditions fuer Timeline/Auto-Edit/Re-Generate sichtbar und testbar.
- Offscreen-Tests + echter PBWindow-Smoke gruen.
- Vault aktualisiert pro Task.

## Task 1: SchnittDataContext

**Files:**
- Create: `services/schnitt_context.py`
- Test: `tests/test_services/test_schnitt_context.py`

- [x] **Step 1: Write failing tests**

```python
from pathlib import Path

from database.models import Project, AudioTrack, VideoClip, Beatgrid, WaveformData, TimelineEntry
from services.schnitt_context import build_schnitt_context
from sqlalchemy.orm import Session


def test_context_empty_project(test_engine):
    with Session(test_engine) as s:
        p = Project(name="p", path="C:/tmp/p")
        s.add(p)
        s.commit()
        pid = p.id

    ctx = build_schnitt_context(test_engine, pid)

    assert ctx.project_id == pid
    assert ctx.audio_id is None
    assert ctx.video_ids == []
    assert ctx.timeline_entry_count == 0
    assert ctx.can_auto_edit is False
    assert "Audio fehlt" in ctx.missing_reasons


def test_context_with_audio_video_and_beatgrid(test_engine):
    with Session(test_engine) as s:
        p = Project(name="p", path="C:/tmp/p")
        s.add(p)
        s.flush()
        a = AudioTrack(project_id=p.id, file_path="song.mp3", title="song", duration=60)
        v = VideoClip(project_id=p.id, file_path="clip.mp4", duration=10)
        s.add_all([a, v])
        s.flush()
        s.add(Beatgrid(audio_track_id=a.id, beat_positions="[0, 1, 2]"))
        s.add(WaveformData(audio_track_id=a.id, band_low="[0.1]", band_mid="[0.2]", band_high="[0.3]", duration=60))
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=v.id, start_time=0, end_time=10))
        s.commit()
        pid = p.id

    ctx = build_schnitt_context(test_engine, pid)

    assert ctx.audio_id == a.id
    assert ctx.video_ids == [v.id]
    assert ctx.has_beatgrid is True
    assert ctx.has_waveform is True
    assert ctx.timeline_entry_count == 1
    assert ctx.can_auto_edit is True
```

- [x] **Step 2: Run fail**

Run:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests\test_services\test_schnitt_context.py -q --tb=short --color=no
```

Expected: import fail for `services.schnitt_context`.

- [x] **Step 3: Implement context**

Create frozen dataclass with fields:

```python
@dataclass(frozen=True)
class SchnittDataContext:
    project_id: int | None
    project_path: str | None
    audio_id: int | None
    video_ids: tuple[int, ...]
    timeline_entry_count: int
    has_stems: bool
    has_waveform: bool
    has_beatgrid: bool
    has_video_analysis: bool
    missing_reasons: tuple[str, ...]

    @property
    def can_auto_edit(self) -> bool:
        return self.project_id is not None and self.audio_id is not None and bool(self.video_ids) and self.has_beatgrid
```

`build_schnitt_context(engine, project_id)` queries first non-deleted audio,
all non-deleted videos, waveform/beatgrid existence, timeline video count and
stem path columns.

- [x] **Step 4: Run pass**

Same pytest command. Expected: pass.

- [x] **Step 5: Commit**

```powershell
git add services/schnitt_context.py tests/test_services/test_schnitt_context.py
git commit -m "feat(B-310): add schnitt data context"
```

## Task 2: SCHNITT Audio Binder

**Files:**
- Create: `ui/controllers/schnitt_audio_binder.py`
- Modify: `ui/controllers/workspace_setup.py`
- Modify: `ui/controllers/stems.py`
- Test: `tests/ui/test_schnitt_audio_binder.py`

- [x] **Step 1: Write failing tests**

Test asserts binder updates `tab_audio.stem_workspace`, not only `_stems_ws.stem_widget`.

```python
def test_audio_binder_targets_schnitt_stem_workspace(qapp, monkeypatch):
    from ui.workspaces.schnitt.tab_audio import SchnittTabAudio
    from ui.controllers.schnitt_audio_binder import SchnittAudioBinder

    tab = SchnittTabAudio()
    calls = []
    tab.stem_workspace.update_for_track = lambda track_id, stems: calls.append((track_id, stems))

    binder = SchnittAudioBinder(tab_audio=tab, stem_player=None)
    binder.update_stems(track_id=7, stem_paths={"vocals": "v.wav"})

    assert calls == [(7, {"vocals": "v.wav"})]
```

- [x] **Step 2: Run fail**

Expected: missing module.

- [x] **Step 3: Implement binder**

Binder responsibilities:

- `update_stems(track_id, stem_paths)`
- `update_waveform(waveform_row, beat_positions, structure_markers)`
- `update_audio_meta(lufs, key, camelot)`
- `connect_stem_player(stem_player)`

`connect_stem_player` wires SCHNITT tab signals to the same player slots as
old Stems page.

- [x] **Step 4: Integrate**

In `workspace_setup.py`, after `_schnitt_ws` creation:

```python
from ui.controllers.schnitt_audio_binder import SchnittAudioBinder
self.window._schnitt_audio_binder = SchnittAudioBinder(
    tab_audio=self.window._schnitt_ws.editor_view.tab_audio,
    stem_player=self.window.stem_player,
)
```

In `StemsController._update_stem_workspace`, call both old workspace and
`_schnitt_audio_binder.update_stems(...)`.

- [x] **Step 5: Run tests**

```powershell
& "<PY>" -m pytest tests/ui/test_schnitt_audio_binder.py tests/ui/test_subtab_audio_layout.py -q --tb=short --color=no
```

- [x] **Step 6: Commit**

```powershell
git add ui/controllers/schnitt_audio_binder.py ui/controllers/workspace_setup.py ui/controllers/stems.py tests/ui/test_schnitt_audio_binder.py
git commit -m "fix(B-310): wire stems into schnitt audio"
```

## Task 3: Audio Metadata Feed

**Files:**
- Modify: `ui/controllers/edit_workspace.py` or new `ui/controllers/schnitt_coordinator.py`
- Test: `tests/ui/test_schnitt_audio_metadata_feed.py`

- [x] **Step 1: Write test**

Test active audio change calls `set_audio_id`, `set_waveform_data`,
`set_structure_markers`, `set_lufs`, `set_key` on SCHNITT audio tab.

- [x] **Step 2: Implement**

Preferred: create `SchnittCoordinator.refresh_audio(audio_id)` and call from
audio combo change. If existing controller is too coupled, keep only one
adapter call in `EditWorkspaceController._on_audio_combo_changed`.

- [x] **Step 3: Verify**

Run targeted tests plus `test_subtab_audio_waveform.py`,
`test_subtab_audio_structure.py`, `test_subtab_audio_key_format.py`.

- [x] **Step 4: Commit**

```powershell
git commit -m "fix(B-310): feed audio data into schnitt tab"
```

## Task 4: Timeline Usability Shell

**Files:**
- Create: `ui/workspaces/schnitt/timeline_shell.py`
- Modify: `ui/workspaces/schnitt/tab_schnitt.py`
- Test: `tests/ui/test_schnitt_timeline_shell.py`

- [x] **Step 1: Write test**

Assert shell exposes:

- `btn_zoom_out`
- `btn_zoom_fit`
- `btn_zoom_reset`
- `btn_zoom_in`
- `zoom_label`
- `legend_label`
- `status_label`

All buttons have non-empty tooltip and accessible name.

- [x] **Step 2: Implement shell**

Wrap existing `InteractiveTimeline` and wire buttons:

- out: `timeline.zoom_by_factor(1 / 1.25)`
- in: `timeline.zoom_by_factor(1.25)`
- reset: `timeline.reset_zoom()` added if missing
- fit: `timeline.fit_to_content()` added if missing

- [x] **Step 3: Add `reset_zoom` and `fit_to_content`**

Modify `ui/timeline.py` with programmatic helpers. No behavior change to DB.

- [x] **Step 4: Verify**

Run shell tests + timeline smoke tests.

- [x] **Step 5: Commit**

```powershell
git commit -m "feat(B-310): add timeline zoom shell"
```

## Task 5: Action Gating + No Silent Returns

**Files:**
- Create: `ui/controllers/schnitt_action_binder.py`
- Modify: `ui/controllers/workspace_setup.py`
- Modify: `ui/controllers/edit_workspace.py`
- Test: `tests/ui/test_schnitt_action_gating.py`

- [x] **Step 1: Write tests**

Given context missing audio, buttons disabled and tooltip contains `Audio fehlt`.
Given context ready, buttons enabled.

- [x] **Step 2: Implement binder**

Binder receives `SchnittDataContext`, updates buttons and tab hints.

- [x] **Step 3: Replace silent returns**

`_auto_edit_to_beat` and `_generate_timeline_impl` must show visible message and
restore Loading->Empty/Editor if preconditions fail.

- [x] **Step 4: Commit**

```powershell
git commit -m "fix(B-310): gate schnitt actions by context"
```

## Task 6: Tooltip + AccessibleName Audit

**Files:**
- Create: `tests/ui/test_schnitt_tooltip_audit.py`
- Modify: SCHNITT widgets found by audit

- [x] **Step 1: Write audit**

Instantiate `SchnittWorkspace`; collect all enabled `QPushButton`,
`QComboBox`, `QSlider`, `QSpinBox`, `QTreeWidget`, `QTextEdit`.
Fail if tooltip missing. Fail buttons if accessibleName missing.

- [x] **Step 2: Fix missing metadata**

Add concrete German tooltips. Disabled controls must explain missing data.

- [x] **Step 3: Commit**

```powershell
git commit -m "fix(B-310): complete schnitt tooltips"
```

## Task 7: Hidden EditWorkspace Sunset Checkpoint

**Files:**
- Create: `docs/superpowers/synthesis/2026-05-13-schnitt-hidden-host-audit.md`
- Test: source grep test if needed

- [x] **Step 1: Map remaining `EditWorkspaceController` usages**

Use `rg` to list every SCHNITT call still routed through `edit_workspace`.

- [x] **Step 2: Decide per usage**

Move to:

- `SchnittCoordinator`
- `SchnittAudioBinder`
- `SchnittTimelineBinder`
- `SchnittActionBinder`

or document why it remains temporarily.

- [x] **Step 3: Commit audit**

```powershell
git commit -m "docs(B-310): audit schnitt hidden host"
```

## Task 8: Live Verify

**Files:**
- Vault synthesis under `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\`
- Screenshots under `C:\Brain-Bug\projects\pb-studio\screenshots\`

- [ ] **Step 1: PBWindow smoke**

Start app, open SCHNITT, verify no project Empty-state.

- [ ] **Step 2: Real project smoke**

Use available real dataset. Verify audio/stems/timeline controls with screenshots.

- [ ] **Step 3: Update B-310**

If code green but user clickpath incomplete: `code-fix-pending-live-verification`.
If full user workflow completed: propose `fixed`; user confirms.

## Verification Commands

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_schnitt_context.py tests/ui/test_schnitt_audio_binder.py tests/ui/test_schnitt_audio_metadata_feed.py tests/ui/test_schnitt_timeline_shell.py tests/ui/test_schnitt_action_gating.py tests/ui/test_schnitt_tooltip_audit.py -q --tb=short --color=no
git diff --check
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" C:\Brain-Bug\scripts\vault_lint.py pb-studio
```

## Notes

- `outputs/pytest_brain_v3_results.txt` remains generated report; do not stage unless deliberately refreshing Brain V3 proof.
- Update `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-310-schnitt-workspace-unusable-half-wired-ux.md` after every task.

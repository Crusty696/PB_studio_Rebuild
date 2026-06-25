# Phase 02 — Data Services

**Ziel:** Zentrale Daten-Klassen + Service-Layer; UI bindet später daran statt direkt aus Widgets zu lesen.

---

## Task 2.1: `PacingProfile`-Dataclass

**Files:**
- Create: `services/pacing_profile.py`
- Test: `tests/test_services/test_pacing_profile.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_pacing_profile.py
import pytest
from services.pacing_profile import PacingProfile


def test_default_construction():
    p = PacingProfile()
    assert p.audio_id is None
    assert p.video_id is None
    assert p.cut_rate_index == 2
    assert p.style_preset == "Standard"
    assert p.energy_reactivity == 50
    assert p.breakdown == "halve"
    assert p.manual_density_curve is None
    assert p.anchors == []


def test_from_preset_techno():
    p = PacingProfile.from_preset("Techno")
    assert p.cut_rate_index == 2  # 4 Beats
    assert p.energy_reactivity == 70
    assert p.breakdown == "halve"
    assert p.style_preset == "Techno"


def test_from_preset_cinematic():
    p = PacingProfile.from_preset("Cinematic")
    assert p.cut_rate_index == 4  # 16 Beats
    assert p.energy_reactivity == 30
    assert p.breakdown == "none"


def test_from_preset_unknown_raises():
    with pytest.raises(ValueError):
        PacingProfile.from_preset("DoesNotExist")


def test_to_advanced_settings_maps_correctly():
    p = PacingProfile(audio_id=1, video_id=2, vibe="dunkel",
                      cut_rate_index=3, style_preset="House",
                      energy_reactivity=60, breakdown="force16")
    s = p.to_advanced_settings()
    assert s.base_cut_rate == 8
    assert s.energy_reactivity == 60
    assert s.breakdown_behavior == "force16"
    assert s.vibe == "dunkel"
```

- [ ] **Step 2: Test ausführen, Fail**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_pacing_profile.py -v --tb=short
```

Erwartet: ImportError.

- [ ] **Step 3: Implementierung**

```python
# services/pacing_profile.py
"""PacingProfile — Single Source of Truth für Pacing-Parameter."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from services.pacing_service import AdvancedPacingSettings

_CUT_RATE_INDEX_TO_BEATS = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}

_PRESETS = {
    "Techno":     {"cut_rate_index": 2, "energy_reactivity": 70, "breakdown": "halve"},
    "Cinematic":  {"cut_rate_index": 4, "energy_reactivity": 30, "breakdown": "none"},
    "House":      {"cut_rate_index": 3, "energy_reactivity": 50, "breakdown": "halve"},
    "Festival":   {"cut_rate_index": 1, "energy_reactivity": 90, "breakdown": "halve"},
}


@dataclass(slots=True)
class ClipAnchorRef:
    anchor_id: int
    time_offset: float
    label: Optional[str] = None


@dataclass(slots=True)
class PacingProfile:
    audio_id: Optional[int] = None
    video_id: Optional[int] = None
    vibe: str = ""
    cut_rate_index: int = 2
    style_preset: str = "Standard"
    energy_reactivity: int = 50
    breakdown: str = "halve"
    manual_density_curve: Optional[list[float]] = None
    anchors: list[ClipAnchorRef] = field(default_factory=list)

    @classmethod
    def from_preset(cls, key: str) -> "PacingProfile":
        if key not in _PRESETS:
            raise ValueError(f"Unbekanntes Preset: {key}")
        cfg = _PRESETS[key]
        return cls(
            cut_rate_index=cfg["cut_rate_index"],
            energy_reactivity=cfg["energy_reactivity"],
            breakdown=cfg["breakdown"],
            style_preset=key,
        )

    def to_advanced_settings(self) -> AdvancedPacingSettings:
        beats = _CUT_RATE_INDEX_TO_BEATS.get(self.cut_rate_index, 4)
        return AdvancedPacingSettings(
            base_cut_rate=beats,
            energy_reactivity=self.energy_reactivity,
            breakdown_behavior=self.breakdown,
            vibe=self.vibe,
            manual_density_curve=self.manual_density_curve,
            anchors=[a for a in self.anchors],
        )
```

- [ ] **Step 4: Test ausführen, Pass**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_pacing_profile.py -v --tb=short
```

Erwartet: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/pacing_profile.py tests/test_services/test_pacing_profile.py
git commit -m "feat(schnitt): add PacingProfile dataclass with presets"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 2.2: `TimelineState`-Dataclass

**Files:**
- Create: `services/timeline_state.py`
- Test: `tests/test_services/test_timeline_state.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_timeline_state.py
import pytest
from database import init_db
from database.models import Project, TimelineEntry
from database.session import DBSession
from database import engine
from services.timeline_state import TimelineState, ClipEntry


def _make_project_with_clips():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="ts-test")
        s.add(p)
        s.flush()
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                             start_time=0.0, end_time=2.0, lane=0, locked=True))
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=2,
                             start_time=2.0, end_time=4.0, lane=0, locked=False))
        s.commit()
        return p.id


def test_load_returns_clips_with_lock_state():
    pid = _make_project_with_clips()
    state = TimelineState.load(pid)
    assert state.project_id == pid
    assert len(state.clips) == 2
    locks = sorted(c.locked for c in state.clips)
    assert locks == [False, True]


def test_lock_count():
    pid = _make_project_with_clips()
    state = TimelineState.load(pid)
    assert state.lock_count() == 1


def test_save_snapshot_returns_id_and_persists():
    pid = _make_project_with_clips()
    state = TimelineState.load(pid)
    snap_id = state.save_snapshot(label="vor-regen")
    assert snap_id is not None
    from database.models import TimelineSnapshot
    with DBSession(engine) as s:
        snap = s.get(TimelineSnapshot, snap_id)
        assert snap.label == "vor-regen"
        assert snap.project_id == pid
        assert "media_id" in snap.payload_json
```

- [ ] **Step 2: Fail bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_timeline_state.py -v --tb=short
```

Erwartet: ImportError.

- [ ] **Step 3: Implementierung**

```python
# services/timeline_state.py
"""TimelineState — zentraler Snapshot der Timeline für Versionierung."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from typing import Optional

from sqlalchemy import func

from database import engine
from database.session import DBSession
from database.models import TimelineEntry, TimelineSnapshot


@dataclass(slots=True)
class ClipEntry:
    entry_id: int
    media_id: int
    track: str
    start: float
    end: Optional[float]
    lane: int
    locked: bool = False
    source_start: float = 0.0
    source_end: Optional[float] = None


@dataclass(slots=True)
class TimelineState:
    project_id: int
    version: int
    clips: list[ClipEntry] = field(default_factory=list)
    snapshot_label: Optional[str] = None

    def lock_count(self) -> int:
        return sum(1 for c in self.clips if c.locked)

    @classmethod
    def load(cls, project_id: int) -> "TimelineState":
        with DBSession(engine) as s:
            rows = (
                s.query(TimelineEntry)
                .filter_by(project_id=project_id)
                .order_by(TimelineEntry.start_time)
                .all()
            )
            clips = [
                ClipEntry(
                    entry_id=r.id,
                    media_id=r.media_id,
                    track=r.track,
                    start=r.start_time,
                    end=r.end_time,
                    lane=r.lane,
                    locked=bool(r.locked),
                    source_start=r.source_start or 0.0,
                    source_end=r.source_end,
                )
                for r in rows
            ]
            latest = (
                s.query(func.max(TimelineSnapshot.version))
                .filter_by(project_id=project_id)
                .scalar()
            ) or 0
        return cls(project_id=project_id, version=latest, clips=clips)

    def save_snapshot(self, label: str) -> int:
        payload = json.dumps([c.__dict__ for c in self.clips])
        with DBSession(engine) as s:
            current = (
                s.query(func.max(TimelineSnapshot.version))
                .filter_by(project_id=self.project_id)
                .scalar()
            ) or 0
            snap = TimelineSnapshot(
                project_id=self.project_id,
                version=current + 1,
                label=label,
                payload_json=payload,
            )
            s.add(snap)
            s.commit()
            return snap.id
```

- [ ] **Step 4: Pass bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_timeline_state.py -v --tb=short
```

Erwartet: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/timeline_state.py tests/test_services/test_timeline_state.py
git commit -m "feat(schnitt): add TimelineState with load/save_snapshot"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 2.3: `TimelineSnapshotService`

**Files:**
- Create: `services/timeline_snapshot_service.py`
- Test: `tests/test_services/test_timeline_snapshot_service.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_timeline_snapshot_service.py
from database import init_db, engine
from database.models import Project, TimelineEntry
from database.session import DBSession
from services.timeline_snapshot_service import (
    create_snapshot, list_snapshots, restore_snapshot,
)


def _project_with_clips(name="snap-svc"):
    init_db()
    with DBSession(engine) as s:
        p = Project(name=name)
        s.add(p)
        s.flush()
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                             start_time=0.0, end_time=2.0, lane=0))
        s.commit()
        return p.id


def test_create_and_list():
    pid = _project_with_clips()
    snap_id = create_snapshot(pid, "first")
    assert snap_id > 0
    snaps = list_snapshots(pid)
    assert len(snaps) == 1
    assert snaps[0].label == "first"
    assert snaps[0].version == 1


def test_create_increments_version():
    pid = _project_with_clips("snap-svc-2")
    create_snapshot(pid, "v1")
    create_snapshot(pid, "v2")
    snaps = list_snapshots(pid)
    versions = sorted(s.version for s in snaps)
    assert versions == [1, 2]


def test_restore_replaces_clips():
    pid = _project_with_clips("snap-svc-3")
    snap_id = create_snapshot(pid, "before-mutation")
    # Mutiere DB
    with DBSession(engine) as s:
        s.query(TimelineEntry).filter_by(project_id=pid).delete()
        s.commit()
    # Restore
    restore_snapshot(snap_id)
    with DBSession(engine) as s:
        n = s.query(TimelineEntry).filter_by(project_id=pid).count()
        assert n == 1
```

- [ ] **Step 2: Fail bestätigen** (`pytest ... -v --tb=short`).

- [ ] **Step 3: Implementierung**

```python
# services/timeline_snapshot_service.py
"""Service für persistente Timeline-Snapshots (Hybrid-Undo)."""
from __future__ import annotations
import json

from sqlalchemy import func
from database import engine
from database.session import DBSession
from database.models import TimelineEntry, TimelineSnapshot
from services.timeline_state import TimelineState


def create_snapshot(project_id: int, label: str) -> int:
    state = TimelineState.load(project_id)
    return state.save_snapshot(label)


def list_snapshots(project_id: int) -> list[TimelineSnapshot]:
    with DBSession(engine) as s:
        return (
            s.query(TimelineSnapshot)
            .filter_by(project_id=project_id)
            .order_by(TimelineSnapshot.version.asc())
            .all()
        )


def restore_snapshot(snapshot_id: int) -> None:
    with DBSession(engine) as s:
        snap = s.get(TimelineSnapshot, snapshot_id)
        if snap is None:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        clips = json.loads(snap.payload_json)
        s.query(TimelineEntry).filter_by(project_id=snap.project_id).delete()
        for c in clips:
            s.add(TimelineEntry(
                project_id=snap.project_id,
                track=c["track"],
                media_id=c["media_id"],
                start_time=c["start"],
                end_time=c["end"],
                lane=c["lane"],
                source_start=c.get("source_start", 0.0),
                source_end=c.get("source_end"),
                locked=c.get("locked", False),
            ))
        s.commit()
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add services/timeline_snapshot_service.py tests/test_services/test_timeline_snapshot_service.py
git commit -m "feat(schnitt): TimelineSnapshotService with restore"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 2.4: `ProjectNotesService`

**Files:**
- Create: `services/project_notes_service.py`
- Test: `tests/test_services/test_project_notes_service.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_project_notes_service.py
from database import init_db, engine
from database.models import Project
from database.session import DBSession
from services.project_notes_service import get_notes, update_notes


def _project(name="notes-svc"):
    init_db()
    with DBSession(engine) as s:
        p = Project(name=name)
        s.add(p)
        s.commit()
        return p.id


def test_get_notes_default_empty():
    pid = _project()
    assert get_notes(pid) == ""


def test_update_creates_row_if_missing():
    pid = _project("notes-svc-2")
    update_notes(pid, "# Hello")
    assert get_notes(pid) == "# Hello"


def test_update_overwrites_existing():
    pid = _project("notes-svc-3")
    update_notes(pid, "first")
    update_notes(pid, "second")
    assert get_notes(pid) == "second"
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# services/project_notes_service.py
"""Service für Projekt-Notes (Sub-Tab RL & Notes)."""
from __future__ import annotations

from database import engine
from database.session import DBSession
from database.models import ProjectNote


def get_notes(project_id: int) -> str:
    with DBSession(engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=project_id).one_or_none()
        return row.content_md if row else ""


def update_notes(project_id: int, content_md: str) -> None:
    with DBSession(engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=project_id).one_or_none()
        if row is None:
            s.add(ProjectNote(project_id=project_id, content_md=content_md))
        else:
            row.content_md = content_md
        s.commit()
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add services/project_notes_service.py tests/test_services/test_project_notes_service.py
git commit -m "feat(schnitt): ProjectNotesService get/update"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 2.5: `ui_binder` (bidirektionales PacingProfile-Widget-Binding)

**Files:**
- Create: `services/ui_binder.py`
- Test: `tests/test_services/test_ui_binder_pacing.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_ui_binder_pacing.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox, QLineEdit
from services.pacing_profile import PacingProfile
from services.ui_binder import PacingProfileBinder


def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_widget_to_profile_then_profile_to_widget():
    _qapp()
    profile = PacingProfile()
    cut = QComboBox(); cut.addItems(["1B", "2B", "4B", "8B", "16B"])
    style = QComboBox(); style.addItems(["Standard", "Techno", "House"])
    react_slider = QSlider(); react_slider.setRange(0, 100)
    react_spin = QSpinBox(); react_spin.setRange(0, 100)
    breakdown = QComboBox(); breakdown.addItems(["halve", "force16", "none"])
    vibe = QLineEdit()

    binder = PacingProfileBinder(
        profile, cut_rate_combo=cut, style_combo=style,
        reactivity_slider=react_slider, reactivity_spin=react_spin,
        breakdown_combo=breakdown, vibe_input=vibe,
    )

    cut.setCurrentIndex(3)
    react_spin.setValue(75)
    style.setCurrentIndex(1)
    breakdown.setCurrentIndex(2)
    vibe.setText("dunkel")

    assert profile.cut_rate_index == 3
    assert profile.energy_reactivity == 75
    assert profile.style_preset == "Techno"
    assert profile.breakdown == "none"
    assert profile.vibe == "dunkel"

    new_p = PacingProfile.from_preset("Cinematic")
    binder.apply_profile(new_p)
    assert cut.currentIndex() == 4
    assert react_spin.value() == 30
    assert breakdown.currentText() == "none"
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# services/ui_binder.py
"""Bidirektionales Binding zwischen PacingProfile und UI-Widgets."""
from __future__ import annotations
from PySide6.QtWidgets import QComboBox, QSlider, QSpinBox, QLineEdit
from services.pacing_profile import PacingProfile

_BREAKDOWN_INDEX = {"halve": 0, "force16": 1, "none": 2}
_BREAKDOWN_LIST = ["halve", "force16", "none"]


class PacingProfileBinder:
    def __init__(
        self,
        profile: PacingProfile,
        *,
        cut_rate_combo: QComboBox,
        style_combo: QComboBox,
        reactivity_slider: QSlider,
        reactivity_spin: QSpinBox,
        breakdown_combo: QComboBox,
        vibe_input: QLineEdit,
    ):
        self.profile = profile
        self._cut = cut_rate_combo
        self._style = style_combo
        self._react_slider = reactivity_slider
        self._react_spin = reactivity_spin
        self._breakdown = breakdown_combo
        self._vibe = vibe_input

        self._cut.currentIndexChanged.connect(self._on_cut)
        self._style.currentIndexChanged.connect(self._on_style)
        self._react_slider.valueChanged.connect(self._react_spin.setValue)
        self._react_spin.valueChanged.connect(self._react_slider.setValue)
        self._react_spin.valueChanged.connect(self._on_react)
        self._breakdown.currentIndexChanged.connect(self._on_breakdown)
        self._vibe.textChanged.connect(self._on_vibe)

    def _on_cut(self, idx: int):
        self.profile.cut_rate_index = idx

    def _on_style(self, idx: int):
        self.profile.style_preset = self._style.itemText(idx)

    def _on_react(self, val: int):
        self.profile.energy_reactivity = val

    def _on_breakdown(self, idx: int):
        self.profile.breakdown = _BREAKDOWN_LIST[idx]

    def _on_vibe(self, txt: str):
        self.profile.vibe = txt

    def apply_profile(self, new_profile: PacingProfile) -> None:
        self.profile.audio_id = new_profile.audio_id
        self.profile.video_id = new_profile.video_id
        self.profile.vibe = new_profile.vibe
        self.profile.cut_rate_index = new_profile.cut_rate_index
        self.profile.style_preset = new_profile.style_preset
        self.profile.energy_reactivity = new_profile.energy_reactivity
        self.profile.breakdown = new_profile.breakdown
        self.profile.manual_density_curve = new_profile.manual_density_curve
        self.profile.anchors = list(new_profile.anchors)

        self._cut.setCurrentIndex(new_profile.cut_rate_index)
        idx = max(0, self._style.findText(new_profile.style_preset))
        self._style.setCurrentIndex(idx)
        self._react_spin.setValue(new_profile.energy_reactivity)
        self._breakdown.setCurrentIndex(_BREAKDOWN_INDEX.get(new_profile.breakdown, 0))
        self._vibe.setText(new_profile.vibe)
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add services/ui_binder.py tests/test_services/test_ui_binder_pacing.py
git commit -m "feat(schnitt): PacingProfileBinder bidirectional"
```

- [ ] **Step 6: Vault-Update.**

---

## Phasen-Abschluss

Nach Task 2.5 ist Phase 02 fertig. Alle Datenklassen + Services existieren und sind getestet.

Nächste Phase: [03_BUILDING_BLOCKS.md](03_BUILDING_BLOCKS.md).

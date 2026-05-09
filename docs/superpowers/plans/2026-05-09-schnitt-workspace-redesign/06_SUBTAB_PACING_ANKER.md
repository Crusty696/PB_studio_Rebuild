# Phase 06 — Sub-Tab „Pacing & Anker"

**Ziel:** Pacing-Curve + Settings + Anker-Liste + Re-Generate-Confirm-Dialog. `apply_auto_edit_segments` wird lock-aware.

---

## Task 6.1: Layout des Sub-Tabs

**Files:**
- Create: `ui/workspaces/schnitt/tab_pacing_anker.py`
- Modify: `ui/workspaces/schnitt/editor_view.py`
- Test: `tests/ui/test_subtab_pacing_anker_layout.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_subtab_pacing_anker_layout.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker


def _qapp():
    return QApplication.instance() or QApplication([])


def test_widgets_present():
    _qapp()
    t = SchnittTabPacingAnker()
    assert t.pacing_curve is not None
    assert t.cut_rate_combo.count() == 5
    assert t.style_combo.count() >= 4
    assert t.breakdown_combo.count() == 3
    assert t.reactivity_slider is not None
    assert t.reactivity_spin is not None
    assert t.vibe_input is not None
    assert t.btn_regenerate is not None
    assert t.anchor_list is not None
    assert t.btn_add_anchor is not None
    assert t.btn_remove_anchor is not None
    assert t.btn_sync_anchors is not None
    assert t.btn_learn_ai is not None


def test_btn_regenerate_label():
    _qapp()
    t = SchnittTabPacingAnker()
    assert "neuen Pacing" in t.btn_regenerate.text()
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/workspaces/schnitt/tab_pacing_anker.py
"""Sub-Tab 'Pacing & Anker' im SCHNITT-Editor."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSplitter,
    QComboBox, QSlider, QSpinBox, QLineEdit, QPushButton, QTreeWidget,
)
from ui.widgets.pacing_curve import PacingCurveWidget


class SchnittTabPacingAnker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_pacing_column())
        splitter.addWidget(self._build_anker_column())
        splitter.setSizes([500, 500])
        outer.addWidget(splitter)

    def _build_pacing_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        v.addWidget(self._small_label("MANUAL PACING"))
        self.pacing_curve = PacingCurveWidget()
        self.pacing_curve.setMinimumHeight(280)
        v.addWidget(self.pacing_curve, stretch=1)

        # Settings-Grid
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._small_label("Cut Rate"))
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beat", "4 Beat", "8 Beat", "16 Beat"])
        self.cut_rate_combo.setCurrentIndex(2)
        row1.addWidget(self.cut_rate_combo, stretch=1)
        row1.addWidget(self._small_label("Style"))
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "Standard", "Techno", "House", "Drum & Bass",
            "Hip-Hop", "Ambient", "Minimal", "Cinematic", "Festival",
        ])
        row1.addWidget(self.style_combo, stretch=1)
        row1.addWidget(self._small_label("Breakdown"))
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems(["halve", "force16", "none"])
        row1.addWidget(self.breakdown_combo, stretch=1)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._small_label("Reaktivität"))
        self.reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.reactivity_slider.setRange(0, 100)
        self.reactivity_slider.setValue(50)
        row2.addWidget(self.reactivity_slider, stretch=1)
        self.reactivity_spin = QSpinBox()
        self.reactivity_spin.setRange(0, 100)
        self.reactivity_spin.setSuffix("%")
        self.reactivity_spin.setValue(50)
        row2.addWidget(self.reactivity_spin)
        v.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._small_label("Vibe"))
        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("z.B. 'dunkel, strobo, club'")
        row3.addWidget(self.vibe_input, stretch=1)
        v.addLayout(row3)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.btn_regenerate = QPushButton("Mit neuen Pacing-Einstellungen generieren")
        self.btn_regenerate.setObjectName("btn_accent")
        self.btn_regenerate.setFixedHeight(30)
        self.btn_regenerate.setStyleSheet(
            "QPushButton#btn_accent {"
            " background:#d4a44a; color:#0a0d12; font-weight:700;"
            " border:none; border-radius:4px; padding:0 14px;"
            "}"
            "QPushButton#btn_accent:hover { background:#f0c866; }"
        )
        action_row.addWidget(self.btn_regenerate)
        v.addLayout(action_row)

        return col

    def _build_anker_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        v.addWidget(self._small_label("ANKER (feste Audio-Video-Sync-Punkte)"))
        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video", "Label", "Gewicht"])
        self.anchor_list.setSortingEnabled(True)
        v.addWidget(self.anchor_list, stretch=1)

        toolbar = QHBoxLayout()
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_remove_anchor = QPushButton("− Anker")
        self.btn_sync_anchors = QPushButton("Sync")
        for b in (self.btn_add_anchor, self.btn_remove_anchor, self.btn_sync_anchors):
            b.setFixedHeight(24)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        v.addLayout(toolbar)

        self.btn_learn_ai = QPushButton("Als KI-Lernregel speichern")
        self.btn_learn_ai.setFixedHeight(24)
        v.addWidget(self.btn_learn_ai)

        return col

    @staticmethod
    def _small_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#6b7280; font-size:9px; font-weight:700; letter-spacing:1px;")
        return lbl
```

- [ ] **Step 4: Editor-View einbinden**

In `editor_view.py` ersetze Stub-Tab 1 durch das echte Tab analog Phase 05.

```python
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
self.tab_pacing_anker = SchnittTabPacingAnker(self)
self.sub_tabs.addTab(self.tab_pacing_anker, "Pacing & Anker")
```

(Stub für Tab 1 entfernen.)

- [ ] **Step 5: Pass bestätigen.**

- [ ] **Step 6: Commit**

```bash
git add ui/workspaces/schnitt/tab_pacing_anker.py ui/workspaces/schnitt/editor_view.py tests/ui/test_subtab_pacing_anker_layout.py
git commit -m "feat(schnitt): subtab Pacing & Anker layout"
```

- [ ] **Step 7: Vault-Update.**

---

## Task 6.2: Lock-aware `apply_auto_edit_segments`

**Files:**
- Modify: `services/timeline_service.py` (`apply_auto_edit_segments`)
- Test: `tests/test_services/test_apply_auto_edit_locked.py`

- [ ] **Step 1: Failing Test**

```python
# tests/test_services/test_apply_auto_edit_locked.py
from database import init_db, engine
from database.models import Project, TimelineEntry
from database.session import DBSession
from services.timeline_service import apply_auto_edit_segments


def test_locked_clip_preserved_unchanged():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="lock-apply")
        s.add(p); s.flush()
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                             start_time=10.0, end_time=14.0, lane=0, locked=True))
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=2,
                             start_time=0.0, end_time=2.0, lane=0, locked=False))
        s.commit()
        pid = p.id

    new_segments = [
        {"media_id": 99, "start": 0.0, "end": 5.0, "lane": 0,
         "source_start": 0.0, "source_end": 5.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
        {"media_id": 100, "start": 5.0, "end": 12.0, "lane": 0,
         "source_start": 0.0, "source_end": 7.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
        {"media_id": 101, "start": 14.0, "end": 20.0, "lane": 0,
         "source_start": 0.0, "source_end": 6.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
    ]
    apply_auto_edit_segments(new_segments, pid)

    with DBSession(engine) as s:
        rows = s.query(TimelineEntry).filter_by(project_id=pid, track="video") \
            .order_by(TimelineEntry.start_time).all()
        # Locked-Range [10..14] muss erhalten sein
        locked_rows = [r for r in rows if r.locked]
        assert len(locked_rows) == 1
        assert locked_rows[0].media_id == 1
        assert locked_rows[0].start_time == 10.0
        assert locked_rows[0].end_time == 14.0
        # Neue Segmente die in [10..14] hineinragen, müssen geklemmt sein
        unlocked = [r for r in rows if not r.locked]
        for r in unlocked:
            assert not (r.start_time < 14.0 and r.end_time > 10.0 and r.start_time >= 10.0 - 1e-6)
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Service umbauen**

In `services/timeline_service.py`:

```python
def apply_auto_edit_segments(segments: list[dict], project_id: int) -> None:
    """Ersetzt ungesperrte Video-Clips. Locked-Ranges werden erhalten;
    neue Segmente, die in eine Locked-Range hineinragen, werden auf die
    Boundaries der Locked-Range geklemmt oder verworfen, falls sie
    vollstaendig innerhalb liegen."""
    with DBSession(engine) as s:
        locked_ranges = [
            (r.start_time, r.end_time)
            for r in (
                s.query(TimelineEntry)
                .filter_by(project_id=project_id, track="video", locked=True)
                .all()
            )
            if r.end_time is not None
        ]
        s.query(TimelineEntry).filter_by(
            project_id=project_id, track="video", locked=False
        ).delete()
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            for lr_start, lr_end in locked_ranges:
                if seg_end <= lr_start or seg_start >= lr_end:
                    continue
                # Schneidet Locked-Range. Wenn vollstaendig innerhalb: verwerfen.
                if seg_start >= lr_start and seg_end <= lr_end:
                    seg_start = seg_end  # markiert leer
                    break
                if seg_start < lr_start and seg_end > lr_start:
                    seg_end = lr_start
                if seg_end > lr_end and seg_start < lr_end:
                    seg_start = lr_end
            if seg_end - seg_start <= 1e-3:
                continue
            s.add(TimelineEntry(
                project_id=project_id,
                track="video",
                media_id=seg["media_id"],
                start_time=seg_start,
                end_time=seg_end,
                lane=seg.get("lane", 0),
                source_start=seg.get("source_start", 0.0),
                source_end=seg.get("source_end"),
                crossfade_duration=seg.get("crossfade_duration", 0.0),
                brightness=seg.get("brightness", 0.0),
                contrast=seg.get("contrast", 1.0),
                locked=False,
            ))
        s.commit()
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add services/timeline_service.py tests/test_services/test_apply_auto_edit_locked.py
git commit -m "feat(schnitt): lock-aware apply_auto_edit_segments"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 6.3: Re-Generate Confirm-Dialog

**Files:**
- Create: `ui/workspaces/schnitt/regenerate_dialog.py` (Helper)
- Test: `tests/ui/test_regenerate_dialog.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_regenerate_dialog.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.workspaces.schnitt.regenerate_dialog import confirm_regenerate


def _qapp():
    return QApplication.instance() or QApplication([])


def test_yes_returns_true():
    _qapp()
    with patch.object(QMessageBox, "warning",
                      return_value=QMessageBox.StandardButton.Yes):
        assert confirm_regenerate(None) is True


def test_no_returns_false():
    _qapp()
    with patch.object(QMessageBox, "warning",
                      return_value=QMessageBox.StandardButton.No):
        assert confirm_regenerate(None) is False
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/workspaces/schnitt/regenerate_dialog.py
"""QMessageBox-Helper für Re-Generate-Confirm im Sub-Tab Pacing & Anker."""
from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_regenerate(parent: QWidget | None) -> bool:
    answer = QMessageBox.warning(
        parent,
        "Pacing neu anwenden?",
        "Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/workspaces/schnitt/regenerate_dialog.py tests/ui/test_regenerate_dialog.py
git commit -m "feat(schnitt): confirm_regenerate dialog helper"
```

- [ ] **Step 6: Vault-Update.**

---

## Phasen-Abschluss

Phase 06 fertig. Pacing & Anker Sub-Tab hat Layout, Service ist lock-aware, Confirm-Dialog ready.

Nächste Phase: [07_SUBTAB_AUDIO.md](07_SUBTAB_AUDIO.md).

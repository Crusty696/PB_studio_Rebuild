# Phase 05 — Sub-Tab „Schnitt"

**Ziel:** Preview + Transport + InteractiveTimeline + Clip-Locking. Persistenter Inspector wird durch Editor-View geliefert; dieses Sub-Tab pflegt nur den linken Center-Bereich.

---

## Task 5.1: `SchnittTabSchnitt`-Layout (ohne Locking-Logik)

**Files:**
- Create: `ui/workspaces/schnitt/tab_schnitt.py`
- Modify: `ui/workspaces/schnitt/editor_view.py` (Stub durch echtes Tab ersetzen)
- Test: `tests/ui/test_subtab_schnitt_layout.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_subtab_schnitt_layout.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt


def _qapp():
    return QApplication.instance() or QApplication([])


def test_tab_has_preview_transport_timeline():
    _qapp()
    t = SchnittTabSchnitt()
    assert t.video_preview is not None
    assert t.btn_play.text() in ("▶", "▶")
    assert t.btn_stop.text() in ("■", "■")
    assert t.timeline_view is not None
    assert t.cut_info_label is not None


def test_preview_size_640x360():
    _qapp()
    t = SchnittTabSchnitt()
    assert t.video_preview.minimumWidth() == 640
    assert t.video_preview.minimumHeight() == 360
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/workspaces/schnitt/tab_schnitt.py
"""Sub-Tab 'Schnitt' im SCHNITT-Editor: Preview + Transport + Timeline."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)
from ui.timeline import InteractiveTimeline
from ui.widgets.video_preview import VideoPreviewWidget


class SchnittTabSchnitt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        preview_row = QHBoxLayout()
        preview_row.addStretch(1)
        self.video_preview = VideoPreviewWidget()
        self.video_preview.setMinimumSize(640, 360)
        self.video_preview.setMaximumSize(640, 360)
        preview_row.addWidget(self.video_preview)
        preview_row.addStretch(1)
        v.addLayout(preview_row)

        transport = QHBoxLayout()
        transport.addStretch(1)
        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedSize(28, 24)
        self.btn_play.setToolTip("Vorschau Play / Pause")
        transport.addWidget(self.btn_play)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedSize(28, 24)
        self.btn_stop.setToolTip("Vorschau Stop")
        transport.addWidget(self.btn_stop)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        v.addLayout(transport)

        self.timeline_view = InteractiveTimeline()
        self.timeline_view.setToolTip(
            "Timeline: Drag&Drop, Mausrad zum Zoomen, Lock-Icon pro Clip."
        )
        v.addWidget(self.timeline_view, stretch=1)

        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #6b7280; font-size: 10px; padding: 1px 4px;")
        v.addWidget(self.cut_info_label)
```

- [ ] **Step 4: Editor-View hat jetzt echtes Tab statt Stub**

```python
# ui/workspaces/schnitt/editor_view.py — Import + Tab 0 ersetzen
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt
# In _build_ui:
self.tab_schnitt = SchnittTabSchnitt(self)
self.sub_tabs.addTab(self.tab_schnitt, "Schnitt")
# (Den vorherigen self._stub(...)-Aufruf für Schnitt löschen.)
```

- [ ] **Step 5: Pass bestätigen** (`pytest tests/ui/test_subtab_schnitt_layout.py tests/ui/test_schnitt_editor_view_skeleton.py -v`).

- [ ] **Step 6: Commit**

```bash
git add ui/workspaces/schnitt/tab_schnitt.py ui/workspaces/schnitt/editor_view.py tests/ui/test_subtab_schnitt_layout.py
git commit -m "feat(schnitt): subtab Schnitt with preview + transport + timeline"
```

- [ ] **Step 7: Vault-Update.**

---

## Task 5.2: Clip-Locking auf `TimelineClipItem`

**Files:**
- Modify: `ui/timeline.py` (`TimelineClipItem.__init__` + neue Methoden)
- Test: `tests/ui/test_timeline_clip_lock.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_timeline_clip_lock.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.timeline import TimelineClipItem


def _qapp():
    return QApplication.instance() or QApplication([])


def test_clip_has_lock_icon():
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
    )
    assert clip.lock_icon is not None
    assert clip.is_locked() is False


def test_set_locked_updates_visual_and_state():
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
    )
    clip.set_locked(True)
    assert clip.is_locked() is True
    assert clip.lock_icon.is_locked is True
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: `TimelineClipItem` ergänzen**

In `ui/timeline.py` innerhalb `class TimelineClipItem` nach den bestehenden `_brain_v3_*`-Initialisierungen (vor `_apply_anchors`/`_load_anchors`):

```python
# Lock-Icon — rechts oben
from ui.widgets.lock_icon_item import LockIconItem  # falls noch nicht oben importiert
self.lock_icon = LockIconItem(parent_width=width, parent_height=height, parent=self)
self._locked: bool = False
```

Neue Methoden ans Ende der Klasse:

```python
def is_locked(self) -> bool:
    return self._locked

def set_locked(self, locked: bool) -> None:
    self._locked = bool(locked)
    self.lock_icon.set_locked(self._locked)
    # Goldrand bei Lock
    if self._locked:
        self.setPen(QPen(QColor(212, 164, 74, 255), 2))
    else:
        self.setPen(QPen(self._base_color.darker(120), 1))
```

`QPen`, `QColor` sind bereits importiert.

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/timeline.py tests/ui/test_timeline_clip_lock.py
git commit -m "feat(schnitt): TimelineClipItem locked state + visual"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 5.3: Lock-Toggle-Klick-Handler

**Files:**
- Modify: `ui/timeline.py` (`TimelineClipItem.mousePressEvent`)
- Modify: `ui/timeline.py` (`InteractiveTimeline.load_from_db` muss `locked` aus DB laden + setzen)
- Test: `tests/ui/test_clip_lock_click.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_clip_lock_click.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent
from database import init_db, engine
from database.models import Project, TimelineEntry
from database.session import DBSession
from ui.timeline import InteractiveTimeline


def _qapp():
    return QApplication.instance() or QApplication([])


def test_clicking_lock_icon_toggles_db_value():
    _qapp()
    init_db()
    with DBSession(engine) as s:
        p = Project(name="lock-click")
        s.add(p); s.flush()
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                             start_time=0, end_time=2, lane=0, locked=False))
        s.commit()
        pid = p.id

    tl = InteractiveTimeline()
    tl.load_from_db(pid)
    clips = tl.get_video_clip_items()
    assert len(clips) == 1
    clip = clips[0]
    # Simuliere Klick auf das Lock-Icon (rechts oben)
    clip._handle_lock_icon_click(force=True)
    with DBSession(engine) as s:
        from database.models import TimelineEntry as TE
        assert s.query(TE).filter_by(project_id=pid).first().locked is True
```

Helper-Methode `get_video_clip_items` und `_handle_lock_icon_click(force=True)` müssen in `InteractiveTimeline` / `TimelineClipItem` existieren bzw. ergänzt werden.

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: `_handle_lock_icon_click` + Mouse-Press-Hit-Test in `TimelineClipItem`**

```python
def _hit_lock_icon(self, local_pos) -> bool:
    rect = self.lock_icon.boundingRect().translated(self.lock_icon.pos())
    return rect.contains(local_pos)

def _handle_lock_icon_click(self, *, force: bool = False) -> None:
    new = not self._locked
    self.set_locked(new)
    from ui.undo_commands import ToggleClipLockCommand
    cmd = ToggleClipLockCommand(self.entry_id, new)
    if force:
        # In Tests ohne aktive Scene/UndoStack direkt persistieren
        cmd.redo()
        return
    if self.scene() and hasattr(self.scene().views()[0], "undo_stack"):
        self.scene().views()[0].undo_stack.push(cmd)
    else:
        cmd.redo()
```

In `mousePressEvent` (Top-Level `class TimelineClipItem`) am Anfang:

```python
def mousePressEvent(self, event):
    if event.button() == Qt.MouseButton.LeftButton and self._hit_lock_icon(event.pos()):
        self._handle_lock_icon_click()
        event.accept()
        return
    super().mousePressEvent(event)
```

`Qt` ist bereits importiert.

- [ ] **Step 4: `InteractiveTimeline` Helper + locked aus DB laden**

```python
# ui/timeline.py — innerhalb InteractiveTimeline
def get_video_clip_items(self) -> list["TimelineClipItem"]:
    return [it for it in self.scene().items()
            if isinstance(it, TimelineClipItem) and it.track_type == "video"]
```

In `load_from_db` an der Stelle wo neue `TimelineClipItem` erzeugt werden, nach Erzeugung:

```python
clip.set_locked(bool(getattr(entry, "locked", False)))
```

`entry` ist der DB-Row, der hier sowieso schon iteriert wird.

- [ ] **Step 5: Pass bestätigen.**

- [ ] **Step 6: Commit**

```bash
git add ui/timeline.py tests/ui/test_clip_lock_click.py
git commit -m "feat(schnitt): clip lock icon click toggles DB state"
```

- [ ] **Step 7: Vault-Update.**

---

## Phasen-Abschluss

Phase 05 fertig. Sub-Tab Schnitt funktional inkl. Locking.

Nächste Phase: [06_SUBTAB_PACING_ANKER.md](06_SUBTAB_PACING_ANKER.md).

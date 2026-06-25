# Phase 03 — Building Blocks

**Ziel:** Maus-Schutz (`WheelGuard`) und `LockIconItem` als wiederverwendbare Bausteine — bevor Sub-Tabs sie nutzen.

---

## Task 3.1: `WheelGuard`-EventFilter

**Files:**
- Create: `ui/widgets/wheel_guard.py`
- Modify: `main.py` (Filter beim QApplication-Start installieren)
- Test: `tests/ui/test_wheel_guard.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_wheel_guard.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox

from ui.widgets.wheel_guard import WheelGuard


def _qapp():
    return QApplication.instance() or QApplication([])


def _wheel(widget, delta=120):
    return QWheelEvent(
        QPointF(10.0, 10.0), widget.mapToGlobal(QPoint(10, 10)),
        QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_combo_unfocused_blocks_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    cb = QComboBox()
    cb.addItems(["a", "b", "c"])
    cb.setCurrentIndex(0)
    cb.show()
    cb.clearFocus()
    QApplication.sendEvent(cb, _wheel(cb))
    assert cb.currentIndex() == 0


def test_slider_focused_passes_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(50)
    sl.show()
    sl.setFocus()
    QApplication.sendEvent(sl, _wheel(sl, delta=120))
    assert sl.value() != 50


def test_spinbox_unfocused_blocks_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    sb = QSpinBox()
    sb.setRange(0, 100)
    sb.setValue(50)
    sb.show()
    sb.clearFocus()
    QApplication.sendEvent(sb, _wheel(sb, delta=-120))
    assert sb.value() == 50
```

- [ ] **Step 2: Fail bestätigen** (`pytest ... -v`).

- [ ] **Step 3: Implementierung**

```python
# ui/widgets/wheel_guard.py
"""Application-weiter EventFilter: blockiert Wheel-Events auf
QComboBox/QSlider/QSpinBox/QDoubleSpinBox solange das Widget keinen Fokus hat.
Verhindert versehentliches Verstellen beim Mausrad-Drüberscrollen."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QComboBox, QSlider, QSpinBox, QDoubleSpinBox


_GUARDED_TYPES = (QComboBox, QSlider, QSpinBox, QDoubleSpinBox)


class WheelGuard(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(obj, _GUARDED_TYPES):
            if not obj.hasFocus():
                event.ignore()
                return True
        return super().eventFilter(obj, event)
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Filter in `main.py` installieren**

```python
# main.py — direkt nach app = QApplication(sys.argv)
from ui.widgets.wheel_guard import WheelGuard
_wheel_guard = WheelGuard(app)
app.installEventFilter(_wheel_guard)
```

Halte Referenz `_wheel_guard` als Modul-Level- oder Window-Attribut, damit der Filter nicht GC'd wird.

- [ ] **Step 6: Smoke-Test**

App starten, in den existierenden `EditWorkspace` gehen, mit Maus über `cut_rate_combo` scrollen ohne zu klicken — Wert darf sich nicht ändern. Klicken, dann scrollen — ändert sich.

- [ ] **Step 7: Commit**

```bash
git add ui/widgets/wheel_guard.py tests/ui/test_wheel_guard.py main.py
git commit -m "feat(schnitt): WheelGuard event filter for combos/sliders"
```

- [ ] **Step 8: Vault-Update.**

---

## Task 3.2: `LockIconItem` (QGraphicsItem)

**Files:**
- Create: `ui/widgets/lock_icon_item.py`
- Test: `tests/ui/test_lock_icon_item.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_lock_icon_item.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtCore import QPointF, QRectF
from ui.widgets.lock_icon_item import LockIconItem


def _qapp():
    return QApplication.instance() or QApplication([])


def test_initial_state_unlocked():
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)
    assert item.is_locked is False


def test_set_locked_changes_visual():
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)
    initial_color = item.brush().color().rgba()
    item.set_locked(True)
    assert item.is_locked is True
    assert item.brush().color().rgba() != initial_color


def test_position_top_right():
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)
    pos = item.pos()
    assert pos.x() > 180  # rechtsbündig
    assert pos.y() < 5    # oben
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/widgets/lock_icon_item.py
"""LockIconItem — visualer State auf TimelineClipItems.
Klick togglet `locked`-Flag; Toggle wird vom Parent-Clip via
mouse-press abgefangen und in QUndoStack gepusht."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem


_SIZE = 12


class LockIconItem(QGraphicsRectItem):
    UNLOCKED_COLOR = QColor(255, 255, 255, 100)
    LOCKED_COLOR = QColor(255, 215, 70, 230)

    def __init__(self, parent_width: float, parent_height: float, parent=None):
        super().__init__(QRectF(0, 0, _SIZE, _SIZE), parent)
        self.is_locked: bool = False
        # rechte obere Ecke, 4 px Innenabstand
        self.setPos(parent_width - _SIZE - 4, 2)
        self.setZValue(15)
        self.setPen(QPen(QColor(0, 0, 0, 180), 1))
        self.setBrush(QBrush(self.UNLOCKED_COLOR))
        self.setAcceptHoverEvents(True)
        self.setToolTip("Clip sperren / entsperren — gesperrte Clips bleiben bei Re-Generate erhalten")

    def set_locked(self, locked: bool) -> None:
        self.is_locked = locked
        self.setBrush(QBrush(self.LOCKED_COLOR if locked else self.UNLOCKED_COLOR))
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/widgets/lock_icon_item.py tests/ui/test_lock_icon_item.py
git commit -m "feat(schnitt): LockIconItem visual lock state"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 3.3: `ToggleClipLockCommand`

**Files:**
- Modify: `ui/undo_commands.py` (neue Klasse hinzufügen)
- Test: `tests/ui/test_toggle_clip_lock_command.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_toggle_clip_lock_command.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from database import init_db, engine
from database.models import Project, TimelineEntry
from database.session import DBSession
from ui.undo_commands import ToggleClipLockCommand


def _qapp():
    return QApplication.instance() or QApplication([])


def _entry():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="lock-cmd")
        s.add(p); s.flush()
        e = TimelineEntry(project_id=p.id, track="video", media_id=1,
                          start_time=0, end_time=2, lane=0, locked=False)
        s.add(e); s.commit()
        return e.id


def test_redo_sets_locked_true():
    _qapp()
    eid = _entry()
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    with DBSession(engine) as s:
        assert s.get(TimelineEntry, eid).locked is True


def test_undo_reverts():
    _qapp()
    eid = _entry()
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    cmd.undo()
    with DBSession(engine) as s:
        assert s.get(TimelineEntry, eid).locked is False
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Command anhängen**

```python
# ui/undo_commands.py — am Ende
class ToggleClipLockCommand(QUndoCommand):
    """Togglet das locked-Flag eines TimelineEntry."""

    def __init__(self, entry_id: int, new_locked: bool):
        super().__init__("Clip sperren" if new_locked else "Clip entsperren")
        self._entry_id = entry_id
        self._new = new_locked
        self._old: bool | None = None

    def redo(self):
        with DBSession(engine) as s:
            e = s.get(TimelineEntry, self._entry_id)
            if e is None:
                return
            self._old = bool(e.locked)
            e.locked = self._new
            s.commit()

    def undo(self):
        if self._old is None:
            return
        with DBSession(engine) as s:
            e = s.get(TimelineEntry, self._entry_id)
            if e is None:
                return
            e.locked = self._old
            s.commit()
```

`DBSession`, `engine`, `TimelineEntry` müssen importiert sein (sind sie i.d.R. schon im File).

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/undo_commands.py tests/ui/test_toggle_clip_lock_command.py
git commit -m "feat(schnitt): ToggleClipLockCommand QUndoCommand"
```

- [ ] **Step 6: Vault-Update.**

---

## Phasen-Abschluss

Phase 03 fertig. Bausteine bereit für Sub-Tabs.

Nächste Phase: [04_SCHNITT_SKELETON.md](04_SCHNITT_SKELETON.md).

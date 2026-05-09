# Phase 07 — Sub-Tab „Audio"

**Ziel:** Waveform + Beatgrid + Strukturmarker + Stems-Mixer + LUFS + Tonart in einem Sub-Tab.

---

## Task 7.1: Layout

**Files:**
- Create: `ui/workspaces/schnitt/tab_audio.py`
- Modify: `ui/workspaces/schnitt/editor_view.py`
- Test: `tests/ui/test_subtab_audio_layout.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_subtab_audio_layout.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_widgets_present():
    _qapp()
    t = SchnittTabAudio()
    assert t.waveform_view is not None
    assert t.stem_workspace is not None
    assert t.lufs_label is not None
    assert t.key_label is not None
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/workspaces/schnitt/tab_audio.py
"""Sub-Tab 'Audio' im SCHNITT-Editor: Waveform + Stems + LUFS + Key."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
)
from ui.widgets.stem_workspace import StemWorkspaceWidget


class SchnittTabAudio(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        # Waveform mit Beatgrid + Strukturmarker
        self.waveform_view = QGraphicsView()
        self.waveform_view.setMinimumHeight(120)
        self.waveform_view.setMaximumHeight(160)
        self.waveform_view.setScene(QGraphicsScene())
        self.waveform_view.setToolTip("Waveform mit Beatgrid und Strukturmarkern (Intro/Drop/Outro).")
        v.addWidget(self.waveform_view)

        # Stems-Mixer
        self.stem_workspace = StemWorkspaceWidget()
        v.addWidget(self.stem_workspace, stretch=1)

        # Footer-Row: LUFS + Key
        footer = QHBoxLayout()
        self.lufs_label = QLabel("LUFS: —")
        self.lufs_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        footer.addWidget(self.lufs_label)
        footer.addStretch(1)
        self.key_label = QLabel("Tonart: —")
        self.key_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        footer.addWidget(self.key_label)
        v.addLayout(footer)

    def set_lufs(self, lufs_value: float | None) -> None:
        if lufs_value is None:
            self.lufs_label.setText("LUFS: —")
        else:
            self.lufs_label.setText(f"LUFS: {lufs_value:.1f}")

    def set_key(self, key_text: str | None, camelot: str | None = None) -> None:
        if not key_text:
            self.key_label.setText("Tonart: —")
            return
        if camelot:
            self.key_label.setText(f"Tonart: {key_text} ({camelot})")
        else:
            self.key_label.setText(f"Tonart: {key_text}")
```

- [ ] **Step 4: Editor-View einbinden** (analog Phasen 05/06).

- [ ] **Step 5: Pass bestätigen.**

- [ ] **Step 6: Commit**

```bash
git add ui/workspaces/schnitt/tab_audio.py ui/workspaces/schnitt/editor_view.py tests/ui/test_subtab_audio_layout.py
git commit -m "feat(schnitt): subtab Audio with waveform + stems + lufs + key"
```

- [ ] **Step 7: Vault-Update.**

---

## Task 7.2: Waveform + Beatgrid Render

**Files:**
- Modify: `ui/workspaces/schnitt/tab_audio.py` (Methode `set_audio_id`)
- Test: `tests/ui/test_subtab_audio_render.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_subtab_audio_render.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_set_audio_id_renders_grid_items():
    _qapp()
    t = SchnittTabAudio()
    t.set_audio_id(None)  # Defensive: kein Audio
    assert t.waveform_view.scene().itemsBoundingRect().isEmpty()

    # mit fake-Daten
    t.render_grid_lines([0.5, 1.0, 1.5, 2.0])
    assert len(t.waveform_view.scene().items()) >= 4
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Methoden ergänzen**

```python
# ui/workspaces/schnitt/tab_audio.py — innerhalb SchnittTabAudio
from PySide6.QtGui import QColor, QPen
from PySide6.QtCore import QLineF


def render_grid_lines(self, beat_times: list[float], pixels_per_second: float = 50.0) -> None:
    scene = self.waveform_view.scene()
    scene.clear()
    pen_beat = QPen(QColor(180, 200, 230, 90), 1)
    height = self.waveform_view.height() or 120
    for t in beat_times:
        x = t * pixels_per_second
        line = scene.addLine(QLineF(x, 0, x, height), pen_beat)


def set_audio_id(self, audio_id: int | None) -> None:
    self._audio_id = audio_id
    self.waveform_view.scene().clear()
    if audio_id is None:
        return
    # Beatgrid-Rendering aus DB folgt im Controller (Phase 09 Worker).
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/workspaces/schnitt/tab_audio.py tests/ui/test_subtab_audio_render.py
git commit -m "feat(schnitt): audio tab grid line rendering"
```

- [ ] **Step 6: Vault-Update.**

---

## Phasen-Abschluss

Phase 07 fertig. Audio-Sub-Tab steht; Datenanbindung an aktiven Track folgt im Controller-Schritt.

Nächste Phase: [08_SUBTAB_RL_NOTES.md](08_SUBTAB_RL_NOTES.md).

# Keyboard Shortcuts Reference

All shortcuts are configurable via **Edit → Settings → Keyboard Shortcuts**.

---

## Playback

| Action | Default Key | Description |
|---|---|---|
| Play / Pause | `Space` | Toggle playback |
| Stop | `Escape` | Stop playback and deselect all |
| Shuttle Backward | `J` | Slow-reverse / fast-rewind (hold for faster) |
| Shuttle Pause | `K` | Pause shuttle playback |
| Shuttle Forward | `L` | Slow-forward / fast-forward (hold for faster) |
| Jump to Start | `Home` | Move playhead to timeline start |
| Jump to End | `End` | Move playhead to timeline end |
| Frame Back | `←` (Left) | Step one frame backward |
| Frame Forward | `→` (Right) | Step one frame forward |

> **JKL Shuttle** is the industry-standard three-finger shuttle system. Press `J` once for slow reverse, twice for faster reverse. Press `K` to stop. Press `L` once for slow forward, twice for faster forward.

---

## Editing

| Action | Default Key | Description |
|---|---|---|
| Set In-Point | `I` | Mark the start of a clip selection at the playhead |
| Set Out-Point | `O` | Mark the end of a clip selection at the playhead |
| Set Anchor | `M` | Pin the selected clip to its current beat position |
| Delete | `Del` | Delete selected clips |
| Undo | `Ctrl+Z` | Undo the last action |
| Redo | `Ctrl+Y` | Redo the last undone action |
| Copy | `Ctrl+C` | Copy selected clips |
| Paste | `Ctrl+V` | Paste clips at playhead position |

---

## Navigation & View

| Action | Default Key | Description |
|---|---|---|
| Zoom In | `+` | Zoom the timeline in |
| Zoom Out | `-` | Zoom the timeline out |

---

## Customizing Shortcuts

1. Open **Edit → Settings**
2. Click the **Keyboard Shortcuts** tab
3. Click on any action row and press the new key combination
4. Click **Save** to apply

To reset all shortcuts to factory defaults, click **Reset to Defaults**.

Shortcuts are stored in the Windows registry via Qt's QSettings (`HKCU\Software\PBStudio\PBStudio\shortcuts\`).

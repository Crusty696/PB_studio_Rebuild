# PB Studio — Feature Overview

## Smart Director (AI Auto-Edit)

The core editing engine. One click generates a complete beat-synchronized timeline from your audio and video.

**How it works:**
- Reads the beatgrid and macro-structure detected during audio analysis
- Calculates a dynamic cut-rate score (`S_eff`) per beat:
  - **Drop sections** → fast cuts, high energy
  - **Breakdown sections** → slow cuts, contemplative
  - **Warmup / Buildup** → gradually increasing pace
- Selects the best-matching video clip for each beat moment using:
  - Motion energy score (RAFT optical flow — high motion on drops, low motion on calm sections)
  - Visual similarity (SigLIP embeddings — avoids repeating the same visual look back-to-back)
- Respects any **Anchors** you have set before running

**Anchors:** Pin any video clip to a specific beat by selecting it and pressing `M`. The Smart Director works around your fixed points and fills the rest automatically.

---

## Beat Detection & Waveform Editor

PB Studio uses `beat_this` (CPJKU) for GPU-accelerated beat detection — the same model used in professional DJ analysis tools.

**Features:**
- Detects individual beats and downbeats
- Classifies macro-sections: Warmup, Buildup, Drop, Breakdown, Cooldown
- Draws a Rekordbox-style frequency waveform: Bass (red), Mid (green), High (blue)
- Beatgrid overlay with level-of-detail rendering (zooms in at high magnification)
- Manual beat-to-clip anchor markers visible on the waveform

**Waveform navigation:**
- Scroll horizontally to move through the track
- `+` / `-` to zoom the timeline
- Click anywhere to move the playhead
- `J` / `K` / `L` for shuttle playback (industry standard)

---

## Stem Separation

Powered by **Demucs `htdemucs_ft`** (Meta AI), one of the most accurate open-source stem separators available.

| Stem | How PB Studio uses it |
|---|---|
| **Drums** | Onset detection triggers cut candidates |
| **Bass** | RMS spikes above 0.5 signal a drop |
| **Vocals** | Active vocals slow the cut rate (sensitivity × 2) — avoids cutting mid-sentence |
| **Other** | Used for overall energy context |

Stems are stored in `storage/stems/` as WAV files and reused across sessions.

---

## Video Analysis

PB Studio analyzes every video clip before editing to understand its visual content.

**Scene Detection** (PySceneDetect)
- Finds natural scene boundaries within each clip
- Each scene becomes an independent editing unit

**Motion Scoring** (RAFT Optical Flow)
- Computes frame-to-frame motion for each scene
- GPU-cached per batch — re-runs only when clips change
- High-motion scenes are matched to high-energy audio moments

**Visual Embeddings** (SigLIP-so400m)
- 1152-dimensional visual fingerprint per scene stored in SQLite
- Used for semantic clip search and diversity-aware clip selection
- Prevents the same visual look from appearing on consecutive beats

**Proxy Generation**
- NVENC hardware encoder generates 540p or 720p proxy clips
- Proxies allow smooth real-time preview on lower-end systems
- Originals are used for final export

---

## Timeline Editor

A non-destructive timeline with full undo/redo history.

- Drag clips to reorder
- Trim in/out points by dragging clip edges (or use `I` / `O` to set at playhead)
- Delete selected clips with `Del`
- Copy / Paste clips with `Ctrl+C` / `Ctrl+V`
- Zoom with `+` / `-`, navigate with `Home` / `End`
- Step through frame-by-frame with `Left` / `Right`

All edits are non-destructive — the original media files are never modified.

---

## Multi-Agent AI Chat

Open the chat dock (bottom panel) to interact with the built-in AI system.

**Available agents:**
| Agent | Specialization |
|---|---|
| **Pacing** | Cut timing, beat alignment, S_eff adjustments |
| **Audio** | Stem analysis, waveform interpretation, LUFS targets |
| **Vision** | Clip selection, scene scoring, visual coherence |
| **Editor** | Timeline operations, export settings |
| **Orchestrator** | Routes complex requests across multiple agents |

The system runs a local **Qwen 2.5 0.5B** model — no internet connection required after first download.

**Human-in-the-Loop Learning**
When you manually correct a cut (move, trim, or replace a clip), PB Studio records your decision as an anchor rule and reuses it in future auto-edits within the same session. Use "Learn as AI Rule" to persist the correction across sessions.

---

## Export

Final rendering via FFmpeg with hardware acceleration where available.

**Options:**
- **Resolution & codec:** H.264 (CPU), H.265 (CPU/NVENC), VP9
- **NVENC hardware encoding** for fast GPU-accelerated render
- **LUFS normalization:** Target loudness level for the audio mix
- **Crossfades:** Per-section transition style (cut, dissolve, dip-to-black)
- **Color correction:** Per-clip brightness and contrast adjustments

Output files are saved to `exports/` inside your project folder.

---

## Settings & Customization

Access via **Edit → Settings** or the gear icon.

| Setting | Description |
|---|---|
| GPU / VRAM limit | Reserve VRAM for other applications |
| Proxy quality | 540p / 720p / disabled |
| LUFS target | Default export loudness (-14 / -16 / -23 LUFS) |
| Keyboard shortcuts | Fully remappable — see [Keyboard Shortcuts](keyboard_shortcuts.md) |
| Language | UI language (English, Deutsch — more planned) |

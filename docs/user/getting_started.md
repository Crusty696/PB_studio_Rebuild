# Getting Started with PB Studio

**Version:** 0.5.0

PB Studio is a beat-synchronized video editor for DJs and music video creators. It analyzes your audio track and automatically cuts your video clips in time with the music — fast cuts on drops, slow cuts on breakdowns.

---

## Requirements

| Item | Requirement |
|---|---|
| Operating System | Windows 10/11 |
| GPU | NVIDIA GeForce GTX 1060 6 GB, exclusively `cuda:0` |
| CUDA/PyTorch | CUDA 11.3, PyTorch `1.12.1+cu113` |
| FFmpeg | Bundled `bin/` preferred, otherwise system PATH |
| Python | 3.10 via conda env `pb-studio` |
| Hugging Face token | Required for gated models (Demucs, SigLIP) |

> PB Studio requires a CUDA-capable GPU. CPU-only mode is not supported.

---

## Installation

### 1. Install dependencies

```bat
git clone <repo-url>
cd pb-studio-rebuild
setup_pb_studio.bat
```

Manual equivalent:

```powershell
conda env create -f environment.yml
conda activate pb-studio
python scripts/setup_py310_gpu.py --skip-venv
```

### 2. Set your Hugging Face token

Create a `.env` file in the project root:

```
HF_TOKEN=your_token_here
```

Get a free token at [huggingface.co](https://huggingface.co) — required for first-time model downloads.

### 3. Launch the app

```bat
start_pb_studio.bat
```

On first launch a **Setup Wizard** will verify FFmpeg, GPU, and model availability.

For an observed diagnostic session:

```bat
start_pb_studio_clicklog.bat
```

See `docs/superpowers/LIVE_TEST_SESSION.md`.

---

## Your First Project

### Step 1 — Create a project

Go to **File → New Project** or use the project dialog on startup. Give your project a name and choose a folder to store outputs.

### Step 2 — Import media (MATERIAL & ANALYSE tab)

1. Click **Import Audio** and select your DJ track (MP3, WAV, FLAC, or AIFF).
2. Click **Import Video** and add your footage clips (MP4, MOV, AVI, MKV).

You can drag-and-drop files directly into the media table.

### Step 3 — Analyze audio

Click **Analyze** on your audio track. PB Studio will:
- Detect every beat and downbeat (GPU-accelerated via `beat_this`)
- Map the macro-structure: Warmup → Buildup → Drop → Breakdown → Cooldown
- Draw the Rekordbox-style frequency waveform (Bass / Mid / High bands)

*Typical time: 10–30 seconds for a 5-minute track.*

### Step 4 — Separate stems (optional, recommended)

Click **Separate Stems** on the audio track. Demucs splits the track into:

| Stem | Role in editing |
|---|---|
| Drums | Triggers cuts (onset detection) |
| Bass | Detects drops (RMS spike > 0.5) |
| Vocals | Slows cut rate when vocals are active |
| Other | Background instrumentation |

*Typical time: 1–3 minutes for a 5-minute track. Requires ~4 GB VRAM.*

### Step 5 — Analyze video clips

Click **Analyze** on each video clip (or select all and batch-analyze). PB Studio will:
- Detect scene boundaries (PySceneDetect)
- Score each scene for motion energy (RAFT optical flow)
- Generate visual embeddings (SigLIP) for semantic clip matching

*Typical time: 30–90 seconds per clip depending on length and GPU.*

### Step 6 — Auto-Edit (SCHNITT tab)

Switch to the **SCHNITT** tab. The tab opens in an Empty-State with Preset-Buttons (Smooth, Energetic, Cinematic, Custom) — pick a preset or click **Auto-Edit (Phase 3)** in sub-tab **Schnitt**. The Smart Director:
1. Maps each beat to a cut-rate score based on section type
2. Selects video clips by matching motion energy and visual content to audio moments
3. Assembles the timeline with beat-accurate cut points

The **SCHNITT** tab has 4 sub-tabs:
- **Schnitt** — Timeline editor with cuts, clips, anchors
- **Pacing & Anker** — Section-based cut-rate tuning, anchor management
- **Audio** — Stem mixing, vocal-aware tweaks, ducking
- **RL & Notes** — Reinforcement-learning rules, manual notes

Review the result in the timeline viewer. You can:
- Drag clips to reorder
- Trim in/out points with the waveform editor
- Pin any clip to a specific beat using the **Anchor** tool (`M`)
- Lock a clip via Lock-Click on the clip badge to protect it from re-runs
- Filter clips with the mouse-wheel filter on the media bin
- Undo/redo changes with `Ctrl+Z` / `Ctrl+Y`

### Step 7 — Export (EXPORT tab)

Switch to the **EXPORT** tab and click **Export**. Options include:
- Output resolution and codec (NVENC hardware encoding available)
- LUFS normalization target for the audio
- Crossfade transition style per section type
- Color correction (brightness / contrast) per clip

The rendered file is saved to your project's `exports/` folder.

---

## Tips

- **Proxy generation** — PB Studio can create 540p/720p proxy clips for smooth playback. Enable in Settings → Performance.
- **AI Chat** — Open the chat dock (bottom panel) to ask questions or issue commands in natural language. The system routes requests to specialized agents (Pacing, Vision, Audio, Editor).
- **Human-in-the-Loop learning** — When you manually correct a cut, PB Studio stores your decision and uses it to improve future edits in the same session.

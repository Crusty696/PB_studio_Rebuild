# PB Studio

**v0.5.0** — Beat-synchronized video editing powered by AI

PB Studio is a desktop video production tool designed for DJs and music video creators. It analyzes your audio track (beats, drops, stems) and automatically cuts your video footage in sync — the way a professional editor would. Built with PySide6, PyTorch, and FFmpeg.

---

## Core Features

### Smart Director (AI Auto-Edit)
- Analyzes beats, downbeats, and energy curves from your audio with GPU-accelerated beat detection (`beat_this`)
- Detects macro-structure: Warmup → Buildup → Drop → Breakdown → Cooldown
- Calculates a dynamic cut-rate (`S_eff`) per beat: fast cuts on drops, slow cuts on breakdowns
- Matches video clips to audio moments by motion energy (RAFT optical flow) and visual content (SigLIP embeddings)
- Anchors: pin any video clip to a specific beat — the engine works around it

### Stem-Aware Pacing
- Separates audio into four stems via Demucs: **Vocals, Drums, Bass, Other**
- Drums drive cut triggers (onset detection)
- Bass signals drop detection (RMS spike > 0.5)
- Active vocals → slower cutting (sensitivity × 2)
- Auto-ducking: background music lowers during spoken words

### Video Analysis
- Scene detection (PySceneDetect content detector)
- Per-scene motion scoring with RAFT optical flow (GPU-cached per batch)
- Per-scene visual embeddings (SigLIP-so400m, 1152-dim) stored in SQLite VectorDB
- Numpy-vectorized semantic clip search
- Keyframe extraction for preview

### Waveform & Beatgrid Editor
- Rekordbox-style frequency waveform (Bass/Mid/High color bands)
- Beatgrid overlay with level-of-detail rendering
- Manual beat-to-clip anchor markers

### Multi-Agent Chat
- Built-in AI chat dock connected to the entire action system
- Routes requests to specialized agents: Pacing, Vision, Audio, Editor
- Powered by a local small LLM (Qwen 0.5B) for fully offline operation
- Human-in-the-Loop learning: manual cut corrections are stored and reused in future sessions

### Export
- LUFS-normalized audio output
- Crossfade transitions (per section type)
- Color correction (brightness/contrast) per clip
- NVENC hardware proxy generation (540p/720p) for smooth editing performance

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11 or 3.12 |
| CUDA GPU | Required (GTX 1060 6GB minimum recommended) |
| FFmpeg | Must be on PATH |
| Poetry | Latest |

> **Note:** CPU-only mode is not supported. The pipeline is designed for GPU acceleration.

---

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd pb-studio-rebuild
```

### 2. Install Poetry

```bash
pip install poetry
```

### 3. Add the PyTorch CUDA source

The project uses a custom PyTorch index for CUDA 12.8. This is already configured in `pyproject.toml`.

### 4. Install dependencies

```bash
poetry install
```

This installs all dependencies including PyTorch with CUDA support, Demucs, beat_this (from GitHub), and the full ML stack.

### 5. Configure environment variables

Create a `.env` file in the project root:

```env
HF_TOKEN=your_huggingface_token_here
```

A Hugging Face token is required to download gated models (e.g., Demucs, SigLIP).

### 6. Run the application

```bash
poetry run python main.py
```

---

## First Steps

1. **MEDIA tab** — Import your audio file (MP3, WAV, FLAC) and video clips (MP4, MOV)
2. Click **Analyze** on the audio track — this runs beat detection and generates the beatgrid
3. Click **Separate Stems** — this runs Demucs to extract Vocals/Drums/Bass/Other (takes 1–3 minutes)
4. Click **Analyze** on your video clips — this runs scene detection, RAFT motion scoring, and SigLIP embeddings
5. **EDIT tab** — Click **Auto-Edit (Phase 3)** to generate a beat-synchronized timeline
6. **DELIVER tab** — Click **Export** to render the final video

---

## Project Structure

```
pb-studio-rebuild/
├── main.py                  # Application entry point, Qt app, background workers
├── database.py              # SQLAlchemy ORM schema (all models)
├── agents/                  # Multi-agent AI system
│   ├── orchestrator_agent.py
│   ├── pacing_agent.py      # PhD-level DJ pacing logic
│   ├── audio_agent.py
│   ├── vision_agent.py
│   └── editor_agent.py
├── services/                # Core processing services
│   ├── pacing_service.py    # Beat-sync auto-edit algorithm
│   ├── ai_audio_service.py  # Demucs stem separation
│   ├── beat_analysis_service.py  # beat_this GPU beat detection
│   ├── video_analysis_service.py # RAFT + SigLIP + SceneDetect
│   ├── export_service.py    # FFmpeg render pipeline
│   ├── model_manager.py     # GPU/VRAM singleton controller
│   └── ...
├── ui/                      # PySide6 UI components
│   ├── chat_dock.py         # AI chat interface
│   ├── waveform_item.py     # Rekordbox-style waveform
│   └── widgets/
│       └── stem_workspace.py
├── docs/                    # Technical documentation
│   ├── ARCHITECTURE.md      # System architecture overview
│   └── pacing_logic_phd.md  # Full pacing algorithm specification
├── storage/                 # Runtime output (auto-created)
│   ├── stems/               # Demucs stem files
│   ├── proxies/             # NVENC proxy videos
│   └── keyframes/           # Extracted video frames
├── exports/                 # Final rendered videos
└── data/vector/             # SQLite vector database (SigLIP embeddings)
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| GUI | PySide6 (Qt 6.8+) |
| Database | SQLAlchemy + SQLite |
| Vector Search | SQLite + numpy (cosine similarity) |
| Timeline | OpenTimelineIO (OTIO) |
| Beat Detection | beat_this (CPJKU, GPU) |
| Stem Separation | Demucs `htdemucs_ft` |
| Optical Flow | RAFT (torchvision) |
| Visual Embeddings | SigLIP-so400m-patch14-384 |
| Local LLM | Gemma 4 (Ollama) |
| Video Processing | FFmpeg + OpenCV + PySceneDetect |
| Audio Analysis | librosa |

---

## Development

### Run tests

```bash
poetry run pytest tests/
```

### Database

The SQLite database is stored at `pb_studio.db` in the project root. It is auto-created on first launch via `init_db()`.

To reset the database, delete `pb_studio.db` and restart the application.

### Studio Brain Pipeline (D-023)

The Studio Brain RL-Pacing-Pipeline is implemented but **off by default** — Reward-Weights need to be tuned against your aesthetic preference first. Workflow:

1. Activate the pipeline before launching:
   ```powershell
   $env:PB_USE_STUDIO_BRAIN_PIPELINE = "1"
   python start_pb_studio.py
   ```
2. Import an audio track + video clips, run analysis, run Auto-Edit. The pipeline writes one row per cut to `mem_decision`.
3. Open Studio Brain → tab **Pacing-Explorer**, label cuts with 👍 / 👎 (target: 30+ cuts).
4. Export the labeled cuts to JSON:
   ```bash
   python scripts/build_pacing_truth_set.py
   ```
5. Tune the reward weights:
   ```bash
   python scripts/tune_pacing_reward.py
   ```
6. Verify with A/B-Run (`services/pacing/ab_runner.py`) before flipping the default flag.

See `wiki/synthesis/truth-set-workflow-2026-04-28.md` in the Brain-Bug vault for the full guide.

---

## License

Private project — not yet licensed for public distribution.

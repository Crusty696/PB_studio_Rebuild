---
related_bugs:
---
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
- Per-scene visual embeddings: legacy SigLIP-1 1152-dim in the current video pipeline; Brain V3 uses SigLIP-2 768-dim in project-local sqlite-vec storage
- Numpy-vectorized semantic clip search
- Keyframe extraction for preview

### Waveform & Beatgrid Editor
- Rekordbox-style frequency waveform (Bass/Mid/High color bands)
- Beatgrid overlay with level-of-detail rendering
- Manual beat-to-clip anchor markers

### Multi-Agent Chat
- Built-in AI chat dock connected to the entire action system
- Routes requests to specialized agents: Pacing, Vision, Audio, Editor
- Powered by local Ollama models when available, with `gemma3:4b` as default fallback and Qwen tool-use models preferred when installed
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
| Python | 3.10 via conda env `pb-studio` |
| CUDA GPU | Required: NVIDIA GTX 1060 6GB / CUDA `cuda:0` target |
| CUDA stack | PyTorch `1.12.1+cu113`, CUDA 11.3 wheels |
| FFmpeg | In `bin/` (preferred) or on system PATH |
| Conda | Miniconda/Anaconda, `environment.yml` |

> **Note:** CPU-only mode is not supported. The pipeline is designed for GPU acceleration.

---

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd pb-studio-rebuild
```

### 2. Create/update the conda environment

Recommended on Windows:

```bat
setup_pb_studio.bat
```

Manual equivalent:

```powershell
conda env create -f environment.yml
conda activate pb-studio
python scripts/setup_py310_gpu.py --skip-venv
```

`environment.yml` installs Python 3.10 and pip dependencies from `requirements-py310-cu113.txt`. The setup helper also installs `vendor/beat_this` and checks FFmpeg/Ollama/model prerequisites.

`requirements-py310-cu113.txt` is the active GTX-1060 setup path. `requirements.txt` is retained only as a legacy/future Python 3.11+cu124 reference and must not be used for the current CUDA 11.3 target machine.

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
HF_TOKEN=your_huggingface_token_here
```

A Hugging Face token is required to download gated models (e.g., Demucs, SigLIP).

### 4. Run the application

```bat
start_pb_studio.bat
```

Alternative:

```powershell
python start_pb_studio.py
```

---

## First Steps

The app uses 4 top tabs: **PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT** (SCHNITT replaces the legacy AUTO-SCHNITT + REVIEW tabs since 2026-05-09).

1. **PROJEKT** — Create a new project or open an existing one.
2. **MATERIAL & ANALYSE** — Import audio (MP3/WAV/FLAC) and video clips (MP4/MOV). Run beat detection, stem separation (Demucs Vocals/Drums/Bass/Other), and per-clip video analysis (scene detection + RAFT motion + SigLIP embeddings).
3. **SCHNITT** — Empty state shows preset buttons (Techno/Cinematic/House/Festival). Pick one to trigger Auto-Edit. Editor state has 4 sub-tabs:
   - *Schnitt* — Preview + Transport + InteractiveTimeline with per-clip Lock-icons (locked clips survive Re-Generate).
   - *Pacing & Anker* — PacingCurve, Cut-Rate, Style, Reactivity, Vibe, Anchor list, Re-Generate button (with confirm dialog).
   - *Audio* — Waveform with beatgrid + structure markers (Intro/Drop/Outro/Buildup/Breakdown), Stems mixer, LUFS + Tonart.
   - *RL & Notes* — RL feedback (👍/👎) + Markdown notes editor with auto-save (1 s debounce).
4. **EXPORT** — Render the final video (LUFS-normalized, NVENC).

---

## Project Structure

```
pb-studio-rebuild/
├── main.py                  # Application entry point, Qt app, background workers
├── database/                # SQLAlchemy ORM schema, sessions, migrations
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
│   ├── superpowers/         # Active implementation plans, specs, synthesis
│   └── user/                # User-facing guides
├── storage/                 # Runtime output (auto-created)
│   ├── stems/               # Demucs stem files
│   ├── proxies/             # NVENC proxy videos
│   └── keyframes/           # Extracted video frames
├── exports/                 # Final rendered videos
└── data/vector/             # Legacy vector data (runtime/project data is DB-backed)
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| GUI | PySide6 (Qt 6.6–6.7, pinned `<6.8` for CUDA 11.3 compat) |
| Database | SQLAlchemy + SQLite |
| Vector Search | SQLite + numpy (cosine similarity) |
| Timeline | OpenTimelineIO (OTIO) |
| Beat Detection | beat_this (CPJKU, GPU) |
| Stem Separation | Demucs `htdemucs_ft` |
| Optical Flow | RAFT (torchvision) |
| Visual Embeddings | Legacy SigLIP-1 1152-dim + Brain V3 SigLIP-2 768-dim |
| Local LLM | Ollama auto-detect, default fallback `gemma3:4b`, Qwen tool-use models preferred |
| Video Processing | FFmpeg + OpenCV + PySceneDetect |
| Audio Analysis | librosa |

---

## Development

### Run tests

```bat
run_pytest_schnitt.bat
run_pytest_brain_v3.bat
```

Manual:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest tests -q
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

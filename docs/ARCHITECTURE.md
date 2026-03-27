# PB Studio — Architecture Overview

This document explains how PB Studio works under the hood: what the key folders contain, how data flows through the system, and how the "Smart Director" connects audio beats to video motion.

---

## Folder Overview

### `main.py` + `ui/mixins/` — The Application Shell

The entry point (`main.py`, ~1000 lines) plus 8 mixin modules (`ui/mixins/`). Together they do three things:

1. **Creates the Qt application** and builds the 5-tab workspace (MEDIA / EDIT / STEMS / CONVERT / DELIVER), styled after DaVinci Resolve. The `PBWindow` class uses multiple inheritance from 8 mixins (`AudioAnalysisMixin`, `VideoAnalysisMixin`, `EditWorkspaceMixin`, `ImportMediaMixin`, `ConvertMixin`, `ExportMixin`, `StemsMixin`, `SearchMixin`).
2. **Owns all background threads** via a `GlobalTaskManager` singleton. Every heavy operation (beat analysis, stem separation, video analysis, export) runs in its own `QThread` so the UI never freezes.
3. **Implements the Command Pattern**: AI agents don't touch threads directly. Instead, they emit a signal with an action name (e.g., `"analyze_audio"`). The `GlobalTaskManager` receives this signal on the main thread, looks up the right worker class in its registry, creates it, and starts it.

### `database.py` — What Gets Saved

A single SQLite file (`pb_studio.db`), managed via SQLAlchemy ORM. The key tables are:

| Table | What it stores |
|---|---|
| `Project` | Name, resolution, FPS — the container for everything |
| `AudioTrack` | File path, BPM, key, stem file paths (after Demucs) |
| `VideoClip` | File path, proxy path, duration, resolution |
| `Beatgrid` | Beat timestamps, downbeat positions, energy per beat |
| `WaveformData` | Per-sample amplitude split into Bass/Mid/High bands |
| `Scene` | Scene boundaries detected in a video clip |
| `TimelineEntry` | A clip placed on the timeline: start time, end time, crossfade duration |
| `AIPacingMemory` | Learned cut decisions — what audio context led to which cut |
| `ClipAnchor` | A manual sync marker pinned to a specific beat |

### `agents/` — The AI Decision Layer

Four specialized agents handle different kinds of requests from the chat dock:

- **`orchestrator_agent.py`** — The router. Reads the user's text and decides which agent handles it. If the request involves multiple steps (e.g., "analyze everything and then auto-edit"), it coordinates the sequence.
- **`pacing_agent.py`** — The core creative brain. Knows the PhD-level rules for beat-synchronized editing (see `docs/pacing_logic_phd.md`). Handles all requests about cut timing, drops, buildups, and clip selection.
- **`audio_agent.py`** — Handles audio-specific tasks: transcription (Whisper), stem separation (Demucs), and librosa analysis.
- **`vision_agent.py`** — Handles video-specific tasks: scene detection, motion scoring, and visual content descriptions (Moondream2).

Agents are plain Python objects — no Qt inheritance. They communicate with the rest of the app only through the action registry.

### `services/` — Where the Work Happens

Each service is a focused module for one kind of processing:

| Service | What it does |
|---|---|
| `pacing_service.py` | The auto-edit algorithm: takes a beatgrid + video clips, returns a list of timeline segments |
| `ai_audio_service.py` | Runs Demucs stem separation (chunked, 30s blocks) and extracts frequency bands |
| `beat_analysis_service.py` | Runs `beat_this` on GPU to get beat timestamps and energy per beat |
| `video_analysis_service.py` | Runs PySceneDetect, RAFT optical flow, and SigLIP embeddings |
| `model_manager.py` | Ensures only one AI model is loaded in GPU memory at a time |
| `export_service.py` | Builds an FFmpeg filterchain from timeline entries and renders the final MP4 |
| `convert_service.py` | Generates NVENC proxy files for smooth playback during editing |
| `local_agent_service.py` | Runs the local Qwen 0.5B LLM for offline AI inference |
| `vector_db_service.py` | Stores and queries SigLIP embeddings in LanceDB for semantic clip search |
| `register_actions.py` | Registers ~30 callable actions that agents and the UI can trigger by name |

### `ui/` — The Interface

- **`chat_dock.py`** — A floating chat panel. Sends user text to the Orchestrator agent, displays responses, and shows the action being performed.
- **`waveform_item.py`** — A Qt canvas item that draws the Rekordbox-style waveform: blue for bass, pink for mids, white for highs, with a beatgrid overlay.
- **`widgets/stem_workspace.py`** — The stem mixing panel where you adjust per-stem volume sliders before export.

### `docs/` — Specifications

- **`ARCHITECTURE.md`** — This file.
- **`pacing_logic_phd.md`** — The full mathematical specification of the pacing algorithm, including formulas, axioms, and the macro-structure detection system.

---

## How the Smart Director Works

The "Smart Director" is the name for the pipeline that connects audio beats to video clips. Here is what happens when you click **Auto-Edit**:

### Step 1: Audio Analysis

`beat_analysis_service.py` loads your audio and runs `beat_this` on the GPU. The output is:
- A list of **beat timestamps** (e.g., every 0.5 seconds at 120 BPM)
- A list of **downbeat timestamps** (every 4th beat = one bar)
- An **energy value per beat** (0.0 to 1.0, derived from RMS amplitude)

These are stored in the `Beatgrid` table.

### Step 2: Stem Separation

`ai_audio_service.py` runs Demucs on your audio and splits it into four stems:
- **Drums** — used as cut triggers
- **Bass** — used to detect drops (sudden RMS increase)
- **Vocals** — used to slow down cutting when a singer is active
- **Other** — used as a mood indicator

Each stem is saved to `storage/stems/` and referenced in `AudioTrack`.

### Step 3: Video Analysis

`video_analysis_service.py` processes each video clip:
1. PySceneDetect splits the clip into scenes at content-change boundaries
2. RAFT (optical flow) scores each scene from 0.0 (static) to 1.0 (high motion)
3. SigLIP generates a 1152-dimensional visual embedding for each scene's keyframe
4. Embeddings are stored in LanceDB for later semantic search

### Step 4: Macro-Structure Detection

`pacing_service.py` reads the beatgrid and detects the overall shape of the track:

```
WARMUP → BUILDUP → DROP → BREAKDOWN → TRANSITION → COOLDOWN
```

Each section gets a label and a base cut-rate multiplier. Drops get the fastest cutting, breakdowns get the slowest.

### Step 5: Dynamic Cut-Rate Calculation

For each beat, the engine calculates `S_eff` — the effective cut rate in beats:

```
S_eff = S_base × energy_modifier × reactivity × section_modifier
```

Where:
- `S_base` — the user-chosen base rate (1, 2, 4, 8, or 16 beats between cuts)
- `energy_modifier` — higher energy → more frequent cuts
- `reactivity` — user-controlled sensitivity (0–100%)
- `section_modifier` — DROP = 0.5× (cut faster), BREAKDOWN = 2× (cut slower)

If a vocal stem is active, `S_eff` is multiplied by 2 (cut less aggressively).

### Step 6: Video Clip Matching

At each cut point, the engine selects the best video scene by scoring candidates:

```
score = 0.6 × motion_match + 0.4 × semantic_similarity
```

- **`motion_match`**: How well the scene's RAFT motion score matches the audio energy at this beat
- **`semantic_similarity`**: How similar the scene's SigLIP embedding is to the search context (the user's "vibe" keyword if set, or the section label)

Manual anchors (clips pinned to specific beats) always win over the algorithm.

### Step 7: Timeline Assembly

The engine writes `TimelineEntry` rows to the database: one per cut, each with a start time, end time, source offset, and crossfade duration. The EDIT tab reads these to display the timeline.

### Step 8: Export

`export_service.py` reads all `TimelineEntry` rows and builds an FFmpeg filterchain:
- Each clip is trimmed to its source offsets
- Crossfades are applied between adjacent clips
- The audio track is normalized to a target LUFS level
- The result is rendered to `exports/<project_name>.mp4`

---

## Threading Model

All heavy processing runs off the main thread:

```
User action / Agent signal
        │
        ▼
GlobalTaskManager (main thread)
        │  creates Worker + QThread
        ▼
Worker.run() ──► service function (GPU/CPU)
        │
        ▼ finished signal (back to main thread)
UI update / DB write
```

The `ModelManager` singleton ensures that only one AI model is in GPU memory at any time. Before loading a new model, it unloads the current one and calls `cuda.empty_cache()`.

---

## Human-in-the-Loop Learning

When you manually move or trim a clip in the EDIT tab, PB Studio records the decision in the `AIPacingMemory` table:

- What was the audio context? (BPM, bass energy, drum energy, mood, section type)
- What was the video context? (RAFT motion score, SigLIP tags)
- What cut decision did you make? (cut type, crossfade duration)

The next time the Smart Director runs, it retrieves similar past decisions from `AIPacingMemory` and biases its clip selection accordingly. Over time, the system learns your editing style.

---

## Data Flow Summary

```
Audio File ──► beat_this ──► Beatgrid (DB)
           └──► Demucs ───► Stems (filesystem) ──► AudioTrack (DB)

Video File ──► SceneDetect ──► Scenes (DB)
           ├──► RAFT ────────► motion scores (DB)
           └──► SigLIP ──────► embeddings (LanceDB)

Beatgrid + Stems + Scenes + Embeddings
           └──► pacing_service.auto_edit_phase3()
                    └──► TimelineEntry rows (DB)
                              └──► export_service.export_timeline()
                                        └──► final MP4 (exports/)
```

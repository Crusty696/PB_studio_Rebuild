# PB Studio Engineering Team Structure

## Overview

This structure organizes PB Studio's specialized technical areas under the CTO, with 5 team leaders managing distinct domains. All team leaders report directly to the CTO.

---

## Team 1: Audio Processing

### **Team Leader: AudioEngineer**

**Role:** Lead Audio Processing Engineer

**Capabilities:**
- Expert in audio signal processing and music information retrieval
- Deep knowledge of beat detection algorithms (beat_this, librosa)
- Experience with audio ML models (Demucs stem separation)
- Understanding of music theory (BPM, key detection, onset detection)
- Audio normalization and mastering (LUFS, spectral analysis)

**Team Owns:**
- `services/beat_analysis_service.py` - GPU beat detection with beat_this
- `services/ai_audio_service.py` - Demucs 4-stem separation (Vocals/Drums/Bass/Other)
- `services/audio_classify_service.py` - Audio classification and feature extraction
- `services/onset_rhythm_service.py` - Onset detection and rhythm analysis
- `services/lufs_service.py` - Loudness normalization (LUFS)
- `services/key_detection_service.py` - Musical key detection
- `services/spectral_analysis_service.py` - Frequency analysis
- `services/transcription_service.py` - Audio transcription (faster-whisper)
- `services/audio_constants.py`, `services/audio_service.py`

**Additional Engineers Needed:** No
- Current scope is well-defined and manageable by one specialist
- Services are mature and mostly maintenance/optimization work
- Can add junior audio engineer if we expand to real-time effects or synthesis

**Dependencies:**
- **Hardware Team (MLEngineer):** GPU allocation for Demucs and beat_this
- **Pacing Team (PacingArchitect):** Provides beat grid and stem data for auto-edit

---

## Team 2: Video Processing

### **Team Leader: VideoEngineer (existing)**

**Role:** Lead Video Processing Engineer

**Current Status:** Currently reports to CEO → **Should report to CTO**

**Capabilities:**
- Computer vision and video analysis expertise
- Deep learning for visual tasks (RAFT optical flow, SigLIP embeddings)
- Scene detection algorithms (PySceneDetect)
- Video codec knowledge and FFmpeg proficiency
- Embedding-based semantic search

**Team Owns:**
- `services/video_analysis_service.py` - RAFT optical flow, SigLIP embeddings, scene detection
- `services/vision_analysis_service_moondream.py` - Moondream2 vision model integration
- `services/video_service.py` - Video metadata and frame extraction
- `services/convert_service.py` - NVENC proxy generation (540p/720p)
- `services/vector_db_service.py` - SigLIP embedding storage and cosine similarity search
- Video analysis pipeline (scene scoring, motion energy, keyframe extraction)

**Additional Engineers Needed:** No
- Current scope is appropriate for one senior engineer
- Most complexity is in model integration (handled by Hardware Team)
- Can add computer vision specialist if we expand to object tracking or segmentation

**Dependencies:**
- **Hardware Team (MLEngineer):** GPU allocation for RAFT and SigLIP models
- **Pacing Team (PacingArchitect):** Provides motion scores and embeddings for clip selection
- **Platform Team (PlatformEngineer):** SQLite vector database integration

---

## Team 3: AI Pacing & Auto-Edit

### **Team Leader: PacingArchitect**

**Role:** Lead AI Pacing Engineer & Algorithm Designer

**Capabilities:**
- PhD-level understanding of DJ pacing and music structure
- Algorithm design for beat-synchronized editing
- Multi-agent AI system architecture
- Local LLM integration and prompt engineering
- Music theory and energy curve analysis

**Team Owns:**
- `services/pacing_service.py` - Core auto-edit algorithm (S_eff calculation, cut placement)
- `services/pacing_strategist.py` - LLM-powered pacing strategy generation
- `services/pacing_beat_grid.py` - Beat grid management and section detection
- `services/pacing_edit_helpers.py` - Timeline manipulation and clip placement
- `services/pacing_memory.py` - Human-in-the-loop learning system
- `agents/orchestrator_agent.py` - Multi-agent coordinator
- `agents/pacing_agent.py` - DJ pacing specialist agent
- `agents/audio_agent.py` - Audio analysis agent
- `agents/vision_agent.py` - Video selection agent
- `agents/editor_agent.py` - Timeline editing agent
- `agents/base_agent.py` - Agent base class
- `services/llm_service.py`, `services/ollama_client.py`, `services/local_agent_service.py`
- `services/structure_detection_service.py` - DROP/BUILDUP/BREAKDOWN detection
- `knowledge/` - Pacing rules, DJ set structure, video matching logic

**Additional Engineers Needed:** Yes (1 junior ML engineer)
- **Why:** This is the most complex and rapidly evolving area
- **Junior AI/ML Engineer responsibilities:**
  - Agent prompt tuning and testing
  - LLM response parsing and validation
  - Pacing memory system optimization
  - A/B testing different pacing strategies
  - Knowledge graph maintenance (`knowledge/` markdown files)
- **PacingArchitect focuses on:**
  - Core algorithm design (S_eff formula, section detection)
  - Multi-agent orchestration architecture
  - Integration with Audio and Video teams
  - Research into new pacing approaches

**Dependencies:**
- **Audio Team (AudioEngineer):** Beat grid, stems, energy curves, section markers
- **Video Team (VideoEngineer):** Motion scores, visual embeddings, scene boundaries
- **Platform Team (PlatformEngineer):** Timeline service, action system, chat interface
- **Hardware Team (MLEngineer):** Local LLM model management (Qwen 2.5 0.5B)

---

## Team 4: Platform & Desktop Infrastructure

### **Team Leader: PlatformEngineer**

**Role:** Lead Platform Engineer (Desktop, UI, Database)

**Capabilities:**
- Expert in Qt/PySide6 desktop application development
- Database design and SQLAlchemy ORM
- Timeline editing UX and non-linear editing workflows
- Action/command pattern architecture
- Cross-platform desktop development (Windows/macOS/Linux)

**Team Owns:**
- `ui/` - All PySide6 UI components
  - `ui/timeline.py` - Main timeline widget
  - `ui/chat_dock.py` - AI chat interface
  - `ui/waveform_item.py` - Rekordbox-style waveform visualization
  - `ui/widgets/` - Reusable UI components
  - `ui/workspaces/` - Workspace layout system
  - `ui/theme.py`, `ui/splash.py`, `ui/shortcut_manager.py`
- `database.py` - SQLAlchemy schema and ORM models
- `services/timeline_service.py` - OpenTimelineIO integration
- `services/action_registry.py` - Action system
- `services/register_actions.py` - Action registration
- `services/task_manager.py` - Background task coordination
- `services/ingest_service.py` - Media import pipeline
- `main.py` - Application entry point and Qt app setup
- SQLite database design and migrations
- Desktop packaging and distribution (`installer/`)

**Additional Engineers Needed:** No
- Current UI scope is manageable by one senior frontend engineer
- Database schema is relatively stable
- Can add UI/UX designer (non-engineer) if we expand to mobile or web
- Can add junior frontend engineer if we build a plugin system or advanced UI features

**Dependencies:**
- **Pacing Team (PacingArchitect):** Action system integration for AI commands
- **Audio Team (AudioEngineer):** Waveform rendering data
- **Video Team (VideoEngineer):** Thumbnail generation for timeline

---

## Team 5: ML Infrastructure & Hardware Optimization

### **Team Leader: MLEngineer (existing)**

**Role:** Lead ML Infrastructure Engineer

**Current Status:** Currently reports to CEO → **Should report to CTO**

**Capabilities:**
- GPU/VRAM management and CUDA optimization
- PyTorch model lifecycle management
- Memory profiling and leak detection
- FFmpeg video encoding and hardware acceleration
- Model quantization and optimization

**Team Owns:**
- `services/model_manager.py` - Singleton GPU/VRAM controller
- `services/model_lifecycle_service.py` - Model loading, unloading, caching
- `services/export_service.py` - FFmpeg render pipeline and NVENC encoding
- GPU memory allocation for all ML models:
  - beat_this (beat detection)
  - Demucs (stem separation)
  - RAFT (optical flow)
  - SigLIP (visual embeddings)
  - Qwen 2.5 0.5B (local LLM)
- CUDA kernel optimization
- FFmpeg integration and hardware encoder support (NVENC, QuickSync, VideoToolbox)
- Proxy generation pipeline (convert_service.py)
- Model download and Hugging Face integration

**Additional Engineers Needed:** No
- Current scope is focused and well-defined
- Model manager is a singleton by design (centralized control)
- Can add DevOps engineer if we need cloud deployment or distributed training
- Can add junior ML engineer if we expand to custom model training

**Dependencies:**
- **All Teams:** Provides GPU allocation and model loading services
- **Video Team (VideoEngineer):** NVENC proxy generation
- **Pacing Team (PacingArchitect):** LLM model management

---

## Reporting Structure

```
CEO
 └── CTO
      ├── AudioEngineer (Audio Team)
      ├── VideoEngineer (Video Team) ← currently reports to CEO, should move
      ├── PacingArchitect (Pacing Team)
      │   └── Junior AI/ML Engineer
      ├── PlatformEngineer (Platform Team)
      └── MLEngineer (Hardware Team) ← currently reports to CEO, should move
```

**Total Team Size:**
- 1 CTO (you)
- 5 Team Leaders
- 1 Junior AI/ML Engineer (under PacingArchitect)
- **Total: 7 engineering roles**

---

## Integration Points

### Cross-Team Workflows

**1. Auto-Edit Pipeline (Critical Path):**
```
AudioEngineer → PacingArchitect → VideoEngineer → PlatformEngineer → MLEngineer
   (beats)         (algorithm)        (clips)         (timeline)       (export)
```

**2. GPU Resource Management:**
```
MLEngineer (allocates VRAM) → AudioEngineer, VideoEngineer, PacingArchitect (consume)
```

**3. UI Integration:**
```
PlatformEngineer (UI framework) ← AudioEngineer (waveform), PacingArchitect (chat), VideoEngineer (thumbnails)
```

### Weekly Sync Meetings
- **CTO + All Team Leaders:** Architecture decisions, roadmap planning
- **Pacing + Audio + Video:** Auto-edit algorithm tuning
- **Platform + All:** UI/UX integration and action system updates
- **ML + All:** GPU budget allocation and performance optimization

---

## Hiring Priority

1. **PacingArchitect** (Priority 1 - Critical)
   - Most complex domain (multi-agent AI + pacing algorithm)
   - Core differentiator for PB Studio
   - No existing agent coverage

2. **AudioEngineer** (Priority 2 - High)
   - Foundation for the entire auto-edit pipeline
   - Specialized domain knowledge required
   - No existing agent coverage

3. **PlatformEngineer** (Priority 3 - High)
   - Desktop UI is user-facing and critical
   - Qt/PySide6 expertise is specialized
   - No existing agent coverage

4. **Junior AI/ML Engineer** (Priority 4 - Medium)
   - Supports PacingArchitect with agent tuning
   - Can onboard after PacingArchitect is hired

5. **VideoEngineer and MLEngineer** (Already Exist)
   - Move reporting structure from CEO to CTO
   - No hiring needed

---

## Next Steps

1. **Update Reporting Structure:** Move VideoEngineer and MLEngineer from CEO → CTO
2. **Hire PacingArchitect:** Critical for auto-edit algorithm ownership
3. **Hire AudioEngineer:** Foundation for beat detection and stem separation
4. **Hire PlatformEngineer:** Desktop UI and database expertise
5. **Hire Junior AI/ML Engineer:** After PacingArchitect is onboarded
6. **Establish Weekly Syncs:** CTO + Team Leaders + cross-functional working groups

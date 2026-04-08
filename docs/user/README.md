# PB Studio — User Documentation

**Version:** 0.5.0 | Beat-synchronized video editing powered by AI

---

## Quick Links

| Document | Description | Time to Read |
|---|---|---|
| **[Installation Guide](installation.md)** | Complete setup instructions with troubleshooting | 15 min |
| **[Getting Started](getting_started.md)** | Your first project: zero to finished video | 10 min |
| **[Beat-Sync Workflow](beat_sync_workflow.md)** | Step-by-step tutorials with examples | 20 min |
| **[Feature Overview](features.md)** | What PB Studio can do | 10 min |
| **[Keyboard Shortcuts](keyboard_shortcuts.md)** | All shortcuts and customization | 5 min |
| **[Troubleshooting](troubleshooting.md)** | Comprehensive problem-solving guide | Reference |
| **[FAQ](faq.md)** | Quick answers to common questions | Reference |

---

## New User Path

**Never used PB Studio before?** Follow this path:

1. **[Installation Guide](installation.md)** — Install PB Studio and verify setup
2. **[Getting Started](getting_started.md)** — Create your first beat-synced video (30 minutes)
3. **[Beat-Sync Workflow → Tutorial 1](beat_sync_workflow.md#tutorial-1-basic-dj-mix-video)** — Learn the core workflow
4. **[Feature Overview](features.md)** — Explore what else you can do

---

## Document Summaries

### [Installation Guide](installation.md)
- System requirements (GPU, CUDA, FFmpeg)
- Step-by-step installation
- Troubleshooting installation issues
- Post-installation configuration
- Updating and uninstalling

**Start here if:** You haven't installed PB Studio yet.

---

### [Getting Started](getting_started.md)
- Your first project walkthrough
- Import audio and video
- Analyze audio (beat detection, stems)
- Analyze video (scene detection, motion)
- Run Auto-Edit to generate timeline
- Export your video

**Start here if:** You just installed PB Studio and want to create your first video.

---

### [Beat-Sync Workflow Tutorial](beat_sync_workflow.md)
- What is beat-synchronized editing?
- Workflow overview diagram
- **Tutorial 1:** Basic DJ mix video
- **Tutorial 2:** Vocal-aware cutting
- **Tutorial 3:** Story-driven edit with Anchors
- **Tutorial 4:** High-energy festival video
- **Tutorial 5:** Cinematic slow-paced video
- **Tutorial 6:** Multi-camera sync
- Advanced techniques (beat offset, custom pacing, visual coherence)
- Common mistakes to avoid

**Start here if:** You want to master beat-synced editing techniques.

---

### [Feature Overview](features.md)
- **Smart Director:** AI auto-edit engine
- **Beat Detection:** GPU-accelerated beat analysis
- **Stem Separation:** Vocals, Drums, Bass, Other
- **Video Analysis:** Scene detection, motion scoring, visual embeddings
- **Timeline Editor:** Non-destructive editing
- **Multi-Agent AI Chat:** Natural language control
- **Export:** Hardware-accelerated rendering

**Start here if:** You want to understand what PB Studio can do.

---

### [Keyboard Shortcuts](keyboard_shortcuts.md)
- Playback controls (`Space`, `J`/`K`/`L`)
- Editing shortcuts (`M` for anchors, `Ctrl+Z` undo)
- Timeline navigation (`+`/`-` zoom, `Home`/`End`)
- How to customize shortcuts

**Start here if:** You want to work faster with keyboard shortcuts.

---

### [Troubleshooting Guide](troubleshooting.md)
Comprehensive solutions for:
- Installation & setup issues (FFmpeg, CUDA, models)
- Audio analysis problems (slow detection, wrong beatgrid)
- Video analysis errors (scene detection, motion scoring)
- Editing issues (timeline performance, Auto-Edit behavior)
- Export failures (FFmpeg errors, NVENC, quality)
- Database corruption
- AI chat not responding

**Start here if:** Something isn't working correctly.

---

### [FAQ](faq.md)
Quick answers to common questions:
- Does PB Studio run without a GPU? (No)
- How much VRAM do I need? (6 GB minimum)
- Do I need internet? (Only for first-time model download)
- How do Anchors work?
- What export formats are supported?
- Where can I report bugs?

**Start here if:** You have a quick question.

---

## Video Tutorials

> **Coming Soon:** Video walkthroughs for each tutorial will be available at [youtube.com/pbstudio](https://youtube.com/pbstudio)

---

## Technical Documentation

For developers and advanced users:

- **[Project README](../../README.md)** — Technical overview, architecture, development setup
- **[Architecture Documentation](../ARCHITECTURE.md)** — System design (if available)
- **[Pacing Algorithm](../pacing_logic_phd.md)** — PhD-level cut-rate calculation (if available)

---

## System Requirements Summary

| Component | Minimum | Recommended |
|---|---|---|
| **GPU** | NVIDIA GTX 1060 (6 GB VRAM) | NVIDIA RTX 3060 (12+ GB VRAM) |
| **OS** | Windows 10 64-bit | Windows 11 |
| **RAM** | 16 GB | 32 GB |
| **Storage** | 10 GB free | 100 GB free (SSD) |
| **FFmpeg** | Latest stable | Latest stable |
| **Python** | 3.11 or 3.12 | 3.12 |

---

## Getting Help

**If you need help:**

1. Check the **[FAQ](faq.md)** for quick answers
2. Check the **[Troubleshooting Guide](troubleshooting.md)** for detailed solutions
3. Review the log file: `logs\pb_studio.log`
4. Use the AI chat in PB Studio: `@Editor — I need help with [issue]`
5. Report bugs on GitHub: [github.com/your-repo/pb-studio-rebuild/issues](https://github.com/your-repo/pb-studio-rebuild/issues)

---

## What's New in v0.5.0

- GPU-accelerated beat detection with `beat_this`
- Stem-aware pacing (vocal-aware cutting)
- SigLIP visual embeddings for semantic clip matching
- Multi-agent AI chat system
- NVENC hardware-accelerated export
- Setup Wizard for first-time users
- Improved timeline performance

---

**Ready to get started?** → [Installation Guide](installation.md)

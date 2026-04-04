# Frequently Asked Questions

## Installation & Setup

**Q: Does PB Studio run without a GPU?**
No. The pipeline relies on CUDA-accelerated models (beat_this, RAFT, SigLIP, Demucs). A minimum of 6 GB VRAM is recommended. CPU-only mode is not supported.

---

**Q: The app says "FFmpeg not found" on startup.**
FFmpeg must be on your system PATH. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org), extract it, and add the `bin/` folder to your Windows `PATH` environment variable. Restart PB Studio after.

---

**Q: Do I need a Hugging Face token?**
Yes, for the first run only. The token is required to download gated models (Demucs, SigLIP). After the models are cached locally, the token is no longer needed for offline use. Get a free token at huggingface.co.

---

**Q: How much VRAM does PB Studio need?**
- Beat detection (beat_this): ~1 GB
- Stem separation (Demucs): ~4 GB
- Video analysis (RAFT + SigLIP): ~3–4 GB

PB Studio's ModelManager loads and unloads models automatically to stay within your VRAM budget. You can set a VRAM limit in **Settings → Performance**.

---

**Q: The Setup Wizard shows a warning about a missing model.**
On first launch, models are downloaded from Hugging Face. This requires an internet connection and can take several minutes depending on your connection speed. After the first download, the app works fully offline.

---

## Audio Analysis

**Q: Beat detection is slow. How long should it take?**
A 5-minute track typically takes 10–30 seconds on a modern NVIDIA GPU. If it takes much longer, check that CUDA is active (Status bar shows GPU usage during analysis).

---

**Q: The beatgrid looks wrong — beats are off.**
Beat detection is based on neural networks and works best on music with a clear pulse. For unusual time signatures or very ambient tracks, the grid may be imprecise. You can manually adjust anchor points in the waveform editor to correct the auto-edit result.

---

**Q: Stem separation is taking very long.**
Demucs `htdemucs_ft` processes audio on the GPU. For a 5-minute track expect 1–3 minutes. If it is much slower, the model may have fallen back to CPU processing — check that CUDA is available and that another process is not consuming all VRAM.

---

## Video Analysis

**Q: Video analysis finished but the clips look wrong in the timeline.**
Try re-running analysis on the affected clips. If the issue persists, check that FFmpeg can read the file format. Some high-bitrate formats (e.g., Sony XAVC) may require a specific FFmpeg build.

---

**Q: Can I skip video analysis?**
You can, but clip selection will be random rather than content-aware. The Smart Director needs motion scores and visual embeddings to match clips intelligently to the audio.

---

## Editing

**Q: How do Anchors work?**
Select a clip in the timeline and press `M`. The clip is "pinned" to its current beat position. When you run Auto-Edit again, the Smart Director treats anchored clips as fixed and fills the gaps around them. This lets you keep manually chosen clips while letting the AI handle the rest.

---

**Q: I made a cut the AI won't repeat. How do I teach it?**
After manually correcting a clip placement, the change is recorded as a session anchor. To persist the learning across future sessions, click **"Learn as AI Rule"** in the clip inspector panel. The system stores the rule in the AIPacingMemory database.

---

**Q: Can I undo auto-edit?**
Yes. Every auto-edit result is a single undoable action. Press `Ctrl+Z` immediately after Auto-Edit to revert to your previous timeline state.

---

**Q: The timeline preview is choppy.**
Enable proxy generation in **Settings → Performance**. PB Studio will create 540p or 720p proxy clips using NVENC hardware encoding. The proxy clips are used during preview; the originals are used for final export.

---

## Export

**Q: What export formats are supported?**
H.264, H.265 (HEVC), and VP9. NVENC hardware acceleration is used automatically when available for H.264 and H.265.

---

**Q: What does LUFS normalization do?**
LUFS (Loudness Units Full Scale) is the standard for measuring perceptual loudness. PB Studio normalizes your exported audio to the target level so your video sounds consistent with other content on streaming platforms:
- `-14 LUFS` — YouTube, Spotify recommended
- `-16 LUFS` — Podcast standard
- `-23 LUFS` — Broadcast (EBU R128)

---

**Q: Where does the exported file go?**
Exports are saved to the `exports/` folder inside your project directory.

---

## AI Chat

**Q: Does the AI chat require an internet connection?**
No. The chat system uses a local **Qwen 2.5 0.5B** model that runs entirely on your machine. No data leaves your computer.

---

**Q: Which agent should I talk to?**
The Orchestrator agent routes your message automatically. You can also address specific agents directly:
- **@Pacing** — cut timing questions
- **@Audio** — waveform, stems, loudness
- **@Vision** — clip selection, scene content
- **@Editor** — timeline operations, export settings

---

## Troubleshooting

**Q: The app crashes on startup.**
Check the crash log at `logs/pb_studio.log`. Common causes:
- Missing CUDA / outdated GPU driver
- Corrupted model files (delete the Hugging Face cache and re-download)
- Database locked (close any duplicate PB Studio instances)

---

**Q: The database seems corrupted / I want to start fresh.**
Delete `pb_studio.db` from the project root and restart. The database is rebuilt automatically on the next launch. Note: all project history, anchors, and learned AI rules will be lost.

---

**Q: Where can I report bugs?**
Open a GitHub issue in the project repository with:
1. The log file from `logs/pb_studio.log`
2. Your GPU model and VRAM amount
3. Steps to reproduce the issue

# PB Studio — Troubleshooting Guide

**Version:** 0.5.0

Comprehensive troubleshooting for common issues and error messages.

---

## Installation & Setup Issues

### FFmpeg Issues

#### Error: "FFmpeg not found on PATH"

**Cause:** Windows cannot locate the FFmpeg executable.

**Solutions:**
1. Verify FFmpeg location:
   ```bash
   where ffmpeg
   ```
2. Add FFmpeg to PATH:
   - Open System Properties → Environment Variables
   - Edit the system `Path` variable
   - Add `C:\ffmpeg\bin` (or your FFmpeg location)
   - Restart Command Prompt and PB Studio

3. Quick fix: Copy `ffmpeg.exe` to the project directory

#### Error: "FFmpeg process failed with return code 1"

**Cause:** FFmpeg cannot process the input file.

**Solutions:**
1. Check file format compatibility:
   ```bash
   ffprobe your_video.mp4
   ```
2. Try re-encoding the video to a standard format:
   ```bash
   ffmpeg -i input.mov -c:v libx264 -c:a aac output.mp4
   ```
3. Check for special characters in the file path — rename files with simple names

---

### GPU & CUDA Issues

#### Error: "CUDA not available" or "torch.cuda.is_available() returns False"

**Cause:** PyTorch cannot access your GPU.

**Solutions:**
1. Update GPU drivers from [nvidia.com/drivers](https://www.nvidia.com/drivers)
2. Verify CUDA is working:
   ```bash
   nvidia-smi
   ```
3. Reinstall PyTorch with CUDA:
   ```bash
   poetry install --sync
   ```
4. Check for driver conflicts (uninstall old drivers with DDU if needed)

#### Error: "CUDA out of memory"

**Cause:** The GPU ran out of VRAM during processing.

**Solutions:**
1. **Immediate fix:** Close other GPU apps (Chrome, games, video editors)
2. Set a VRAM limit in **Settings → Performance** → **VRAM Limit** (set to 80% of total)
3. Reduce batch sizes:
   - Video analysis: Analyze clips one at a time instead of batch
   - Stem separation: Process shorter audio segments
4. Upgrade GPU (6 GB VRAM is minimum, 8+ GB recommended)

#### Warning: "Model fallback to CPU"

**Cause:** GPU is unavailable or out of memory — processing will be very slow.

**Solutions:**
1. Check GPU availability:
   ```bash
   poetry run python -c "import torch; print(torch.cuda.is_available())"
   ```
2. Free up VRAM by closing other applications
3. Restart PB Studio to reset VRAM allocation

---

### Model Download Issues

#### Error: "HTTP 401: Unauthorized" (Hugging Face)

**Cause:** Invalid or missing Hugging Face token.

**Solutions:**
1. Verify `.env` file exists in project root with:
   ```env
   HF_TOKEN=your_token_here
   ```
2. Check token is valid at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
3. Regenerate token if needed and update `.env`

#### Error: "Failed to download model"

**Cause:** Network issue or Hugging Face service down.

**Solutions:**
1. Check your internet connection
2. Check Hugging Face status: [status.huggingface.co](https://status.huggingface.co)
3. Try downloading manually:
   ```bash
   poetry run python -c "from transformers import AutoModel; AutoModel.from_pretrained('google/siglip-so400m-patch14-384')"
   ```
4. If behind a corporate proxy, configure proxy settings:
   ```bash
   set HTTP_PROXY=http://proxy.company.com:8080
   set HTTPS_PROXY=http://proxy.company.com:8080
   ```

#### Error: "Corrupted model cache"

**Cause:** Model files were partially downloaded or corrupted.

**Solutions:**
1. Delete Hugging Face cache:
   ```bash
   rmdir /s %USERPROFILE%\.cache\huggingface
   ```
2. Restart PB Studio to re-download models

---

## Audio Analysis Issues

### Beat Detection

#### Issue: Beat detection is very slow

**Expected time:** 10–30 seconds for a 5-minute track.

**If slower:**
1. Verify GPU is being used (Status bar shows GPU usage during analysis)
2. Check `torch.cuda.is_available()` returns `True`
3. Close GPU-intensive background apps
4. Check VRAM usage with `nvidia-smi` — if at 100%, close other GPU apps

#### Issue: Beatgrid is offset or incorrect

**Cause:** Neural network beat detection is not perfect, especially for unusual music.

**Solutions:**
1. **Manual correction:** Use Anchors to fix key beats:
   - Select a clip that should hit a drop
   - Press `M` to anchor it
   - Re-run Auto-Edit — the engine works around your anchor
2. **Genre-specific:** Beat detection works best on 4/4 electronic music. Jazz, classical, or ambient may have less accurate grids.
3. Try adjusting the BPM manually in **Audio → Edit BPM** if the tempo is clearly wrong

#### Issue: Macro-sections are wrong (Warmup/Drop/Breakdown detection)

**Cause:** Section detection is based on RMS energy curves and may misclassify ambiguous sections.

**Solutions:**
1. Manually override section boundaries in **Audio → Edit Sections**
2. Use Anchors to force specific clips at section boundaries
3. Provide feedback via the AI chat: `@Pacing — this section at 2:30 should be a Drop, not a Breakdown`

### Stem Separation

#### Issue: Stem separation is very slow or stalls

**Expected time:** 1–3 minutes for a 5-minute track.

**If much slower:**
1. Check GPU usage with `nvidia-smi` — Demucs should be at ~4 GB VRAM
2. If CPU usage is high but GPU usage is low, Demucs fell back to CPU:
   - Verify CUDA is available
   - Restart PB Studio
3. If stalled: Kill the process and try again with a shorter audio clip first (test with 30 seconds)

#### Issue: Stem quality is poor (vocals bleeding into other stems)

**Cause:** Demucs is not perfect, especially for complex mixes.

**Solutions:**
1. Use higher-quality source audio (WAV/FLAC instead of MP3)
2. For critical projects, use professional stem separation tools (iZotope RX, Spleeter) and import stems manually
3. PB Studio's stem-aware pacing can be disabled in **Settings → Audio → Disable Stem-Aware Editing** if stems are unusable

---

## Video Analysis Issues

### Scene Detection

#### Issue: Scenes are not detected or too many scenes

**Cause:** PySceneDetect threshold is too high or too low.

**Solutions:**
1. Adjust scene detection sensitivity in **Settings → Video → Scene Threshold**:
   - **Too few scenes:** Lower threshold (try 25.0 → 20.0)
   - **Too many scenes:** Raise threshold (try 30.0 → 35.0)
2. For clips with gradual fades, scene detection may fail — manually split clips if needed

#### Issue: Video analysis crashes or hangs

**Cause:** RAFT optical flow or SigLIP processing ran out of VRAM.

**Solutions:**
1. Analyze clips one at a time instead of batch
2. Set VRAM limit in **Settings → Performance**
3. Check video file integrity with `ffprobe`:
   ```bash
   ffprobe -v error your_video.mp4
   ```
4. Try a different video format (re-encode with standard H.264)

### Motion Scoring

#### Issue: Motion scores are all 0.0 or very low

**Cause:** RAFT failed to process the video.

**Solutions:**
1. Re-run video analysis
2. Check if the video is static (motion scores will legitimately be 0)
3. Check log file for RAFT errors:
   ```bash
   type logs\pb_studio.log | findstr RAFT
   ```

### Visual Embeddings

#### Issue: "SigLIP embedding failed"

**Cause:** SigLIP model failed to process video frames.

**Solutions:**
1. Verify SigLIP model is downloaded:
   ```bash
   dir %USERPROFILE%\.cache\huggingface\hub | findstr siglip
   ```
2. Re-download SigLIP:
   ```bash
   poetry run python -c "from transformers import AutoModel; AutoModel.from_pretrained('google/siglip-so400m-patch14-384')"
   ```
3. Check VRAM availability — SigLIP needs ~2 GB VRAM

---

## Editing Issues

### Timeline Performance

#### Issue: Timeline preview is choppy or slow

**Solutions:**
1. Enable proxy generation:
   - **Settings → Performance → Proxy Quality** → 720p or 540p
   - Re-analyze video clips to generate proxies
2. Lower playback resolution: **View → Playback Quality → 50%**
3. Reduce timeline zoom level — rendering too many clips at once is slow
4. Close the AI chat dock if not in use

#### Issue: Clips are not loading in the timeline

**Cause:** File paths are invalid or files were moved.

**Solutions:**
1. Check file paths in **Media** tab — missing files show a red warning
2. Re-link missing files: Right-click → **Relink Media** → Browse to new location
3. Check file permissions — PB Studio needs read access to source files

### Auto-Edit Behavior

#### Issue: Auto-Edit does nothing or timeline is empty

**Cause:** Missing prerequisites or no valid clips.

**Solutions:**
1. Verify prerequisites:
   - Audio has been analyzed (beatgrid exists)
   - At least one video clip has been analyzed
2. Check video clip duration — clips shorter than 1 beat may be skipped
3. Check log for errors:
   ```bash
   type logs\pb_studio.log | findstr "Auto-Edit"
   ```

#### Issue: Auto-Edit ignores Anchors

**Cause:** Anchor data is not saved or corrupted.

**Solutions:**
1. Re-apply anchors: Select clip → Press `M`
2. Check Anchor list in **Edit → Show Anchors** — should list pinned beats
3. Database issue: Delete `pb_studio.db` and restart (⚠️ loses project history)

#### Issue: Cuts are not beat-synchronized

**Cause:** Beatgrid is inaccurate or cut alignment is disabled.

**Solutions:**
1. Re-run audio analysis
2. Enable snap-to-beat in **Edit → Snap to Grid**
3. Manually adjust beat alignment in the waveform editor

---

## Export Issues

### Rendering Failures

#### Error: "FFmpeg encoding failed"

**Cause:** FFmpeg cannot write the output file.

**Solutions:**
1. Check output path exists and has write permissions
2. Check disk space — exports can be several GB
3. Try a different codec:
   - H.264 instead of H.265
   - Disable NVENC if GPU encoder fails
4. Check log for FFmpeg error:
   ```bash
   type logs\pb_studio.log | findstr ffmpeg
   ```

#### Error: "NVENC not available"

**Cause:** GPU does not support NVENC or drivers are outdated.

**Solutions:**
1. Update GPU drivers
2. Use CPU encoding: **Deliver → Export Settings → Codec → H.264 (CPU)**
3. Check GPU NVENC support: [developer.nvidia.com/video-encode-and-decode-gpu-support-matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix)

#### Issue: Export is very slow

**Expected time:** 1–5× real-time depending on codec and effects.

**If much slower:**
1. Use NVENC instead of CPU encoding (5–10× faster)
2. Disable color correction if not needed
3. Reduce output resolution
4. Check CPU/GPU usage during export — should be near 100%

#### Issue: Exported video has no audio

**Cause:** Audio track is missing or muted.

**Solutions:**
1. Verify audio track exists in timeline
2. Check audio is not muted (speaker icon in timeline)
3. Check FFmpeg audio codec support:
   ```bash
   ffmpeg -codecs | findstr aac
   ```

#### Issue: Exported video quality is poor

**Cause:** Bitrate too low or codec settings suboptimal.

**Solutions:**
1. Increase bitrate in **Deliver → Export Settings → Bitrate**
2. Use H.265 for better quality at same file size
3. Use highest quality preset: **Deliver → Export Settings → Quality Preset → Slow**
4. Check source video quality — export cannot improve low-quality source

---

## Database Issues

### Database Corruption

#### Error: "Database is locked" or "Database disk image is malformed"

**Cause:** Database file is corrupted or locked by another process.

**Solutions:**
1. Close all PB Studio instances
2. Check for leftover processes:
   ```bash
   tasklist | findstr python
   ```
   Kill any orphaned `python.exe` processes
3. Backup and reset database:
   ```bash
   copy pb_studio.db pb_studio_backup.db
   del pb_studio.db
   ```
   Restart PB Studio — database is recreated

#### Issue: Projects or media are missing

**Cause:** Database was reset or entries were deleted.

**Solutions:**
1. Restore from backup (if available):
   ```bash
   copy pb_studio_backup.db pb_studio.db
   ```
2. Re-import media files from **Media → Import**

---

## AI Chat Issues

### Chat Not Responding

#### Issue: AI chat is not responding or responses are very slow

**Solutions:**
1. Check model is loaded: Status bar shows "Qwen 2.5 0.5B loaded"
2. First query takes longer (~5–10 seconds) to load model
3. Check VRAM availability — close other GPU apps if VRAM is full
4. Restart PB Studio if chat becomes unresponsive

#### Issue: Chat responses are nonsensical or incorrect

**Cause:** Local LLM has limitations or lacks context.

**Solutions:**
1. Be more specific in queries:
   - ❌ "Fix the timeline"
   - ✓ "Move the clip at beat 16 to beat 32"
2. Address specific agents for specialized tasks:
   - `@Pacing` — cut timing
   - `@Vision` — clip selection
   - `@Audio` — waveform/stems
   - `@Editor` — timeline operations
3. For complex requests, use manual editing instead

---

## Performance Optimization

### General Performance Tips

1. **Close unnecessary applications** before running PB Studio
2. **Set VRAM limit** to 80% in Settings to prevent OOM crashes
3. **Use proxies** for 4K footage — enable in Settings → Performance
4. **Reduce timeline complexity** — fewer clips = smoother preview
5. **Upgrade hardware:**
   - GPU: 8+ GB VRAM recommended
   - RAM: 32 GB for large projects
   - Storage: NVMe SSD for best performance

### Memory Management

If PB Studio is using too much RAM or VRAM:

1. Clear cache periodically:
   - **Edit → Clear Cache** → Clears temp files, proxies, keyframes
2. Restart PB Studio between projects to release GPU memory
3. Set model unload timeout in **Settings → Performance → Model Unload Delay** (lower = more aggressive unload)

---

## Reporting Bugs

When reporting issues, include:

1. **System info:**
   - GPU model and VRAM
   - Windows version
   - Python version (`python --version`)

2. **Log file:**
   ```bash
   type logs\pb_studio.log
   ```
   Include the last 100 lines or the section with the error

3. **Steps to reproduce:**
   - What you were doing when the error occurred
   - Specific file formats/sizes if relevant

4. **Screenshots/videos** of the issue (if applicable)

Submit issues at: **[GitHub Issues](https://github.com/your-repo/pb-studio-rebuild/issues)**

---

## Additional Resources

- [Installation Guide](installation.md) — Detailed setup instructions
- [Getting Started](getting_started.md) — First project walkthrough
- [FAQ](faq.md) — Quick answers to common questions
- [Feature Overview](features.md) — What PB Studio can do

---

**Still stuck?** Open the chat dock and ask `@Editor — I need help with [your issue]`. The AI may be able to diagnose common problems.

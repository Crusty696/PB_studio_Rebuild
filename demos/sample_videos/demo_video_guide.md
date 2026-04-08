# Demo Video Production Guide

This guide explains how to create compelling demo videos for PB Studio sales presentations.

## Video Types

### 1. Before/After Comparison
**Goal:** Show the time saved and quality difference between manual editing and PB Studio auto-edit

### 2. Feature Showcase
**Goal:** Highlight specific features (beat-sync, stem-aware pacing, visual matching)

### 3. End-to-End Workflow
**Goal:** Show the complete process from import to export

---

## Video 1: Before/After Comparison

### Setup
**Duration:** 2-3 minutes
**Format:** Split-screen or sequential comparison

### Script

**Part A: Manual Editing (Time-Lapse)**
1. Open generic video editor (Premiere/DaVinci)
2. Import same audio + video clips
3. Time-lapse of:
   - Manually placing clips on timeline
   - Listening to beats repeatedly
   - Adjusting cut points frame-by-frame
   - Reviewing and tweaking
4. **Show timer:** "2 hours 15 minutes"

**Part B: PB Studio Auto-Edit (Real-Time)**
1. Open PB Studio
2. Import same audio + video clips (drag & drop)
3. Click "Analyze" on audio → show beat detection
4. Click "Separate Stems" → show progress (2 min)
5. Click "Analyze" on videos → show progress (3 min)
6. Click "Auto-Edit (Phase 3)" → instant timeline
7. Quick preview playback
8. Click "Export" → show render progress
9. **Show timer:** "5 minutes 42 seconds"

**Part C: Side-by-Side Playback**
- Play 30-second clip from both outputs
- Highlight beat accuracy
- Show energy matching (drop sync)

### Recording Tips
- Use OBS Studio for screen capture (1080p60)
- Enable system audio capture
- Use picture-in-picture for timer overlay
- Speed up manual editing to 8x-16x for time-lapse
- Keep PB Studio at 1x speed (shows real performance)

### Post-Production
- Add text overlays:
  - "Manual Editing: 2 hours 15 minutes"
  - "PB Studio: 5 minutes 42 seconds"
  - "40x faster"
- Highlight UI elements with red circles/arrows
- Add background music (low volume)

---

## Video 2: Feature Showcase

### Setup
**Duration:** 3-4 minutes
**Format:** Screen recording with voiceover

### Script

**Intro (15 sec)**
"PB Studio uses AI to edit music videos the way a professional would. Let's see how."

**Feature 1: Beat Detection (30 sec)**
1. Show waveform view
2. Click "Analyze Audio"
3. Zoom into beatgrid overlay
4. **Voiceover:** "GPU-accelerated beat detection finds every beat, downbeat, and energy curve in seconds."

**Feature 2: Stem Separation (45 sec)**
1. Click "Separate Stems"
2. Show progress bar (~2 min, sped up to 10 sec)
3. Show stem workspace with 4 waveforms
4. Play each stem isolated
5. **Voiceover:** "AI separates your track into Drums, Bass, Vocals, and Other. This lets PB Studio understand musical context."

**Feature 3: Video Analysis (45 sec)**
1. Select video clips
2. Click "Analyze Videos"
3. Show scene detection in progress
4. Show motion score visualization
5. **Voiceover:** "Each scene gets a motion score from optical flow analysis and a visual embedding for semantic search."

**Feature 4: Stem-Aware Pacing (60 sec)**
1. Click "Auto-Edit"
2. Show timeline generation
3. Zoom into a drop section
4. Highlight rapid cuts triggered by drum hits
5. Zoom into a vocal section
6. Highlight slower cuts
7. **Voiceover:** "When vocals are detected, cuts slow down. When the bass drops, cuts go rapid. It's like having a DJ edit your video."

**Feature 5: Manual Anchors (30 sec)**
1. Show anchor marker in beatgrid
2. Pin a clip to a specific beat
3. Re-run auto-edit
4. Show that pinned clip stays locked
5. **Voiceover:** "Want control? Pin any clip to any beat. The AI works around it."

**Outro (15 sec)**
"PB Studio: Beat-synchronized video editing powered by AI."

### Recording Tips
- Script and rehearse voiceover first
- Use a good microphone (Blue Yeti or similar)
- Record screen at 1080p60
- Use zoom transitions for UI focus
- Add subtle motion graphics for feature names

---

## Video 3: End-to-End Workflow

### Setup
**Duration:** 5-7 minutes (or sped up to 2-3 min)
**Format:** Real-time or 2x speed with narration

### Script

**Step 1: Import (30 sec)**
- Drag audio file into MEDIA tab
- Drag 10-15 video clips into MEDIA tab
- **Show:** File browser and import confirmation

**Step 2: Analyze Audio (45 sec)**
- Click "Analyze" on audio track
- Show beat detection progress
- Click "Separate Stems"
- Show stem separation progress (speed up to 10 sec)
- **Result:** Beatgrid visible, stems ready

**Step 3: Analyze Videos (90 sec)**
- Click "Analyze" on first video clip
- Show scene detection + motion + visual analysis
- Batch-analyze remaining clips
- **Result:** All clips have motion scores and embeddings

**Step 4: Auto-Edit (60 sec)**
- Switch to EDIT tab
- Click "Auto-Edit (Phase 3)"
- Show timeline generation
- **Result:** Fully populated timeline

**Step 5: Preview & Adjust (90 sec)**
- Play timeline preview
- Show a manual adjustment:
  - Drag a clip to different position
  - Trim a clip duration
  - Add an anchor marker
- Re-run auto-edit section

**Step 6: Export (60 sec)**
- Switch to DELIVER tab
- Configure export settings:
  - Resolution: 1080p
  - Frame rate: 30fps
  - LUFS: -14.0
- Click "Export"
- Show render progress (speed up to 15 sec)
- **Result:** Final video file

**Step 7: Final Playback (60 sec)**
- Play exported video in external player
- Show beat-perfect cuts
- Highlight energy matching

### Recording Tips
- Use 2x speed for analysis/render steps
- Slow down to 1x for UI interactions
- Add progress bar overlay for long processes
- Use chapter markers for each step

---

## Sample Content Recommendations

### Audio Tracks
**Ideal characteristics:**
- 120-140 BPM (EDM, House, Techno)
- Clear drop structure
- Distinct vocals vs. instrumental sections
- 2-4 minutes duration

**Royalty-free sources:**
- Incompetech (Kevin MacLeod)
- Purple Planet Music
- Bensound
- Free Music Archive (CC-licensed)

### Video Clips
**Ideal characteristics:**
- 1080p or 4K resolution
- 30fps or 60fps
- Varying motion levels (static, medium, high)
- Thematically related (club, concert, dance, abstract)

**Royalty-free sources:**
- Pexels Videos
- Pixabay Videos
- Videvo
- Coverr

**Recommended clip types for demo:**
- Crowd dancing (high motion)
- DJ booth close-ups (medium motion)
- Light effects (high motion, abstract)
- Slow-mo dancers (low motion)
- Aerial shots (medium motion)

---

## Export Settings

### For Web (YouTube, Vimeo)
- **Resolution:** 1080p (1920×1080)
- **Frame Rate:** 30fps
- **Codec:** H.264
- **Bitrate:** 8-12 Mbps (VBR)
- **Audio:** AAC 192kbps, 48kHz

### For Presentations (PowerPoint, Keynote)
- **Resolution:** 1080p (smaller file size)
- **Frame Rate:** 30fps
- **Codec:** H.264 (high compatibility)
- **Bitrate:** 5-8 Mbps
- **Audio:** AAC 128kbps

### For High-Quality Archive
- **Resolution:** 4K (3840×2160) if source supports
- **Frame Rate:** 60fps if source supports
- **Codec:** H.264 or ProRes
- **Bitrate:** 20-50 Mbps
- **Audio:** AAC 320kbps or uncompressed

---

## Screen Recording Tools

### Recommended Software

**OBS Studio (Free, Windows/Mac/Linux)**
- Best for high-quality recordings
- GPU-accelerated encoding
- Scene switching support
- Audio mixing

**Windows Game Bar (Built-in, Windows)**
- Quick and easy (Win+G)
- Good for simple screen captures
- Limited editing features

**QuickTime (Built-in, macOS)**
- Simple screen recording
- Good quality
- Export to H.264

**ScreenFlow (Paid, macOS)**
- Professional screen recording
- Built-in editing
- Motion graphics support

### OBS Settings for Demo Videos
```
Video:
- Base Canvas: 1920×1080
- Output Resolution: 1920×1080
- FPS: 60
- Encoder: NVENC H.264 (GPU) or x264 (CPU)
- Rate Control: CBR
- Bitrate: 12000 Kbps

Audio:
- Sample Rate: 48kHz
- Channels: Stereo
- Bitrate: 192kbps
```

---

## Voiceover Script Template

### Introduction
"Hi, I'm [Name], and today I'm going to show you how PB Studio uses AI to create beat-synchronized music videos in minutes, not hours."

### Feature Highlight
"[Feature name] works by [brief technical explanation]. This means [user benefit]. Let me show you."

### Transition
"Now that we've [completed step], let's move on to [next step]."

### Problem/Solution
"Traditional editing requires [manual process]. With PB Studio, you just [simple action], and the AI handles the rest."

### Conclusion
"As you can see, PB Studio takes the guesswork out of music video editing. Want to try it yourself? Visit [website] for beta access."

---

## Publishing Checklist

Before publishing demo videos:

**Quality Check:**
- [ ] Audio levels normalized (-16 LUFS for YouTube)
- [ ] No frame drops or stuttering
- [ ] UI text is readable at 1080p
- [ ] No personal information visible (file paths, emails)
- [ ] Color grading consistent

**Content Check:**
- [ ] All music is royalty-free or licensed
- [ ] All video clips are royalty-free or licensed
- [ ] No copyrighted UI elements from other software
- [ ] Branding consistent (logo, colors)

**Technical Check:**
- [ ] Exported at correct resolution/fps
- [ ] File size appropriate for platform
- [ ] Thumbnail image created (1280×720)
- [ ] Captions/subtitles added (accessibility)

**Distribution:**
- [ ] Upload to YouTube with proper description
- [ ] Upload to Vimeo as backup
- [ ] Host on company website
- [ ] Share on social media with hashtags
- [ ] Add to sales deck as embedded video

---

## Example Timeline

### Week 1: Pre-Production
- Day 1-2: Source royalty-free music and video clips
- Day 3-4: Write detailed scripts for each video type
- Day 5: Record voiceover narration

### Week 2: Production
- Day 1-2: Record Before/After comparison video
- Day 3: Record Feature Showcase video
- Day 4: Record End-to-End Workflow video
- Day 5: Buffer day for reshoots

### Week 3: Post-Production
- Day 1-2: Edit Before/After video, add graphics
- Day 3: Edit Feature Showcase video
- Day 4: Edit Workflow video
- Day 5: Final review and corrections

### Week 4: Distribution
- Day 1: Upload to YouTube/Vimeo
- Day 2: Create thumbnails and marketing assets
- Day 3-4: Promote on social media
- Day 5: Gather feedback and iterate

---

## Feedback Loop

After publishing demo videos:

**Metrics to Track:**
- View count
- Average watch time (should be >70%)
- Click-through rate on CTA
- Comments and questions
- Social shares

**Iterate Based On:**
- If watch time drops at a specific point, that section needs editing
- If CTR is low, improve the call-to-action
- If comments ask the same question, add clarification
- If shares are low, make content more shareable (shorter, punchier)

**Update Frequency:**
- Refresh demo videos every 6 months
- Update immediately after major version releases
- Create new videos for new features

---

## Contact

For questions about demo video production:
- Technical: [CTO email]
- Marketing: [CMO email]
- Sales: [Sales email]

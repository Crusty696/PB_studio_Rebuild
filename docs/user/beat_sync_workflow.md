# PB Studio — Beat-Sync Workflow Tutorial

**Version:** 0.5.0

Learn how to create professional beat-synchronized music videos with PB Studio's Smart Director AI.

---

## What is Beat-Synchronized Editing?

Beat-synchronized editing means every cut in your video happens exactly on a musical beat — creating a rhythmic flow that matches the energy of the music. PB Studio automates this process using AI.

**Traditional workflow:**
1. Manually mark every beat in your audio track (hundreds of markers)
2. Manually select video clips for each beat
3. Manually cut and align clips to beat markers
4. **Time required:** 4–8 hours for a 5-minute video

**PB Studio workflow:**
1. Import audio and video
2. Click Analyze → Separate Stems → Analyze Videos → Auto-Edit
3. Review and adjust with AI assistance
4. Export
5. **Time required:** 15–30 minutes for a 5-minute video

---

## Workflow Overview

> **Updated 2026-05-09:** UI uses 4-Tab layout — PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT. The former AUTO-SCHNITT and REVIEW tabs are merged into a single **SCHNITT** tab with sub-tabs (Schnitt / Pacing & Anker / Audio / RL & Notes).

```
┌──────────────────────────┐
│ MATERIAL & ANALYSE tab   │  Import audio + video clips
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Analyze Audio            │  Detect beats, stems, structure
│                          │  Time: 2–4 minutes
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Analyze Videos           │  Scene detection, motion, embeddings
│                          │  Time: 1–3 minutes per clip
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ SCHNITT tab              │  Sub-tabs: Schnitt / Pacing & Anker /
│  → Auto-Edit             │           Audio / RL & Notes
│  → Review & Refine       │  Time: 5–10 s auto-edit + variable review
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ EXPORT tab               │  Export final video
│                          │  Time: 1–5× real-time
└──────────────────────────┘
```

---

## Tutorial 1: Basic DJ Mix Video

**Goal:** Create a 5-minute music video from a DJ set with 10 video clips.

### Step 1: Prepare Your Media

**Audio:**
- Format: WAV, FLAC, or high-quality MP3 (320 kbps)
- Length: 5 minutes
- Genre: Electronic music (house, techno, trance, etc.)

**Video:**
- 10–20 clips (30 seconds to 2 minutes each)
- Resolution: 1080p or 4K
- Content: Mix of high-energy (crowd, lasers, effects) and low-energy (ambience, B-roll)

### Step 2: Import Media

1. Open PB Studio and create a new project: **File → New Project**
2. Switch to **MATERIAL & ANALYSE** tab
3. Import audio:
   - Click **Import Audio**
   - Select your DJ track
4. Import videos:
   - Click **Import Video**
   - Select all video clips (you can select multiple)
   - Or drag-and-drop files into the media table

### Step 3: Analyze Audio

1. In the **MATERIAL & ANALYSE** tab, find your audio track
2. Click **Analyze** button
3. Wait 10–30 seconds

**What happens:**
- `beat_this` detects every beat and downbeat
- Macro-structure is classified: Warmup → Buildup → Drop → Breakdown → Cooldown
- Rekordbox-style waveform is drawn

**Visual check:** You should see a colorful waveform with beat markers (vertical lines).

### Step 4: Separate Stems (Recommended)

1. Click **Separate Stems** button on the audio track
2. Wait 1–3 minutes

**What happens:**
- Demucs extracts Vocals, Drums, Bass, Other stems
- Stems are saved to `storage/stems/`
- Stem waveforms appear below the main waveform

**Why this matters:** Stems enable intelligent pacing:
- Cuts happen on drum hits
- Drop detection is more accurate (bass RMS spikes)
- Vocals slow down cutting (prevents mid-sentence cuts)

### Step 5: Analyze Video Clips

1. Select all video clips in the media table (Ctrl+A)
2. Click **Analyze** button
3. Wait 30–90 seconds per clip

**What happens:**
- PySceneDetect finds natural scene boundaries
- RAFT optical flow calculates motion energy per scene
- SigLIP generates visual embeddings for semantic matching

**Visual check:** Clips show "Analyzed" status and motion score (0.0–1.0).

### Step 6: Auto-Edit

1. Switch to **SCHNITT** tab (sub-tab **Schnitt**)
2. Click **Auto-Edit (Phase 3)** button
3. Wait 5–10 seconds

**What happens:**
- Smart Director calculates cut-rate score (`S_eff`) per beat based on section type
- High-motion scenes are matched to high-energy beats (drops)
- Low-motion scenes are matched to low-energy beats (breakdowns)
- Timeline is assembled with beat-accurate cuts

**Result:** A complete timeline with 100–300 cuts perfectly synced to beats.

### Step 7: Review & Refine

**Playback navigation:**
- Spacebar: Play/Pause
- `J` / `K` / `L`: Shuttle playback (industry standard)
- Left/Right arrows: Step frame-by-frame
- `+` / `-`: Zoom timeline

**Common adjustments:**

#### Fix a jarring cut
- Find the problematic clip
- Delete it (Select → `Del`)
- Drag a better clip from the media bin
- The clip automatically snaps to the beat

#### Pin a specific moment
- Select a clip you want to keep
- Press `M` to create an Anchor
- Re-run **Auto-Edit** — the anchored clip stays, everything else re-generates around it

#### Adjust clip timing
- Drag clip edges to trim in/out points
- Or: Move playhead → Press `I` (set in-point) or `O` (set out-point)

#### Ask the AI for help
- Open chat dock (bottom panel)
- Example queries:
  - "Move the crowd clip to the big drop at 2:30"
  - "@Pacing — make the cuts faster during the second drop"
  - "@Vision — find a high-energy clip for beat 64"

### Step 8: Export

1. Switch to **EXPORT** tab
2. Configure export settings:
   - **Resolution:** 1080p (or match source)
   - **Codec:** H.265 NVENC (fast, high quality)
   - **LUFS Target:** -14 LUFS (YouTube standard)
3. Click **Export**
4. Wait 1–5× real-time

**Output:** Your rendered video is saved to `exports/your-project-name.mp4`.

---

## Tutorial 2: Music Video with Vocal Sync

**Goal:** Create a music video where cuts respect vocal phrases (no mid-sentence cuts).

### Prerequisites
- Audio track with clear vocals
- Stem separation completed (Demucs extracts vocals)

### Workflow

1. **Import & Analyze** as usual (Tutorial 1, Steps 1–5)

2. **Verify Vocal Detection:**
   - In **MATERIAL & ANALYSE** tab, find your audio track
   - Check that "Vocals" stem is present
   - Play the Vocals stem to verify quality

3. **Enable Vocal-Aware Editing:**
   - **Settings → Audio → Vocal-Aware Cutting** → Enabled
   - **Sensitivity:** 2.0 (default) — higher = fewer cuts during vocals

4. **Auto-Edit:**
   - Run **Auto-Edit** as normal
   - Smart Director will slow cut rate during vocal activity

5. **Result:** Cuts happen on beats *between* vocal phrases, not mid-word.

**Manual Override:**
If a cut still interrupts vocals, use Anchors to pin clips around that section.

---

## Tutorial 3: Story-Driven Edit with Anchors

**Goal:** Keep key narrative moments fixed while letting AI fill transitions.

### Scenario
You have a 3-minute track with this structure:
- 0:00–0:30 — Intro (ambient B-roll)
- 0:30–1:00 — Buildup (crowd shots)
- 1:00–1:30 — Drop (main performer close-up)
- 1:30–2:00 — Breakdown (wide landscape)
- 2:00–2:30 — Final drop (confetti/fireworks)
- 2:30–3:00 — Outro (sunset)

### Workflow with Anchors

1. **Import & Analyze** everything (Tutorial 1)

2. **Manually place key clips:**
   - Drag "performer close-up" to beat at 1:00 (first drop)
   - Drag "confetti" clip to beat at 2:00 (final drop)
   - Drag "sunset" clip to beat at 2:30 (outro)

3. **Anchor these clips:**
   - Select first clip → Press `M`
   - Select second clip → Press `M`
   - Select third clip → Press `M`

4. **Run Auto-Edit:**
   - Smart Director treats anchored clips as fixed
   - Fills all gaps (intro, buildup, breakdown, transitions) automatically

5. **Result:** Your story beats are preserved, but you didn't have to manually edit 150+ cuts.

---

## Tutorial 4: High-Energy Festival Video

**Goal:** Create a fast-paced video for a drop-heavy festival set.

### Prerequisites
- Audio: High-energy electronic music (150+ BPM)
- Video: Fast-motion clips (crowd, lasers, strobes, fireworks)

### Workflow

1. **Import & Analyze** (Tutorial 1)

2. **Verify Macro-Structure:**
   - Check that drops are correctly identified
   - If not: Manually edit sections in **Audio → Edit Sections**

3. **Increase Cut Rate:**
   - Open chat: `@Pacing — increase cut rate by 50% for all drops`
   - Or manually adjust in **Edit → Pacing Settings → S_eff Multiplier → Drops → 1.5**

4. **Prioritize High-Motion Clips:**
   - **Edit → Clip Selection → Motion Priority → High**
   - Smart Director will prefer high-motion clips during drops

5. **Run Auto-Edit**

6. **Result:** Ultra-fast cutting (1–2 seconds per clip) during drops, matching festival energy.

**Tip:** Preview at 50% speed first (`View → Playback Speed → 0.5×`) to check for strobing or too-fast cuts.

---

## Tutorial 5: Cinematic Music Video

**Goal:** Create a slower, more contemplative video with longer shots.

### Prerequisites
- Audio: Downtempo or ambient music (80–100 BPM)
- Video: Cinematic B-roll (landscapes, slow-motion, drone footage)

### Workflow

1. **Import & Analyze** (Tutorial 1)

2. **Reduce Cut Rate:**
   - Chat: `@Pacing — reduce cut rate by 70% globally`
   - Or: **Edit → Pacing Settings → S_eff Multiplier → Global → 0.3**

3. **Prioritize Low-Motion Clips:**
   - **Edit → Clip Selection → Motion Priority → Low**

4. **Add Crossfades:**
   - **Deliver → Export Settings → Transitions → Dissolve (1 second)**

5. **Run Auto-Edit**

6. **Result:** Cuts every 8–16 beats (longer clips), smooth dissolves, contemplative pacing.

---

## Tutorial 6: Multi-Camera Sync

**Goal:** Sync multiple camera angles to one master audio track.

### Scenario
You have:
- 1 master audio track (from mixing board)
- 3 camera angles (all filming the same performance, not in sync)

### Workflow

1. **Import master audio** and analyze (Tutorial 1)

2. **Import all camera clips**

3. **Sync cameras to audio:**
   - Select first camera clip
   - **Audio → Sync to Master** → PB Studio aligns using waveform matching
   - Repeat for all cameras

4. **Analyze synced clips** (scene detection, motion, embeddings)

5. **Run Auto-Edit:**
   - Smart Director selects best camera angle per beat based on motion/content

6. **Result:** Automatic multi-camera cut using AI, perfectly in sync.

---

## Advanced Techniques

### Technique 1: Beat Offset

Some tracks have a "swing" or "groove" where cuts sound better slightly before/after the beat.

**How to adjust:**
1. **Edit → Beatgrid Settings → Beat Offset**
2. Set offset in milliseconds (±50ms typical)
3. Re-run Auto-Edit

### Technique 2: Custom Section Pacing

Override Smart Director's section-based cut rates:

1. Open chat: `@Pacing — show me current S_eff values`
2. Adjust per section:
   - `@Pacing — set Buildup S_eff to 0.6 instead of 0.3`
3. Re-run Auto-Edit

### Technique 3: Visual Coherence Control

Avoid repetitive visuals or force specific clip sequences:

1. **Edit → Clip Selection → Diversity Threshold**
2. Higher value = more visual variety (clips look different)
3. Lower value = allow similar clips back-to-back

### Technique 4: Export Variations

Generate multiple versions quickly:

1. Complete your edit
2. **File → Save Timeline Snapshot** (`Ctrl+Shift+S`)
3. Run Auto-Edit with different settings
4. **File → Load Timeline Snapshot** to restore original
5. Export both versions

---

## Tips for Best Results

### Audio Quality Matters
- Use WAV or FLAC for best beat detection
- 320 kbps MP3 minimum for good stem separation
- Avoid low-bitrate or heavily compressed audio

### Video Clip Selection
- **Variety:** Mix high/low motion, wide/close shots, different colors
- **Length:** 30 seconds to 2 minutes per clip is ideal
- **Quality:** 1080p minimum, 4K preferred

### Let the AI Learn
- When you manually correct a cut, PB Studio records it
- Click **"Learn as AI Rule"** to persist the correction across sessions
- Over time, the AI learns your editing style

### Use Proxies for 4K
- Enable proxy generation for smooth playback
- Originals are used for final export automatically

### Iterate Quickly
- Auto-Edit is fast (~5 seconds) — experiment with settings
- Use Anchors to preserve good sections while regenerating the rest
- Undo (`Ctrl+Z`) is your friend

---

## Common Mistakes to Avoid

❌ **Skipping stem separation** → Less intelligent pacing
✓ Always separate stems for vocal-aware and drop-aware editing

❌ **Not analyzing video clips** → Random clip selection
✓ Analyze all clips before Auto-Edit for content-aware matching

❌ **Ignoring macro-structure** → Wrong pacing for sections
✓ Verify Warmup/Buildup/Drop/Breakdown detection is correct

❌ **Too few video clips** → Repetitive visuals
✓ Use 10–20+ clips for a 5-minute video

❌ **Deleting anchors accidentally** → Loses manual work
✓ Check **Edit → Show Anchors** before re-running Auto-Edit

---

## Keyboard Shortcuts Summary

| Action | Shortcut |
|---|---|
| **Playback** | |
| Play/Pause | `Space` |
| Shuttle (slower/faster) | `J` / `L` |
| Stop | `K` |
| Frame step | `Left` / `Right` |
| Set In point | `I` |
| Set Out point | `O` |
| **Editing** | |
| Create Anchor | `M` |
| Delete clip | `Del` |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Copy | `Ctrl+C` |
| Paste | `Ctrl+V` |
| **Timeline** | |
| Zoom in/out | `+` / `-` |
| Fit to window | `F` |
| Go to start | `Home` |
| Go to end | `End` |

Full shortcuts: [Keyboard Shortcuts](keyboard_shortcuts.md)

---

## Next Steps

- **[Getting Started](getting_started.md)** — Basic project walkthrough
- **[Feature Overview](features.md)** — Detailed feature documentation
- **[FAQ](faq.md)** — Common questions
- **[Troubleshooting](troubleshooting.md)** — Fix common issues

---

**Ready to create?** Open PB Studio and try Tutorial 1 — you'll have a complete music video in 30 minutes.

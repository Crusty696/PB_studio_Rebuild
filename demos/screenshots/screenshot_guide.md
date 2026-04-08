# Screenshot Guide for PB Studio Demo Materials

This guide lists the key screenshots needed for sales presentations, marketing materials, and documentation.

## Screenshot Checklist

### Essential Screenshots (Must-Have)

#### 1. Main Interface Overview
**File:** `01_main_interface.png`
**What to show:**
- Full PB Studio window
- MEDIA tab visible with imported files
- Left sidebar with project tree
- Bottom timeline panel
- Right properties panel

**Setup:**
- Import 3-4 audio files
- Import 10-15 video clips
- Ensure clean, professional-looking file names
- Use 1920×1080 window size

---

#### 2. Beatgrid Editor
**File:** `02_beatgrid_editor.png`
**What to show:**
- Rekordbox-style frequency waveform (Bass/Mid/High colors)
- Beatgrid overlay with vertical beat markers
- Zoom controls visible
- Playhead at an interesting position (near a drop)

**Setup:**
- Analyze an EDM track (clear beat structure)
- Zoom to show ~8-16 beats
- Position playhead at a drop or buildup
- Enable all waveform layers

**Colors to highlight:**
- Red: Bass
- Yellow: Mids
- Blue: Highs
- White: Beat markers

---

#### 3. Stem Separation Workspace
**File:** `03_stem_separation.png`
**What to show:**
- 4 stem waveforms stacked vertically
- Labels: Vocals, Drums, Bass, Other
- Per-stem mute/solo buttons
- Synchronized playhead across all stems

**Setup:**
- Run stem separation on a track with clear vocals
- Zoom to show vocal section clearly
- Highlight the drums stem during a drop

---

#### 4. Video Analysis Results
**File:** `04_video_analysis.png`
**What to show:**
- Grid view of video clips
- Each clip showing:
  - Thumbnail (keyframe)
  - Motion score (numeric or bar)
  - Scene count badge
  - Duration
- Filter/sort controls visible

**Setup:**
- Analyze 12+ video clips
- Show variety of motion scores (low, medium, high)
- Use visually distinct clips (easy to differentiate)

---

#### 5. Auto-Edit Timeline
**File:** `05_autoedit_timeline.png`
**What to show:**
- Timeline with beat-synced cuts
- Clips of varying lengths
- Beatgrid aligned with clip boundaries
- Section markers (Warmup, Buildup, Drop, Breakdown)

**Setup:**
- Run Phase 3 auto-edit
- Zoom to show ~30 seconds of timeline
- Highlight a drop section with rapid cuts
- Add section marker annotations if possible

---

#### 6. Multi-Agent Chat Interface
**File:** `06_chat_interface.png`
**What to show:**
- Chat dock on right side
- Conversation with at least 3 messages
- Agent icons/avatars visible
- Example query: "Make the drop section more energetic"

**Setup:**
- Ask Pacing Agent a question
- Show response with specific suggestions
- Use realistic use-case dialogue
- Keep conversation professional

---

#### 7. Export Settings Panel
**File:** `07_export_settings.png`
**What to show:**
- Export/Deliver tab
- Resolution dropdown (1080p selected)
- Frame rate: 30fps
- LUFS normalization: -14.0
- Codec: H.264 (NVENC)
- Progress bar (optional: mid-render at ~40%)

**Setup:**
- Configure export for 1080p30
- Show realistic file size estimate
- Include output path

---

### Advanced Screenshots (Nice-to-Have)

#### 8. Manual Anchor Markers
**File:** `08_anchor_markers.png`
**What to show:**
- Timeline with anchor marker pinning a clip to a beat
- Distinct icon/color for anchored clips
- Beatgrid visible underneath

---

#### 9. Scene Detection Visualization
**File:** `09_scene_detection.png`
**What to show:**
- Video clip with detected scene boundaries
- Scene thumbnail strip
- Scene duration indicators

---

#### 10. Motion Score Heatmap
**File:** `10_motion_heatmap.png`
**What to show:**
- Video timeline with color-coded motion intensity
- Gradient from blue (low) to red (high)
- Correlation with beatgrid

---

#### 11. Visual Similarity Search
**File:** `11_visual_search.png`
**What to show:**
- Search query: "crowd dancing"
- Results showing visually similar clips
- Similarity scores (0.0-1.0)

---

#### 12. Stem-Aware Pacing Graph
**File:** `12_pacing_graph.png`
**What to show:**
- S_eff (effective sensitivity) curve over time
- Overlay with audio waveform
- Annotations for Warmup/Buildup/Drop/Breakdown sections

---

## Screenshot Capture Settings

### Window Size
- **Recommended:** 1920×1080 (Full HD)
- **Minimum:** 1280×720 (HD)
- **For web:** Can downscale to 1280×720 after capture

### File Format
- **Primary:** PNG (lossless, best for UI)
- **Alternative:** JPEG (smaller file size, acceptable for web)
- **Avoid:** BMP, GIF (too large or limited colors)

### Tools

**Windows:**
- Snipping Tool (Win+Shift+S) - Quick captures
- ShareX - Advanced with annotations
- Greenshot - Professional screenshots

**macOS:**
- Cmd+Shift+4 - Selection capture
- Cmd+Shift+5 - Advanced capture options

**Cross-platform:**
- Flameshot - Open-source with annotations
- Lightshot - Quick sharing

### Best Practices

1. **Clean workspace:**
   - Remove personal file paths
   - Use generic project names ("Demo Project", not "My Music Video")
   - Clear any error messages or warnings

2. **Consistent styling:**
   - Use same color theme across all screenshots
   - Same window size for all captures
   - Same zoom level for similar views

3. **Annotations:**
   - Add red circles/arrows for key UI elements
   - Use text labels for important features
   - Keep annotations minimal and professional

4. **File naming:**
   - Use numbered prefixes (01_, 02_, etc.)
   - Descriptive names (beatgrid_editor, not screenshot1)
   - Include version if iterating (v1, v2)

5. **Resolution:**
   - Capture at native resolution (don't upscale)
   - If downscaling, use 50% increments (1920→1280, not 1920→1400)
   - Maintain aspect ratio

---

## Screenshot Workflow

### Step 1: Prepare Demo Project
1. Create new project: "Sales Demo"
2. Import sample audio (EDM track, clear structure)
3. Import 15 video clips (variety of motion levels)
4. Ensure all file names are professional

### Step 2: Capture Base Screenshots
1. Main interface (01)
2. Beatgrid editor (02)
3. Stem separation (03)
4. Video analysis (04)
5. Auto-edit timeline (05)
6. Chat interface (06)
7. Export settings (07)

### Step 3: Add Annotations
1. Open in image editor (Photoshop, GIMP, Figma)
2. Add red circles around key features
3. Add text callouts where needed
4. Add subtle drop shadow to annotations for contrast

### Step 4: Export Final Assets
1. Save PSD/XCF (master file with layers)
2. Export PNG (for presentations)
3. Export JPEG 90% quality (for web)
4. Organize in `demos/screenshots/` directory

---

## Annotation Examples

### Feature Callout
```
Red circle around "Auto-Edit" button
Arrow pointing to it
Text label: "One-click beat-synchronized editing"
```

### Workflow Step
```
Numbered badge: "1"
Text: "Import your audio and video clips"
Arrow pointing to import area
```

### Comparison
```
Split screen: Before (left) vs After (right)
Text overlay: "Manual: 2 hours" vs "PB Studio: 5 minutes"
```

---

## Usage in Marketing Materials

### PowerPoint/Keynote
- Resolution: 1920×1080 or 1280×720
- Format: PNG (transparent backgrounds if needed)
- Placement: Use "Picture" → "Insert from file"
- Compression: "High Quality" setting in PowerPoint

### Website
- Resolution: 1280×720 (web-optimized)
- Format: JPEG 85% quality or WebP
- Optimization: TinyPNG or ImageOptim
- Lazy loading: Use `loading="lazy"` attribute

### Social Media
- **Twitter/X:** 1200×675 (16:9)
- **Instagram:** 1080×1080 (1:1 square)
- **LinkedIn:** 1200×627
- **Facebook:** 1200×630

Crop from original 1920×1080 screenshots

---

## Screenshot Library Organization

```
demos/screenshots/
├── originals/           # Raw captures (1920×1080 PNG)
│   ├── 01_main_interface.png
│   ├── 02_beatgrid_editor.png
│   └── ...
├── annotated/          # With callouts and labels
│   ├── 01_main_interface_annotated.png
│   └── ...
├── web/                # Web-optimized (1280×720 JPEG)
│   ├── 01_main_interface.jpg
│   └── ...
├── social/             # Social media crops
│   ├── twitter/
│   ├── instagram/
│   └── linkedin/
└── masters/            # PSD/XCF with layers
    ├── 01_main_interface.psd
    └── ...
```

---

## Quality Checklist

Before finalizing screenshots:

- [ ] No personal information visible
- [ ] No error messages or warnings
- [ ] Consistent color theme
- [ ] Professional file/project names
- [ ] Clear, readable text (minimum 12pt)
- [ ] High contrast for key elements
- [ ] Annotations are clear and minimal
- [ ] File size appropriate (<500KB for web)
- [ ] Metadata stripped (EXIF data removed)
- [ ] Aspect ratio maintained
- [ ] No compression artifacts
- [ ] Proper file naming convention

---

## Update Schedule

Screenshots should be updated:
- Every major version release (v0.5 → v0.6)
- When UI significantly changes
- When adding new features to highlight
- At least once every 6 months

Keep a changelog:
```
2026-04-07: Initial screenshot set for v0.5.0
2026-XX-XX: Updated beatgrid editor for v0.6.0
```

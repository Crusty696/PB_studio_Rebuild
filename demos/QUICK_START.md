# Demo Materials Quick Start Guide

**For Sales Teams, Marketing, and Presenters**

This guide gets you up and running with PB Studio demo materials in under 10 minutes.

---

## What's Included

```
demos/
├── README.md                    # Overview of all materials
├── QUICK_START.md              # This file - start here!
├── sales_deck/
│   ├── PB_Studio_Sales_Deck.md      # Main presentation (markdown)
│   └── CONVERSION_GUIDE.md          # How to convert to PowerPoint/PDF
├── sample_videos/
│   ├── demo_video_guide.md          # How to create demo videos
│   └── generate_demo_video.py       # Automated demo generation script
└── screenshots/
    └── screenshot_guide.md          # How to capture key screenshots
```

---

## 5-Minute Setup

### 1. Get the Presentation (2 minutes)

**Option A: PDF (Easiest)**
```bash
cd demos/sales_deck
marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.pdf --pdf --allow-local-files
```

**Option B: PowerPoint**
```bash
marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.pptx
```

**Option C: Web (Interactive)**
```bash
marp -s PB_Studio_Sales_Deck.md
# Open http://localhost:8080 in browser
```

### 2. Add Screenshots (Optional, 3 minutes)

If you have PB Studio installed:
1. Open PB Studio
2. Import sample audio and videos
3. Take screenshots per `screenshots/screenshot_guide.md`
4. Add to presentation deck

If you don't have screenshots yet, use placeholders or skip for now.

### 3. Customize Contact Info (1 minute)

Edit `sales_deck/PB_Studio_Sales_Deck.md`:
- Replace email addresses (search for `@pbstudio.dev`)
- Replace URLs (search for `pbstudio.dev`)
- Replace placeholder names (search for `[Your Name]`)

---

## Pre-Built Demo Scenarios

### Scenario 1: Executive Pitch (15 minutes)
**Goal:** High-level overview, focus on ROI

**Slides to use:**
1. Title slide
2. The Problem
3. The Solution
4. Core Features (overview)
5. Technical Differentiators (table)
6. Use Cases
7. Pricing & Availability
8. Call to Action

**Talking points:**
- Time saved: 40x faster editing
- Target audience: DJs, music video producers
- Unique tech: GPU-accelerated, fully offline
- Pricing: TBD (mention beta access)

---

### Scenario 2: Technical Deep Dive (30 minutes)
**Goal:** Detailed feature walkthrough for engineers

**Slides to use:**
1. Title slide
2. The Solution
3. All Core Features slides (1-5)
4. Technology Stack
5. Appendix: Technical Deep Dive
6. Appendix: System Architecture
7. Appendix: Performance Metrics

**Talking points:**
- Architecture: Multi-agent AI system
- Beat detection: beat_this (CPJKU research)
- ML models: Demucs, RAFT, SigLIP
- Performance: ~6.5 minutes for 3-minute video

**Demo focus:**
- Show actual code/architecture
- Explain pacing algorithm (`S_eff`)
- GPU vs CPU performance comparison

---

### Scenario 3: Live Demo (5 minutes)
**Goal:** Show the product in action

**What to show:**
1. Import audio + videos (30 sec)
2. Analyze audio (show beat detection) (45 sec)
3. Analyze videos (show scene detection) (45 sec)
4. Run Auto-Edit (instant) (30 sec)
5. Play timeline preview (90 sec)
6. Explain export settings (30 sec)

**Preparation:**
- Have PB Studio open and ready
- Pre-select sample files (don't search during demo)
- Test audio/screen sharing beforehand
- Have backup video ready if demo fails

---

## Common Questions & Answers

### "How long does it take to edit a 3-minute video?"
**Answer:** Under 10 minutes total:
- Beat detection: ~12 seconds
- Stem separation: ~2 minutes
- Video analysis: ~3 minutes (for 15 clips)
- Auto-edit: ~8 seconds
- Export: ~1.5 minutes

vs. manual editing: 2+ hours

### "What's the minimum GPU requirement?"
**Answer:** GTX 1060 6GB or better. We use GPU for:
- Beat detection (beat_this)
- Stem separation (Demucs)
- Optical flow (RAFT)
- Visual embeddings (SigLIP)

CPU-only mode is not supported (too slow).

### "Can it work with any music genre?"
**Answer:** Best with electronic music (EDM, House, Techno) that has clear beats. Also works with Hip-Hop, Pop, and Rock. May struggle with:
- Classical (no consistent beat)
- Jazz (irregular tempo)
- Ambient (minimal percussion)

### "How does it compare to Adobe Premiere with plugins?"
**Answer:**
- **Speed:** 40x faster (automated vs. manual)
- **Intelligence:** Stem-aware pacing (Premiere doesn't have this)
- **Offline:** Fully offline (no cloud required)
- **Price:** TBD (likely cheaper than Premiere + BeatEdit plugin)

### "Can I manually adjust the auto-edit?"
**Answer:** Yes! Auto-edit generates a starting point. You can:
- Drag clips to different positions
- Trim clip durations
- Add anchor markers (pin clips to beats)
- Re-run auto-edit with anchors locked

### "Is there a free trial?"
**Answer:** Currently in private beta. Contact [email] for early access.

---

## Demo Best Practices

### Before the Demo

**Technical check (30 minutes before):**
- [ ] PB Studio launches correctly
- [ ] Sample files are loaded
- [ ] Audio/screen sharing tested
- [ ] Internet connection stable (if remote)
- [ ] Backup plan ready (pre-recorded video)

**Environment check:**
- [ ] Close unnecessary apps (notifications off)
- [ ] Hide personal files/folders
- [ ] Full screen mode ready
- [ ] Second monitor configured (presenter view)

### During the Demo

**Do:**
- Explain what you're doing before clicking
- Highlight key features with mouse pointer
- Pause for questions after each section
- Show confidence, even if something glitches

**Don't:**
- Apologize excessively ("Sorry, this is slow...")
- Click randomly while talking
- Rush through complex features
- Skip over errors without acknowledging

### After the Demo

**Follow-up:**
- Send PDF deck within 24 hours
- Include beta signup link
- Offer 1-on-1 technical Q&A session
- Share demo video recording (if available)

---

## Troubleshooting

### Presentation won't open
**Problem:** Marp not installed
**Solution:**
```bash
npm install -g @marp-team/marp-cli
```

### Images missing in exported PDF
**Problem:** Local file permissions
**Solution:**
```bash
marp --pdf --allow-local-files PB_Studio_Sales_Deck.md -o output.pdf
```

### Demo video creation fails
**Problem:** Missing dependencies
**Solution:**
```bash
cd PB_studio_Rebuild
poetry install  # Install all Python dependencies
```

### Screenshots look blurry
**Problem:** Wrong export settings
**Solution:** Capture at native 1920×1080, save as PNG (not JPEG)

---

## Customization Checklist

Before presenting to customers, customize:

**Sales Deck:**
- [ ] Company logo added to slides
- [ ] Contact information updated (email, phone, website)
- [ ] Pricing information (if available)
- [ ] Testimonials (replace placeholders with real quotes)
- [ ] Social media links updated
- [ ] Product screenshots added
- [ ] Demo video embedded or linked

**Demo Environment:**
- [ ] Project name is professional ("Demo Project", not "Test123")
- [ ] File names are clean (no profanity, personal info)
- [ ] Sample content is appropriate (no copyrighted material)
- [ ] UI theme matches brand colors (if possible)

**Marketing Copy:**
- [ ] Tagline is consistent across all materials
- [ ] Feature descriptions match product website
- [ ] Pricing tiers (if any) are clearly defined
- [ ] Call-to-action is clear and actionable

---

## Resources

**Official Documentation:**
- User Guide: `docs/user/README.md`
- Installation: `docs/user/installation.md`
- Troubleshooting: `docs/user/troubleshooting.md`

**Demo Assets:**
- Sales Deck (markdown): `demos/sales_deck/PB_Studio_Sales_Deck.md`
- Video Guide: `demos/sample_videos/demo_video_guide.md`
- Screenshot Guide: `demos/screenshots/screenshot_guide.md`

**External Links:**
- Marp (presentation tool): https://marp.app/
- Sample royalty-free music: https://freemusicarchive.org/
- Sample royalty-free videos: https://pexels.com/videos/

---

## Quick Reference Card

Print this out for presentations:

```
PB STUDIO DEMO QUICK REFERENCE

Key Stats:
• 40x faster than manual editing
• ~10 minutes for 3-minute video
• GPU required (GTX 1060 6GB min)
• Fully offline, no cloud

Core Features:
1. Smart Director (AI Auto-Edit)
2. Stem-Aware Pacing (Vocals/Drums/Bass/Other)
3. Advanced Video Analysis (Motion + Visual)
4. Rekordbox-Style Beatgrid Editor
5. Multi-Agent AI Chat

Tech Stack:
• Beat: beat_this (CPJKU)
• Stems: Demucs
• Motion: RAFT optical flow
• Visual: SigLIP embeddings
• LLM: Qwen 2.5 0.5B

Contact:
• Beta: beta@pbstudio.dev
• Sales: sales@pbstudio.dev
• Demo: calendly.com/pbstudio
• Web: pbstudio.dev

Demo Flow (5 min):
1. Import (30s)
2. Analyze audio (45s)
3. Analyze videos (45s)
4. Auto-edit (30s)
5. Preview (90s)
6. Export (30s)

Common Objections:
"Too expensive" → Time saved = 40x ROI
"Too complex" → One-click auto-edit
"Need control" → Manual anchors supported
"Wrong genre" → Best for EDM, also works for Pop/Rock
```

---

## Next Steps

1. **Generate presentation:**
   ```bash
   cd demos/sales_deck
   marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.pdf --pdf
   ```

2. **Review slide content:**
   - Verify all information is accurate
   - Replace placeholders with real data
   - Add screenshots if available

3. **Practice demo:**
   - Run through full 5-minute demo
   - Time yourself
   - Record and review

4. **Schedule beta demos:**
   - Identify target customers (DJs, producers)
   - Send email with PDF deck
   - Schedule 30-minute demo calls

5. **Gather feedback:**
   - Note common questions
   - Update FAQ section
   - Iterate on deck based on responses

---

## Support

For questions or assistance:
- **Technical issues:** [CTO email]
- **Sales inquiries:** [Sales email]
- **Marketing materials:** [Marketing email]

Good luck with your demo! 🎬

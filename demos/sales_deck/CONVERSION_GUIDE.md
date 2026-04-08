# Sales Deck Conversion Guide

This guide explains how to convert the markdown sales deck (`PB_Studio_Sales_Deck.md`) into various presentation formats.

## Recommended Tools

### 1. Marp (Markdown Presentation Ecosystem)
**Best for:** Quick conversions, simple styling, PDF export

**Installation:**
```bash
npm install -g @marp-team/marp-cli
```

**Convert to PowerPoint:**
```bash
marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.pptx
```

**Convert to PDF:**
```bash
marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.pdf
```

**Convert to HTML:**
```bash
marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.html
```

**Live preview while editing:**
```bash
marp -w -s PB_Studio_Sales_Deck.md
```
Then open `http://localhost:8080` in your browser.

---

### 2. Slidev (Vue-Powered Presentations)
**Best for:** Interactive presentations, web-first, animations

**Installation:**
```bash
npm init slidev
```

**Usage:**
1. Create a new Slidev project
2. Copy `PB_Studio_Sales_Deck.md` content into `slides.md`
3. Adjust frontmatter and styling
4. Run development server:
   ```bash
   npm run dev
   ```
5. Export to PDF:
   ```bash
   npm run export
   ```

**Features:**
- Live presenter notes
- Drawing on slides during presentation
- Two-screen mode (presenter view + audience view)
- Code syntax highlighting
- Built-in diagrams (Mermaid, PlantUML)

---

### 3. reveal.js (HTML Presentations)
**Best for:** Web-based presentations, maximum customization

**Installation:**
```bash
npm install -g reveal-md
```

**Convert:**
```bash
reveal-md PB_Studio_Sales_Deck.md -w
```

**Export to PDF:**
```bash
reveal-md PB_Studio_Sales_Deck.md --print PB_Studio_Sales_Deck.pdf
```

**Features:**
- Vertical and horizontal slide navigation
- Speaker notes
- Slide transitions
- Theme customization

---

## Customization Tips

### Adding Company Logo

**Marp:**
Add to frontmatter:
```yaml
---
marp: true
theme: default
style: |
  section::before {
    content: '';
    background-image: url('path/to/logo.png');
    background-size: 100px;
    width: 100px;
    height: 100px;
    position: absolute;
    top: 20px;
    right: 20px;
  }
---
```

**Slidev:**
Create `global-top.vue`:
```vue
<template>
  <div class="logo">
    <img src="/logo.png" alt="PB Studio" />
  </div>
</template>

<style>
.logo {
  position: fixed;
  top: 20px;
  right: 20px;
}
</style>
```

---

### Custom Color Scheme

**Current deck uses:**
- Background: `#1a1a1a` (dark)
- Primary text: `#ffffff` (white)
- Accent: `#00d4ff` (cyan)

**To change:**
Edit the `style:` section in frontmatter:
```yaml
style: |
  section {
    background: #yourColorHex;
    color: #textColorHex;
  }
  h1, h2 {
    color: #accentColorHex;
  }
```

---

### Adding Screenshots

**In markdown:**
```markdown
![Screenshot description](../screenshots/01_main_interface.png)
```

**Tips:**
- Place images in a relative path (e.g., `images/` folder)
- Use descriptive alt text for accessibility
- Optimize images to <500KB each (use TinyPNG)
- Prefer PNG for UI screenshots, JPEG for photos

---

### Embedding Videos

**Marp (HTML export only):**
```html
<video controls width="100%">
  <source src="../sample_videos/demo.mp4" type="video/mp4">
</video>
```

**Slidev:**
```vue
<video src="/videos/demo.mp4" controls />
```

**Note:** For PowerPoint export, videos must be manually inserted after conversion.

---

## Export Settings

### PDF Export
**Recommended settings:**
- Page size: 16:9 (1920×1080)
- DPI: 150 (good balance of quality/file size)
- Compression: Medium
- Embed fonts: Yes

**Marp command:**
```bash
marp PB_Studio_Sales_Deck.md \
  --pdf \
  --allow-local-files \
  -o PB_Studio_Sales_Deck.pdf
```

### PowerPoint Export
**Marp to PPTX:**
```bash
marp PB_Studio_Sales_Deck.md -o PB_Studio_Sales_Deck.pptx
```

**Post-conversion steps:**
1. Open in PowerPoint/Keynote
2. Review slide transitions (may need manual adjustment)
3. Add videos manually (drag & drop)
4. Adjust font sizes if needed
5. Add presenter notes in Notes pane
6. Test slide animations

### HTML Export
**For web hosting:**
```bash
marp PB_Studio_Sales_Deck.md \
  --html \
  --theme custom-theme.css \
  -o index.html
```

**Self-contained (all assets embedded):**
```bash
marp PB_Studio_Sales_Deck.md \
  --html \
  --bespoke \
  -o presentation.html
```

---

## Presenter Notes

Add presenter notes using HTML comments:

```markdown
---

## Slide Title

Content here...

<!--
Presenter notes:
- Emphasize this point
- Expected question: "What about CPU-only mode?"
  Answer: Not supported, GPU is required for real-time performance
- Demo cue: Launch PB Studio and show beatgrid
-->

---
```

**View notes:**
- **Marp:** Press `P` during HTML presentation
- **Slidev:** Automatic presenter view at `http://localhost:3030/presenter`
- **reveal.js:** Press `S` to open speaker view

---

## Live Presentation Tips

### Keyboard Shortcuts

**Navigation:**
- `→` or `Space`: Next slide
- `←`: Previous slide
- `Home`: First slide
- `End`: Last slide

**Presentation mode:**
- `F11`: Fullscreen (browser)
- `Esc`: Exit fullscreen
- `P`: Presenter notes (Marp)
- `S`: Speaker view (reveal.js)
- `B`: Black screen (pause)

### Two-Screen Setup

**Marp (HTML):**
1. Open presentation in browser
2. Press `P` for presenter view
3. Move presenter window to secondary screen
4. Share primary screen with audience

**Slidev:**
1. Start dev server
2. Presenter view automatically at `:3030/presenter`
3. Audience view at `:3030`

**PowerPoint/Keynote:**
1. Preferences → Slideshow → Enable Presenter View
2. Select which screen for presenter vs. audience

---

## Customization Examples

### Adding a QR Code

**For beta signup or website:**
```markdown
## Call to Action

Scan to join the beta:

![QR Code](images/beta_signup_qr.png)

Or visit: **pbstudio.dev/beta**
```

Generate QR codes:
- https://www.qr-code-generator.com/
- https://goqr.me/

### Adding a Demo Video

**On a slide:**
```markdown
## Live Demo

<video controls width="80%">
  <source src="../sample_videos/before_after_comparison.mp4" type="video/mp4">
</video>
```

**Or link to external:**
```markdown
## Live Demo

Watch on YouTube: [PB Studio Demo](https://youtube.com/watch?v=...)
```

### Adding a Comparison Table

**Already included in deck, but to customize:**
```markdown
| Feature | PB Studio | Competitor A | Competitor B |
|---------|-----------|--------------|--------------|
| **Beat Detection** | GPU (beat_this) | CPU only | Manual |
| **Price** | $X/mo | $Y/mo | $Z/mo |
```

---

## Quality Checklist

Before presenting:

**Content:**
- [ ] All placeholder text replaced (emails, URLs, names)
- [ ] Testimonials are real or clearly marked as examples
- [ ] Pricing information is current
- [ ] Product version number is correct
- [ ] Contact information is accurate

**Visual:**
- [ ] All images load correctly
- [ ] Screenshots are high-resolution
- [ ] Videos play without buffering
- [ ] Fonts are embedded or web-safe
- [ ] Colors are consistent with brand

**Technical:**
- [ ] Presentation tested on target device
- [ ] Backup PDF version prepared
- [ ] Internet connection required? Plan accordingly
- [ ] All external links tested
- [ ] Slide transitions are smooth

**Practice:**
- [ ] Run-through with timer (aim for 20-25 min)
- [ ] Prepared answers for common questions
- [ ] Demo environment tested (if live demo)
- [ ] Contingency plan if demo fails (video backup)

---

## Distribution Formats

### For Email Sharing
**PDF (best):**
- Self-contained
- Works on all devices
- No software required
- ~5-15MB file size

**PowerPoint (acceptable):**
- Editable by recipient
- Animations work
- ~10-30MB file size

### For Web Sharing
**HTML (best):**
- Interactive
- Responsive
- Embed on website
- Host on GitHub Pages or Netlify

### For Print Handouts
**PDF with notes:**
```bash
marp PB_Studio_Sales_Deck.md \
  --pdf \
  --notes \
  -o PB_Studio_Handout.pdf
```

**6 slides per page:**
Use PowerPoint "Print" → "Handouts" → "6 slides per page"

---

## Version Control

Keep track of deck versions:

```
sales_deck/
├── PB_Studio_Sales_Deck.md          # Master (always current)
├── archive/
│   ├── PB_Studio_Sales_Deck_v1.0.md  # Initial version
│   ├── PB_Studio_Sales_Deck_v1.1.md  # After Q2 updates
│   └── ...
└── exports/
    ├── PB_Studio_Sales_Deck_v1.1.pdf
    ├── PB_Studio_Sales_Deck_v1.1.pptx
    └── PB_Studio_Sales_Deck_v1.1.html
```

**Update log in markdown:**
```markdown
<!-- 
Version History:
v1.0 - 2026-04-07 - Initial deck for v0.5.0 launch
v1.1 - 2026-XX-XX - Updated pricing and testimonials
-->
```

---

## Advanced: Custom Marp Theme

Create `custom-theme.css`:

```css
/* @theme custom-pb-studio */

@import 'default';

section {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  color: #ffffff;
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}

h1 {
  color: #00d4ff;
  border-bottom: 4px solid #00d4ff;
  padding-bottom: 0.5em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

h2 {
  color: #00d4ff;
}

strong {
  color: #00d4ff;
  font-weight: 700;
}

code {
  background: #000;
  color: #00ff00;
  padding: 0.2em 0.4em;
  border-radius: 3px;
}

table {
  border-collapse: collapse;
  width: 100%;
}

table th {
  background: #00d4ff;
  color: #000;
  padding: 0.75em;
}

table td {
  padding: 0.5em;
  border-bottom: 1px solid #444;
}

a {
  color: #00d4ff;
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: border-color 0.2s;
}

a:hover {
  border-bottom-color: #00d4ff;
}
```

**Use custom theme:**
```bash
marp --theme custom-theme.css PB_Studio_Sales_Deck.md -o output.pdf
```

Or in frontmatter:
```yaml
---
marp: true
theme: custom-pb-studio
---
```

---

## Troubleshooting

### Images not appearing in PDF
**Solution:** Use `--allow-local-files` flag:
```bash
marp PB_Studio_Sales_Deck.md --pdf --allow-local-files -o output.pdf
```

### Fonts not embedding
**Solution:** Specify font source in CSS:
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');

section {
  font-family: 'Inter', sans-serif;
}
```

### Slides too crowded
**Solution:** Split long slides:
```markdown
---

## Topic (Part 1)

First half of content...

---

## Topic (Part 2)

Second half of content...
```

### Video not playing in PowerPoint
**Solution:**
1. Convert to PPTX
2. Open in PowerPoint
3. Insert → Video → Video on My PC
4. Select video file
5. Adjust video size/position

---

## Resources

**Marp:**
- Docs: https://marpit.marp.app/
- Themes: https://github.com/marp-team/marp-core/tree/main/themes
- CLI: https://github.com/marp-team/marp-cli

**Slidev:**
- Docs: https://sli.dev/
- Themes: https://sli.dev/themes/gallery.html
- Examples: https://sli.dev/showcases.html

**reveal.js:**
- Docs: https://revealjs.com/
- Themes: https://revealjs.com/themes/
- Plugins: https://github.com/hakimel/reveal.js/wiki/Plugins,-Tools-and-Hardware

**Markdown to Slides:**
- Comparison: https://github.com/topics/markdown-to-slides
- Best practices: https://blog.bit.ai/presentation-design-guide/

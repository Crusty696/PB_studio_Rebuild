# PB Studio — UI-Redesign Layout-Plan

**Ziel:** Alles sichtbar und lesbar, **festes Fenster 1513×936 px**, KEINE Scrollbars,
KEINE Splitter, KEIN Resize. Inhalte per Tab-Hierarchie statt per Platzwucher.

**Datum:** 2026-04-14
**Status:** ENTWURF — Freigabe erforderlich vor jeder Implementation.

---

## 0. Kernprinzipien (gelten ÜBERALL)

1. **`setFixedSize(1513, 936)` auf QMainWindow** — User kann NICHT resizen.
2. **Minimum-Size == Maximum-Size** auf jedem Haupt-Container — keine
   Splitter, keine Stretch-Explosion.
3. **Kein QScrollArea in Haupt-Inhaltsflächen.** Überschüssiger Inhalt wird in
   Tabs/Subtabs verschoben.
4. **Überall max-items mit "more" Button**: z. B. VIDEO POOL zeigt immer genau
   8 Zeilen; der Rest ist auf Untertabs verteilt oder per Paginierung.
5. **Einheitliche Schrift-Größen:**
   - H1 (Section-Titel): 12 pt bold
   - H2 (Subsection): 10 pt bold
   - Body: 9 pt
   - Caption/Hint: 8 pt
6. **Einheitliche Knopf-Größen:**
   - Primary-Action: 90 × 28 px
   - Secondary/Toolbar: 70 × 24 px
   - Icon-Only: 24 × 24 px
7. **Einheitliche Abstände:** 6 px Padding, 4 px Spacing. Aktuell oft 10–20 px.
8. **Feste Spaltenbreiten** in Tabellen — keine `stretchLastSection`.

---

## 1. Gesamtstruktur (1513 × 936)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ TOP BAR — 28 px                                                          │
│ [+Neu] [Öffnen] [Zuletzt▾] [Speichern] ───── [Tasks][Konsole][KI][⚙][?] │
├─────────────────────────────────────────────────────────────────────────┤
│ MAIN CONTENT — 876 px                                                    │
│ ┌─────────────────────────────────────────┬─────────────────────────┐   │
│ │                                         │  RIGHT PANEL — 300 px   │   │
│ │  WORKSPACE CONTENT — 1193 px            │  Tabs: CHAT / TASKS /   │   │
│ │  (siehe pro Workspace unten)            │        KONSOLE / INSP.  │   │
│ │                                         │                         │   │
│ │                                         │                         │   │
│ └─────────────────────────────────────────┴─────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────┤
│ WORKSPACE TABS — 18 px                                                   │
│ [ MEDIA ] [ EDIT ] [ STEMS ] [ CONVERT ] [ DELIVER ]                    │
├─────────────────────────────────────────────────────────────────────────┤
│ STATUS-BAR — 14 px  (CPU | GPU | VRAM | Ollama | FFmpeg | AI ready)     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Was sich vs. jetzt ändert
| Bereich | Alt (px) | Neu (px) | Einspar |
|---------|----------|----------|---------|
| Top-Bar | ~80 | 28 | **−52** |
| Workspace-NavBar | ~110 Row | 18 Tabs | **−92** |
| Status-Bar | ~30 | 14 | **−16** |
| Docks (Tasks/Konsole/Chat) | als Docks variabel | fest 300px rechts | aufgeräumt |
| Hintergrund-Prozesse-Panel | ~200 | entfällt (in Right Panel/TASKS) | **−200** |

**Brutto-Gewinn in Hauptinhalt: ~360 px vertikal, ~100 px horizontal.**

---

## 2. RIGHT PANEL (300 × 876, immer sichtbar)

Ersetzt alle `QDockWidget`s. Vier Tabs, 300 px breit, feste Höhe 876:

```
┌─ RIGHT PANEL ─────────────┐
│ [CHAT] [TASKS] [LOG] [ⓘ] │ 24 px Tab-Bar
├───────────────────────────┤
│                           │
│   Tab-Inhalt              │ 852 px
│                           │
└───────────────────────────┘
```

- **CHAT** — KI-Assistent (heute `ui/chat_dock.py`). Eingabezeile unten, Verlauf oben.
- **TASKS** — Laufende + fertige Background-Jobs (heute `task_manager_dock.py`).
  Ersetzt auch das große "HINTERGRUND-PROZESSE"-Panel im Footer.
- **LOG** — Konsolen-Stream (heute `console_text`). Fix 300 Zeichen/Zeile, max 500 Zeilen.
- **ⓘ (Inspector)** — Clip-Eigenschaften (heute `clip_inspector.py`). Nur aktiv im EDIT-Workspace, sonst greyed-out.

---

## 3. Pro Workspace — detailliert

Content-Area pro Workspace: **1193 × 876 px**.

### 3.1 MEDIA (heute chaotisch, 4+ Bereiche mischen sich)

```
┌ MEDIA 1193×876 ──────────────────────────────────────────────────┐
│ [VIDEO] [AUDIO]  ───────────── Toolbar: [+Import][+Ordner][⟳] │ 32 px
├──────────────────────────────────────────────────────────────────┤
│ ┌ POOL (VIDEO oder AUDIO, abh. von Tab) ─────────────────────┐ │
│ │  Tabelle: ID│Titel│Auflösung│FPS│Codec│Analyse%│Pfad         │ │
│ │  Genau 16 Zeilen sichtbar @ 28 px = 448 px                   │ │
│ │  Darunter: [◀ Seite 1/7 ▶]  [Alle wählen] [Löschen]          │ │
│ └──────────────────────────────────────────────────────────────┘ │ 490 px
├──────────────────────────────────────────────────────────────────┤
│ ┌ UNTERTABS ───────────────────────────────────────────────────┐ │
│ │  [ANALYSE-PIPELINE] [STATUS] [FILTER]                         │ │ 24 px
│ │ ───────────────────────────────────────                       │ │
│ │  ANALYSE-PIPELINE:                                             │ │
│ │    Video: [Szenen][Analyse][Voll-Pipeline][Voll+KI]            │ │
│ │    Audio: [BPM][Waveform][Key][LUFS][Struktur][Stems][Komplett]│ │
│ │    [Zur Timeline hinzufügen] (prominenter Primary)             │ │
│ └──────────────────────────────────────────────────────────────┘ │ 330 px
├──────────────────────────────────────────────────────────────────┤
│ Footer nichts — Analyse-Progress landet in RIGHT PANEL/TASKS     │
└──────────────────────────────────────────────────────────────────┘
```

**Was ersetzt was:**
- Der 92 px hohe VIDEO/AUDIO-Mode-Toggle → 32 px Tab-Bar
- Linke Sidebar mit Import/Pipeline-Buttons → Toolbar oben + Unter-Tab "ANALYSE-PIPELINE"
- VIDEO-POOL-Liste (heute scrollt) → feste 16 Zeilen + Paginierung
- ANALYSE-STATUS (heute eigenes Panel) → als Sub-Tab
- Sammlung bereinigen etc. → unter FILTER-Sub-Tab

---

### 3.2 EDIT (heute 5 Bereiche mischen sich unscharf)

```
┌ EDIT 1193×876 ────────────────────────────────────────────────────┐
│ [TIMELINE] [PACING] [INSPECTOR] [ANKER]                          │ 24 px
├──────────────────────────────────────────────────────────────────┤
│ TIMELINE-Tab (Standard):                                         │
│ ┌ Video-Preview ───────────────────────────────────────────────┐ │
│ │  640 × 360                                                    │ │ 360 px
│ └──────────────────────────────────────────────────────────────┘ │
│ ┌ Timeline-View (feste Höhe) ──────────────────────────────────┐ │
│ │  Ruler 24 / Audio-Track 80 / Video-Track 80 / Beatgrid 16    │ │
│ │  = 200 px                                                     │ │ 200 px
│ └──────────────────────────────────────────────────────────────┘ │
│ ┌ Transport ───────────────────────────────────────────────────┐ │
│ │  [▶][⏸][⏹] 0:12.34 / 62:25.50  [−][=][+] Zoom  [↥][↧] Fit  │ │ 32 px
│ └──────────────────────────────────────────────────────────────┘ │
│ Freiraum: 260 px → könnte Mini-Waveform/Spektrum/Beatgrid-Viz    │
└──────────────────────────────────────────────────────────────────┘

PACING-Tab:
┌ Audio/Video-Combos ──────────────────────────────────────────────┐
│ Audio: [────────▾]  Video: [────────▾]  Vibe: [────────────]     │ 28 px
├──────────────────────────────────────────────────────────────────┤
│ ┌ Manual Curve Drawer ─────────────────────────────────────────┐ │
│ │   Große Pacing-Kurve 1150 × 280                              │ │ 280 px
│ │   [Zurücksetzen]  [Exportieren]                               │ │
│ └──────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ Settings Grid 4×3:                                               │
│   Cut Rate [▾]    Style Preset [▾]    Breakdown [▾]              │ 180 px
│   Reactivity [===|===]  Density [===|===]                         │
│   Info-Label: "4 Cuts | Beat:3 | Drop:1 | 3745s"                 │
├──────────────────────────────────────────────────────────────────┤
│ Actions: [Timeline generieren] [Auto-Edit starten] [Als Regel▾] │ 32 px
└──────────────────────────────────────────────────────────────────┘

INSPECTOR-Tab:
- Heute rechts in schmalem Panel → hier als voller Tab 1193 × 828
- Clip-Liste links (selected), Felder rechts: start, end, brightness,
  contrast, crossfade_duration, effects, anchors, etc.

ANKER-Tab:
- Liste aller Anchors (audio_video_anchors + clip_anchors)
- Spalten: ID, Type, Audio-Time, Scene-ID, Video-Clip, Offset
- Buttons: [Hinzufügen] [Entfernen] [Synchronisieren]
```

**Heute-Problem:** Pacing-Kurve ist mickrig 80 × 60 — in neuem Design 1150 × 280.
Inspector ist 100 × 450 eingeklemmt — im neuen volles Tab.

---

### 3.3 STEMS (heute schon OK, nur Feintuning)

```
┌ STEMS 1193×876 ──────────────────────────────────────────────────┐
│ Track-Picker:   Audio-Track [▾]   [Stems neu trennen]            │ 32 px
├──────────────────────────────────────────────────────────────────┤
│ ┌ 4 Stem-Tracks ───────────────────────────────────────────────┐ │
│ │  [M][S] VOCALS  ━━━━━━━ Waveform 1100px ━━━━━━━━━  [Vol====] │ │  92 px
│ │  [M][S] DRUMS   ━━━━━━━ Waveform            ━━━━━  [Vol====] │ │  92 px
│ │  [M][S] BASS    ━━━━━━━ Waveform            ━━━━━  [Vol====] │ │  92 px
│ │  [M][S] OTHER   ━━━━━━━ Waveform            ━━━━━  [Vol====] │ │  92 px
│ └──────────────────────────────────────────────────────────────┘ │ 368 px
├──────────────────────────────────────────────────────────────────┤
│ Playback-Strip:  [▶][⏸][⏹]  0:00 / 62:25  ────=●====  Loop [□]  │ 44 px
├──────────────────────────────────────────────────────────────────┤
│ SUB-Tabs:   [ENERGIE] [ONSETS] [SNR]                             │ 24 px
│   - Energie pro Stem (normalisiert, 0-1)                          │
│   - Onsets-Plot (Drums/Bass)                                       │
│   - SNR-Metriken (heute schon berechnet, aber nicht gezeigt)      │
└──────────────────────────────────────────────────────────────────┘ 412 px für Tabs
```

**Heute-Problem:** Chat-Tabs zeigen "PB_studio v0.5.0 — PB_Stu..." (Fenstertitel)
statt sinnvolle Labels. Das ist ein separater Bug — fix: explizite Tab-Titel setzen.

---

### 3.4 CONVERT (heute: LOG-Riese, Side nur halb genutzt)

```
┌ CONVERT 1193×876 ────────────────────────────────────────────────┐
│ [BATCH-STANDARDISIERUNG] [CLIP-EFFEKTE]                          │ 24 px
├──────────────────────────────────────────────────────────────────┤
│ BATCH-Tab:                                                        │
│ ┌ Format-Settings ─────────────────────────────────────────────┐ │
│ │  Auflösung [1920×1080▾]  FPS [30▾]  Container [mp4 (H.264)▾]│ │ 80 px
│ │  Preset [Edit-Proxy 540p▾]     [NVENC prüfen] [Test-Frame]  │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ ┌ Quellen-Liste ───────────────────────────────────────────────┐ │
│ │  Tabelle: Clip│Aktuell│Ziel│Progress│Status (16 Zeilen)     │ │ 480 px
│ └──────────────────────────────────────────────────────────────┘ │
│ Actions: [Alle standardisieren] [Ausgewählte] [Abbrechen]        │ 32 px

CLIP-EFFEKTE-Tab:
│ Clip-Picker [▾]                                                   │ 28 px
│ ┌ Preview + Slider ────────────────────────────────────────────┐ │
│ │  Left: Preview 480×270                                        │ │
│ │  Right: Helligkeit [====|===]  -1.0 … 1.0                    │ │ 280 px
│ │         Kontrast   [====|===]   0.0 … 2.0                    │ │
│ │         Crossfade  [====|===]   0 … 5.0 s                    │ │
│ │         [Effekte anwenden]                                    │ │
│ └──────────────────────────────────────────────────────────────┘ │

SUB-Footer — Log (beiden Tabs): 120 px hoch, feste Höhe, in Bottom
```

**Heute-Problem:** CONVERT LOG nahm ~500px — reduziert auf 120 px am Fuß.
Clip-Effekte versteckt in linker Seitenleiste — bekommen eigenen Tab.

---

### 3.5 DELIVER (heute: leere Vorschau + leeres Protokoll dominieren)

```
┌ DELIVER 1193×876 ────────────────────────────────────────────────┐
│ [EXPORT] [VORSCHAU] [PROTOKOLL]                                  │ 24 px
├──────────────────────────────────────────────────────────────────┤
│ EXPORT-Tab:                                                       │
│ ┌ Timeline-Status ─────────────────────────────────────────────┐ │
│ │  Video-Clips: 766 | Audio-Tracks: 6 | Dauer: 3745.5 s         │ │ 44 px
│ └──────────────────────────────────────────────────────────────┘ │
│ ┌ Export-Settings Grid ────────────────────────────────────────┐ │
│ │  Dateiname [output.mp4──────]     Auflösung [1920×1080▾]     │ │
│ │  FPS [30▾]   Preset [▾]   LUFS-Normalisierung [✓]  -14 LUFS  │ │ 120 px
│ │  Ziel-Pfad: [C:\...──────────────────────────────────] [📁] │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ Actions: [Quick-Preview (~30s)] [Finales Video exportieren]      │ 32 px
│ Progress-Zeile (nur sichtbar während Export)                      │ 28 px
│                                                                   │
│ Freiraum ~620 px — Reserve oder Render-Queue-Tabelle              │

VORSCHAU-Tab:
│  Video-Player 960×540 zentriert                                  │
│  Transport: [◀10s][▶][⏸][▶10s]  0:00 / 5:32  Vol[=====]         │

PROTOKOLL-Tab:
│  Scrollbar-frei: 40 Zeilen × 20 Zeichen-Breite, danach rotation  │
│  Filter: [Alle▾] Timestamp | Level | Message                     │
```

---

## 4. Was komplett WEGGERÄUMT wird

Diese Elemente verschwinden oder wandern in Tabs:

| Element | Schicksal |
|---------|-----------|
| QMainWindow-Resize-Handle | `setFixedSize(1513,936)` |
| `_main_splitter` (Vertikal) | entfällt |
| `_bottom_panel` (Tasks/Konsole) | entfällt — wandert in RIGHT PANEL |
| `HINTERGRUND-PROZESSE`-Panel unten | entfällt — RIGHT PANEL/TASKS |
| `StatusBar` mit GPU-Percent + Splitter | reduziert auf 14 px Text-Zeile |
| `workspace_stack` riesige NavBar-Buttons 200×110 | 90×18 Tab-Bar |
| Alle `QScrollArea` in Workspaces | → Paginierung oder Tabs |
| `_audio_pool_stack` (ListenAnsicht/KachelAnsicht switch) | ein Mode, Rest als Filter |

---

## 5. Schriftgrößen-Audit (heute vs. neu)

Aktuelle Inkonsistenzen (aus dem UIA-Dump):
- NavBar-Buttons: Text in ~11 pt Bold, aber Buttons 200×110 → Text-Fläche nur 20%
- Toolbar-Buttons haben oft 10 pt, Dialoge 9 pt, Status 8 pt — chaotisch
- "STEM TRACKS"-Label: verschieden groß pro Stem

Neuer Standard (durchgängig):
```
Header:    12 pt 600 weight
Sub-Header: 10 pt 600
Body:        9 pt 400
Caption:     8 pt 400
Mono:        9 pt (Consolas) für Zahlen, Pfade, Log
```

---

## 6. Implementations-Reihenfolge (wenn du freigibst)

Pro Step ein separater Commit, testbar im Harness:

1. **Step 1 — Rahmen fix + Status/NavBar kompakt** (main.py, nav_bar.py)
   - `setFixedSize(1513, 936)`, Resize-disabled
   - TopBar auf 28 px, NavBar auf 18 px Tabs, Status auf 14 px
2. **Step 2 — RIGHT PANEL als TabWidget** (main.py, panel_setup.py)
   - QTabWidget ersetzt 3 Docks
   - HINTERGRUND-PROZESSE-Panel entfällt
3. **Step 3 — MEDIA-Workspace neu** (ui/workspaces/media_workspace.py)
4. **Step 4 — EDIT-Workspace neu** (ui/workspaces/edit_workspace.py)
5. **Step 5 — STEMS, CONVERT, DELIVER** (je eigener Commit)
6. **Step 6 — Theme-Audit** (ui/theme.py): einheitliche Fonts, Paddings, Farbe

**Geschätzter Aufwand:**
- Step 1+2: 2–3 h (Grundgerüst)
- Step 3–5: je 3–5 h (Workspaces komplett überarbeiten)
- Step 6: 1–2 h
- **Gesamt 15–25 h** verteilt auf 6 Commits

---

## 7. Risiken & offene Fragen an Dich

1. **Pacing-Kurve** war mal klein weil sie mit Inspector & Timeline den Platz geteilt hat. Neu: volle 1150×280 im PACING-Tab. OK?
2. **KI-Chat immer sichtbar?** Oder dynamisch ein-/aus­klappbar über die TOP-BAR-Knöpfe `[Tasks][Konsole][KI]`?
3. **"Zur Timeline hinzufuegen"** ist heute überall prominent. Ich hatte es im MEDIA→ANALYSE-PIPELINE-Tab vorgesehen. Reicht das oder auch in TOP-BAR?
4. **Statusleiste 14 px:** reicht dir das noch für CPU/GPU/VRAM/FFmpeg/Ollama/AI?
5. **Tab-Hotkeys?** (Ctrl+1..5 für Workspace-Wechsel, Ctrl+Tab innerhalb?) — kann ich einbauen.

---

**Nächster Schritt:** Ich warte auf dein OK oder deine Korrekturen zu diesem Plan.
Anschließend: Step 1 implementieren, App starten, dir Screenshot zur Freigabe.
Keine Änderung ohne Bestätigung.

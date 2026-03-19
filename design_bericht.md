# PB_studio v0.2.0 — Design Overhaul Bericht

## Status: ABGESCHLOSSEN

---

## 1. Dark Steel Stylesheet

**Datei:** `styles/dark_steel.qss` (komplett neues zentrales Stylesheet)

**Farbpalette:**
| Element | Farbe | Hex |
|---------|-------|-----|
| Hintergrund (Main) | Dunkel-Anthrazit | `#15171c` |
| Hintergrund (Widget) | Dunkel-Grau | `#1b1d23` |
| Hintergrund (Input) | Mittel-Grau | `#22252d` |
| Akzent Primaer | Neon-Cyan | `#00d4ff` |
| Akzent Sekundaer | Neon-Violett | `#7c3aed` |
| Text Normal | Hell-Grau | `#d0d0d0` |
| Text Gedaempft | Blau-Grau | `#808899` |

**Gestylte Komponenten:**
- QTabWidget: Abgerundete Tabs mit Cyan-Unterstrich bei Selektion
- QPushButton: 6px Radius, Hover-Glow, Pressed-State in Cyan
- QPushButton#btn_accent: Violett-zu-Cyan Gradient fuer Hauptaktionen
- QTableWidget: Dunkle Zeilen, violette Selektion, Cyan Header
- QScrollBar: Schlanke 10px mit runden Handles
- QSlider: Cyan-Handles auf dunkler Groove
- QProgressBar: Violett-zu-Cyan Gradient Chunk
- QGroupBox: Cyan-Title mit subtiler Border
- QDockWidget: Monospace Console mit Cyan-Text
- QComboBox: Custom Down-Arrow in Cyan

---

## 2. Video-Player (Vorschau)

**Klasse:** `VideoPreviewWidget(QLabel)` in `main.py`

**Position:** Director's Desk Tab, oben rechts (via QSplitter, 25% Breite)

**Features:**
- Extrahiert Frames via FFmpeg (320x180 Rohformat, pipe:1)
- Play/Stop Buttons mit Timer-basierter Frame-Abfolge (0.5s Schritte)
- Automatisches Laden beim Wechsel des Video-Combos
- Fallback-Text wenn FFmpeg nicht verfuegbar
- Windows-kompatibel (CREATE_NO_WINDOW Flag)

**Layout:**
```
+-----------------------------------+-------------+
| Pacing-Steuerung                  | Vorschau    |
| [Vibe] [Audio] [Video]           | [320x180]   |
| [Tempo] [Energie] [Dichte]       | [Play][Stop]|
| [Generate]                        | 00:00/00:00 |
+-----------------------------------+-------------+
| Timeline (Drag & Drop)                          |
| [Audio Track]                                    |
| [Video Track]                                    |
| [Cut Markers + Ruler]                            |
+--------------------------------------------------+
```

---

## 3. UI-Refinement (Icons + About)

**Button-Icons (Emoji-basiert):**
| Button | Icon |
|--------|------|
| Video importieren | Kamera |
| Audio importieren | Musiknote |
| Audio analysieren | Lupe |
| Video analysieren | Lupe rechts |
| Zur Timeline hinzufuegen | Plus |
| Timeline generieren | Blitz |
| Video exportieren | Rakete |
| Aktualisieren | Pfeil-Kreis |
| About | Info-Kreis |

**Tab-Icons:**
| Tab | Icon |
|-----|------|
| Media Ingest | Ordner |
| Director's Desk | Filmklappe |
| Production | Kamera |

**About-Dialog:**
- `AboutDialog(QDialog)` mit PB_studio Branding
- Version v0.2.0 Anzeige
- Cyan Title + Violett Subtitle
- Gradient "Schliessen" Button
- Fixe Groesse: 400x280

---

## 4. Stabilitaet

- Stylesheet wird einmalig beim App-Start via `QApplication.setStyleSheet()` geladen
- Kein Performance-Impact auf Timeline (QSS wird von Qt gecached)
- Inline-Styles aus Production Tab entfernt (Export-Button, Export-Log)
- VideoPreview nutzt subprocess mit Timeout (3s) — kein UI-Blocking
- Bestehende Worker-Threads und Signale unberuehrt

---

## Geaenderte Dateien

| Datei | Aenderung |
|-------|-----------|
| `main.py` | VideoPreviewWidget, AboutDialog, Icons, Stylesheet-Loading, Version |
| `styles/dark_steel.qss` | NEU — Komplettes Dark Steel Theme |
| `design_bericht.md` | NEU — Dieser Bericht |

---

## Naechste Schritte (Optional)

- [ ] Keyboard-Shortcuts fuer Play/Pause (Space)
- [ ] Timeline-Position an Preview koppeln (Click-to-Seek)
- [ ] Waveform-Overlay in Audio-Track
- [ ] Custom SVG-Icons statt Emojis (fuer aeltere Windows-Versionen)

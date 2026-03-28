# PB Studio Rebuild — Roadmap to Release

**Stand:** 2026-03-28
**Version:** v0.5.0 (stable, alle Audit-Bugs gefixt)
**Ziel:** v1.0.0 Release-Candidate fuer erste User

---

## Aktueller Status

| Metrik | Wert |
|--------|------|
| Python-Dateien | 94 |
| Code-Zeilen | ~27.500 |
| Tests | 202 (alle gruen) |
| Offene Bugs | 0 |
| Systemgesundheit | GUT |
| main.py | 1002 Zeilen (8 Mixins) |

### Was FUNKTIONIERT (v0.5.0)
- [x] Audio-Import + BPM/Beat Detection (beat_this, GPU)
- [x] Stem Separation (Demucs htdemucs_ft, GPU-Chunking)
- [x] Video-Import + Proxy-Erstellung (NVENC)
- [x] Szenen-Erkennung + RAFT Motion-Scoring (Batch-cached)
- [x] SigLIP Embeddings + Semantische Suche (VectorDB)
- [x] Key Detection, LUFS, Genre/Mood, Spektral, Struktur
- [x] Pacing Engine (PhD-Level, Beat-Sync, Energy-Reactive)
- [x] Auto-Edit (Timeline generieren aus Audio+Video)
- [x] Timeline-Ansicht (Waveform, Beats, Clips verschiebbar)
- [x] Export/Render (FFmpeg, Crossfades, Color Correction)
- [x] Multi-Agent Chat (Qwen 0.5B, lokal, offline)
- [x] Gold-Accent Dark Theme (DaVinci Resolve Style)
- [x] 5 Workspaces (Media, Edit, Stems, Convert, Deliver)

### Was FEHLT fuer v1.0

---

## Phase 6: Critical Blockers (v0.6.0)

**Ohne diese Features kann kein User die App produktiv nutzen.**

### 6.1 Projekt Save/Load — P0
- [ ] "Neues Projekt" Dialog (Name, Pfad, Resolution, FPS)
- [ ] "Projekt oeffnen" Dialog (waehlt .pbstudio Ordner)
- [ ] "Projekt speichern unter" (kopiert DB + Storage in Zielordner)
- [ ] Multi-Projekt Support (DB-Pfad wird dynamisch, nicht hardcoded)
- [ ] "Letzte Projekte" Liste im Startscreen
- **Aufwand:** Mittel — DB-Engine muss dynamisch werden, UI fuer Dialoge
- **Abhaengigkeit:** Keine

### 6.2 Timeline Clip-Operationen — P0
- [ ] Clip loeschen (Delete-Taste + Rechtsklick-Menue)
- [ ] Clip trimmen (In/Out Points per Drag an Clip-Kanten)
- [ ] Clip splitten (an Playhead-Position)
- [ ] Multi-Clip Selektion (Shift+Click, Rubber-Band)
- [ ] Timeline Playhead (klickbar, scrubbing)
- **Aufwand:** Mittel — UI-Interaktionen in ui/timeline.py
- **Abhaengigkeit:** Keine

### 6.3 Dependency-Check beim Start — P0
- [ ] FFmpeg auf PATH pruefen (mit Version)
- [ ] CUDA/GPU erkennen und anzeigen (Name, VRAM)
- [ ] Warnung wenn kein GPU → "CPU-Modus nicht unterstuetzt"
- [ ] HuggingFace Cache pruefen (Modelle vorhanden?)
- [ ] Ergebnis in Statusbar + Startup-Dialog anzeigen
- **Aufwand:** Gering
- **Abhaengigkeit:** Keine

### 6.4 Keyboard Shortcuts — P1
- [ ] Space = Play/Pause
- [ ] Delete = Clip loeschen
- [ ] Ctrl+Z = Undo (benoetigt 6.5)
- [ ] Ctrl+I = Import
- [ ] Ctrl+E = Export
- [ ] Ctrl+S = Projekt speichern
- [ ] +/- = Timeline Zoom
- [ ] L/J/K = Playback (wie Premiere/Resolve)
- **Aufwand:** Gering — QAction + QShortcut
- **Abhaengigkeit:** 6.2 (Clip-Operationen)

### 6.5 Undo/Redo — P1
- [ ] QUndoStack in MainWindow
- [ ] Undo-Commands fuer: Clip verschieben, loeschen, trimmen, hinzufuegen
- [ ] Ctrl+Z / Ctrl+Y Shortcuts
- **Aufwand:** Mittel — Qt hat QUndoStack, aber jede Aktion braucht ein Command
- **Abhaengigkeit:** 6.2 (Clip-Operationen muessen definiert sein)

---

## Phase 7: UX & Polish (v0.7.0)

**Macht die App benutzbar und professionell.**

### 7.1 Drag & Drop Import — P1
- [ ] Dateien aus Explorer auf Media-Workspace droppen
- [ ] Auto-Erkennung: Audio vs Video anhand Extension
- [ ] Fortschrittsanzeige beim Import
- **Aufwand:** Gering — QWidget.setAcceptDrops(True) + dragEnterEvent/dropEvent

### 7.2 Video-Preview mit Audio — P1
- [ ] Timeline-Playhead synchronisiert mit Video-Preview
- [ ] Audio-Playback waehrend Preview (gemixte Timeline)
- [ ] Scrubbing: Klick auf Timeline → Preview springt
- **Aufwand:** Hoch — Erfordert Audio/Video Sync-Engine (QMediaPlayer oder custom)
- **Abhaengigkeit:** 6.2 (Timeline Playhead)

### 7.3 Settings Dialog — P2
- [ ] FFmpeg Pfad konfigurierbar
- [ ] Standard-Resolution / FPS
- [ ] Proxy-Qualitaet (360p/540p/720p)
- [ ] GPU-Device Auswahl (falls mehrere)
- [ ] Theme-Auswahl (Dark/Gold — spaeter weitere)
- [ ] Settings in QSettings (persistent, plattformunabhaengig)
- **Aufwand:** Mittel

### 7.4 Verbesserte Progress-Anzeige — P2
- [ ] Geschaetzte Restzeit bei langen Operationen
- [ ] Cancel-Button direkt im Workspace (nicht nur Tasks-Panel)
- [ ] Fortschrittsbalken bei Video-Batch-Analyse sichtbar im Hauptfenster
- **Aufwand:** Gering

### 7.5 Error-Recovery UI — P2
- [ ] "Etwas ist schiefgegangen" Dialog statt stiller Fehler
- [ ] GPU OOM → Benutzerfreundliche Meldung + Vorschlaege
- [ ] FFmpeg-Fehler → "FFmpeg nicht gefunden" mit Installationsanleitung
- **Aufwand:** Gering

---

## Phase 8: Packaging & Installer (v0.8.0)

**Macht die App installierbar fuer User ohne Python-Kenntnisse.**

### 8.1 PyInstaller EXE — P0
- [ ] .spec Datei erstellen (hidden imports: torch, PySide6, librosa, etc.)
- [ ] One-folder Mode (nicht one-file — zu gross fuer AV-Scanner)
- [ ] App-Icon (.ico) erstellen und einbinden
- [ ] Entry Point: `main.py:main()`
- [ ] Test: EXE startet auf sauberem Windows 11 System
- **Aufwand:** Hoch — PyTorch + CUDA + PySide6 Bundling ist komplex
- **Abhaengigkeit:** Alle Features von Phase 6+7 muessen stabil sein

### 8.2 FFmpeg Bundling — P0
- [ ] FFmpeg Binaries (ffmpeg.exe + ffprobe.exe) mit ausliefern
- [ ] Oder: Installer prueft + installiert FFmpeg automatisch
- [ ] FFMPEG_PATH auf gebundelte Binaries setzen
- **Aufwand:** Gering — Statische Binaries von gyan.dev, ~80MB

### 8.3 KI-Modell Pre-Download — P1
- [ ] Script: Alle HuggingFace-Modelle vorab herunterladen
- [ ] Cache-Ordner in Installer integrieren oder beim First-Run laden
- [ ] Fortschrittsanzeige beim Model-Download (~3-5 GB)
- [ ] Offline-Modus: Wenn alle Modelle gecached sind
- Modelle: SigLIP (~1.5GB), Demucs (~300MB), beat_this (~200MB), Qwen (~500MB)
- **Aufwand:** Mittel

### 8.4 CUDA Toolkit — P1
- [ ] CUDA Runtime DLLs mit ausliefern (oder Installer prueft NVIDIA-Treiber)
- [ ] cuDNN Bibliotheken bundeln
- [ ] Treiber-Version Check beim Start (min. 535.xx fuer CUDA 12.x)
- **Aufwand:** Mittel — PyTorch bringt eigene CUDA-Libs mit, aber Treiber muss passen

### 8.5 Windows Installer (NSIS/Inno Setup) — P1
- [ ] Installer-Wizard: Willkommen → Lizenz → Pfad → Installieren → Fertig
- [ ] Desktop-Shortcut + Startmenue-Eintrag
- [ ] Uninstaller
- [ ] File Association: .pbstudio → PB Studio
- [ ] Optional: FFmpeg mitinstallieren
- [ ] Optional: NVIDIA Treiber-Check + Download-Link
- **Aufwand:** Mittel — Inno Setup Script, ca. 200 Zeilen
- **Abhaengigkeit:** 8.1 (EXE muss existieren)

### 8.6 First-Run Wizard — P2
- [ ] "Willkommen bei PB Studio" Screen
- [ ] System-Check: GPU, FFmpeg, Speicherplatz
- [ ] "KI-Modelle herunterladen" Button (3-5 GB)
- [ ] "Beispiel-Projekt laden" Option
- [ ] "Los gehts!" → Oeffnet leeres Projekt
- **Aufwand:** Mittel

---

## Phase 9: Release-Candidate (v0.9.0 → v1.0.0)

### 9.1 QA & Testing — P0
- [ ] Vollstaendiger E2E-Test: Import → Analyse → Auto-Edit → Export
- [ ] Test mit 2h DJ-Mix (Langstrecken-Stabilitaet)
- [ ] Test auf 3 verschiedenen Windows-Systemen
- [ ] Test mit/ohne GPU (graceful degradation)
- [ ] Test mit 200+ Video-Clips (Batch-Performance)
- [ ] Memory-Leak Test (24h Idle + wiederholte Analyse)

### 9.2 Dokumentation — P1
- [ ] Benutzerhandbuch (PDF/HTML, 20-30 Seiten)
- [ ] Quick-Start Guide (1 Seite)
- [ ] FAQ: "App startet nicht" / "GPU nicht erkannt" / "Export dauert lang"
- [ ] Changelog v0.1 → v1.0

### 9.3 Legal & Lizenzen — P1
- [ ] Open-Source Lizenzen aller Dependencies auflisten
- [ ] Eigene Lizenz waehlen (MIT? Proprietary? Freemium?)
- [ ] EULA fuer Installer
- [ ] Privacy: Welche Daten werden lokal gespeichert? (Antwort: alles lokal, kein Cloud)

### 9.4 Release — P0
- [ ] Version Bump → 1.0.0
- [ ] Release Notes schreiben
- [ ] GitHub Release + Installer Upload
- [ ] Landing Page / Download-Seite

---

## Abhaengigkeits-Graph

```
Phase 6 (Blocker)          Phase 7 (UX)              Phase 8 (Installer)
━━━━━━━━━━━━━━━━           ━━━━━━━━━━━━━             ━━━━━━━━━━━━━━━━━━
6.1 Projekt Save ──────┐
6.2 Clip-Ops ─────┬───┐│   7.1 Drag&Drop
6.3 Dep-Check      │   ││   7.2 Preview+Audio ←── 6.2
6.4 Shortcuts ←── 6.2  ││   7.3 Settings
6.5 Undo/Redo ←── 6.2  ││   7.4 Progress
                        ││   7.5 Error UI
                        ││                         8.1 PyInstaller EXE
                        ││                         8.2 FFmpeg Bundle
                        │└─────────────────────→  8.3 Model Pre-Download
                        └──────────────────────→  8.5 Installer ←── 8.1
                                                  8.6 First-Run ←── 6.3

                              Phase 9 (Release)
                              ━━━━━━━━━━━━━━━━━
                              9.1 QA ←── 8.5
                              9.2 Docs
                              9.3 Legal
                              9.4 Release ←── 9.1 + 9.2 + 9.3
```

---

## Aufwand-Schaetzung (grob)

| Phase | Aufwand | Beschreibung |
|-------|---------|--------------|
| **Phase 6** | 3-5 Tage | Projekt Save/Load, Clip-Ops, Shortcuts, Undo |
| **Phase 7** | 3-5 Tage | Drag&Drop, Preview+Audio, Settings, Error UI |
| **Phase 8** | 3-5 Tage | PyInstaller, FFmpeg Bundle, Installer, Models |
| **Phase 9** | 2-3 Tage | QA, Docs, Legal, Release |
| **Gesamt** | **~12-18 Tage** | Von jetzt bis v1.0.0 |

---

## Empfohlene Reihenfolge

**Sprint 1 (Phase 6.1-6.3):** Projekt Save/Load + Clip-Ops + Dep-Check
→ Danach kann man die App das erste Mal "echt" benutzen

**Sprint 2 (Phase 6.4-6.5 + 7.1-7.2):** Shortcuts + Undo + Drag&Drop + Preview
→ App fuehlt sich wie ein echtes Tool an

**Sprint 3 (Phase 7.3-7.5 + 8.1-8.2):** Settings + Error UI + EXE + FFmpeg
→ App laeuft standalone

**Sprint 4 (Phase 8.3-8.6 + 9):** Models + Installer + QA + Release
→ v1.0.0

---

## LOCKED Entscheidungen (nicht aendern ohne Freigabe)

| Komponente | Entscheidung |
|------------|-------------|
| GUI Framework | PySide6/Qt6 |
| Database | SQLAlchemy + SQLite WAL |
| GPU Pipeline | PyTorch + CUDA 12.x |
| Beat Detection | beat_this (CPJKU) |
| Stem Separation | Demucs htdemucs_ft |
| Visual Embeddings | SigLIP-so400m-patch14-384 (1152-dim) |
| Timeline Format | OpenTimelineIO |
| Agent LLM | Qwen 2.5 0.5B Instruct (lokal) |
| Installer | Inno Setup (Windows) |
| EXE Builder | PyInstaller (one-folder) |

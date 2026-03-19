# PB_studio Mega Night Log

## Datum: 2026-03-19

---

## PHASE 0: Tooling & Setup

### Pakete installiert
- `demucs 4.0.1` - KI Stem Separation (htdemucs Modell)
- `opencv-python 4.13.0.92` - Computer Vision / Video
- `scipy 1.17.1` - Audio-Mathematik (bereits als transitive Dep vorhanden)
- `torchcodec 0.10.0` - nachinstalliert fuer Demucs (DLL-Problem auf Windows, Workaround: --mp3 Flag)
- `torch 2.10.0` + `torchaudio 2.10.0` - als Demucs-Dependencies

### DB-Migration
- `audio_tracks`: Neue Spalten `stem_vocals_path`, `stem_drums_path`, `stem_bass_path`, `stem_other_path`
- `timeline_entries`: Neue Spalten `crossfade_duration`, `brightness`, `contrast`
- Migration via ALTER TABLE auf bestehende pb_studio.db

---

## PHASE 1: AI Audio Deep-Dive

### Stem Separation (services/ai_audio_service.py)
- **StemSeparator**: Nutzt Demucs htdemucs Modell
- Trennt Audio in 4 Stems: Vocals, Drums, Bass, Other
- Output als MP3 (--mp3 Flag, vermeidet torchcodec DLL-Problem auf Windows)
- Stems werden in `storage/stems/htdemucs/<trackname>/` gespeichert
- Pfade werden in AudioTrack DB-Spalten persistiert
- **Test**: 30s Psy-Track in 96s separiert (CPU-only, GTX 1060)
- **GUI**: Button "KI Stem Separation" im Media Ingest Tab

### Auto-Ducking
- **AutoDucker**: Senkt Musik ab wenn Voice erkannt wird
- Primär: Scipy-basiert (robust, plattformunabhaengig)
  - Voice RMS Envelope mit 50ms Fenster
  - Gain-Faktor aus dB (-12dB = 0.25 Multiplikator)
  - Smooth via uniform_filter1d (Attack/Release)
  - Clipping-Schutz (Peak-Normalisierung auf 0.95)
- Fallback-Kette: FFmpeg sidechaincompress -> Scipy
- Automatische WAV-Konvertierung fuer MP3-Inputs
- **Test**: 30s Ducking in <1s (Scipy-Methode)
- **GUI**: Button "Auto-Ducking" im Media Ingest Tab

---

## PHASE 2: Smart Auto-Editing

### Drum-Track-Analyse (pacing_service.py)
- `calculate_drum_cuts()`: Onset Detection auf Drums-Stem
  - librosa onset_strength + onset_detect
  - RMS-basierte Staerke-Bewertung pro Onset
  - Konfigurierbarer energy_threshold
- **Problem**: Progressive Psy Track hat Drums nur im Buildup (letzte 2s)
- **Loesung**: Fallback auf BPM-Beats wenn <10 Drum-Cuts

### Auto-Edit to Beat
- `auto_edit_to_beats()`: Verteilt Video-Clips auf Beat-Marker
  - Drum-Cuts oder BPM-Beats als Zeitpunkte
  - Mindest-Segmentdauer: 0.3s
  - Clips rotieren zyklisch durch verfuegbare Videos
  - Lueckenlose Abdeckung der Gesamtdauer
- **Test**: 143.6 BPM -> 72 Segmente auf 30s (0.418s pro Beat)
- **GUI**: Button "Auto-Edit to Beat" im Director's Desk

---

## PHASE 3: Advanced Video Engine & Effekte

### Crossfades
- `xfade` FFmpeg-Filter fuer weiche Ueberblendungen
- Konfigurierbar: 0-3.0 Sekunden Dauer
- Automatische Offset-Berechnung basierend auf Clip-Dauer
- Unterstuetzt `fade` Transition
- **Test**: 3 Clips mit 0.5s Crossfade erfolgreich exportiert

### Farbkorrektur
- `eq` FFmpeg-Filter fuer Helligkeit (-1.0 bis 1.0) und Kontrast (0.0 bis 3.0)
- Pro Timeline-Entry konfigurierbar
- Effekt-Vorschau via FFmpeg Frame-Extraction
- **GUI**: Neuer Tab "Effects" mit:
  - Clip-Auswahl Dropdown
  - Helligkeit-Slider (-100 bis +100)
  - Kontrast-Slider (0 bis 300)
  - Crossfade-Slider (0 bis 3.0s)
  - "Effekte anwenden" Button
  - Live-Vorschau des Effekts

### Export-Service Optimierung
- **Strategie-Auswahl**:
  - <=10 Clips mit Effekten: Filtergraph (Crossfades + eq)
  - >10 Clips oder keine Effekte: Optimierter Concat
- **Concat mit Duration**: `duration` Direktive fuer korrekte Segment-Laengen
- **Preset**: `fast` statt `medium` fuer schnelleren Export
- **Test**: 23 Clips + Audio in 29s exportiert (854x480)

---

## PHASE 4: Multithreading & Performance

### Thread-Architektur
- **Generische Thread-Verwaltung**: `_start_worker_thread()` Methode
- Alle schweren Operationen in QThread:
  - `AnalysisWorker`: Audio-Analyse (librosa BPM/Beats)
  - `VideoAnalysisWorker`: Video-Metadaten + Proxy
  - `StemSeparationWorker`: Demucs KI-Analyse
  - `AutoDuckingWorker`: Scipy/FFmpeg Ducking
  - `ExportWorker`: FFmpeg Video-Export
  - `AutoEditWorker`: Drum-Cut-Berechnung
- Worker-Cleanup nach Thread-Ende
- GUI friert waehrend keiner Operation ein

### Globaler Task-Manager
- **TaskInfo** Dataclass: task_id, name, status, progress, elapsed
- **GlobalTaskManager** (QObject):
  - Qt Signals: task_added, task_updated, task_finished
  - Thread-sicheres Task-Tracking
  - Fortschritts-Propagation von Workers
- **TaskManagerWidget** (QTreeWidget):
  - 4 Spalten: Task, Status, Fortschritt, Zeit
  - Auto-Update der Elapsed-Zeit (1s Timer)
  - Farbkodierung: Running=Gruen, Done=Cyan, Error=Rot
  - In Hauptfenster integriert

---

## Test-Ergebnisse

### Unit Tests (pytest)
- 21 bestehende Tests: ALLE PASSED
- 12 neue Feature-Tests: ALLE PASSED
- Gesamt: 33/33 Tests bestanden

### Integration Tests (echte Daten)
| Test | Ergebnis | Details |
|------|----------|---------|
| Audio-Import (MP3, WAV, M4A) | OK | 3 Tracks importiert |
| Video-Import (5x MP4) | OK | 720x480, 30fps, h264 |
| Audio-Analyse (BPM) | OK | 143.6 BPM, 8696 Beats |
| Video-Analyse (ffprobe) | OK | Metadaten + Proxy |
| Stem Separation (30s) | OK | 4 Stems in 96s (CPU) |
| Auto-Ducking (30s) | OK | Scipy in <1s |
| Pacing (287 Cuts) | OK | Beat-basiert @143.6 BPM |
| Auto-Edit (72 Segmente) | OK | Lueckenlos auf 30s |
| Simple Export | OK | 3 Clips + Audio |
| Effects Export (Crossfade+Color) | OK | 3 Clips mit Effekten, 20s |
| Komplex-Export (23 Clips) | OK | Auto-Edit + Effekte + Audio, 29s |

### Exportierte Videos
| Datei | Groesse | Dauer | Beschreibung |
|-------|---------|-------|--------------|
| test_phase3_simple.mp4 | ~5 MB | 30s | 3 Clips concat |
| test_phase3_effects.mp4 | ~5 MB | 30s | Crossfade + Farbkorrektur |
| test_quick_export.mp4 | 5.3 MB | 10s | 24 Auto-Edit Segmente |
| test_effects_crossfade.mp4 | 4.8 MB | 30s | Filtergraph-Export |
| mega_night_complex.mp4 | 6.3 MB | 24.4s | 23 Segmente + Effekte + Audio |

---

## Architektur-Uebersicht (v0.3.0)

```
PB_studio v0.3.0
├── main.py (PBWindow - 4 Tabs + Task Manager)
│   ├── Tab 1: Media Ingest (Import + Analyse + Stems + Ducking)
│   ├── Tab 2: Director's Desk (Pacing + Auto-Edit + Timeline)
│   ├── Tab 3: Effects (Farbkorrektur + Crossfade)
│   └── Tab 4: Production (Export)
│
├── database.py (8 Models + Stem-Felder + Effect-Felder)
│
├── services/
│   ├── ai_audio_service.py   [NEU] Demucs Stems + Auto-Ducking
│   ├── audio_service.py       BPM/Beat-Analyse (librosa)
│   ├── video_service.py       Metadaten + Proxy (ffprobe/ffmpeg)
│   ├── pacing_service.py     [ERWEITERT] + Drum-Cuts + Auto-Edit
│   ├── export_service.py     [ERWEITERT] + Crossfade + Farbkorrektur
│   └── ingest_service.py     [ERWEITERT] + Stem-Status
│
├── tests/
│   ├── test_new_features.py  [NEU] 12 Tests Phase 1-4
│   └── ... (21 bestehende Tests)
│
└── storage/
    ├── stems/htdemucs/       KI-separierte Stems
    ├── ducked/               Auto-Ducking Outputs
    └── proxies/              Video-Proxies
```

---

## Bekannte Limitierungen
1. **Demucs auf CPU**: 96s fuer 30s Audio. GPU (CUDA) wuerde ~10x schneller sein.
2. **torchcodec DLL-Problem**: Auf Windows muss `--mp3` Flag verwendet werden.
3. **Concat-Export mit vielen Clips**: 24 Clips = 51s Export. Fuer 100+ Clips waere ein Pre-Concat sinnvoll.
4. **Drum-Onset in Ambient-Tracks**: Wenige Onsets bei leisen/atmosphaerischen Passagen. Fallback auf BPM funktioniert.
5. **FFmpeg sidechaincompress**: Stream-Specifier-Problem mit MP3-Inputs. Scipy-Fallback funktioniert zuverlaessig.

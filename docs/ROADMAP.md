# PB Studio Rebuild — Roadmap

**Letzte Aktualisierung:** 2026-03-27
**Version:** v0.5.0-dev
**Branch:** master

---

## Projekt-Status: AKZEPTABEL

| Metrik                | Wert                    |
|-----------------------|-------------------------|
| Python-Dateien        | 94                      |
| Code-Zeilen (Python)  | ~27.500                 |
| Tests                 | 292 (alle gruen)        |
| Phase-4 Service Tests | 66/66 gruen             |
| Systemgesundheit      | AKZEPTABEL (nach Audit) |
| Kritische Bugs        | 0                       |
| Offene mittlere Bugs  | 9 (dokumentiert)        |

---

## Abgeschlossene Meilensteine

### Phase 1-3: Core (DONE)
- [x] PySide6 MainWindow mit Dark Theme
- [x] SQLAlchemy DB mit 15+ Models (WAL-Modus)
- [x] Video-Import + SigLIP Embeddings (768-dim)
- [x] Audio-Import + Beat Detection (beat_this)
- [x] Stem Separation (Demucs htdemucs_ft)
- [x] Multi-Agent System (Orchestrator, Audio, Vision, Editor)
- [x] Pacing Engine (PhD-Level, Beat-Sync)
- [x] Timeline (OpenTimelineIO)
- [x] Export/Render Pipeline

### Phase 4: Audio-Analyse Services (DONE)
- [x] Key Detection Service (Camelot Wheel)
- [x] LUFS Analysis Service (FFmpeg loudnorm)
- [x] Audio Classify Service (Genre, Mood, Energy, DJ-Mix)
- [x] Spectral Analysis Service (Band-Energie, Events)
- [x] Structure Detection Service (Intro/Verse/Drop/Outro)
- [x] Gold-Accent Dark Theme
- [x] UI Workspaces (Media, Edit, Stems, Convert, Deliver)

### Grand Audit (DONE — 2026-03-27)
- [x] 3-Zyklen Audit mit 14 Unteragenten
- [x] 89 Findings analysiert, 30+ Bugs gefixt
- [x] 5 hohe Fehler behoben (GPU-Startup, Syntax, Algorithmen)
- [x] Security: trust_remote_code entfernt, SQL-Injection gefixt
- [x] Systemgesundheit: PROBLEMATISCH -> AKZEPTABEL

---

## Abgeschlossene Phase: v0.5.0 — Refactoring & Stabilisierung (DONE)

Basiert auf: `docs/REFACTORING_PLAN.md` — alle 5 Phasen abgeschlossen.

### Phase A: Tests (DONE)
- [x] 66 Unit-Tests fuer alle 5 Phase-4 Services
- [x] conftest.py mit In-Memory DB Fixtures
- [x] Alle Tests gruen

### Phase B: audio_constants.py einbauen (DONE)
- [x] Alle 5 Services nutzen audio_constants (19 Imports)
- [x] Keine Magic Numbers mehr in Analyse-Logik

### Phase C: Librosa Import-Guard vereinheitlichen (DONE)
- [x] Alle Services nutzen _HAS_LIBROSA auf Modul-Ebene

### Phase D: Lange Methoden aufsplitten (DONE)
- [x] structure_detection_service.detect() -> 5 Sub-Methoden
- [x] spectral_analysis_service._detect_events() -> 4 Sub-Methoden
- [x] lufs_service.analyze() -> _run_ffmpeg() + _extract_values()

### Phase E: Worker Template-Method Pattern (DONE)
- [x] BaseAnalysisWorker mit Template-Pattern in workers/audio_analysis.py
- [x] 5 Worker erben von BaseAnalysisWorker

---

## Bekannte offene Probleme

### Mittlere Prioritaet (P2 — ALLE GEFIXT)
| ID       | Beschreibung                          | Status       |
|----------|---------------------------------------|--------------|
| V-003    | 3 GPU-Systeme nicht serialisiert      | GEFIXT       |
| S-01     | ai_audio stderr nicht via Sanitizer   | GEFIXT       |
| L-02     | VectorDB ID-Arithmetik fragil         | GEFIXT       |
| E-005    | vf_extra float(None)/NaN              | GEFIXT       |
| Z2S-003  | audio_service Race Condition          | GEFIXT       |
| Z2S-004  | structure_detection Off-by-One        | GEFIXT       |
| Z2S-008  | Spektral Nyquist-Grenze               | GEFIXT       |
| Z2S-022  | action_registry mutiert Handler-Dict  | GEFIXT       |
| Z2S-025  | TaskManager Singleton nicht threadsafe | GEFIXT       |

### Tech Debt (P3 — Backlog)
- ~~main.py Modularisierung~~ ERLEDIGT (2785 → 1002 Zeilen, 8 Mixins)
- ~~PyTorch CVE-2025-32434~~ ERLEDIGT (v2.10.0+cu126 ist sicher)
- ~~Clip-Drag DB-Writes ohne Debounce~~ ERLEDIGT (200ms Timer in ui/timeline.py)
- ~~Worker-Leaks: deleteLater()~~ ERLEDIGT (_start_worker_thread hat korrektes Cleanup)

### Erledigte Security/Bug Items (diese Session)
- PyTorch CVE: v2.10.0 installiert (Fix war in v2.6.0)
- S-01: _sanitize_ffmpeg_error() in ai_audio_service.py eingebaut
- Z2S-003: Per-Track Threading-Lock in audio_service.py
- __init__ Struktur-Bug: UI-Setup aus _do_refresh_media_table zurueck in __init__
- Worker deleteLater(): Bereits korrekt in _start_worker_thread()
- Clip-Drag Debounce: Bereits implementiert (200ms Timer)

---

## Naechste Schritte (Empfehlung)

1. **v0.6.0 Feature-Planung** — Naechste Feature-Phase definieren
2. **QA-Lauf** — Vollstaendiger E2E-Test mit echten Daten
3. **Release vorbereiten** — Changelog, Version bump, PyInstaller-Test

---

## LOCKED Entscheidungen (nicht aendern ohne Freigabe)

| Komponente         | Entscheidung                          |
|--------------------|---------------------------------------|
| GUI Framework      | PySide6/Qt6                           |
| Database           | SQLAlchemy + SQLite WAL               |
| GPU Pipeline       | PyTorch + CUDA 12.1                   |
| Beat Detection     | beat_this (CPJKU)                     |
| Stem Separation    | Demucs htdemucs_ft                    |
| Visual Embeddings  | SigLIP-so400m-patch14-384 (768-dim)   |
| Timeline Format    | OpenTimelineIO                        |
| Agent LLM          | Qwen 2.5 0.5B Instruct (lokal)       |
| ModelManager       | Singleton Pattern                     |
| SessionManager     | Single Source of Truth fuer State     |

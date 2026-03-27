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

### Mittlere Prioritaet (P2 — dokumentiert)
| ID       | Beschreibung                          | Status       |
|----------|---------------------------------------|--------------|
| V-003    | 3 GPU-Systeme nicht serialisiert      | AKZEPTIERT   |
| S-01     | ai_audio stderr nicht via Sanitizer   | OFFEN        |
| L-02     | VectorDB ID-Arithmetik fragil         | AKZEPTIERT   |
| E-005    | vf_extra float(None)/NaN              | AKZEPTIERT   |
| Z2S-003  | audio_service Race Condition          | DOKUMENTIERT |
| Z2S-004  | structure_detection Off-by-One        | DOKUMENTIERT |
| Z2S-008  | Spektral Nyquist-Grenze               | DOKUMENTIERT |
| Z2S-022  | action_registry mutiert Handler-Dict  | DOKUMENTIERT |
| Z2S-025  | TaskManager Singleton nicht threadsafe | AKZEPTIERT   |

### Tech Debt (P3 — Backlog)
- main.py hat 2781 Zeilen (Refactoring-Kandidat, aber funktional)
- PyTorch CVE-2025-32434 (CVSS 9.3) — Update auf sichere Version noetig
- Clip-Drag DB-Writes ohne Debounce (Performance bei vielen Clips)
- Worker-Leaks: deleteLater() fehlt an manchen Stellen

---

## Naechste Schritte (Empfehlung)

1. **P1: Security** — PyTorch auf sichere Version updaten (CVE-2025-32434)
2. **P2: main.py Modularisierung** — 2781 Zeilen aufteilen in Module
3. **P2: Mittlere Bugs** — S-01 (Sanitizer), Z2S-003 (Race Condition) fixen
4. **P3: Performance** — Clip-Drag Debounce, Worker deleteLater()
5. **P3: Feature** — Naechste Feature-Phase planen (v0.6.0)

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

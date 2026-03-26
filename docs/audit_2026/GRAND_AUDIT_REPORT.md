# Grand Audit Abschlussbericht

**Datum**: 2026-03-23
**Projekt**: PB Studio Rebuild (`C:\Users\david\Documents\App_Projekte\PB_studio_Rebuild`)
**Audit-Zyklen durchgefuehrt**: 1 (Findings eindeutig genug fuer hohe Konfidenz)
**Unteragenten eingesetzt**: 5 (Syntax+Security, Pacing-Engine, Database+Services, GUI-Wiring+Integration, Audio/Video/GPU)
**Geprueft von**: Grand Auditor (Claude Opus 4.6)
**Dateien im Scope**: 27 Python-Dateien + 1 Markdown-Spec
**Dateien tatsaechlich gelesen**: 27/27 (100%)

---

## Executive Summary

PB Studio Rebuild hat eine **solide Grundarchitektur**: korrektes Qt-Threading, sauberes Session-Handling, keine Security-Vulnerabilities, GPU-Zwang konsequent durchgesetzt. Die neu erstellte PhD-Level Pacing-Spezifikation und der PacingAgent sind syntaktisch korrekt und gut strukturiert.

**Jedoch**: Die drei Kernfeatures des PhD-Algorithmus (Stem-gewichtete Energie, Makro-Sektionserkennung, Motion-adaptives Pacing) sind **nicht implementiert** — sie existieren nur als Spezifikation und System-Prompt. Zusaetzlich werden `source_end`-Werte nie in die Datenbank geschrieben, wodurch der Auto-Edit-Export inhaltlich falsch ist. Ein falscher SigLIP-Default im ModelManager wuerde alle Embeddings mit falscher Dimension erzeugen.

**Empfehlung**: Die 5 kritischen und 11 hohen Fehler muessen vor jedem Produktiveinsatz behoben werden.

---

## Gesamt-Bewertung

- **Systemgesundheit**: PROBLEMATISCH
- **Konfidenz dieser Bewertung**: HOCH (alle 5 Agenten konsistent)
- KRITISCHE Fehler: **5**
- HOHE Fehler: **11**
- MITTLERE Fehler: **14**
- NIEDRIGE Fehler / Hinweise: **12**
- POSITIV-Befunde: **8**

---

## KRITISCHE FEHLER

### F-001: source_end NIE in Datenbank geschrieben — Auto-Edit inhaltlich wertlos

- **Datei**: `main.py:3625-3636`
- **Problem**: Die Dict-Konvertierung der `TimelineSegment`-Objekte nach `auto_edit_phase3()` laesst das Feld `source_end` weg. Alle 4349 `timeline_entries` in der Produktions-DB haben `source_end = NULL`.
- **Beweis**: Forensische DB-Abfrage: `SELECT COUNT(*) FROM timeline_entries WHERE source_end IS NOT NULL` = **0**
- **Gefunden durch**: Database-Agent (statische Analyse + echte DB-Pruefung)
- **Auswirkung**: Der Export-Service schneidet JEDES Segment ab Frame 0 des Quellvideos statt vom berechneten Offset. Das gesamte Auto-Edit erzeugt visuell falsches Material.
- **Empfehlung**: `source_end` in die Dict-Konvertierung aufnehmen und bei DB-Insert setzen.

### F-002: load_siglip() Default ist falsches Modell (768-dim statt 1152-dim)

- **Datei**: `services/model_manager.py:312`
- **Problem**: `load_siglip(model_id="google/siglip-base-patch16-384")` — Default ist `siglip-base` mit 768-dim Embeddings. LanceDB-Schema erwartet 1152-dim (`vector_db_service.py:19: EMBEDDING_DIM = 1152`).
- **Beweis**: Code-Lesung beider Dateien, Modellkarten-Vergleich
- **Gefunden durch**: Audio/Video/GPU-Agent
- **Auswirkung**: Wenn `generate_embeddings()` ohne explizites `model_id` aufgerufen wird, entstehen 768-dim Vektoren die nicht ins 1152-dim Schema passen.
- **Empfehlung**: Default aendern zu `"google/siglip-so400m-patch14-384"`.

### F-003: _motion_adjusted_step() ist Dead Code — PhD-Kernalgorithmus inaktiv

- **Datei**: `services/pacing_service.py:828-870`
- **Problem**: Die Funktion implementiert `combined = E*0.6 + M*0.4`, wird aber **nirgendwo aufgerufen**. PhD-Spec Schritt 3 ist komplett inaktiv.
- **Beweis**: grep zeigt nur Definition, kein Aufruf
- **Gefunden durch**: Pacing-Engine-Agent
- **Auswirkung**: Cut-Rate wird nur von Audio-Energie beeinflusst, nie von Video-Motion.
- **Empfehlung**: In `_compute_effective_step()` integrieren.

### F-004: Stem-gewichtete Energie nicht implementiert — Stereo-Summe statt Stems

- **Datei**: `services/pacing_service.py:427-483` + `services/beat_analysis_service.py:343`
- **Problem**: `energy_per_beat[]` kommt aus der Stereo-Summe, nicht aus den individuellen Stems. PhD-Spec definiert `E_weighted = 0.40*E_drums + 0.30*E_bass + 0.10*E_vocals + 0.20*E_other`. Demucs-Stems existieren in der DB, werden fuer Pacing nie genutzt.
- **Gefunden durch**: Pacing-Engine-Agent
- **Auswirkung**: Drop-Erkennung, Vocal-Aware Pacing und gesamte Stem-Semantik inaktiv.

### F-005: detect_sections() Makro-Strukturerkennung nicht implementiert

- **Datei**: Nicht vorhanden (sollte in `services/pacing_service.py` sein)
- **Problem**: PhD-Spec Abschnitt 2 beschreibt WARMUP/BUILDUP/DROP/BREAKDOWN/TRANSITION/COOLDOWN-Erkennung. Existiert nicht im Code.
- **Gefunden durch**: Pacing-Engine-Agent
- **Auswirkung**: DJ-Set wird als homogener Block behandelt statt in Sektionen.

---

## HOHE FEHLER

### F-006: "pacing" Keyword loest auto_edit aus statt Erklaerung

- **Datei**: `agents/pacing_agent.py:186`
- **Problem**: "erklaere mir pacing" triggert `_handle_auto_edit()` statt `_explain_pacing()`.
- **Empfehlung**: "pacing" aus auto-edit Keywords entfernen.

### F-007: energy_value=0.5 hardcoded in Video-Matching

- **Datei**: `services/pacing_service.py:556-558`
- **Problem**: `energy_value = 0.5` (konstant). `seg_mid` berechnet aber ungenutzt. Motion-Matching ist konstant.
- **Empfehlung**: Echte Audio-Energie per Beat-Index uebergeben.

### F-008: IndexError in _match_video_by_motion bei leerem available_ids

- **Datei**: `services/pacing_service.py:888`
- **Problem**: `best_vid = candidates[0]` crasht bei leerer Liste. Nur extern abgefangen.

### F-009: Vocal-Active Pacing (S_eff x 2) nicht implementiert

- **Datei**: `services/pacing_service.py:427-483`
- **Problem**: Vocal-Stem-Aktivitaet wird nie geprueft.

### F-010: Chat-Dock Thread-Cleanup: falscher Attributname → Segfault

- **Datei**: `ui/chat_dock.py:556`
- **Problem**: `hasattr(self, '_agent_thread')` — korrekt: `_thread`. Thread wird beim Close NICHT gestoppt.
- **Empfehlung**: `_agent_thread` zu `_thread` korrigieren.

### F-011: result_stems Akkumulator ~5.4 GB RAM fuer 60-Min-Mix

- **Datei**: `services/ai_audio_service.py:125`
- **Problem**: 4 Stems * 2 Channels * 158M Samples * 4 Bytes = ~4.8 GB. Kein OOM-Handler.

### F-012: text_to_embedding() nicht Thread-Safe

- **Datei**: `services/video_analysis_service.py:528-563`
- **Problem**: load → inference → unload nicht unter Lock. Race-Condition moeglich.

### F-013: LUFS Pass 1+2 returncode nicht geprueft

- **Datei**: `services/export_service.py:393, 422`
- **Problem**: FFmpeg-Fehler werden nicht erkannt.

### F-014: xfade-Offset ab Segment 3 mathematisch falsch

- **Datei**: `services/export_service.py:329`
- **Problem**: Offset lokal statt kumulativ. Crossfades treten zu frueh auf.

### F-015: add_embeddings_batch() ohne Dimension-Check

- **Datei**: `services/vector_db_service.py:94-107`
- **Problem**: Kein EMBEDDING_DIM Check. Zusammen mit F-002 werden falsche Dimensionen still akzeptiert.

### F-016: Chat-Dock Fallback-Thread: kein deleteLater() → Memory-Leak

- **Datei**: `ui/chat_dock.py:291-303`
- **Problem**: Worker und Thread nie freigegeben.

---

## MITTLERE FEHLER

| ID | Datei:Zeile | Problem |
|---|---|---|
| F-017 | `pacing_agent.py:348` | Drop-Schwellenwerte inkonsistent (Prompt: <0.2/>0.7, Code: <0.3/>0.6) |
| F-018 | `pacing_service.py:745` | clip_offsets nutzt ungecappte Summe statt source_end |
| F-019 | `pacing_service.py:749` | used_recently waechst unbegrenzt (14.5MB fuer 4h Set) |
| F-020 | `pacing_service.py:486` | breakdown="none" + niedrige Energie → 1 Segment |
| F-021 | `main.py:1806` | thread.wait(1000) blockiert GUI-Thread |
| F-022 | `main.py:4779` | LocalAgentService() im Main-Thread initialisiert |
| F-023 | `main.py:1005` | Mapper kw["track_id"] ohne KeyError-Schutz |
| F-024 | `main.py:1145,3620,3873` | DB-Writes direkt in UI-Code |
| F-025 | `ai_audio_service.py:21` | STEMS_DIR relativer Pfad — CWD-abhaengig |
| F-026 | `ai_audio_service.py:427` | FrequencyAnalyzer nutzt librosa BPM statt beat_this |
| F-027 | `video_analysis_service.py:82` | min_scene_len hardcoded 30 FPS |
| F-028 | `pacing_service.py:99,171,322,596` | BPM-Fallback-Logik 4x dupliziert |
| F-029 | `pacing_service.py:818` | N+1 Queries in generate_keyframe_strings_for_project |
| F-030 | `local_agent_service.py:47-55` | System-Prompt propagiert nicht implementierte Features |

---

## NIEDRIGE FEHLER / HINWEISE

| ID | Datei:Zeile | Problem |
|---|---|---|
| F-031 | `database.py:256,298` | SQL f-Strings mit hardcodierten Tabellennamen |
| F-032 | `beat_analysis_service.py:233` | Beat-Stitching Overlap-Dedup mit 0.05s Threshold |
| F-033 | `beat_analysis_service.py:222` | torch Import abhaengig von anderem Codepfad |
| F-034 | `beat_analysis_service.py:60` | ModelManager.unload() Fehler silently ignoriert |
| F-035 | `ai_audio_service.py:103` | Doppeltes Overlap-Processing |
| F-036 | `pacing_agent.py:287` | Import privater Funktion _get_audio_duration |
| F-037 | `pacing_agent.py:290` | CutPoint-Serialisierung laesst "source"-Feld weg |
| F-038 | `pacing_agent.py:437` | Vibe-Regex schlueckt Restsatz |
| F-039 | `stem_workspace.py:316/517` | seek_requested hat unterschiedliche Einheiten |
| F-040 | `main.py:397` | Tasks akkumulieren ohne automatisches Cleanup |
| F-041 | `pacing_service.py:248` | Detached ORM-Objekte aus geschlossener Session |
| F-042 | `main.py:3555+` | project_id=1 an 8 Stellen hart kodiert |

---

## POSITIV-BEFUNDE

| # | Bereich | Befund |
|---|---|---|
| 1 | **Syntax** | 0 Syntaxfehler in 27 Dateien. Alle Dateien parsbar. |
| 2 | **Security** | 0 hardcodierte Secrets. Alle API-Keys in .env (gitignored). Kein shell=True. |
| 3 | **Session-Handling** | Alle SQLAlchemy-Sessions in `with`-Blocks. Session-Split-Pattern korrekt. |
| 4 | **Foreign Keys** | ON DELETE CASCADE korrekt in allen Child-Tabellen. |
| 5 | **Thread-Safety** | check_same_thread=False korrekt. Worker→Signal→UI Pattern korrekt. |
| 6 | **N+1 Fixes** | _get_beat_data_combined (Bug-14) und export_service Bulk-Load korrekt. |
| 7 | **Stem-Signals** | StemWorkspace ↔ StemPlayer: Alle 8 Verbindungen korrekt. |
| 8 | **GPU-Zwang** | ModelManager CUDA konsequent. unload() mit gc.collect() + cuda.empty_cache(). |

---

## Spec vs. Implementation Gap

| PhD-Spec Feature | Status |
|---|---|
| Audio = Master, Timeline = Audio-Dauer | IMPLEMENTIERT |
| Jeder Schnitt auf Beat-Timestamp | IMPLEMENTIERT |
| Base Cut Rate 1/2/4/8/16 | IMPLEMENTIERT |
| Energy Reactivity (Stereo-RMS) | IMPLEMENTIERT (auf Stereo-Summe) |
| Breakdown Behavior (halve/force16/none) | IMPLEMENTIERT |
| Anker-System (erzwungene Clips) | IMPLEMENTIERT |
| LanceDB Vibe Semantic Search | IMPLEMENTIERT (SigLIP-Default falsch) |
| Round-Robin (letzte 3 vermeiden) | IMPLEMENTIERT |
| **Stem-gewichtete Energie (E_weighted)** | **NICHT IMPLEMENTIERT** |
| **Makro-Sektionserkennung (detect_sections)** | **NICHT IMPLEMENTIERT** |
| **Motion-Adjusted Step (combined intensity)** | **DEAD CODE** |
| **Vocal-Active Pacing (S_eff x 2)** | **NICHT IMPLEMENTIERT** |
| **Drop-Detection via Bass-Stem** | **NICHT IMPLEMENTIERT** |
| **Crossfade per Section Type** | **NICHT IMPLEMENTIERT** |
| **Transition-Erkennung** | **NICHT IMPLEMENTIERT** |

**7 von 15 PhD-Features implementiert. 8 Features nur Spezifikation.**

---

## GPU/VRAM Budget (GTX 1060, 6GB)

| Modell | VRAM | ModelManager-geschuetzt? |
|---|---|---|
| beat_this | ~0.9 GB | NEIN (eigener Loader) |
| Demucs | ~3.0 GB | NEIN (eigener Loader) |
| RAFT | ~0.15 GB | NEIN (eigener Loader) |
| SigLIP-so400m | ~2.0 GB | JA |
| Qwen 2.5 0.5B | ~1.5 GB | JA |

**Worst Case**: beat_this + Demucs + SigLIP = **5.9 GB** (parallele QThread-Starts moeglich)

---

## Empfohlene Fix-Reihenfolge

| Prio | Finding | Aufwand | Impact |
|---|---|---|---|
| 1 | F-001: source_end in DB-Insert | 1 Zeile | Auto-Edit funktioniert |
| 2 | F-002: SigLIP Default korrigieren | 1 Zeile | Embeddings korrekt |
| 3 | F-010: _agent_thread → _thread | 1 Zeile | Segfault verhindert |
| 4 | F-006: "pacing" aus auto-edit Keywords | 1 Zeile | Agent-Routing korrekt |
| 5 | F-014: xfade kumulativ berechnen | 5 Zeilen | Crossfades korrekt |
| 6 | F-007: energy_value dynamisch | 3 Zeilen | Motion-Match adaptiv |
| 7 | F-003: _motion_adjusted_step einbinden | 10 Zeilen | PhD-Schritt 3 aktiv |
| 8 | F-004/F-005/F-009: PhD-Kern | Feature | Volle Spec-Konformitaet |

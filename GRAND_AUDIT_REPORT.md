# Grand Audit Abschlussbericht

**Datum**: 2026-03-19
**Projekt**: PB_studio_Rebuild (C:\Users\david\Documents\App_Projekte\PB_studio_Rebuild)
**Version**: v0.3.0
**Audit-Zyklen durchgefuehrt**: 3 von 3 (Zyklus 3 = Konsolidierung + Verifikation)
**Unteragenten eingesetzt**: 5 (DB-Admin, GUI-Specialist, Audio/Video/Security, Integration/Deps, Verifikation)
**Geprueft von**: Grand Auditor

---

## Executive Summary

PB_studio v0.3.0 ist ein funktional beeindruckendes Projekt mit 4 neuen Feature-Phasen
(Stem Separation, Auto-Edit, Effects, Task Manager). Die Kernarchitektur ist solide:
Services sind korrekt vom GUI getrennt, Workers greifen nie auf Widgets zu, die DB-Schema-
Erweiterung ist sauber. **Aber**: Es gibt 2 harte UX-Blocker (subprocess im Main-Thread
friert die GUI ein), einen stillen Datenverlust-Bug (Effekte werden bei >10 Segments
ignoriert), und systematisch fehlendes Error-Handling in subprocess-Aufrufen. Die Test-
Abdeckung der neuen Features ist oberflachlich - die kritischsten Code-Pfade (Drum-Cuts,
Export-Pipeline) sind ungetestet.

## Gesamt-Bewertung

- **Systemgesundheit**: AKZEPTABEL (funktional, aber mit spuerbaren Defekten)
- **Konfidenz dieser Bewertung**: HOCH (alle 3 Zyklen konsistent bei Kernfindings)
- KRITISCHE Fehler: **4** (davon in allen Zyklen bestaetigt: 3)
- HOHE Fehler: **8**
- MITTLERE Fehler: **15**
- NIEDRIGE Fehler / Hinweise: **12**
- POSITIV-Befunde: **8**

---

## Zyklus-Vergleich (Konsistenz-Uebersicht)

| Finding-ID | Zyklus 1 | Zyklus 2 | Zyklus 3 (Verif.) | Konfidenz |
|------------|----------|----------|-------------------|-----------|
| CRIT-01 (subprocess Main-Thread) | KRITISCH | KRITISCH | BESTAETIGT | HOCH |
| CRIT-02 (Effekte >10 Segs ignoriert) | - | KRITISCH | BESTAETIGT | HOCH |
| CRIT-03 (Xfade-Offset falsch) | - | KRITISCH | BESTAETIGT | HOCH |
| CRIT-04 (Fehlende Kern-Tests) | - | KRITISCH | BESTAETIGT | HOCH |
| HIGH-01 (kein closeEvent) | HOCH | HOCH | BESTAETIGT | HOCH |
| HIGH-02 (deleteLater fehlt) | HOCH | - | BESTAETIGT | HOCH |
| HIGH-03 (N+1 Queries) | HOCH | - | BESTAETIGT | HOCH |
| HIGH-04 (Cascades fehlen) | HOCH | - | BESTAETIGT | HOCH |
| HIGH-05 (subprocess Timeout unhndld) | HOCH | - | BESTAETIGT | HOCH |
| HIGH-06 (FFmpeg returncode ignoriert) | HOCH | - | BESTAETIGT | HOCH |
| HIGH-07 (librosa.load kein try/except) | HOCH | - | BESTAETIGT | HOCH |
| HIGH-08 (Timeline-Clip-Breite falsch) | - | MITTEL | BESTAETIGT | HOCH |
| MED-01 (check_same_thread) | KRITISCH | - | ABGESCHWAECHT | MITTEL |
| MED-xx (DetachedInstanceError) | KRITISCH | - | WIDERLEGT | - |
| MED-yy (Newline-Injection) | KRITISCH | - | WIDERLEGT | - |

---

## KRITISCHE FEHLER

### CRIT-01: subprocess.run() blockiert Main-Thread bei Video-Preview

- **Datei**: `main.py:505-525` (VideoPreviewWidget._extract_and_show_frame)
- **Datei**: `main.py:1189` (_show_effect_preview)
- **Problem**: `subprocess.run()` mit FFmpeg wird direkt im GUI-Thread aufgerufen. Bei Play-Modus (100ms Timer) friert die gesamte App fuer 50-500ms pro Frame ein.
- **Aufgetreten in**: Zyklus 1 + Zyklus 2 + Verifikation
- **Auswirkung**: App ist waehrend Video-Preview unbenutzbar. Jeder Klick auf Play friert das UI ein.
- **Empfehlung**: `FrameExtractWorker(QObject)` in QThread mit `frame_ready = Signal(bytes)`.

### CRIT-02: Effekte werden bei >10 Video-Segments stillschweigend ignoriert

- **Datei**: `export_service.py:73-82`
- **Problem**: `if has_effects and len(video_segments) <= 10` entscheidet zwischen Filtergraph und Concat. Bei Auto-Edit (typisch 20-70 Segments) wird IMMER Concat verwendet - Brightness, Contrast und Crossfade werden ignoriert, ohne Warnung.
- **Aufgetreten in**: Zyklus 2
- **Auswirkung**: User setzt Farbkorrektur, exportiert, sieht keine Effekte. Stiller Datenverlust.
- **Empfehlung**: Brightness/Contrast in den `-vf` Filter des Concat-Pfads integrieren. Crossfade-Warnung wenn >10 Segments.

### CRIT-03: Crossfade-Offset berechnet aus Quell-Clip-Dauer statt Segment-Dauer

- **Datei**: `export_service.py:179`
- **Problem**: `offset = max(0.1, video_segments[0]["duration"] - xfade_dur)` nutzt `duration` (= Quell-Clip-Gesamtlaenge, z.B. 10s) statt `end - start` (= Segment-Laenge, z.B. 0.4s bei Auto-Edit). Bei Auto-Edit-Workflows faellt der Crossfade weit ausserhalb des sichtbaren Bereichs.
- **Aufgetreten in**: Zyklus 2
- **Empfehlung**: `seg["end"] - seg["start"]` statt `seg["duration"]` verwenden.

### CRIT-04: Kernalgorithmen ohne Testabdeckung

- **Datei**: `tests/` (fehlend)
- **Problem**: `calculate_drum_cuts()` (Herzstuck von Auto-Edit) und `export_timeline()` (finale Ausgabe) haben NULL Tests.
- **Aufgetreten in**: Zyklus 2
- **Empfehlung**: Mindestens je 3 Tests pro Funktion (Happy Path, Edge Case, Error Case).

---

## HOHE FEHLER

### HIGH-01: Kein closeEvent() - Thread-Cleanup fehlt

- **Datei**: `main.py` (PBWindow-Klasse)
- **Problem**: Kein `closeEvent()`. Laufende Threads (Demucs = Minuten!) werden bei App-Schliessung nicht beendet. Zombie-Prozesse und potenzielle DB-Korruption.
- **Empfehlung**: `closeEvent()` mit `thread.quit()` + `thread.wait(3000)` fuer alle `_active_threads`.

### HIGH-02: deleteLater() fehlt in _cleanup_worker()

- **Datei**: `main.py:1738-1742`
- **Problem**: QThread + QObject werden aus Listen entfernt, aber nicht per `deleteLater()` freigegeben. Schleichender Memory-Leak bei vielen Analysen.
- **Empfehlung**: `worker.deleteLater()` + `thread.deleteLater()` ergaenzen.

### HIGH-03: N+1 Query Pattern

- **Datei**: `main.py:343-378` (load_from_db), `export_service.py:39-56`
- **Problem**: Pro Timeline-Eintrag ein separater DB-Query fuer das Media-Objekt. Bei 100 Clips = 101 Queries.
- **Empfehlung**: Alle IDs sammeln, dann mit `IN`-Query laden.

### HIGH-04: Fehlende cascade="all, delete-orphan"

- **Datei**: `database.py:22-23, 49, 69`
- **Problem**: Project -> AudioTrack/VideoClip, VideoClip -> Scene, AudioTrack -> Beatgrid haben keine Cascades. Loeschen hinterlaesst Zombie-Zeilen.
- **Empfehlung**: `cascade="all, delete-orphan"` auf allen Eltern-Relationships.

### HIGH-05: subprocess.TimeoutExpired nicht abgefangen

- **Dateien**: `ai_audio_service.py:50`, `video_service.py:23,66`
- **Problem**: `subprocess.run(timeout=N)` wirft `TimeoutExpired` das nicht separat gefangen wird. Ungefilterte Exception propagiert.
- **Empfehlung**: Explizites `except subprocess.TimeoutExpired`.

### HIGH-06: FFmpeg-Returncode bei WAV-Konvertierung ignoriert

- **Datei**: `ai_audio_service.py:130-133`
- **Problem**: `subprocess.run()` Ergebnis wird nicht gespeichert/geprueft. Fehlgeschlagene Konvertierung fuehrt zu kaputtem Input fuer Ducking.
- **Empfehlung**: `result = subprocess.run(...)` + `if result.returncode != 0: raise`.

### HIGH-07: librosa.load() ohne Exception-Behandlung

- **Datei**: `audio_service.py:24`
- **Problem**: Korrupte/leere Audio-Dateien loesen ungefangene Exceptions aus.
- **Empfehlung**: `try/except` mit sprechender Fehlermeldung.

### HIGH-08: Timeline-Clip-Breite basiert auf Quell-Clip-Dauer

- **Datei**: `main.py:363`
- **Problem**: Auto-Edit-Segments (0.4s) werden als 10s-Breite dargestellt weil `clip.duration` (10s) statt `entry.end_time - entry.start_time` (0.4s) genutzt wird.
- **Empfehlung**: `dur = (entry.end_time - entry.start_time)` wenn end_time gesetzt.

---

## MITTLERE FEHLER

| ID | Datei:Zeile | Problem |
|----|-------------|---------|
| MED-01 | database.py:5 | check_same_thread=False fehlt (Risiko bei bestimmten Pool-Configs) |
| MED-02 | database.py:5 | DB-Pfad relativ zum CWD, nicht zur Datei |
| MED-03 | database.py:141 | TimelineEntry.media_id ohne echten Foreign Key |
| MED-04 | database.py:94 | Beatgrid.audio_track_id ohne UNIQUE trotz 1:1 |
| MED-05 | database.py:79 | FK ohne ondelete=CASCADE + kein PRAGMA foreign_keys=ON |
| MED-06 | main.py:1311 | DELETE + INSERT als zwei Commits (Datenverlust bei Crash) |
| MED-07 | ingest_service.py:26 | Race Condition + fehlendes UNIQUE auf file_path |
| MED-08 | ai_audio_service.py:90 | None-Check fehlt nach langem Demucs-Prozess |
| MED-09 | database.py | Keine Indices auf 8 haeufig abgefragte Spalten |
| MED-10 | main.py:418 | Ruler-Items akkumulieren in QGraphicsScene (Memory-Leak) |
| MED-11 | export_service.py:100 | Pfad-Escaping falsch fuer Apostrophe in Dateinamen |
| MED-12 | pacing_service.py:56 | Cut-Density filtert nicht bei niedrigem energy (Minimum 0.3) |
| MED-13 | All services | STEMS_DIR, PROXY_DIR, EXPORT_DIR relativ zum CWD |
| MED-14 | database.py + services | Scene-Tabelle existiert, wird aber nie befuellt |
| MED-15 | ai_audio_service.py:124 | Vorhersehbare Tempfile-Namen bei Ducking |

---

## NIEDRIGE FEHLER / HINWEISE

| ID | Datei:Zeile | Problem |
|----|-------------|---------|
| LOW-01 | database.py:110 | PacingBlueprint ohne Relationship zu Project |
| LOW-02 | database.py:120 | AudioVideoAnchor komplett ohne Relationships |
| LOW-03 | ai_audio_service.py:30 | Toter Code (cmd two-stems Variante) |
| LOW-04 | ai_audio_service.py:192 | Attack/Release implementiert keinen echten Compressor |
| LOW-05 | pacing_service.py:148 | BPM-Fallback startet bei t=0.0, normaler Pfad nicht |
| LOW-06 | main.py:1237 | Zwei separate Sessions fuer logisch eine Operation |
| LOW-07 | main.py:601 | TaskManager-Timer laeuft permanent |
| LOW-08 | main.py:1673 | _refresh_production_info() beim Start nicht aufgerufen |
| LOW-09 | main.py:915 | effects_clip_combo beim Start nicht befuellt |
| LOW-10 | pyproject.toml | opencv-python deklariert aber nie importiert |
| LOW-11 | pyproject.toml | duckdb deklariert aber nie importiert |
| LOW-12 | main.py:1084 | Gemischtes Connect-Pattern (manuell vs on_finish) |

---

## POSITIV-BEFUNDE (Was zuverlaessig funktioniert)

1. **Worker greifen nie auf Widgets zu** - Alle 6 Worker-Klassen emittieren nur Signals. Thread-Safety-Prinzip korrekt umgesetzt.
2. **Kein shell=True** - Kein einziger subprocess-Aufruf verwendet shell=True. Wichtigste Security-Anforderung erfuellt.
3. **Keine Hardcoded Secrets** - Kein API-Key, Passwort oder Token in keiner Datei.
4. **Service-Layer sauber getrennt** - Business-Logik in Services, GUI in main.py. Keine Geschaeftslogik in Qt-Klassen.
5. **33/33 Tests bestehen** - Bestehende Tests sind stabil und laufen in 61s durch.
6. **TaskManager-Architektur** - GlobalTaskManager mit Qt-Signals ist eine saubere, wiederverwendbare Loesung.
7. **QGraphicsView-Timeline** - Clip-Verschiebung mit DB-Sync funktioniert korrekt.
8. **Demucs-Integration** - trotz Windows-DLL-Problemen funktioniert die Stem-Separation ueber --mp3 Workaround zuverlaessig.

---

## Datenbank-Befund (vollstaendig)

### Schema-Status

| Tabelle | Constraints | Foreign Keys | Cascade | Index | Status |
|---------|------------|--------------|---------|-------|--------|
| projects | PK | - | - | PK auto | OK |
| audio_tracks | PK | project_id FK | FEHLT | FEHLT | Verbesserungsbedarf |
| video_clips | PK | project_id FK | FEHLT | FEHLT | Verbesserungsbedarf |
| scenes | PK | video_clip_id FK | FEHLT | FEHLT | Verbesserungsbedarf |
| beatgrids | PK | audio_track_id FK (kein UNIQUE) | FEHLT | FEHLT | Bug |
| pacing_blueprints | PK | project_id FK (keine Relationship) | FEHLT | - | Unvollstaendig |
| audio_video_anchors | PK | 2 FKs (keine Relationships) | FEHLT | - | Unvollstaendig |
| timeline_entries | PK | KEIN FK (media_id polymorph) | - | FEHLT | Design-Problem |

### Session-Handling

| Datei | Session-Aufrufe | In with-Block | Korrekt |
|-------|----------------|---------------|---------|
| audio_service.py | 1 | Ja | OK |
| video_service.py | 1 | Ja | OK |
| export_service.py | 1 | Ja | OK |
| ingest_service.py | 4 | Alle Ja | OK (Race Condition moeglich) |
| pacing_service.py | 3 | Alle Ja | OK |
| ai_audio_service.py | 3 | Alle Ja | None-Check fehlt in Session 2 |
| main.py | ~10 | Alle Ja | Zwei-Commit-Problem in 1 Stelle |

---

## Selbst-Pruefungs-Protokoll

### Zyklus 1

1. **Dateiabdeckung**: 10/10 relevante Python-Dateien vollstaendig gelesen.
2. **Agenten-Vollstaendigkeit**: 3/3 Agenten berichtet. Keine fehlenden Berichte.
3. **Finding-Qualitaet**: Alle Findings mit Datei:Zeile. 2 Findings spaeter widerlegt (DetachedInstanceError, Newline-Injection).
4. **Selbst-Ehrlichkeit**: Zyklus 1 hatte 2 false-positive KRITISCHE Findings. Korrigiert in Zyklus 2.

### Zyklus 2

1. **Dateiabdeckung**: Fokus auf Zyklus-1-Luecken (Tests, Pacing, Dependencies). Alle geprueft.
2. **Agenten-Vollstaendigkeit**: 2/2 Agenten berichtet. Verifikationsagent hat 3/5 Findings bestaetigt, 2 widerlegt.
3. **Neue Findings**: 18 neue Findings, davon 4 KRITISCH (I-03, I-05, T-03, T-04).
4. **Selbst-Ehrlichkeit**: Keine Beschoenigung. Alle widerlegten Findings dokumentiert.

### Zyklus 3 (Konsolidierung)

1. **Konsolidierung**: 60+ Findings aus Zyklen 1+2 auf 39 unique Findings konsolidiert.
2. **Duplikate bereinigt**: DB-14 = E-01 (zusammengefuehrt), F-005 impliziert in closeEvent.
3. **Schwere kalibriert**: 2 Findings von KRITISCH auf MITTEL herabgestuft nach Verifikation.

---

## Qualitaets-Gate (Freigabe-Checkliste)

- [x] Alle 3 Zyklen vollstaendig abgeschlossen
- [x] Jede .py Datei im Scope mindestens 1x vollstaendig gelesen
- [x] Alle Unteragenten haben berichtet
- [x] Alle Findings haben Datei:Zeile Referenz
- [x] Alle LOCKED-Files unveraendert (keine LOCKED-Files definiert)
- [ ] Laufzeit-Tests (E2E + Stress) - NICHT durchgefuehrt (kein Display/GUI verfuegbar)
- [x] Widersprueche zwischen Zyklen erklaert (2 widerlegte Findings dokumentiert)
- [x] Selbst-Pruefungs-Protokoll vollstaendig ausgefuellt
- [x] 0% Beschoenigung (2 false-positives transparent dokumentiert)
- [x] POSITIV-Befunde fair und ehrlich dokumentiert

**Laufzeit-Tests konnten nicht durchgefuehrt werden (CLI-Umgebung ohne Display). E2E- und Stress-Tests stehen aus.**

---

## Priorisierte Handlungsempfehlungen (Top 10)

| Prio | Finding | Aufwand | Impact |
|------|---------|---------|--------|
| 1 | CRIT-01: subprocess im Main-Thread -> Worker | 1h | UX-Blocker behoben |
| 2 | CRIT-02: Effekte bei >10 Segs in Concat-VF integrieren | 30min | Stiller Datenverlust behoben |
| 3 | CRIT-03: Xfade-Offset mit Segment-Dauer berechnen | 15min | Crossfade funktioniert |
| 4 | HIGH-01: closeEvent() implementieren | 30min | Zombie-Prozesse verhindert |
| 5 | HIGH-02: deleteLater() in _cleanup_worker | 5min | Memory-Leak gestoppt |
| 6 | HIGH-08: Timeline-Breite aus entry.end-start | 15min | Korrekte Auto-Edit-Darstellung |
| 7 | MED-01: check_same_thread=False | 1min | SQLite Thread-Safety |
| 8 | CRIT-04: Tests fuer drum_cuts + export | 2h | Regressions-Schutz |
| 9 | HIGH-03: N+1 Queries durch Batch-Load ersetzen | 30min | Performance bei vielen Clips |
| 10 | MED-06: DELETE+INSERT in einem Commit | 5min | Atomare Timeline-Updates |

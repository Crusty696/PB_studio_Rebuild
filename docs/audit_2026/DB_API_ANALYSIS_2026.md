# DB & API Analyse — PB_studio_Rebuild (2026-03-23)

Analysiert von Claude (pb-master Skill). Vollständige Analyse aller Schichten:
`database.py` · `services/*.py` · `main.py` (4749 Zeilen).

---

## 1. Schema-Analyse

### Modell-Übersicht

| Tabelle | FK-Targets | CASCADE? | back_populates OK? |
|---|---|---|---|
| `projects` | — | — | ✅ |
| `audio_tracks` | projects.id | ✅ | ✅ |
| `video_clips` | projects.id | ✅ | ✅ |
| `scenes` | video_clips.id | ✅ | ✅ |
| `beatgrids` | audio_tracks.id | ✅ | ✅ |
| `waveform_data` | audio_tracks.id | ✅ | ✅ |
| `pacing_blueprints` | projects.id | ✅ | ❌ kein back_populates auf Project |
| `audio_video_anchors` | audio_tracks.id, video_clips.id | ✅ | ❌ kein back_populates auf beiden Seiten |
| `clip_anchors` | timeline_entries.id | ✅ | ❌ TimelineEntry hat kein `anchors` relationship |
| `timeline_entries` | projects.id | ✅ | ❌ Project hat kein `timeline_entries` relationship |

### Fehlende ORM-Relationships

```python
# PacingBlueprint fehlt project = relationship(Project, back_populates="pacing_blueprints")
# Project fehlt pacing_blueprints = relationship(...)

# AudioVideoAnchor fehlt audio_track = relationship(...) und video_clip = relationship(...)

# TimelineEntry fehlt anchors = relationship(ClipAnchor, ...)
# Project fehlt timeline_entries = relationship(TimelineEntry, ...)
```

### Fehlende ALTER TABLE Migrationen

`TimelineEntry` besitzt im ORM-Modell drei Spalten, die **nicht** via `ALTER TABLE` migriert werden:
- `crossfade_duration` FLOAT
- `brightness` FLOAT
- `contrast` FLOAT

Konsequenz: Auf bestehenden Datenbanken führt `_apply_effects()` und `_on_effects_clip_changed()` zu:
```
sqlalchemy.exc.OperationalError: no such column: timeline_entries.crossfade_duration
```

### Migration-Prüfung unvollständig

`_needs_fk_cascade_migration()` prüft **nur** die `scenes`-Tabelle. Die Tabellen
`beatgrids`, `waveform_data`, `pacing_blueprints`, `audio_video_anchors`,
`clip_anchors` und `timeline_entries` werden **nicht geprüft**. Wenn nur eine
dieser Tabellen fehlendes CASCADE hat, wird keine Migration ausgelöst.

---

## 2. Service-Funktion-Matrix

| Service | Funktion | Session-Hygiene | Session-Split | None-Check | N+1? | Bewertung |
|---|---|---|---|---|---|---|
| `ingest_service` | `ingest_audio()` | `with Session` ✅ | n/a | ✅ | — | OK |
| `ingest_service` | `ingest_video()` | `with Session` ✅ | ❌ ffprobe inside session | ✅ | — | NIEDRIG |
| `audio_service` | `analyze_and_store()` | 2-Session-Split ✅ | ✅ | ✅ | — | OK |
| `ai_audio_service` | `StemSeparator.separate_and_store()` | 2-Session-Split ✅ | ✅ | ✅ | — | OK |
| `ai_audio_service` | `FrequencyAnalyzer.analyze_and_store()` | 2-Session-Split ✅ | ✅ | ✅ | — | OK |
| `beat_analysis_service` | `analyze_and_store()` | 2-Session-Split ✅ | ✅ | ✅ | — | OK |
| `video_service` | `VideoAnalyzer.analyze_and_store()` | 3-Session-Split ✅ | ✅ | ✅ | — | OK |
| `pacing_service` | `_get_beat_positions()` | `with Session` ✅ | n/a | ✅ | — | OK |
| `pacing_service` | `_get_downbeat_positions()` | `with Session` ✅ | n/a | ✅ | — | OK |
| `pacing_service` | `_get_energy_per_beat()` | `with Session` ✅ | n/a | ✅ | — | OK |
| `pacing_service` | `auto_edit_phase3()` | ✅ | n/a | ✅ | ❌ 3 Sessions für gleiche audio_id | MITTEL |
| `export_service` | `export_timeline()` | `with Session` ✅ | n/a | ✅ | ❌ session.get() pro Loop | HOCH |
| `vector_db_service` | `delete_by_video()` | n/a (LanceDB) | n/a | — | — | Hinweis: f-string SQL-Filter |
| `timeline_service` | alle | kein DB ✅ | n/a | ✅ | — | OK |
| `convert_service` | alle | kein DB ✅ | n/a | — | — | OK |
| `model_manager` | alle | kein DB ✅ | n/a | ✅ | — | OK |
| `main.py` | `InteractiveTimeline.load_from_db()` | `with Session` ✅ | n/a | ✅ | ❌ get() pro Eintrag | HOCH |
| `main.py` | `InteractiveTimeline.sync_anchors()` | ✅ | n/a | ✅ | ❌ Session pro Video-Clip | MITTEL |
| `main.py` | `_refresh_effects_combos()` | `with Session` ✅ | n/a | ✅ | ❌ get() pro Eintrag | NIEDRIG |
| `main.py` | `_on_auto_edit_finished()` | `with Session` ✅ | n/a | — | — | ❌ Split-Commit Datenverlust |

---

## 3. Bug-Liste (nummeriert, nach Schwere)

### [BUG-13] KRITISCH — Fehlende ALTER TABLE Migrationen: crossfade_duration, brightness, contrast
**Datei:** `database.py` · `init_db()`  
**Problem:** Die ORM-Spalten `crossfade_duration`, `brightness` und `contrast` in `TimelineEntry` werden nie via `ALTER TABLE` zu bestehenden Datenbanken hinzugefügt. Neue DBs werden korrekt angelegt (`create_all`), aber jede existierende `pb_studio.db` läuft in `OperationalError: no such column` bei `_apply_effects()` und `_on_effects_clip_changed()`.  
**Fix:** ALTER TABLE Migrationblock analog zu `source_start`/`source_end` hinzufügen.

---

### [BUG-21] KRITISCH — Split-Commit in `_on_auto_edit_finished()` → Datenverlust
**Datei:** `main.py` · `_on_auto_edit_finished()`  
**Problem:** Zwei getrennte `session.commit()` innerhalb desselben `with DBSession`-Blocks:
1. `DELETE FROM timeline_entries ... COMMIT` — persistiert sofort
2. Loop über `segments` → `session.add(entry)` ... `COMMIT`

Wenn der zweite Block (Insert-Loop) fehlschlägt (z.B. `IntegrityError`), rollback nur die Inserts. Die DELETE ist bereits committed → alle Video-Timeline-Einträge sind weg, keine Ersatz-Einträge wurden geschrieben.  
**Fix:** DELETE + alle Inserts in **eine** Transaktion (einen einzigen `commit()`).

---

### [BUG-12] HOCH — N+1 Query in `export_service.export_timeline()`
**Datei:** `services/export_service.py`  
**Problem:** 
```python
for ve in video_entries:
    clip = session.get(VideoClip, ve.media_id)  # 1 SELECT pro Clip!
```
Bei einem Export mit 100 Segmenten (typisches Auto-Edit Ergebnis) = 100 einzelne SELECT-Queries.  
**Fix:** Bulk-Load aller benötigten VideoClips mit `IN`-Query vor der Schleife:
```python
video_ids = [ve.media_id for ve in video_entries]
clips_by_id = {c.id: c for c in session.query(VideoClip).filter(VideoClip.id.in_(video_ids)).all()}
```

---

### [BUG-17] HOCH — N+1 Query in `InteractiveTimeline.load_from_db()`
**Datei:** `main.py` · `InteractiveTimeline.load_from_db()`  
**Problem:** Pro Timeline-Eintrag ein separater `session.get()`:
```python
for entry in entries:
    if entry.track == "audio":
        track = session.get(AudioTrack, entry.media_id)   # N mal
    elif entry.track == "video":
        clip = session.get(VideoClip, entry.media_id)      # M mal
```
Bei 200 Segmenten nach Auto-Edit = 200+ SELECT-Queries beim UI-Refresh.  
**Fix:** Bulk-Load vor dem Loop per `IN`-Query.

---

### [BUG-16] HOCH — `_needs_fk_cascade_migration()` prüft nur `scenes`-Tabelle
**Datei:** `database.py`  
**Problem:** Die Funktion prüft nur die `scenes`-Tabelle auf CASCADE. Wenn eine andere Child-Tabelle (`beatgrids`, `waveform_data`, `timeline_entries`, etc.) fehlendes CASCADE hat, wird die Migration **nie** ausgelöst. Ältere Datenbanken (vor der FK-Migration) können danach immer noch verwaiste Datensätze haben.  
**Fix:** Alle Child-Tabellen prüfen (OR-Verknüpfung).

---

### [BUG-20] MITTEL — Fehlende `back_populates` auf `PacingBlueprint` und `AudioVideoAnchor`
**Datei:** `database.py`  
**Problem:** 
- `PacingBlueprint` hat kein `project = relationship(Project, back_populates="pacing_blueprints")` und `Project` kein `pacing_blueprints` relationship
- `AudioVideoAnchor` hat keine ORM-Relationships zu `AudioTrack` oder `VideoClip`
- `ClipAnchor` hat keine relationship zu `TimelineEntry` (Rückrichtung fehlt)

Folge: SQLAlchemy SAWarning bei Backref-Traversal; `project.pacing_blueprints` würde AttributeError werfen. CASCADE-Deletes funktionieren trotzdem auf DB-Ebene (FK-Level), aber ORM-seitige Cascade-Propagation schlägt fehl.  
**Fix:** `back_populates` auf beiden Seiten ergänzen.

---

### [BUG-14] MITTEL — 3 separate DB-Sessions für gleiche `audio_id` in `auto_edit_phase3()`
**Datei:** `services/pacing_service.py`  
**Problem:** `auto_edit_phase3()` ruft sequenziell auf:
```python
beat_positions = _get_beat_positions(audio_id)         # Session 1
downbeat_positions = _get_downbeat_positions(audio_id) # Session 2
energy_per_beat = _get_energy_per_beat(audio_id)       # Session 3
```
Alle drei lesen von `Beatgrid WHERE audio_track_id = audio_id`. Das sind 3 DB-Round-Trips für Daten, die in einer einzigen Query geladen werden könnten.  
**Fix:** Kombinierte Hilfsfunktion `_get_beat_data(audio_id)` die alles in einer Session lädt.

---

### [BUG-18] MITTEL — DB-Session pro Video-Clip in `InteractiveTimeline.sync_anchors()`
**Datei:** `main.py` · `InteractiveTimeline.sync_anchors()`  
**Problem:**
```python
for video_clip in video_clips:
    ...
    with DBSession(engine) as session:   # Session pro Clip!
        entry = session.get(TimelineEntry, video_clip.entry_id)
        ...
        session.commit()
```
Bei N Video-Clips = N Sessions geöffnet/geschlossen.  
**Fix:** Eine Session außerhalb der Schleife öffnen, alle Updates sammeln, einmal committen.

---

### [BUG-15] NIEDRIG — `ffprobe`-Subprocess innerhalb aktiver Session in `ingest_video()`
**Datei:** `services/ingest_service.py`  
**Problem:** `_probe_video_meta(resolved)` (ffprobe-Subprocess) wird innerhalb des `with Session(engine)` Blocks aufgerufen. Obwohl ffprobe typischerweise schnell ist (~50ms), verstößt dies gegen das Session-Split-Pattern und kann bei langsamen Laufwerken/Netzwerk-Pfaden die Session unnötig lange offen halten.  
**Fix:** ffprobe vor dem Öffnen der Session aufrufen.

---

### [BUG-19] NIEDRIG — N+1 `session.get()` in `_refresh_effects_combos()`
**Datei:** `main.py` · `PBWindow._refresh_effects_combos()`  
**Problem:**
```python
for entry in entries:
    clip = session.get(VideoClip, entry.media_id)   # N SELECTs
```
Dieser Code ist als `hidden` Widget angelegt (nicht sichtbar), daher niedriger Impact. Trotzdem N+1.  
**Fix:** Bulk-Load mit `IN`-Query.

---

## 4. Performance-Befunde

| # | Datei | Problem | Impact | Fix |
|---|---|---|---|---|
| P1 | `export_service.py` | N+1 VideoClip-Lookup (Bug 12) | 100 SELECTs bei 100 Segmenten | `IN`-Query bulk load |
| P2 | `main.py InteractiveTimeline` | N+1 load_from_db (Bug 17) | bis zu 400 SELECTs nach Auto-Edit | `IN`-Query bulk load |
| P3 | `pacing_service.py` | 3×Beatgrid-Session pro Phase3-Aufruf (Bug 14) | 3 statt 1 Round-Trip | Kombinierte Query |
| P4 | `main.py sync_anchors` | N Sessions in Loop (Bug 18) | N Connections offen/geschlossen | 1 Session außerhalb |
| P5 | `pacing_service.py` | `@lru_cache` auf `_get_audio_path`, `_get_bpm`, `_get_audio_duration` | Stale-Cache nach Track-Update | `invalidate_pacing_caches()` bereits vorhanden — OK |
| P6 | `video_analysis_service.py` | RAFT-Modell wird nach jeder Analyse entladen | GPU-Overhead bei Batch | Akzeptabel für VRAM-Budget |

---

## 5. Datenintegrität

| Befund | Schwere | Status |
|---|---|---|
| FK CASCADE fehlt auf alten DBs ohne Migration | KRITISCH | Migriert, aber Prüfung unvollständig (Bug 16) |
| Fehlende ORM back_populates (Bug 20) | MITTEL | Nicht migriert |
| Split-Commit Datenverlust (Bug 21) | KRITISCH | Nicht gefixt |
| crossfade_duration/brightness/contrast fehlen in ALTER TABLE (Bug 13) | KRITISCH | Nicht migriert |
| `TimelineEntry.project_id` FK ohne ORM-Relationship zu Project | NIEDRIG | Funktioniert auf DB-Ebene |
| `vector_db_service.delete_by_video()` f-string SQL-Injection (LanceDB-Filter) | HINWEIS | LanceDB-API, kein SQLAlchemy — eigene Eingabe, Risiko gering |

---

## 6. Empfehlungen (priorisiert)

1. **Sofort:** Bug 13 fixen — ALTER TABLE für `crossfade_duration`, `brightness`, `contrast` hinzufügen. Ohne diesen Fix crasht die App beim ersten Öffnen des CONVERT-Workspace auf jeder existierenden DB.

2. **Sofort:** Bug 21 fixen — Split-Commit in `_on_auto_edit_finished()` zu Single-Transaction umschreiben. Data-loss-Bug.

3. **Kurzfristig:** Bug 12, 17 — Bulk-Loads einführen. Bereits bei 50 Auto-Edit Segmenten spürbare UI-Verzögerung beim Export/Refresh.

4. **Kurzfristig:** Bug 16 — Migration-Prüfung auf alle Child-Tabellen ausweiten.

5. **Mittelfristig:** Bug 20 — ORM-Relationships vervollständigen. Verhindert zukünftige AttributeErrors wenn Code auf `project.pacing_blueprints` zugreift.

6. **Mittelfristig:** Bug 14, 18 — DB-Round-Trips reduzieren. Pacing-Performance verbessert sich spürbar bei langen DJ-Sets.

7. **Niedrig:** Bug 15, 19 — Session-Hygiene und kleine N+1 bereinigen.

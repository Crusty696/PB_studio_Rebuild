# Plan: PB-STUDIO-PERF-DB-CLEANUP-2026-07-12

status: code-complete-live-pending
decision: D-067 (Vault)
vault_mirror: wiki/synthesis/plan-perf-db-cleanup-2026-07-12.md
quelle: /simplify 4-Agenten-Review 2026-07-12, Efficiency-Angle
(alle 10 Findings vom User beauftragt, Chat 2026-07-12: "nicht nur die
top 3 sondern alle funde")

## Ziel

Wiederkehrende DB-/IO-Verschwendung eliminieren, ohne ein einziges
Verhalten zu aendern: gleiche Ergebnisse, weniger Queries/Blob-Loads/
Prozess-Spawns. Referenz-Pattern existiert im Repo (virt-M4:
`lazyload("*")` in `ui/timeline.py`, Spalten-Queries in
`ui/controllers/convert.py:95-111`).

## Wurzel-Kontext (fuer alle Tasks)

`database/models.py` definiert mapper-weite Eager-Loads:
- AudioTrack: `waveform_data`/`beatgrid` lazy='joined',
  `structure_segments`/`hotcues`/`audio_video_anchors` lazy='selectin'
- VideoClip: `scenes`/`audio_video_anchors` lazy='selectin'
- TimelineEntry: `anchors` lazy='selectin', `project` lazy='joined'
- AnalysisJob: `artifacts` lazy='selectin'

Jede Voll-ORM-Query zahlt diese Loads mit. Fix-Baustein ueberall:
`options(lazyload("*"))` bzw. reine Spalten-Queries.

## Tasks (Reihenfolge = Prioritaet)

### E1 — get_all_audio / get_all_video: Eager-Load-Lawine
- `services/ingest_service.py:472-481` (get_all_audio),
  `:525-532` (get_all_video)
- Kosten: jeder Media-Table-Refresh (Boot `main.py:443`, nach jedem
  Import/Analyse-Abschluss via B-253-Bridge, 10+ Action-Callsites)
  laedt pro AudioTrack Waveform-/Beatgrid-JSON-Blobs (MB pro 2h-Mix)
  + 3 Selectin-Queries; pro VideoClip 2 Selectin-Queries (alle Scenes
  inkl. ai_caption). Gebraucht: nur Skalar-Spalten.
- Fix: `session.query(AudioTrack).options(lazyload("*"))` (analog
  VideoClip). Ergebnis-Dicts byte-identisch.
- Verify: TDD-Guard Query-Count (sqlalchemy event listener) +
  identische Dict-Ausgabe vorher/nachher auf test33.

### E2 — infer_many_from_db: N+1 hoch drei
- `services/analysis_status_service.py:313-328, 331-364, 431-438`
- Kosten: pro Video `session.get(VideoClip)` (+2 Selectin) +
  redundanter `select(Scene)` (Z.347 — `video.scenes` ist schon
  geladen) + bis 4 Einzel-SELECTs in `_ensure_status_done`; pro Audio
  `session.get(AudioTrack)` (laedt Waveform-Blobs ERNEUT, Doppel-Load
  zu E1) + bis 9 Einzel-SELECTs. test33: ~3000+ Queries pro Refresh.
- Fix: ein SELECT aller AnalysisStatus-Rows fuer alle IDs in ein Dict
  `(media_id, step_key) -> Entry`; `video.scenes` statt Re-Select;
  identische Writes.
- Verify: Query-Count-Guard + Status-Dict-Paritaet vorher/nachher.

### E3 — Brain-Run-Klick laedt alles im GUI-Thread
- `main.py:677-679` (`_on_brain_run_requested`)
- Kosten: SteerTab-"Run" blockiert Main-Thread mit komplettem
  E1+E2-Aufwand, nur fuer `[v["id"] for v in ...]`. 375 Clips =
  sekundenlanger Freeze pro Klick.
- Fix: `session.query(VideoClip.id).filter(project_id==..,
  deleted_at.is_(None))` — 1 SELECT, gleiche ID-Liste.
- Verify: gleiche ID-Liste vorher/nachher; Freeze-Probe
  (PB_STUDIO_FREEZE_PROBE=1) beim Run-Klick.

### E4 — F-001 playback_offset-Save: Voll-ORM pro Video
- `services/pacing_service.py:1548-1556`
- Kosten: pro Auto-Edit-Lauf, pro Clip `query(VideoClip)...first()`
  inkl. aller Scenes+Anchors — fuer einen Float. 375 Clips ≈ 1125
  Queries am Ende jedes Pacing-Laufs.
- Fix: `session.execute(update(VideoClip).where(VideoClip.id == vid,
  VideoClip.deleted_at.is_(None)).values(playback_offset=offset))`
  (Semantik inkl. deleted_at-Filter identisch).
- Verify: DB-Zustand (playback_offset aller Clips) vorher/nachher
  identisch auf Kopie-DB.

### E5 — TimelineDBWorker: Anchors doppelt, Projekt pro Entry gejoint
- `ui/timeline.py:1346 + 1369-1373`
- Kosten: `query(TimelineEntry).all()` ohne Options -> Selectin laedt
  ALLE ClipAnchors + joined `project` pro Entry; 2 Zeilen spaeter laedt
  die explizite ClipAnchor-Query dieselben Anchors nochmal. 1428
  Entries = kompletter Anchor-Doppel-Load pro Projekt-Load.
- Fix: `.options(lazyload("*"))` an die Entries-Query (Pattern steht
  6 Zeilen tiefer bereits fuer audio_map/video_map).
- Verify: Timeline-Render-Paritaet (Clip-Anzahl, Anchor-Anzahl) +
  Query-Count.

### E6 — repair_timeline_integrity: session.get pro Row
- `services/timeline_service.py:364-427`, laeuft nach jedem Auto-Edit
  (`timeline_service.py:175`)
- Kosten: pro Row ggf. `session.get(VideoClip/AudioTrack)` mit allen
  Eager-Loads; 1428 Rows = hunderte Queries. Gebraucht: nur `duration`.
- Fix: vorab 2 Spalten-Queries
  `dict(session.query(VideoClip.id, VideoClip.duration).filter(
  id.in_(media_ids)))` (analog AudioTrack).
- Verify: Repair-Ergebnis (geloeschte/gefixte Rows) identisch auf
  praeparierter Test-DB mit kaputten Rows.

### E7 — Anker-Sync-Persist: get pro Update
- `ui/timeline.py:3414-3424`
- Kosten: pro synchronisiertem Video-Clip `session.get(TimelineEntry)`
  + Anchors-Selectin, geschrieben werden nur start/end_time.
- Fix: ein Bulk-Load `query(TimelineEntry).options(lazyload("*"))
  .filter(TimelineEntry.id.in_([...]))` vor der Schleife, in-memory
  updaten, ein Commit.
- Verify: DB-Paritaet der Entry-Zeiten vorher/nachher.

### E8 — storage_browser list_sources: 3-4 Queries pro Source-Hash
- `services/storage_provenance/storage_browser.py:68-97 + 138-146`;
  betrifft auch `disk_budget.py:47/72`
- Kosten: pro distinct source_sha256 Jobs-Query (laedt via
  AnalysisJob.artifacts-Selectin alle Artifacts) + Sources/Project-
  Join-Query + `_total_bytes`-Query die dieselben Artifact-Bytes
  NOCHMAL selektiert. S Sources = 3S+1 Queries.
- Fix: 3 Bulk-Queries ueber alle Hashes, in Python nach source_sha256
  gruppieren; `lazyload("*")` auf der Jobs-Query.
- Verify: Browser-Listing byte-identisch (Titel, Bytes, Counts) auf
  test33-Storage.

### E9 — nullpool_session: neue Engine pro Aufruf
- `database/session.py:161-197`; 102 Callsites, darunter
  Hochfrequenz-Pfade (mark_started/mark_done pro Step pro Medium,
  per-Clip-Worker-Loops, add_anchor_at)
- Kosten: `create_engine` + Listener-Registrierung + Dispose pro
  Aufruf — reiner Konstruktions-Overhead; NullPool holt Connection
  sowieso frisch pro Session.
- Fix: modulweit EINE NullPool-Engine, gecacht keyed auf
  `str(engine.url)` (invalidiert sich beim Projekt-Swap ueber
  URL-Wechsel). Lock-Semantik identisch (NullPool = frische
  Connection pro Session).
- Verify: bestehende Lock-/Threading-Tests (B-512-Suite) gruen;
  Projekt-Swap-Test (set_project -> neuer Pfad wird benutzt).
- ACHTUNG: heikelster Task (DB-Kern). Einzeln committen, einzeln
  live verifizieren.

### E10 — extract_keyframes: sequentielle ffmpeg-Spawns
- `services/video_analysis_service.py:439-472`
- Kosten: ein ffmpeg-Prozess pro Szene, sequentiell. Batch 103 Videos
  x Dutzende Szenen = tausende Spawns nacheinander.
- Fix: `ThreadPoolExecutor(max_workers=4)` ueber die Szenen-Schleife;
  Skip-if-exists-Cache (Z.444) bleibt wirksam. GPU-Hartregel beachten:
  ffmpeg-Aufrufe unveraendert (`-hwaccel cuda` wo vorhanden), nur
  Parallelisierung der Spawns.
- Verify: identische JPG-Outputs (Hash-Vergleich) auf Testvideo;
  CPU-Last-Check auf Surface Book 2 (ggf. max_workers=2).

## Leitplanken

- Ein Task = ein Commit = ein Vault-Log-Eintrag = eigene Verifikation.
- Jeder Task braucht Vorher/Nachher-Paritaetsbeweis (Ergebnis
  identisch) + Query-Count- oder Timing-Beleg (billiger).
- Kein Task aendert Ergebnisse, Fehlerpfade oder Sichtbares.
- DetachedInstanceError-Risiko bei lazyload("*"): pro Callsite
  pruefen, dass keine Relationen nach Session-Ende gelesen werden.
- Reihenfolge E1->E10; E9 zuletzt vor E10 verhandelbar, aber nie
  parallel zu anderen Tasks.
- `status: fixed` setzt nur der User nach Live-Test.

## Abschlussstand 2026-07-13

E1-E10 committed und backend-verifiziert. Paritaets-, Query-/Timing- und
DetachedInstanceError-Belege:
[Abschlusssynthese](../synthesis/perf-db-cleanup-abschluss-2026-07-13.md).
Offen: reale GUI-/App-Livepfade, D-069 Voll-Package-/Installed-App-Test,
User-`fixed`.

# Fixplan — Audit-Findings 2026-07-07 (Entscheidungen eingearbeitet)

- **plan_id:** `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`
- **status:** entscheidungs-komplett. Alle 4 offenen User-Fragen sind am
  2026-07-07 beantwortet (siehe "User-Entscheidungen"). Ausführung gemäß
  Freigabe-Matrix unten: **A0+A3 sofort erlaubt**, Rest nach
  SCHNITT-Live-Abnahme durch den User.
- **Quelle:** `docs/superpowers/synthesis/audit-fehler-luecken-toter-code-verdrahtung-2026-07-07.md`
  (85 Findings, statisch erhoben).
- **Consulting-Reviews:** 2× durchgeführt (2026-07-07). Review 1 →
  Pflicht-Regeln R1–R4. Review 2 → Coverage-Gap geschlossen (A2 um Waveform
  erweitert, B7 neu, Abschnitt "Zurückgestellt" ergänzt), A0 eingefügt,
  Reihenfolge nach R3 gesplittet, Track C in Folgeplan überführt.
- **Verbindlicher Nachfolger (User-Anweisung):**
  `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`
  (`docs/superpowers/plans/2026-07-07-neubauten-vollintegration-plan.md`)
  startet **direkt nach** Abschluss+Test dieses Plans. Hohe Priorität, kein
  anderer Plan dazwischen.

## User-Entscheidungen (2026-07-07, einzeln abgefragt)

| # | Frage | Entscheidung |
|---|---|---|
| 1 | Crossfades oder harte Beat-Cuts? | **Beides steuerbar** — Crossfades verdrahten UND UI-Schalter (pro Projekt/Segment hart vs. weich) |
| 2 | Einordnung ggü. aktivem SCHNITT-Plan | **Option C** — A0+A3 sofort (kein Overlap); A1/A2/B5/B6 erst nach SCHNITT-Live-Abnahme (`fixed` durch User) |
| 3 | Betroffene Alt-DB für DB-010? | **Scan durchgeführt (Option A):** 24 DBs read-only geprüft, 0 betroffen → A3 = **P2 präventiv** |
| 4 | Track-C-Neubauten | **Alle vollständig bauen** — in eigenem Folgeplan `NEUBAUTEN-VOLLINTEGRATION` (siehe oben) |

---

## ⛔ Pflicht-Regeln (aus Consulting-Reviews, nicht verhandelbar)

### R1 — Repro-Gate vor jedem Fix
Kein Finding wird gefixt, bevor es **live mit echten Testdaten reproduziert**
ist (Standard-Testset: Video-Ordner `Solo_Natur`, Audio
`Crusty Progressive Psy Set2.mp3`). Ist-Zustand mit Beweis (Log/DB-Dump/
Screenshot/Render) dokumentieren. Repro schlägt fehl → Finding zurück auf
`unbestätigt`, **kein Fix**. Grund: Findings sind statisch erhoben; DB-013
war nachweislich kein Bug, sondern ein Diagnose-Skript-Artefakt.

### R2 — Track-Trennung
- **Track A** — render-kritische Bugs (repro-gated).
- **Track B** — stille Degradierung sichtbar/robust machen.
- **Track C** — ERLEDIGT: per User-Entscheidung #4 vollständig in den
  Folgeplan `NEUBAUTEN-VOLLINTEGRATION` überführt. In DIESEM Plan kein Code
  an Track-C-Komponenten.
- **Track D** — Aufräumen. **Keine Löschung** ohne pro-Modul-User-OK.

### R3 — Freigabe-Matrix (aus Entscheidung #2, Option C)
| Sofort erlaubt | Erst nach SCHNITT-`fixed` durch User |
|---|---|
| A0 (Render-Smoke-Test), A3 (DB-Migration) | A1, A2, B5, B6 (fassen Auto-Edit/Pacing/Export-Pfad an) |
| B1–B4, B7 nach A0 (kein SCHNITT-Overlap, aber erst Smoke-Test) | |

### R4 — Gekoppelte Findings als Paket
PIPE-002 + PIPE-007 + DB-002 + DB-004-Anschluss = ein Paket (A2).
PIPE-001 = Multi-Key-Angleichung über ALLE Producer/Consumer + UI-Schalter.

---

## Track A — Render-kritische Bugs (repro-gated)

### A0 — Smoke-Test des E2E-Render-Pfads (NEU, vor allem anderen)
- **Warum:** Das Repro-Gate (R1) setzt voraus, dass Import → Analyse →
  Auto-Edit → Export mit dem Testset überhaupt durchläuft. Ungeprüft auf
  aktuellem Branch-Stand.
- **Tun:** Kompletter Durchlauf mit Testset, Ergebnis-Video + Logs sichern.
- **Grün** → Repro-Gate anwendbar. **Rot** → der Befund selbst ist der erste
  Bug und geht VOR allen Audit-Findings an den User.

### A1 — PIPE-001: Crossfades verdrahten + steuerbar machen (Entscheidung #1: "beides")
- **Repro (zuerst):** Auto-Edit mit Testset, Export, prüfen: Übergänge hart?
  DB-Dump `timeline_entries.crossfade_duration` — erwartet 0.0 trotz
  berechneter Werte.
- **Befund:** `workers/edit.py:64` serialisiert `"crossfade"`,
  `services/timeline_service.py:308` liest `"crossfade_duration"` → immer 0.0.
  Zwei Key-Konventionen im Code: `"crossfade"` (`workers/edit.py:64`,
  `ui/clip_inspector.py:196`) vs. `"crossfade_duration"`
  (`ui/undo_commands.py:259/395`, `services/timeline_service.py:308`).
- **Fix-Umfang (erweitert durch Entscheidung #1):**
  1. Kanonische Konvention `crossfade_duration` (DB-Spaltenname); ALLE
     Producer/Consumer angleichen; ClipInspector-Roundtrip testen.
  2. **UI-Schalter "Übergänge: harte Beat-Cuts / automatische Crossfades"**
     pro Projekt (Auto-Edit-Panel, persistiert), Segment-Ebene bleibt über
     bestehenden ClipInspector-Slider (`ui/clip_inspector.py:88`) steuerbar.
     Schalter "hart" → Auto-Edit setzt crossfade_duration=0, manuelle Werte
     bleiben respektiert.
- **Verify:** Export in Stellung "Crossfades" zeigt weiche Übergänge an
  Breakdown-/DJ-Mix-Segmenten; Stellung "hart" → alle Cuts hart; manueller
  Slider-Wert überlebt Undo/Redo und Export. **Live-Export-Gegentest Pflicht**
  — der xfade-Filtergraph-Pfad im Export lief evtl. noch nie live
  (`services/export_service.py:644`), NVENC-Performance auf GTX 1060 prüfen.
- **Risiko:** ClipInspector-Pfad; bisher toter Export-Codepfad wird scharf.

### A2 — Paket: V2-Default vollständig machen (PIPE-002 + PIPE-007 + DB-002 + DB-004-Anschluss)
- **Repro (zuerst):** Track mit V2 komplett analysieren → DB prüfen:
  `audio_tracks.mood/genre/is_dj_mix` NULL? `waveform_data`-Zeile fehlt?
- **Befund:** `DEFAULT_STAGE_ORDER` (`services/audio_pipeline/stages.py:585`)
  ohne Classify- UND ohne Waveform-Stage. Gekoppelt:
  `MAX_DURATION_CLASSIFY=180s` (`services/audio_classify_service.py:218`)
  macht is_dj_mix mathematisch immer False (<600s-Schwelle,
  `audio_constants.py:53`) und verzerrt mood/genre auf die ersten 3 Minuten.
  Zusätzlich verwirft der Classify-Pfad das berechnete `sub_genre` statt es
  zu persistieren (DB-004, `workers/audio_analysis.py:305-313`).
- **Fix-Umfang:**
  1. Classify-Stage in V2-Order MIT Langform-Strategie (Windowing/Sampling
     über volle Länge statt 180s-Kappung).
  2. **Waveform-Stage in V2-Order** (3-Band-Waveform, Writer-Logik existiert
     in `services/ai_audio_service.py:1404` / `workers/analysis.py:88`) —
     SCHNITT-Audio-Tab bekommt nach Komplett-Analyse Daten.
  3. `sub_genre` aus ClassifyResult persistieren (DB-004-Anschluss; die
     Spalte wird von `services/pacing/bridge_mapping.py:107` gelesen).
- **Verify:** Nach V2-Lauf: mood/genre/sub_genre gesetzt; is_dj_mix True für
  den Test-DJ-Mix; `waveform_data`-Zeile vorhanden; SCHNITT-Waveform sichtbar;
  mood repräsentiert Gesamttrack. Laufzeit-Delta des V2-Laufs messen und
  berichten.
- **Risiko:** V2-Laufzeit steigt; GPU-Regel (GTX 1060 / cuda:0, sonst CPU).

### A3 — DB-010: Nachrüst-Migration `beatgrids.stem_weighted_energy` — **P2 präventiv** (Entscheidung #3)
- **Scan-Ergebnis 2026-07-07 (read-only, `PRAGMA table_info`, mode=ro):**
  24 Projekt-/Backup-DBs geprüft → 23× Spalte vorhanden, 0× fehlend, 1×
  keine `beatgrids`-Tabelle (`storage/pb_studio.db`, Stub). **Kein akuter
  Crash-Fall.**
- **Trotzdem fixen (präventiv):** Jede alte Backup-DB / jedes von einem
  anderen Stand wiederhergestellte Projekt kann die Lücke mitbringen;
  `create_all()` ergänzt keine Spalten (extern verifiziert).
- **Fix:** Idempotenter ADD-COLUMN-Block in `database/migrations.py` analog
  zum bestehenden Legacy-Nachrüst-Block (`:439-454`) — NICHT über Alembic
  (der real genutzte Migrationspfad ist `migrations.py`, vgl. DEAD-016).
- **Verify:** Alt-DB-Simulation (Wegwerf-Kopie: Spalte droppen → Migration →
  Beatgrid-Write ok).

---

## Track B — Stille Degradierung sichtbar/robust machen (nach A0; B5/B6 zusätzlich hinter SCHNITT-Gate)

- **B1 — PIPE-008:** SigLIP-Ausfall deaktiviert Embedding-Matching still
  (`services/pacing_service.py:704-713`). Fix: sichtbare UI-Warnung,
  Auto-Edit-Ergebnis als "degradiert" kennzeichnen.
- **B2 — PIPE-009:** Beat-Analyse-Fehler verschluckt → synthetisches Grid
  ohne Downbeats (`workers/analysis.py:61`,
  `services/beat_analysis_service.py:256`). Fix: Fehler sichtbar, Fallback
  gekennzeichnet.
- **B3 — PIPE-015:** stille GPU→CPU-Weichen. NVENC-Fehlercache
  (`services/export_service.py:43`) nicht prozessweit ohne Recheck;
  RAFT/CPU-Motion-Scores skalenkonsistent oder markiert
  (`services/video_analysis_service.py:140/353`).
- **B4 — DB-006:** V2-Worker schreibt keinen `analysis_status`
  (`workers/audio_pipeline_v2_worker.py:40-88`). Fix: Status-Writes analog
  Legacy; Doppel-Analyse-Schutz greift.
- **B5 — PIPE-006:** Quellvideo-Szenenzeit als Timeline-Zeit injiziert
  (`services/pacing_service.py:655-685`). Fix: Einheiten-Klärung, ggf.
  Zusatz-Cut-Logik entfernen. **SCHNITT-Gate (R3).**
- **B6 — PIPE-013:** Media-Panel-Re-Analyse mit kaputtem Konstruktor
  (`ui/workspaces/media_workspace.py:1575`). Fix: `video_path` korrekt
  auflösen, Proxy-First nicht umgehen. **SCHNITT-Gate (R3).**
- **B7 — DB-017 (NEU aus Review 2):** `init_db()` schluckt Alembic-Fehler
  (`database/migrations.py:828-838`) → fehlende `mem_*`-Tabellen crashen
  erst zur Laufzeit (`no such table: mem_pacing_run`,
  `services/pacing_service.py:116`). Fix: Fail-fast oder expliziter
  Tabellen-Existenz-Guard mit klarer Fehlermeldung beim Start.
- **B8 — B-602 (NEU, aufgedeckt durch A0-track2):** Pipeline-Checkpoint
  `stem_cache._STORAGE_ROOT = Path("storage")` war CWD-relativ →
  `pipeline_state/<track_id>.json` global geteilt über alle Projekte gleicher
  track_id → zweites Projekt übersprang alle Audio-Stages → Auto-Edit 0
  Segmente. Fix: `_storage_root()` projekt-relativ via `APP_ROOT`; vergifteter
  Alt-Checkpoint entfernt. Commit `39a6b3d`. Vault: `wiki/bugs/B-602-*.md`.
  **code-complete; Live-Repro (track2 voll durchlaufen) offen.**

---

## Track C — ERLEDIGT durch Entscheidung #4

Alle 11 Komponenten (Studio-Brain-Pipeline, Brain-V3-Reranker,
DAG-Video-Engine, SteerOverrideQueue, Slice-1-Pacing-Cluster, RL-Stack v2,
LLM-Pacing, Lernschleife→Scorer, Timeline-Snapshots, `audio.v2_default`-Setter,
SetupWizard) werden **vollständig gebaut und verdrahtet** im verbindlichen
Folgeplan `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`. In diesem Plan
hier: keine Arbeit daran.

---

## Track D — Aufräumen (unverändert: keine Löschung ohne pro-Modul-OK)

Reine Kandidatenliste, dieser Plan löscht nichts. Achtung: Durch
Entscheidung #4 sind mehrere frühere "Löschkandidaten" jetzt
**Verdrahtungs-Ziele des Folgeplans** (DEAD-001 Slice-1, DEAD-002
SetupWizard, DEAD-013 Timeline-Snapshots, DEAD-008 video_pipeline-Module) —
sie sind aus der Löschliste RAUS.

- Verbleibende Löschkandidaten (User-Freigabe pro Modul): DEAD-003..007
  (Brain-V3-Spikes: subtrack_detector, embedding_repository, onnx_export,
  visual_curves, schemas), DEAD-009 (storage_provenance-Teile — heikel,
  OTK-021-Nähe!), DEAD-010 (release_readiness unter services/ → nach tools/
  verschieben statt löschen?), DEAD-011/012 (audio_pipeline cleanup/
  migration/vram_guard/auto_save_scheduler), DEAD-014 (Re-Export-Shim),
  WIRE-006/007, USE-016 (PrepareWorkspace/LegacyAnalysisWorkspace).
- DB-Ballast: tote Tabellen DB-001/007/008/009/021; DB-012
  (spectral_bands-Doppel-Serialisierung); DB-018 (Index/Wachstum
  ai_pacing_memory).
- Doku-Drift: "8 Mixins"-Beschreibung in CLAUDE.md/AGENTS.md veraltet
  (Controller-Komposition ist real); Vault-`index.md` Zeile 137 defekt
  (71k-Zeichen-Einzelzeile).

---

## Zurückgestellt / bewusst nicht in diesem Plan (Coverage-Vollständigkeit, Review 2)

Kein Finding verschwindet stillschweigend. Nicht geroutete Findings + Grund:

| Finding | Grund der Zurückstellung |
|---|---|
| PIPE-003 (AVPacing-Kurven verpuffen) | Konsument entsteht erst mit Folgeplan (Pacing-Kurven); bis dahin Entscheidung "Stage deaktivieren vs. persistieren" beim User — CPU-Verschwendung dokumentiert |
| PIPE-004 (Onset-Cut-Refinement ohne Caller) | Wird durch Folgeplan T2.5 (cut_snapper) erledigt |
| PIPE-005 (Structure-Enrichment ohne Schnitt-Wirkung) | Konsum entsteht mit Folgeplan Paket 1 (ClipFeatures/Scorer) |
| PIPE-016 (Onset 1800s-Kappung) | Im Folgeplan T2.5 explizit enthalten (Voraussetzung für cut_snapper auf langen Mixen) |
| PIPE-010 (stem_weighted_energy write-only + Reihenfolge) | Kein Leser im Ist-Zustand; neu bewerten wenn Folgeplan-Scorer die Daten nutzt |
| PIPE-012 (lru_cache nicht invalidiert nach Video-Re-Analyse) | P2; nach A0-Smoke-Test als kleiner Fix einplanbar, kein Render-Blocker |
| PIPE-017 (Legacy-Batch veraltetes BPM) | Nur relevant bei `audio.v2_default=false`; Setter kommt erst mit Folgeplan T2.2 |
| DB-004 (sub_genre/spectral_hash/harmonic_tension nie geschrieben) | `sub_genre` in A2 enthalten; `spectral_hash`/`harmonic_tension` brauchen neue Berechnungs-Writer → Folgeplan-Kontext (Scorer nutzt sie) |
| DB-011 (Check-then-Insert-Races) | P2-Härtung (Upsert analog B-581); nach Track B einplanen |
| DB-015 (Soft-Delete-Kinder sichtbar) | Bekanntes, dokumentiertes B-186-Restrisiko; kein akuter Repro |
| DB-020 (is_dj_mix Default-Drift) | Kosmetisch nach A2 (Classify schreibt echte Werte); Alt-Zeilen-Bereinigung optional |
| DB-014 (media_id ohne FK) | Dokumentiertes Design D-028, kein Fix geplant |
| WIRE-003/005/013/014, USE-010/011 | Klein-UI/Konsistenz; WIRE-005 (Feedback-Bestätigung) ist im Folgeplan T1.6; Rest Backlog |
| DEAD-015/016 (Doppel-Implementierungen Video-Engine / Migrationssysteme) | Engine: Folgeplan Paket 3. Migrationssysteme: Konsolidierungs-Entscheidung beim User nach A3 |

---

## Ausführungs-Reihenfolge (final, gemäß Entscheidung #2)

**Phase SOFORT (kein SCHNITT-Overlap):**
1. A0 Smoke-Test → 2. A3 Migration (P2, klein) → 3. B1–B4, B7

**Phase NACH SCHNITT-`fixed` (User-Abnahme):**
4. A1 (Crossfade-Paket + UI-Schalter) → 5. A2 (V2-Komplett-Paket) →
6. B5, B6

**Danach (verbindlich, User-Anweisung):**
7. Folgeplan `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07` — komplett.

**Abschluss:** Jede Task einzeln committet, live verifiziert mit Beweis,
Vault-Log pro Sub-Schritt. `fixed` pro Task setzt nur der User.

# Fixplan (DRAFT) — Audit-Findings 2026-07-07

- **plan_id:** `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`
- **status:** `draft` — NICHT ausführungsreif. `ACTIVE_PLAN.md` bleibt beim
  `PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07` (Status `in_progress`).
  Dieser Plan darf erst Code berühren, wenn der User ihn explizit als aktiven
  Plan wählt.
- **Quelle:** `docs/superpowers/synthesis/audit-fehler-luecken-toter-code-verdrahtung-2026-07-07.md`
  (85 Findings, rein statisch, read-only).
- **Vorab durch Consulting-Team geprüft** (2026-07-07): Recommendation
  GO-mit-Modifikation. Die 4 Modifikationen sind unten als Pflicht-Regeln
  eingebaut.

---

## ⛔ Pflicht-Regeln (aus Consulting-Review, nicht verhandelbar)

### R1 — Repro-Gate vor jedem Fix
Kein Finding wird gefixt, bevor es **live mit echten Testdaten reproduziert**
ist (Standard-Testset: Video-Ordner `Solo_Natur`, Audio
`Crusty Progressive Psy Set2.mp3`). Ist-Zustand mit Beweis (Log/DB-Dump/
Screenshot/Render) dokumentieren. Repro schlägt fehl → Finding zurück auf
`unbestätigt`, **kein Fix**. Grund: mehrere Audit-Findings sind statisch und
mind. eines (DB-013) war nachweislich gar kein Bug, sondern ein
Diagnose-Skript-Artefakt.

### R2 — Vier getrennte Tracks
Findings sind **nicht** homogen. Trennung ist Pflicht:
- **Track A** — render-kritische Bugs (repro-gated, echter User-Impact).
- **Track B** — stille Degradierung sichtbar/robust machen.
- **Track C** — Produkt-Entscheidungen (abgeschnittene Neubauten). **Kein
  Code** in diesem Plan — reine Entscheidungsvorlage für den User.
- **Track D** — Aufräumen (toter Code, Dead-End-Signals). **Keine Löschung**
  ohne pro-Modul-User-OK (HARTREGEL + one-way-door).

### R3 — Governance-Kollision mit aktivem Plan beachten
Track-A-Findings PIPE-001 / PIPE-002 / PIPE-006 mutieren denselben
Auto-Edit/Pacing/Export-Pfad wie der aktive
`SCHNITT-CLIPAUSWAHL-FIXPLAN`. Parallele Mutation ist verboten. Optionen für
den User: (a) render-kritische Findings **in den aktiven SCHNITT-Plan
integrieren**, oder (b) SCHNITT-Plan abschließen, dann diesen Plan aktiv
schalten. Nicht beides gleichzeitig.

### R4 — Gekoppelte Findings als Paket
Findings mit technischer Abhängigkeit werden nicht getrennt gefixt (sonst
Halbfix). Betroffen: PIPE-002+PIPE-007 (Classify + Langform-Strategie),
PIPE-001 (Multi-Key-Angleichung über alle Producer/Consumer).

---

## Track A — Render-kritische Bugs (repro-gated)

### A1 — PIPE-001: Crossfades werden berechnet, aber nie gerendert
- **Repro (zuerst):** Auto-Edit mit Testset laufen lassen, Segment mit
  erwartetem Crossfade (Breakdown/DJ-Mix) exportieren, im Output prüfen ob
  Übergang weich oder hart ist. Zusätzlich DB `timeline_entries.crossfade_duration`
  dumpen — erwartet 0.0 trotz berechneter Werte.
- **Befund:** `workers/edit.py:64` serialisiert `"crossfade"`, aber
  `services/timeline_service.py:308` liest `"crossfade_duration"` → immer 0.0.
- **⚠ Multi-Key-Falle (Domain Expert):** Im Code existieren ZWEI Konventionen.
  `"crossfade"`: `workers/edit.py:64`, `ui/clip_inspector.py:196`.
  `"crossfade_duration"`: `ui/undo_commands.py:259/395`,
  `services/timeline_service.py:308`. Fix = alle Producer/Consumer des
  Segment-Dicts auf EINE kanonische Konvention angleichen, nicht einen Key
  umbenennen.
- **Fix-Skizze:** Grep `"crossfade"` + `crossfade_duration` repo-weit →
  Konvention festlegen (`crossfade_duration`, da DB-Spaltenname) → alle
  Producer angleichen → ClipInspector-Roundtrip (setzen/lesen) testen.
- **Verify:** Export mit Crossfade-Segment zeigt weichen Übergang; ClipInspector
  liest/schreibt Wert korrekt; Undo/Redo erhält Wert.
- **Risiko:** ClipInspector-Pfad bricht bei blindem Rename. Regressionsrisiko
  am Export.
- **Offen (User):** Sind Crossfades überhaupt gewünscht, oder sind harte
  Beat-Cuts das Ziel? (Devil's-Advocate-Einwand). Falls harte Cuts gewollt →
  A1 entfällt / wird zu "Feld sauber entfernen".

### A2 — PIPE-002 + PIPE-007 (Paket): V2-Default ohne taugliche Klassifikation
- **Repro (zuerst):** Track mit V2 komplett analysieren, danach DB
  `audio_tracks.mood/genre/is_dj_mix` prüfen — erwartet NULL. Bei 60-min-Mix
  zusätzlich prüfen, dass is_dj_mix (falls Classify separat getriggert) False
  ist.
- **Befund:** `DEFAULT_STAGE_ORDER` (`services/audio_pipeline/stages.py:585`)
  hat keine Classify-Stage → mood/genre/is_dj_mix NULL → Matching mood-blind.
  Gekoppelt: `MAX_DURATION_CLASSIFY=180s` (`services/audio_classify_service.py:218`)
  macht is_dj_mix mathematisch immer False (180s < 600s-Schwelle) und
  verzerrt mood/genre auf die ersten 3 Min (Intro→calm-Bias).
- **Fix-Skizze:** Classify-Stage in V2-Order einhängen MIT Langform-Strategie
  (Windowing/Sampling über die volle Länge statt 180s-Kappung). Beide Teile
  zusammen, sonst Halbfix.
- **Verify:** Nach V2-Lauf mood/genre gesetzt, is_dj_mix korrekt für echten
  DJ-Mix, mood repräsentiert den ganzen Track (nicht nur Intro).
- **Risiko:** Volle-Länge-Classify erhöht V2-Laufzeit. GPU-Regel beachten
  (nur GTX 1060 / cuda:0, sonst CPU).
- **Abhängigkeit:** überlappt inhaltlich mit aktivem SCHNITT-Plan (Clip-Auswahl)
  → R3.

### A3 — DB-010: Migrations-Lücke `beatgrids.stem_weighted_energy`
- **Repro (zuerst):** Reale Projekt-DB(s) auf Vorhandensein der Spalte prüfen
  (`PRAGMA table_info(beatgrids)`). Fehlt sie auf einer bereits
  Alembic-gestempelten Alt-DB → Beatgrid-Write crasht mit `no such column`.
  Beleg der Kausalkette: `create_all()` ergänzt keine Spalten zu existierenden
  Tabellen (SQLAlchemy-Doku, extern bestätigt 2026-07-07).
- **Befund:** Weder Legacy-Nachrüst-Block (`database/migrations.py:439`) noch
  eine Alembic-Revision legt die Spalte an.
- **Fix-Skizze:** Idempotente Nachrüst-Migration (ADD COLUMN IF NOT EXISTS
  analog zum bestehenden Legacy-Block) ergänzen.
- **Verify:** Alt-DB-Simulation (Spalte droppen, Migration laufen, Beatgrid-Write
  ok).
- **Severity-Weiche:** Repro trifft zu → P0. Keine betroffene DB gefunden →
  P2 präventiv.

---

## Track B — Stille Degradierung sichtbar/robust machen

Kein Verhaltens-Umbau, sondern Fehler nicht mehr verschlucken. Jeweils
repro-gated.

- **B1 — PIPE-008: SigLIP-Ausfall deaktiviert Embedding-Matching still**
  (`services/pacing_service.py:704-713`). Fix: sichtbarer Fehler/Warnung in UI
  statt nur Log; Auto-Edit-Ergebnis als "degradiert" kennzeichnen.
- **B2 — PIPE-009: Beat-Analyse-Fehler verschluckt → synthetisches Grid**
  (`workers/analysis.py:61`, `services/beat_analysis_service.py:256`). Fix:
  Fehler sichtbar machen; kein stiller librosa-ohne-Downbeats-Fallback ohne
  Hinweis.
- **B3 — PIPE-015: stille GPU→CPU-Weichen** (NVENC-Cache
  `services/export_service.py:43`; RAFT-Skalierungs-Mismatch
  `services/video_analysis_service.py:140/353`). Fix: NVENC-Fehler nicht
  prozessweit cachen ohne Recheck; RAFT/CPU-Motion-Scores skalenkonsistent
  oder markiert.
- **B4 — DB-006: V2-Worker schreibt keinen `analysis_status`**
  (`workers/audio_pipeline_v2_worker.py:40-88`). Fix: Status-Writes analog
  Legacy-Worker; Doppel-Analyse-Schutz greift.
- **B5 — PIPE-006: Quellvideo-Szenenzeit als Timeline-Zeit injiziert**
  (`services/pacing_service.py:655-685`). Fix: Einheiten-Klärung; ggf.
  Zusatz-Cut-Logik entfernen. **Überlappt SCHNITT-Plan → R3, ggf. dorthin.**
- **B6 — PIPE-013: Media-Panel-Re-Analyse mit kaputtem Konstruktor**
  (`ui/workspaces/media_workspace.py:1575`). Fix: `video_path` korrekt
  auflösen, Proxy-First nicht umgehen.

---

## Track C — Produkt-Entscheidungen (KEIN Code in diesem Plan)

Abgeschnittene 2026er-Neubauten. Für jeden entscheidet der User:
**verdrahten / löschen / liegenlassen**. Das ist Feature-Rollout bzw.
Aufräumen, kein Bugfix. Reine Vorlage:

| Komponente | Finding | Zustand | Entscheidung offen |
|---|---|---|---|
| Studio-Brain-Pacing-Pipeline | USE-001 | Env-Flag nie gesetzt | verdrahten / löschen |
| Brain-V3-Reranker | USE-002 | `use_brain_v3` nie True | verdrahten / löschen |
| DAG-Video-Engine | USE-003 | Flag nie gesetzt | verdrahten / löschen |
| SteerOverrideQueue | USE-004 | UI schreibt, kein Consumer | Consumer bauen / löschen |
| Slice-1-Pacing-Cluster (16 Mod.) | USE-005 / DEAD-001 | nur Tests | verdrahten / löschen |
| RL-Stack v2 | USE-006 | nur Tests | verdrahten / löschen |
| LLM-Pacing (Strategist/Ollama-EDL) | USE-007 | kein UI-Schalter | UI bauen / löschen |
| Brain-V3-Lernschleife → Scorer | USE-008 | endet in Anzeige | Scorer-Konsum / löschen |
| Timeline-Snapshots (Hybrid-Undo) | USE-009 / DB-005 | kein Caller | verdrahten / löschen |
| `audio.v2_default` Setter | USE-012 | kein UI-Setter | Settings-UI / belassen |
| SetupWizard (First-Run) | WIRE-001 / DEAD-002 | nie aufgerufen | verdrahten / löschen |

**Wichtig (Devil's Advocate):** "Verdrahten" ist Spekulation, solange unklar
ist, ob die Komponente je live gehen soll. Für jede Zeile ist "löschen" eine
gleichwertige Option — evtl. die günstigere.

---

## Track D — Aufräumen (keine Löschung ohne pro-Modul-OK)

Reine Kandidatenliste. **Dieser Plan löscht nichts.** DEAD-009
(`services/storage_provenance/`) ist besonders heikel: gehört evtl. zur
laufenden OTK-021-Branch-Arbeit (Branch-Name = `source-consolidation`) →
one-way-door, erst recht nicht ohne explizite User-Freigabe.

- **Toter Code:** DEAD-003..008, DEAD-010..014 (~2.900 Zeilen). Pro Modul
  einzeln vom User freigeben.
- **Dead-End-Signals (UI):** WIRE-004..014 — geplante Cross-Tab-Navigation
  fehlt. Entscheidung: nachrüsten oder Signal entfernen.
- **DB-Ballast:** tote Tabellen DB-001/007/008/009/021, JSON-Doppel-
  Serialisierung DB-012, Index/Wachstum DB-018.
- **Doku-Drift:** `ui/mixins/` existiert nicht mehr (Controller-Komposition);
  CLAUDE.md/AGENTS.md-Beschreibung "8 Mixins" veraltet. Vault-`index.md`
  Zeile 137 = defekte 71k-Zeichen-Zeile.

---

## Nächster Schritt (User-Entscheidung nötig)

Vor Implementierung offen — siehe Consulting-Review Open Questions:
1. Crossfades gewünscht oder harte Beat-Cuts? (entscheidet A1)
2. Render-kritische Findings in aktiven SCHNITT-Plan integrieren, oder diesen
   Plan aktiv schalten? (R3)
3. Existiert betroffene Alt-DB? (entscheidet A3-Severity)
4. Welche Track-C-Neubauten sollen je live gehen?

Ohne diese Antworten bleibt der Plan `draft`. Empfohlene minimal-invasive
Reihenfolge, sobald freigegeben: A3 (isoliert, kein SCHNITT-Overlap) →
A1 → A2-Paket → Track B → Track C-Vorlage → Track D nach Einzelfreigabe.

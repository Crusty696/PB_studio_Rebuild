# PB Studio — Master-Konsolidierung Offene Tasks (2026-07-16)

> **plan_id:** `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16`
> **status:** `approved-for-implementation` (siehe Registry)
> **decision:** `wiki/decisions/D-071-master-offene-tasks-konsolidierung.md`
> **vault_mirror:** `wiki/synthesis/plan-master-offene-tasks-2026-07-16.md`
> **created:** 2026-07-16
> **Warum:** User-Auftrag 2026-07-16 — ALLE offenen Tasks aus ALLEN Plaenen +
> Vault-only-Punkte in EINEN Plan buendeln; die Original-Plaene per `superseded`
> schliessen. Dieser Plan ist ab jetzt die EINZIGE Quelle offener Arbeit.

## SCQA

- **S (Situation):** Offene Arbeit lag verteilt ueber 7 Registry-Plaene, 2 nicht-
  registrierte Plaene und 44 offene Vault-Bugs.
- **C (Complication):** Kein einzelner Ueberblick; Original-Plaene liessen sich nicht
  schliessen, weil je einzelne Rest-Punkte offen waren.
- **Q (Question):** Was ist wirklich noch offen, und wer muss es tun (Agent vs. User)?
- **A (Answer):** Der ueberwiegende Teil ist reine USER-Live-Sichtung + `fixed`-Marker
  (kein Agent-Code mehr). Echte Agent-Rest-Arbeit ist ueberschaubar und grossteils
  hinter User-Gates. Details in den Buckets unten.

## Governance

- `status: fixed` setzt **ausschliesslich der User** nach Live-Sichtung — nicht der Agent.
- Jede Task traegt ihren **Herkunfts-Plan** (`[HERKUNFT]`) fuer Rueckverfolgbarkeit.
- Die Original-Plaene sind in der Registry auf `superseded` gesetzt mit Verweis auf
  diesen Master. Ihr Task-Text bleibt als Historie erhalten (nicht geloescht).
- Reihenfolge/Gates: Bucket 3 (gated) erst nach den jeweiligen User-Gates
  (SCHNITT-`fixed`, Plan-1-Abschluss, Merge+User-OK).

---

## BUCKET 1 — Nur USER-Live-Sichtung + `fixed`-Marker (KEIN Agent-Code noetig)

Code fertig + committed/getestet. Es fehlt ausschliesslich die User-Live-Sichtung und
das Setzen des `fixed`-Markers.

### Aus Registry-Plaenen
- `[KONSOLIDIERUNG]` K1 (undo_commands→_run_timeline_write), K2 (STEM_NAMES eine Quelle),
  K3 (SigLIP-ID+EMBEDDING_DIM), K4 (subprocess_kwargs, 13 Dateien), K5 (Action-Factory
  audio_actions), K6-A (pacing-Engine ueber Fabrik), K7 (probe_duration+parse_frame_rate),
  K8 (QThread→run_worker, 4 Flows sichten), K9 (toter DB_DIR/DB_FILE-Monkey-Patch) — 9 Punkte.
- `[PERF-DB-CLEANUP]` E1-E10 (alle column-select/lazyload/ThreadPool-Fixes, backend-
  verifiziert + committed) — 10 Punkte, offen: reale GUI-Livepfade.
- `[TIMELINE-VIRT]` M4 (Live-GUI-Check lief bereits 7x per pb-gui-tester; nur User-`fixed`).
- `[AUDIT-FIXPLAN]` B8 / B-602 (Pipeline-Checkpoint projekt-relativ, live bestaetigt
  track2b 138 Segmente).
- `[OTK-MASTERPLAN]` OTK-021 (Global Storage-Provenance, live-evidence-pass, nur `fixed`).

### Aus Vault-Bugs (36 FIX-COMMITTED — Code fertig, nur `fixed` offen)
B-618, B-604, B-595, B-600, B-workspace-switch, B-646, B-635, B-642, B-629, B-628, B-622,
B-620, B-601, B-586, B-644, B-553, B-640, B-631, B-617, B-639, B-636, B-638, B-645, B-630,
B-633, B-625, B-626, B-624, B-623, B-619, B-522, B-521, B-641, B-494, B-550, B-621, B-627,
B-632, B-643, B-637.
(Hinweis: B-643/B-637/B-641/B-644 wurden im Discovery als "OFFEN-AGENT" gefuehrt, sind aber
faktisch bereits committed — daher hier. B-604/B-586 committed, aber im Bug-File als
unverifiziert markiert — User-Live-Verifikation empfohlen vor `fixed`.)

---

## BUCKET 2 — USER-Entscheidungen (one-way-door, NICHT agent-ausfuehrbar)

Brauchen eine Richtungsentscheidung des Users, bevor irgendein Code entstehen darf.
- `[CONSULTING-REVIEW]` D1: Brain v1/v2/v3-Deprecation-Strategie.
- `[CONSULTING-REVIEW]` D2: Vault-Sync-Strategie.
- `[CONSULTING-REVIEW]` D3: cu121/torch-2.x-Migration + requirements.txt (GPU-Hartregel beachten!).
- `[KONSOLIDIERUNG]` K6-B: `foreign_keys=ON` im Auto-Edit-Pfad — STOP+ASK, User entscheidet
  ob FK-Enforcement aktiviert wird; danach Agent-Code.
- `[AUFRAEUM-REFACTOR]` 8 explizite User-Entscheidungen: dist/-Umgang, IDE-Configs,
  DEAD-009, mood/energy-Formel, Migrationssysteme-Wahl, requirements-Dedup u.a.
- `[VAULT B-634]` Dialog-Anker Cyan-Marker-Rendering — vom User geparkt; User entscheidet
  ob wieder aufgenommen.

---

## BUCKET 3 — Agent-Code, HINTER User-Gates (erst nach Freigabe)

### AUDIT-FIXPLAN — hinter SCHNITT-`fixed`-Gate
- `[AUDIT]` A1: Crossfades verdrahten + UI-Schalter hart/weich (Default harte Cuts committed).
- `[AUDIT]` A2: V2-Default komplett (Classify+Waveform+sub_genre).
- `[AUDIT]` B5: Quellvideo-Szenenzeit vs. Timeline-Zeit klaeren.
- `[AUDIT]` B6: Media-Panel Re-Analyse kaputter Konstruktor.

### NEUBAUTEN-VOLLINTEGRATION — hinter Plan-1(AUDIT)-Abschluss-Gate
- `[NEUBAUTEN]` T1.1-T1.6: Studio-Brain-Pacing aktivieren, Brain-V3-Reranker im Cut-Pfad,
  SteerOverrideQueue-Consumer, RL-Stack v2 an Feedback, Lernschleife Patterns→Scorer,
  UI-Ehrlichkeit+Dead-End-Signals.
- `[NEUBAUTEN]` T2.1-T2.5: LLM-Pacing UI-schaltbar, audio.v2_default im Settings-Dialog,
  Timeline-Snapshots verdrahten, SetupWizard First-Run, Slice-1-Pacing 16 Module.
- `[NEUBAUTEN]` Paket3: DAG-Video-Engine vollintegrieren (PIPE-018/DEAD-008).

### AUFRAEUM-REFACTOR — hinter Merge+pro-Kategorie-User-OK
- `[AUFRAEUM]` A1 (Disk-Cleanup ~15GB, risikofrei), A2 (toter Code ~700 Z.), A3 (Doku),
  B1-B4 (Refactors).

---

## BUCKET 4 — Agent-Code, FREI ausfuehrbar (kein Gate)

- `[AUDIT]` A3: Migration `beatgrids.stem_weighted_energy` (praeventiv, sofort erlaubt).
- `[AUDIT]` B1: SigLIP-Ausfall sichtbar/degradiert kennzeichnen.
- `[AUDIT]` B2: Beat-Analyse-Fehler sichtbar + Fallback markieren.
- `[AUDIT]` B3: Stille GPU→CPU-Weichen sichtbar/robust.
- `[AUDIT]` B4: V2-Worker schreibt `analysis_status`.
- `[AUDIT]` B7: `init_db` schluckt Alembic-Fehler → Fail-fast-Guard.
- `[AUDIT]` B9 / B-603: Crossfade-Export-Skalierung (0 Frames) reparieren (auf erstes Update
  terminiert, aber machbar).
- `[PERF-DB-CLEANUP]` D-069: Voll-Package-/Installed-App-Test durchfuehren.
- `[FREEZE-CRASH-SANIERUNG]` ab_compare AudioTrack Rest-Freeze (F1-Teil).
- `[FREEZE-CRASH-SANIERUNG]` F6 / B-618-Rest (Frozen-Warmup, mit Tier R).

---

## BUCKET 5 — Release / Packaging (Agent-Build + User-Abnahme)

- `[FREEZE-CRASH-SANIERUNG]` Tier R (R1-R4): Frozen-Rebuild + Signieren + Clean-VM-Test +
  Release-Gate-Hash.
- `[OTK-MASTERPLAN]` OTK-019: Video-Pipeline schwerer 4h-Live-Gate (DG-001, aufgeschoben).
- `[OTK-MASTERPLAN]` OTK-008: SCHNITT Phase-12 formale Live-Verify — BLOCKIERT: formales
  Dataset fehlt (Crusty-Mix weg, Solo_Natur 124≠103). Braucht Dataset + User-Live.

---

## BUCKET 6 — Sackgassen (keine autonome Diagnose ohne neue Daten)

- `[VAULT B-605]` python.exe QThread::finished Null-Ptr-Crash. Root-Cause-KLASSE 2026-07-16
  identifiziert (Lambda-ohne-Receiver), 1 latente Instanz gefixt (Commit 9b1d5a5,
  model_manager_dialog). Zweite Instanz stem_workspace.py:293 notiert. Original-Dump ohne
  Python-Frames → nicht beweisbar welche Stelle. Weiter nur mit neuem Crash-Beleg.
- `[VAULT B-615]` Self-Close ohne Save-Prompt. Code-Pfad 2026-07-16 live bewiesen korrekt;
  Original-Vorfall bleibt ungeklaerter Einzelfall. Weiter nur mit neuem Vorfall.
- `[VAULT B-592]` B-570-Shutdown-Child-Timeout dGPU-Wait. Weiter nur mit neuem Beleg.

---

## BUCKET 7 — UNKLAR (Bug-File-Abgleich noetig, bevor eingeordnet)

Diese 3 nicht-registrierten Alt-Plaene sind laut Discovery nicht abschliessend als
offen-oder-erledigt entscheidbar ohne Abgleich mit den zugehoerigen Bug-Files:
- `[b469-native-crash-2026-06-03]` B-469 (native Crash) — Status via `wiki/bugs/B-469-*`
  pruefen.
- `[timeline-quality-2026-06-03]` B-472/473/474/475 (Thumbnail-Rendering/Optik) —
  ueberlappt stark mit TIMELINE-VIRT + B471-Recovery; Einzelstatus pruefen.
- `[brain-ui-tooltip-2026-05-09]` Tooltips fuer Brain-V3-Widgets (Task 1-9) — ob real
  gesetzt, nicht aus Plan ableitbar.

Naechster Schritt fuer Bucket 7: je Plan die referenzierten Bug-Files lesen, dann in
Bucket 1/4/6 einsortieren oder als erledigt schliessen.

---

## Herkunfts-Plaene (jetzt `superseded`, siehe Registry)

`PB-STUDIO-KONSOLIDIERUNG-2026-07-12`, `PB-STUDIO-PERF-DB-CLEANUP-2026-07-12`,
`PB-STUDIO-TIMELINE-VIRTUALISIERUNG-2026-07-10`, `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`,
`PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`, `PB-STUDIO-CONSULTING-REVIEW-FIXPLAN-2026-06-12`,
`PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`, `FREEZE-CRASH-SANIERUNG-KONSOLIDIERT-2026-07-14`,
`AUFRAEUM-REFACTOR-2026-07-08`.

`PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07` ist bereits `fixed` — nicht Teil dieser
Konsolidierung. Tote Plaene (source-consolidation, full-app-green, studio-brain-*) ohne
offene Tasks — kein Transfer noetig.

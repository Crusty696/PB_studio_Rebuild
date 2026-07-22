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
- ~~`[NEUBAUTEN]` Paket3: DAG-Video-Engine vollintegrieren (PIPE-018/DEAD-008).~~
  **ENTFALLEN (User-Entscheidung 2026-07-17):** `services/video_pipeline/` als
  dormant Parallel-Engine komplett geloescht (Cleanup-Audit); Monolith-Pfad ist
  der bewiesene Produktivpfad. Wiederherstellbar via Git-Historie.

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
- `[BRAIN-TOOLTIP]` (aus Bucket 7 aufgeloest) Tooltips fuer die noch-live Alt-Brain-V3-
  Widgets `brain_v3_feedback_popup.py` (live via Timeline-Clip-Kontextmenu) +
  `brain_v3_learning_dialog.py` nachziehen (0 `setToolTip`). Low-prio UI-Polish,
  kein Logik-Risiko. studio_brain-Tabs haben bereits Tooltips.
- `[VAULT B-650]` (Live-Test 2026-07-17) LLM pro Aufgabe sichtbar machen: die
  per-Task-LLM-Aufrufe (`pacing_strategist._generate`, `ai_actions`) umgehen den
  `OllamaService` und melden nie Modell/Task ans `ModelStatusField`. Fix: an jeder
  Aufrufstelle `_emit_model_status(model, task)` (oder gemeinsamer run_llm-Wrapper).
  Reine Status-/UI-Meldung, keine GPU-Regel-Beruehrung. User wuenscht das seit langem.

---

## BUCKET 5 — Release / Packaging (Agent-Build + User-Abnahme)

- `[FREEZE-CRASH-SANIERUNG]` Tier R (R1-R4): Frozen-Rebuild + Signieren + Clean-VM-Test +
  Release-Gate-Hash.
- ~~`[OTK-MASTERPLAN]` OTK-019: Video-Pipeline schwerer 4h-Live-Gate (DG-001, aufgeschoben).~~
  **ENTFALLEN (User-Entscheidung 2026-07-17):** bezog sich auf die geloeschte
  DAG-Engine (siehe Paket3-Vermerk).
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
- `[b469-native-crash-2026-06-03 / VAULT B-469]` (aus Bucket 7 aufgeloest) Native
  Qt6Core-Crash bei parallelem Media-DB-Reload nach Doppel-Import. Bug-File-Status
  `parked-not-reproducible-monitoring` — nicht reproduzierbar, unter Beobachtung.
  Weiter nur mit neuem Repro/Crash-Beleg.

---

## BUCKET 7 — AUFGELOEST 2026-07-16 (Bug-File-/Code-Abgleich durchgefuehrt)

Die 3 unklaren Alt-Plaene wurden per Bug-File- und Code-Abgleich eingeordnet; die Plaene
sind jetzt ebenfalls `superseded`. Ergebnis:

- `[b469-native-crash-2026-06-03]` → B-469 Bug-File-Status = `parked-not-reproducible-
  monitoring`. Native Qt6Core-Crash bei parallelem Media-DB-Reload nach Doppel-Import,
  nicht reproduzierbar, unter Beobachtung. → **verschoben nach Bucket 6 (Sackgassen/parked)**.
- `[timeline-quality-2026-06-03]` → alle referenzierten Bugs erledigt: B-471 `fixed`,
  B-472 `fixed`, B-473 `fixed`, B-475 `fixed`, B-474 `cannot-reproduce`. → **KOMPLETT
  ERLEDIGT, keine offene Task** (Plan geschlossen).
- `[brain-ui-tooltip-2026-05-09]` → Teil-erledigt/teil-superseded: die Brain-UI wurde
  spaeter zu `ui/studio_brain/`-Tabs umgebaut (audit/graph/inspector/memory/stats/steer/
  structure — DIESE haben bereits `setToolTip`). Der Plan zielte aber auf die aelteren
  Widgets; davon sind `brain_v3_feedback_popup.py` (live via Timeline-Clip-Kontextmenu,
  `ui/timeline.py`) und `brain_v3_learning_dialog.py` weiterhin OHNE Tooltips (0
  `setToolTip`). → **verschoben nach Bucket 4 (Agent-frei, low-prio):**
  `[BRAIN-TOOLTIP]` Tooltips fuer die noch-live Alt-Brain-V3-Widgets
  (brain_v3_feedback_popup + brain_v3_learning_dialog) nachziehen. Kleine reine
  UI-Polish-Aufgabe, kein Logik-Risiko.

Bucket 7 ist damit leer — nichts mehr unklar.

---

## Herkunfts-Plaene (jetzt `superseded`, siehe Registry)

`PB-STUDIO-KONSOLIDIERUNG-2026-07-12`, `PB-STUDIO-PERF-DB-CLEANUP-2026-07-12`,
`PB-STUDIO-TIMELINE-VIRTUALISIERUNG-2026-07-10`, `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`,
`PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`, `PB-STUDIO-CONSULTING-REVIEW-FIXPLAN-2026-06-12`,
`PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`, `FREEZE-CRASH-SANIERUNG-KONSOLIDIERT-2026-07-14`,
`AUFRAEUM-REFACTOR-2026-07-08`.

Aus der Bucket-7-Aufloesung (2026-07-16) zusaetzlich `superseded`:
`B469-NATIVE-CRASH-FIX-2026-06-03` (B-469 parked → Bucket 6),
`TIMELINE-QUALITY-FIX-2026-06-03` (komplett erledigt, alle Bugs fixed/cannot-reproduce),
`BRAIN-UI-TOOLTIP-COVERAGE-2026-05-09` (Rest-Tooltips → Bucket 4).

`PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07` ist bereits `fixed` — nicht Teil dieser
Konsolidierung. Tote Plaene (source-consolidation, full-app-green, studio-brain-*) ohne
offene Tasks — kein Transfer noetig.

---

## Bucket-4-Abarbeitung 2026-07-18 (Autonom-Lauf)

Recon (10 Parallel-Agents) + Umsetzung. A3/B1/B3/B4/B9 waren bereits code-complete
(8902291+ee0b1bb / 1a38460 / 83ab433 / a930468 / 035a841) — Eintraege oben teils stale.
Rest-Arbeit committed: B7-Fresh-DB-Fail-fast (318fb39), B2-Rest librosa-Fallback
sichtbar + degraded_reason (3a89ebf), ab_compare defer onset_strength_curve (0eeecdb),
Brain-Tooltips + Audit-Test (29053a3), B-650-Rest Chat-Status + Router (f7cb757).
Batch-Test 22+6 passed. Alle unverified — Live-Sichtung + `fixed` = User.
Blockiert geblieben: D-069 + F6/B-618-Rest (User-Anweisung 2026-07-17: keine
Installer-Builds). Offene User-Frage: librosa-Fallback-Grid downstream als degraded
werten (B2-Punkt 3, Semantik).

### Nachtrag 2026-07-18: D-069 + F6 nachgeholt (User-Klarstellung No-Install-Regel)

User-Klarstellung: Regel 2026-07-17 verbietet nur die INSTALLATION von PB Studio
auf dem User-Rechner, nicht Builds/Package-Tests. Daher nachgeholt:
- Voll-Installer-Build Exit 0 (PyInstaller + NSISBI): dist/pb_studio 5.52 GB
  smoke passed; pb_studio_setup_v0.5.0.exe 424.507 B; .nsisbin 2.817.446.413 B.
  Log: test-report/installer-build-20260718.log.
- D-069 PASS: Frozen _internal/bin ffmpeg/ffprobe SHA256 exakt auf Manifest-Pins.
- Frozen-GUI-Live PASS: verify_frozen_gui_workflow.py Exit 0, status=pass,
  Fenster responsiv, 74 UIA-Labels, 4 Workflow-Gruppen, Prozess stabil.
- F6/B-618-Rest: war bereits an der Wurzel geloest (4ef48e3 + 2e0e739: Fit im
  Kind-Prozess statt nutzlosem Frozen-Warmup, 79s-Messung 2026-07-15). Code im
  neuen Build enthalten. EHRLICH OFFEN: Live-Enrichment-Lauf IM Frozen-Build
  (F6-Endbeweis) + Installed-App-Test — Installation nur ausserhalb User-Host
  (Sandbox/VM) bzw. auf User-Anweisung. Installer ist unsigniert (Tier R offen).

### Nachtrag 2026-07-18 (2): F6-Endbeweis PASS
Frozen pb_studio.exe im PB_CLUSTER_FIT-Modus (realer Kind-Prozess-Pfad aus
_fit_subprocess): Exit 0 in 67.4 s (inkl. Numba-JIT), ClusterResult korrekt
(200 Samples, 3/3 Cluster ohne Noise, centroids (3,10), UMAP-Reducer
pickleable, degraded=False). F6/B-618-Rest damit live bewiesen. Offen: nur
GUI-E2E-Enrichment mit echten SigLIP-Embeddings (User-Sichtung) und Tier R.

### Nachtrag 2026-07-19: Bucket 2 komplett entschieden + umgesetzt (D-073)

User-Entscheidungsrunde E1-E6 (Zug um Zug, Vorlage: synthesis/
bucket2-entscheidungsvorlage-2026-07-19.md, Vault: D-073):
- E1 Brain-Deprecation: Usage-Check ergab NICHTS zu loeschen (Kandidaten waren
  brain_v3-Spike, bereits weg; legacy_sqlite.py LIVE via BrainService). Erledigt.
- E2 Vault-Sync = D-064 Opt. 1 (GitHub privat). Wartet auf User-Repo.
- E3 torch-2.x aufgeschoben; requirements.txt -> docs/archive/ (accfdf5).
- E4/K6-B FK-ON aktiviert nach 7/7-PASS-Paritaets-Test (1f1b44f).
- E5: dist/ geloescht (8,1 GB), IDE-Configs weg (e52dfe4), DEAD-009 zu (c98496a),
  Doku konsolidiert (5b93085); 5.4 mood/energy + 5.5 Migrationssysteme GEPARKT.
- E6 B-634-Marker bleibt geparkt.
Bucket 2 damit leer bis auf E2-User-Schritt; 5.4/5.5 als geparkt dokumentiert.

### Nachtrag 2026-07-22: Bucket 3 komplett freigegeben (D-074) + Recon + Safe-Slice

User David 2026-07-22: "B, ich gebe alles frei." Alle drei Bucket-3-Gates offen
(D-074). Recon-Fan-out (3 read-only Agents, Lesson 77583af9 already-done-Check):

- **AUDIT** A1/A2/B6 = code-complete auf main (nur User-`fixed`). B5 Restluecke =
  fehlende Zeit-Semantik-Doku am Scene-Modell -> GESCHLOSSEN (Commit a881e9f,
  Kommentar an `database/models.py` Scene.start_time/end_time: quellvideo-relativ).
  **AUDIT-Bucket damit vollstaendig code-seitig.**
- **NEUBAUTEN** T1.1-T1.6 + T2.1-T2.5 = ALLE code-complete auf main (Ancestor-
  Pruefung + Live-grep der Verdrahtung). Kein Agent-Code offen, nur User-`fixed`.
  Einschraenkung: reine Code-Praesenz-Verifikation, keine Laufzeit-Verifikation.
- **AUFRAEUM** (User-Entscheidung 2026-07-22): B1/B2/B4 God-Object-Splits
  AUFGESCHOBEN bis nach Release-Live-Verify (Regressionsrisiko an working +
  seit Plan GEWACHSENEM Code: timeline.py 4125, main.py 2203, export_service.py
  2070). Safe-Slice umgesetzt:
  - A1 Disk-Cleanup: build/ (145 MB) + .pytest_cache + 107 __pycache__ geloescht
    (gitignored/untracked). logs/ (freeze_stacks-Evidenz), test-report/,
    outputs/test-tabelle/ (Live-Test heute), storage/ BEWUSST behalten. Real
    ~145 MB (die "15 GB" waren dist/, laengst weg).
  - A3 Doku (Commit 49d297d): 4 tote Alt-Plaene -> docs/superpowers/archive/,
    6 datierte Diagnose-Reports -> docs/archive/ (git mv, History erhalten).
  - A2/A4/DEAD-009 waren bereits erledigt (Recon bestaetigt).
  - B3 Util-Dedup: User-Entscheidung "spaeter" (fasst working code an).
  - A3-Rest offen (Content-Risiko/unscharf): module-map-Dedup (beschreibt
    geloeschte Mixin-Architektur), synthesis/-Split (98 Dateien), Grenzfall-
    Reports (HANDOVER/PHASE4/Architektur_Bericht).

**Bucket-3-Restlage:** kein frei-ausfuehrbarer Agent-Code mehr offen. B1/B2/B4 +
B3 warten bewusst (User-Entscheidung). Rest = User-Live-Sichtung + `fixed`.

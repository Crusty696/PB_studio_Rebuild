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

## Nachtrag 2026-07-22 08:11: Live-Verify test-tabelle -> User-fixed

User-Freigabe "alle live-verifizierten fixed" nach GUI-Live-Sichtung (App PID 5164,
tests/gui_harness.py, Projekt test-tabelle, keine destruktiven Eingriffe). Folgende
Tasks vom User als **fixed** bestaetigt (sichtbarer Screenshot-Beleg in
tests/qa_artifacts/):

- A1 (Crossfade-Schalter): Combo "Uebergaenge" beide Optionen, Default Harte Beat-Cuts.
- A2 (V2-Default Classify+Waveform): Audio-Status Waveform 4000 samples + Mood/Genre
  dark/House im Default-Lauf.
- B1 (SigLIP sichtbar): Visual Embeddings dimension:1152.
- B4 (analysis_status): 9/9-Video- + 8/10-Audio-Status-Tabelle pro Clip.
- B6 (Media-Re-Analyse): Per-Schritt "Wiederholen"-Buttons + "Alle Fehler wiederholen".
- T1.1 (Studio-Brain-Pacing): Checkbox aktiv.
- T1.4/T1.5 (RL-Feedback + Lernschleife): RL-Notes Gut/Schlecht + Brain-V3-Lernstatus
  187 Klicks / 18 Brain-Achsen / Feedback heute / Buckets gefuellt.
- T2.1 (LLM-Pacing schaltbar): LLM-Strategist/LLM-EDL-Toggles.
- T2.2 (audio.v2_default Settings): Checkbox "Audio-Analyse V2 als Standard".
- T2.3 (Timeline-Snapshots): Snapshots-Control in Timeline-Leiste.
- T2.5.6 (ab_runner): "A/B-Gewichte testen"-Button.
- M4 (Timeline/Auto-Edit): 94 Cuts, Waveform, Thumbnails, Export-Timeline 337.1s.
- B-650 (Bug): Model-Status pro Aufgabe sichtbar (phi3:mini/Chat) -> Bug-File fixed.
- Zusatz: B-620/B-619/B-634 waren bereits fixed (bestaetigt).

NICHT als fixed markiert (nicht einzeln live-gesichtet, bleiben code-complete-pending):
T1.2 (Brain-V3-Reranker), T1.3 (SteerOverrideQueue-Consumer), T1.6 (UI-Ehrlichkeit,
nur teilweise via CPU-Status), T2.4 (SetupWizard First-Run - braucht First-Run-Reset),
T2.5.1-T2.5.5 (Slice-Module - Backend). Ebenso offen: B9 (Crossfade-Export-0-Frames,
geparkt), B5 (nur Code-Doku), Backend E1-E10/K1-K9 (nur indirekt belegt).

### Nachtrag 2026-07-22 09:29: T1.2 + T1.6 live-verifiziert -> User-fixed

Fortsetzung Live-Sichtung (test-tabelle). User-Freigabe "T1.2 + T1.6 fixed":
- T1.2 Brain-V3-Reranker im Cut-Pfad: Log frischer Auto-Edit-Lauf (LLM off)
  "T1.2: Brain-V3-Reranker aktiv (min_confidence=0.00) — WeightStore wirkt im
  Schnitt", "Phase 3: 94 Segmente/94 CutPoints", "Timeline: 94 Video-Segmente
  geschrieben". Timeline gespeichert.
- T1.6 UI-Ehrlichkeit + Dead-End-Signals: Studio-Brain Audit-Tab, pro-Cut
  Score/Verdict/Alternativen (Top 3)/Term-Beitraege/Budget-Stand, Filter
  "Nur abgelehnte"/"Nur Fallback".
Damit zusaetzlich fixed neben dem Batch von 08:11. T1.3 (SteerTab gebaut,
Consumer im Pfad; keine Override in Queue) + T2.5.5 (Shot-Klassen) live gesehen,
aber vom User (noch) nicht als fixed markiert.
NEU offen: Bug B-666 (LLM-Strategist-Pacing-Hang, high). Rest-Tests: B9, T2.4.

### Nachtrag 2026-07-22 09:58: T2.4 + B9 live-verifiziert -> User-fixed

User-Freigabe "T2.4 + B9 fixed" nach Live-Test test-tabelle:
- T2.4 SetupWizard First-Run: setup_complete=false -> Wizard "PB Studio —
  Ersteinrichtung" + Log "First-Run erkannt — SetupWizard startet (T2.4)";
  =true -> kein Wizard. Beide Richtungen bestaetigt, Registry wiederhergestellt.
- B9/B-603 Crossfade-Export: 0-Frames verhindert (ffprobe 10105 Frames, 337.11s,
  valides Video). Bug-File B-603 status:fixed. Rest-Befund: Batch-xfade scheitert
  bei 94 Seg -> Hard-Cut-Fallback (echte Crossfades rendern nicht) - als
  Folge-Verbesserung dokumentiert, kein eigenes Bug-File (User-Entscheid).
Damit alle vom User beauftragten Live-Tests abgeschlossen. Offener neuer Bug:
B-666 (LLM-Strategist-Pacing-Hang, high). Test-Artefakt output.mp4 (749MB) geloescht.

## Nachtrag 2026-07-27: D-075 Claude-Restwelle

User-Auftrag: alle offenen/angefangenen Claude-Code-Tasks abschliessen;
Pacing, Brain-V3, automatisches Lernen und Zugriff aller LLM-Pfade zuerst.
Decision: Vault `D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md`.

### Verbindliche Reihenfolge

1. **R0 Governance-Reconciliation — abgeschlossen in dieser Doku-Welle**
   - B-730 fehlendes Pattern-Prior-Bugfile angelegt.
   - B-731 korrigiert fachfremde Wiederverwendung der belegten ID B-707.
   - B-732 bis B-738 erfassen die Pacing-/Brain-/Lern-/LLM-Restluecken.
   - B-709 bis B-729 gegen Git abgeglichen; Statusdrift bleibt pro Bugfile
     nachzuziehen, aber kein `fixed` ohne Live/User.
2. **R1 / B-727 — ERSTE naechste Code-Task, P0**
   - `tests/conftest.py:_guarded_connect(database, ...)` shadowt das importierte
     Modul. `database.engine` im Fehlertext wirft `AttributeError`; der breite
     `except Exception` schluckt ihn; reale DB-Verbindung wird nicht blockiert.
   - Zuerst RED-Test: Realpfad muss `RuntimeError` liefern und
     `original_connect` 0-mal aufrufen.
   - Danach Fokus-/Subprozess-Test plus SHA/Laenge/mtime aller kanonischen
     `pb_studio.db`; erst dann CI-identische Vollsuite.
3. **R2 / B-732 — BrainV3Service Credit-Passthrough**
   - `FeedbackRequest.axis_contributions` an Logger durchreichen; Diagnostik
     (`credit_mode`, `n_axes_credited`) vollständig zurückgeben.
4. **R3 / B-733 — LearningDialog echter Context + Credit**
   - Sample-Vertrag, Resolver und Dialog mit realem CutContext und
     Contributions aus Decision/Rationale.
5. **R4 / B-734 — Visual-Metriken in Ranking konsumieren**
   - `struct_clip_tags` → Loader → ClipFeatures → ClipCandidate; NULL bleibt
     no-signal; Score-Varianz beweisen.
6. **R5 / B-737 — Automatisches Lernen garantiert flushen**
   - Run-/Projekt-/App-End-Flush; Brain-Feedback bewusst ans Pattern-Lernen;
     1 Feedback muss nach Neustart als `mem_learned_pattern` bestehen.
7. **R6 / B-738 — Brain/Memory fuer alle LLM-Pfade**
   - Tool- und Non-Tool-Chat, `ask_ai`, PacingStrategist/direkter Pacing-Pfad
     erhalten projektisolierten Recall-/Context-Zugriff.
   - Phi3/Gemma-Familien sind aktuell `NO-TOOLS`; 5a0ac3c allein reicht nicht.
8. **R7 / B-735 + B-736 — Brain-Rollenwirkung + Stub-Servicepfad**
   - Role-Mapping bewusst entscheiden/verdrahten; synthetische
     `BrainV3Service`-Kandidaten durch echten Produktpfad ersetzen oder Stub
     aus Produktfluss entfernen.
9. **R8 — Produkt-Live-Wirkungsbeweis**
   - Auto-Edit → Feedback → Flush/Lernen → zweiter Auto-Edit.
   - Beweis: variable Achsgewichte/Patterns und geänderte Kandidatenreihenfolge;
     App/Logs/DB, nicht nur Standalone.
10. **R9 — restliche B-709…B-729**
    - Priorität: B-710/711/712/718/720/722/723/725, dann B-713…726.
    - Bereits code-seitig vorhanden, live-pending: B-709 (`62108eb`),
      B-716 (`7c77243`/`0f0c948`), B-728 (`0574240`), B-729
      (`a84a880`/`42948e1`).

### Handoff-Grenzen

- Genau eine Task zur Zeit. Nächste Task ist ausschließlich R1/B-727.
- Keine Vollsuite vor wirksamem B-727-Guard-Regressionstest.
- Kein `fixed` ohne Live-Workflow + Userfreigabe.
- Ollama war beim Recon nicht erreichbar; B-738-Livebeweis wartet auf Dienst.

## Nachtrag 2026-07-28: D-077 risikobasiertes Minimaltestprogramm

Userentscheidung: Testaufwand auf Minimum reduzieren, sofern Stabilitätsaussage
nicht beeinträchtigt wird. D-077 ersetzt ausschließlich quantitative
Wiederholungen aus D-076:

- Keine wiederholten Review-/Fokustest-Runden nach grünem Root-Cause-Test.
- Eine Current-Vollsuite mit vollständigem DB-vor/nach-Beweis.
- Acht Kernworkflows je einmal in einer gemeinsamen isolierten Live-Session.
- Ein gezielter GPU-/Race-Kombinationszyklus plus 30-Minuten-Soak statt drei
  Zyklen plus vier Stunden.
- Kein separater finaler Vollsuitenlauf, sofern seit STAB-1 kein Produktcode
  geändert wurde. Nach Produktcodeänderungen genau ein finaler Current-Lauf.
- Frozen-, Installer- und Clean-VM-Smoke je einmal. Keine Wiederholung ohne
  konkreten Fehler oder geändertes Artefakt.
- DB-Isolation, B-727-Negativkontrollen, echte Livepfade, Brain-A/B,
  Cancel-/Shutdown-Races, Clean-VM und User-Endabnahme bleiben Pflicht.

Ein Fehler stoppt weiterhin das nächste Gate. Nur betroffener Fokus- und
angrenzender Regressionstest werden nach Fix wiederholt.

## Nachtrag 2026-07-28: D-078 breite Tests bis Fixabschluss verschoben

Userentscheidung: Während übriger Fix-/Auditarbeit nur absolut notwendige
Tests. Breite Verifikation wird gesammelt nach Abschluss dieser Arbeit
ausgeführt.

- Pro Produktcode-Fix nur kleinster zwingender RED-/Fokuscheck des konkreten
  Root Cause sowie Syntax/Import der geänderten Produktdatei.
- Keine wiederholten Varianten, angrenzenden Sweeps oder Suites nach identisch
  grünem Beleg.
- Current-Vollsuite, acht Live-Workflows, Brain-A/B, GPU-/Thread-/Soak,
  UI-Klickaudit sowie Frozen-/Installer-/Clean-VM-Gates ans Ende verschoben.
- Alle Codefixes bleiben bis diesen Endgates
  `code-fix-pending-live-verification`; kein `fixed`.
- D-077 definiert weiter den minimalen Endumfang; D-078 ändert Zeitpunkt.

## Nachtrag 2026-07-27: D-076 Current-HEAD-Stabilitätsprogramm

Userentscheidung: bestehende Funktionen vor weiterer Entwicklung vollständig
stabilisieren. Feature-Freeze aktiv. Bestehender Masterplan bleibt einzige
Planquelle. Baseline ist `02cddee9e7e8dd50d1d45fdb67fc930de834805b`.

### Stabilitätsziel

- Null bekannte Critical-/High-Fehler.
- Null nutzer- oder kernpfadwirksame Medium-Fehler.
- Sichtbare Funktion funktioniert, ist deaktiviert oder ehrlich als nicht
  verfügbar markiert.
- Eine Current-Vollsuite ohne Änderung realer DBs.
- Acht Current-Live-Kernworkflows, Brain-Lern-A/B, GPU-/Thread-Stress,
  Current-Installer in sauberer VM und User-Endabnahme bestanden.
- Technische Low-Befunde ohne Nutzerwirkung dürfen begründet offen bleiben.
- Razor, sichtbarer Playhead, Timeline-Preview und andere fehlende Features
  bleiben separater Entwicklungsbacklog.

### Verbindliche Reihenfolge

#### STAB-0 — Governance-Reconciliation

- Noch kein Produktcode.
- B-709 bis B-738: Status, Commits, Produktpfade, RED/GREEN/Regression,
  Livebeleg, Current-Reproduktion, Zielstatus und Restnachweis erfassen.
- Commit + Fokus ohne Livepfad:
  `code-fix-pending-live-verification`.
- Current reproduzierbar: `open`.
- Historisch/doppelt: `superseded` mit kanonischem Ziel.
- `fixed` nie ohne Livebeweis + Usermarker ändern.
- B-715, B-723, B-725 und B-726 ausdrücklich neu untersuchen.
- Bug-IDs vaultweit eindeutig machen; keine Datei löschen.
- Gate: Git, Plan, Registry, Active Plan, Vault-Mirror, Bugfiles und Handoff
  synchron; genau nächste Task `STAB-1 / B-727 Vertrauensgate`.

#### STAB-1 — Testfundament und DB-Isolation

- Reproduzierbares JSON-Evidenzmanifest mit Run, Commit, Phase, exaktem
  Befehl, Zeiten, Exitcode, Prozessstatus, DB-vor/nach, Artefakten, Logs,
  Verdict und Grenzen.
- DB-/WAL-/SHM-SHA, Größe, `quick_check`, Migration-Head, Tabellenzählungen
  und logischen Inhalts-Hash erfassen.
- Repo-, Output-, Recent-Project-, AppData-Brain-/Memory- und registrierte
  Projekt-DBs einbeziehen.
- Backups ausschließlich extern unter
  `%LOCALAPPDATA%\PBStudioStability\<run_id>\backups`.
- B-727-Negativkontrollen: beide SQLite-Connect-Pfade, 0 Originalcalls,
  Collection, Kindprozess, APP_ROOT/Projektwechsel blockiert; Temp-DB erlaubt;
  bewusst deaktivierte Kontrolle beweist Gefährdung.
- Danach Import/Syntax, Ruff, Alembic Single-Head/Fresh-Upgrade,
  B-727-Fokus und CI-identische Suite einmal in frischer Session.
- Erster Fehler stoppt Gate und eröffnet genau eine Root-Cause-Task.
- Gate: Current-Vollsuite grün, reale DBs byte-/inhaltsidentisch, kein nativer
  Crash, keine unbekannten Seiteneffekte.

#### STAB-2 — Acht Current-Live-Kernworkflows

Ein gemeinsames isoliertes Projekt für die acht einmaligen Workflows unter
`%LOCALAPPDATA%\PBStudioStability\<run_id>\project`; Kopien von zwei
Test-Audios und 20 Repo-Clips. Originale bleiben unangetastet.

1. Boot, neues/bestehendes Projekt, dreifacher Wechsel, Shutdown, Neustart.
2. Import, Duplikat, Papierkorb, Restore, Reimport, Bulk, Cross-Project-Reuse.
3. Audio V2 komplett, Cancel während AV-Pacing, Retry, Neustart, fehlendes Stem.
4. Videoanalyse mit SceneDetect, RAFT, Keyframes, SigLIP, VLM, defektem Clip
   und Reanalyse mit/ohne Ersatz.
5. SCHNITT/Timeline: Preview/Seek, Move/Trim/Lock/Anchor, Undo/Redo,
   Projektwechsel und Rückkehr.
6. Auto-Edit/Pacing mit fixen Eingaben, flacher/benutzerdefinierter Kurve,
   LLM und Brain jeweils aus/an.
7. Export Hard-Cut/xfade, 8-/10-bit, alle Presets, Cancel/Retry; ffprobe prüft
   Dauer, Frames, Audio und Seek.
8. Persistenz/Shutdown ohne und mit laufenden Audio-/Video-/Exporttasks.

Jeder Workflow braucht Screenshot, Logauszug, DB-Diff und JSON-Verdict.
Fehler einzeln schließen, bevor nächster Workflow startet.

#### STAB-3 — Brain, Pacing und Lernen

- Medien, Seed, Settings und Modellversion fixieren.
- Auto-Edit A inklusive Rangfolge, 18 Brain-Achsen, Pacing, Pattern und Gewichten.
- Negativkontrolle ohne Feedback muss deterministisch bleiben.
- Gezieltes positives/negatives Feedback, Flush, kompletter App-Neustart.
- Persistenz und `mem_learned_pattern > 0` prüfen.
- Auto-Edit B mit identischen Eingaben; erklärbare Änderung nur adressierter
  Beiträge und Kandidatenrangfolge beweisen.
- Tool- und Non-Tool-LLM-Pfade müssen Recall/Stats/Explain/Learn erhalten.

#### STAB-4 — GPU, Threads, Prozesse, Langlauf

- Sequenziell B-723, B-725, B-726, Ollama-Prozessbesitz und
  Shutdown-/Cancel-/Projektwechsel-Races.
- Jeder Fix: erzwungenes Interleaving, rote Fehlerkontrolle, grüne Korrektur,
  Lock-Ordering und echter Produktpfad.
- Ein gezielter Kombinationszyklus Audio, Video, Ollama, Preview, Export,
  Cancel, Projektwechsel, Shutdown; danach 30-Minuten-Soak.
- Alle fünf Sekunden VRAM, RAM, Prozessbaum, Threads, Taskstatus,
  UI-Heartbeat, DB und Lockzeiten erfassen.
- Gate: kein Hang/Crash/Lock-Inversion/Zombie; UI-Block höchstens 2 s;
  Progress spätestens 10 s; Threads Baseline +5; VRAM nach 60 s höchstens
  Baseline +512 MiB; DB konsistent.

#### STAB-5 — UI-Ehrlichkeit

- Buttons, Menüs, QActions, Shortcuts, Chat-Actions, Analyse-/Fortschrittsstatus,
  Presets und Tooltips inventarisieren.
- Je Element Aktion, Handler/Worker, Zustandsänderung, Erfolg, Fehler/Cancel und
  Testbeleg dokumentieren.
- Kein sichtbarer Erfolgs-No-Op, erfundener Shortcut, 100 % bei degraded/error,
  Label-only-Preset oder unsichtbar weiterlaufendes Cancel.
- Fehlende Features deaktivieren/kennzeichnen, nicht neu entwickeln.

#### STAB-6 — Current Release-Kette

- Erst nach STAB-0 bis STAB-5.
- Final-Vollsuite genau einmal nur, wenn seit STAB-1 Produktcode geändert wurde.
- `installer\build_installer.bat` ohne `PB_SKIP_PYINSTALLER`.
- Smoke, FFmpeg/ffprobe-Identität, Frozen-GUI, Installer + NSISBI-Payload,
  Artefaktpaar, Evidence-Matrix, Release-Gate, ZIP + SHA256SUMS.
- Je ein Durchlauf. Saubere Windows-VM: Installation, Installed-App-Kernworkflow,
  Deinstallation/Rückstände.
- Alle Belege an exakt denselben Commit und Artefakt-SHA binden.
- Keine Releasefreigabe vor User-Endabnahme.

#### STAB-7 — Abschluss

- Matrix je Bereich: Code-Fix, Fokus, Regression, Live, Stress, Release,
  Usermarker.
- Git, Masterplan, Vault und Bugs final synchronisieren.
- Keine Critical/High oder nutzer-/kernpfadwirksame Medium offen.
- Low-Risiken begründen; fehlende Features separat halten.
- Abnahmebericht mit Screenshots, Logs, DB-Diffs, ffprobe, GPU-/Soak-Daten und
  Installer-Hashes.
- `fixed`/„Stabilisierung abgeschlossen“ erst nach Userbestätigung.

### Arbeits- und Freigaberegeln

- Genau eine Task aktiv; Codefixes in `.worktrees/` auf `codex/B-XXX-*`.
- Ein Root Cause = ein Bug = ein Commit; kein `git add -A`.
- Nach jedem Sub-Schritt Vault aktualisieren.
- Keine neue Library, Architekturänderung oder destruktive Migration ohne
  Userentscheidung.
- CUDA ausschließlich GTX 1060 `cuda:0`.
- Keine Push-, Release- oder Veröffentlichungsaktion ohne separate
  Userautorisierung.
- Kein Gate überspringen.

### Evidenzvertrag

```json
{
  "run_id": "timestamp-phase",
  "baseline_commit": "sha",
  "phase": "STAB-N",
  "command": "exact command",
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601",
  "exit_code": 0,
  "verdict": "pass",
  "db_before": {},
  "db_after": {},
  "artifacts": [],
  "logs": [],
  "limits": []
}
```

Decision: Vault
`D-076-stabilitaetsprogramm-current-head.md`.

### STAB-0 Ergebnis 2026-07-27

- Baseline/Current HEAD: `02cddee9e7e8dd50d1d45fdb67fc930de834805b`.
- B-709 bis B-738 vollständig gegen Commits, Produktpfade, historische Tests
  und Current-Code abgeglichen.
- 22 Bugs `code-fix-pending-live-verification`.
- 8 Bugs Current-offen: B-715, B-723, B-725, B-726, B-735, B-736, B-737,
  B-738.
- Vaultweit keine doppelte Bug-ID; genau eine B-738; keine Umnummerierung.
- Kein Produktcode, kein pytest-Lauf, kein `fixed`.
- Evidenz:
  `docs/superpowers/synthesis/stab-0-b709-b738-evidenzmatrix-2026-07-27.md`.
- Nächste einzige Task: `STAB-1 / B-727 Vertrauensgate`.

### STAB-1 Laufstatus 2026-07-28

- DB-Baseline und B-727-Negativkontrollen bestanden; B-727 bleibt
  `code-fix-pending-live-verification`.
- Command-Evidenzrunner Commit `2d204fd`; Fokus 6/6 grün.
- Adversariales Review fand sechs Integritätslücken. Bug B-739 `in_progress`.
- Syntax-Run war formal pass; Import-Run Exit 0. Beide gelten bis B-739-Fix
  nicht als abschließende Gatebelege.
- Genau nächste Task: `STAB-1 / B-739 Evidenzrunner-False-Pass`.
- B-739 Code-Follow-up 2026-07-28: Fokus 19/19, echter detached Child,
  Syntax und fokussiertes Ruff grün. Commit/Re-Review offen.
- B-739 Runde 2: Fokus 30/30, Syntax/Ruff grün, Commits `c068169` und
  D-077-Governance `0968eed`.
- Post-Commit-Evidenz `20260728T0214-b739-postcommit-0968eed`: pass,
  Source Dirty 0 vor/nach, 13/13 reale DBs byte-/logisch identisch,
  13× quick_check ok, 0 Prozessreste.
- B-739 bleibt `code-fix-pending-live-verification`; kein `fixed`.
- Syntax/Import-Evidenz `20260728T0226-stab1-syntax-import`: pass;
  1120 Python-Dateien kompiliert, 10 Kernmodule importiert, 13/13 reale DBs
  unverändert, 0 Prozessreste.
- Current-Ruff-Evidenz `20260728T0232-stab1-ruff`: pass; Repo-Ruff Exit 0,
  13/13 reale DBs unverändert, 0 Prozessreste.
- Alembic-Evidenz `20260728T0241-stab1-alembic`: ein Head
  `f2a3b4c5d6e7`, frische Temp-DB bis Head, quick_check ok; reale DBs
  unverändert, 0 Prozessreste.
- B-727-Beleg 33/33 + 3/3 wird gemäß D-077 nicht wiederholt:
  Guard-/Testpfade seit `321dc31` unverändert; Runner nur verschärft.
- Current-Suite `20260728T0250-stab1-current-suite`: pytest 3362 passed,
  54 skipped, 3 deselected; 13/13 reale DBs unverändert. Runner-Gate fail:
  orphaned Ollama runner PID 3980 plus conhost, Parent 6876 verschwunden.
- Neuer High-Bug B-740; kein Prozess blind beendet.
- B-740 Root Cause: unisolierter PBWindow-Layouttest startete Host-Ollama;
  Stop/Start-Races und Parent-only-Cleanup ließen Runner-Kind zurück.
- B-740 Commit `abedf08`: Stop-Generation, serialisierter Owned-Tree-Cleanup,
  External-Null-Kill und PBWindow-Testisolation. Fokus 11/11, Syntax/Ruff und
  Post-Commit-Prozessgate grün; Status live-pending, kein `fixed`.
- Folgefund B-741: vier Default-Suite-Tests können echtes localhost/Ollama
  erreichen. Gemäß D-078 keine breite Suite; nur Source-Isolation plus
  kleinster zwingender Fokuscheck bei Codeänderung.
- Genau nächste Task: `STAB-1 / B-741 Default-Suite-Ollama-Isolation`.

### B-741 Default-Suite-Ollama-Isolation 2026-07-28

- Vier Deep-Test-Pfade hostisoliert: Vision nutzt Fake-Client; OllamaService-
  Socket/API/Inference/Pull werden gemockt; OllamaClient blockiert `urlopen`;
  Orchestrator-Generalpfad bleibt offline.
- Kleinster zwingender Fokus: exakt vier betroffene Tests `4 passed in 8.70s`;
  Syntaxcheck grün. Keine breite Suite nach D-078.
- B-741: `code-fix-pending-live-verification`, kein `fixed`.
- Nächste einzige Task: `STAB-4 / B-723 GPU-Cleanup-Lockscope`.

### B-723 GPU-Cleanup-Lockscope 2026-07-28

- Stem-CUDA-Cache-Cleanup in Inference-Lock verschoben.
- Video-RAFT-/SigLIP-Exception-Cleanup in eigene Execution-Lease verschoben.
- Kleinste Fokusbelege: Stem-Lockscope `1 passed in 5.16s`; Video-Exception-
  Lease-Vertrag `1 passed in 0.38s`; Syntax grün.
- B-723: `code-fix-pending-live-verification`, kein GPU-/Cancel-/Stress-Livebeweis.
- Nächste einzige Task: `STAB-4 / B-725 CPU-/Copy-Konvertierung außerhalb GPU-Lease`.

### Restfix-Fortschritt 2026-07-28

- B-725 Commit `5f174fd`: CPU-/Copy-Codecs außerhalb GPU-Lease; Fokus `2 passed`.
- B-726 Commit `963586a`: öffentlicher RAFT-Direktpfad unter Execution-Lease;
  Fokus `2 passed`.
- B-715 Commit `df617fa`: vollständiger SCHNITT-Projektsnapshot vor Workerstart;
  Fokus `8 passed`.
- B-735 Commit `ddcb027`: `role_match_weight` als 18. sichtbare, lernbare
  Brain-Achse; 59 fokussierte Tests grün.
- Alle vier Codefixes `code-fix-pending-live-verification`; kein `fixed`.
- B-736 Commit `dc253d4`: synthetischer ID-/Index-Rankingpfad entfernt;
  ohne echte Ranking-Eingaben fail-closed. RED 1 fail → GREEN 1 pass.
- B-736 `code-fix-pending-live-verification`; kein `fixed`.
- B-737 am 2026-07-28 vor erstem Codeedit sauber gestoppt; keine Tests/Commits.
- D-085 priorisiert beobachtete Live-Session vor B-737/B-738.
- W1 Retry 1: Boot/Setup/Hauptfenster/Shutdown mit Exit 0; 13/13 geschützte
  DB-Quellen danach byte- und logisch unverändert.
- W1 Retry 2: sichtbare Statusleiste meldete gleichzeitig `KI: Fallback` und
  `AI ready`, obwohl Ollama API-ready war. B-278 deshalb `partial-fix`;
  Workflow vor Projektanlage gestoppt.
- Nächste einzige Task:
  `LIVE-VERIFY / B-743 Settings-/Recent-Project-AppData-Isolation`.
- Runbook: `docs/superpowers/LIVE_TEST_SESSION.md`.
- B-278-Fix als `1b2f161` integriert; Fokus 3/3, sichtbarer Status im Retry
  kohärent. Exakter Timeout-Race blieb im Live-Retry nicht erzwungen; kein
  `fixed`.
- W1-Projektanlage `STAB-W1-A` im isolierten Projektroot gelang.
- B-743 Current-Regression: SettingsStore schrieb trotz isoliertem Launcher in
  echte `%APPDATA%\PBStudio\settings.json` und ergänzte Host-RecentProjects.
  App sofort sauber beendet; Host-Datei nicht geraten zurückgesetzt.
- B-743-Fix `b0aac7e` live bewiesen: sichtbare Projektanlage, Session-Settings
  und RecentProjects isoliert; Host-JSON und 15 Pre-DBs unverändert.
- B-744: isolierter Erststart migriert Host-QSettings aus Windows-Registry in
  Session-JSON. Kein Host-Write; dennoch Host-State-Read.
- Nächste einzige Task:
  `LIVE-VERIFY / B-744 isolierte Session-Settings ohne Host-QSettings`.
- B-744-Fix `ebc6546` live bewiesen: Session-JSON startet `{}`, null
  QSettings-Migration; sichtbare Projektanlage ergänzt nur isolierten Pfad.
  Host-JSON und 15 geschützte DBs unverändert.
- Nächste einzige Task:
  `LIVE-VERIFY / W1 Projektwechsel und Neustart`.
- W1-Wechselpfad sichtbar: B→C→B→C, Neustart, Screenshot, DBs unverändert,
  keine Prozessreste.
- B-745 blockiert W1-Abschluss: vier frühere Shutdown-Logs enden mit
  `Windows fatal exception: code 0x80010108`; neuester normaler
  `CloseMainWindow()`-Run nicht.
- Nächste einzige Task:
  `LIVE-VERIFY / B-745 W1-Shutdown 0x80010108`.
- B-745 geklärt: programmatischer UI-Automationsschluss
  (`spontaneous=False`) erzeugte `RPC_E_DISCONNECTED`; zwei native
  Windows-Schlüsse (`spontaneous=True`) ohne Fatal. Kein Produktcodefix.
- W1-Bericht:
  `docs/superpowers/synthesis/functional-test-w1-boot-projects-2026-07-28.md`;
  Verdict `live-pass-user-marker-pending`.
- Nächste einzige Task:
  `LIVE-VERIFY / W2 Import, Papierkorb, Restore, Reimport`.

### W2 Laufstatus 2026-08-02

- Import, aktiver Duplikatimport, Bulk-Soft-Delete, Papierkorb, Bulk-Restore,
  Reimport und Cross-Project-Reuse Current-live bestanden.
- B-746 Fresh Current-Live nicht reproduzierbar; Audio-Modus schaltet korrekt.
- B-747 projektpfadgebundener Mute-Key: RED/GREEN, Ruff und sichtbarer
  Reuse-Dialog grün; ohne Usermarker nicht `fixed`.
- DB-Gate: 15/15 geschützte Pre-Pfade für DB/WAL/SHM byte-identisch;
  18/18 Post-Quickchecks ok; Host-Settings-SHA unverändert.
- Prozessgate rot: `ollama.exe` PID 5944 lebt mit Parent PID 4620, dem alten
  W2-App-PID. Prozess nicht beendet.
- Bericht:
  `docs/superpowers/synthesis/functional-test-w2-import-restore-2026-08-02.md`.
- Nächste einzige Task:
  `ROOT-CAUSE / B-740 Current-Live Ollama-Ownership/Cleanup`.
- Bestandene W2-Funktionspfade werden nicht wiederholt; nur betroffener
  Ownership-/Shutdownpfad.

### B-740/W2 Abschluss 2026-08-02

- Historischer PID-5944-Rest stammt aus abnormal beendetem W2-Launcher ohne
  Exitmetadaten; nach Ownership-Beweis exakt Prozessbaum entfernt.
- Frische Current-App startete eigenen Ollama-Serve und Runner. Nativer
  Shutdown beendete App, Serve und Runner; Port 11434 frei.
- Finalmanifest `20260802T0818-w2-final`: 15/15 geschützte Pre-Pfade
  unverändert, 18/18 Quickcheck, Host-Settings-SHA unverändert,
  PB-/Ollama-Prozesse 0.
- W2 Verdict `live-pass-user-marker-pending`; STAB-2 25 %.
- Nächste einzige Task:
  `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.
- W2-Preflight: `tests/fixtures/clips_20` enthält nur Provenienz; alle 20
  referenzierten MP4-Pfade fehlen. 46 MP4-Proxies und 8 WAV-Stems in
  `outputs/test-tabelle/storage` sind vorhanden.
- Nächste einzige Task:
  `USER-DECISION / W2 fehlende 20 Clip-Fixtures`: Proxy-Substitution freigeben
  oder echten Quellpfad nennen.
- D-086 akzeptiert: 20 deterministisch ausgewählte MP4-Proxies und zwei
  WAV-Stems werden ausschließlich nach `%LOCALAPPDATA%\PBStudioStability`
  kopiert; Quellen bleiben read-only.
- Nächste einzige Task:
  `LIVE-VERIFY / W2 Import, Papierkorb, Restore, Reimport`.

### B-748 Incident-Recovery und Stability-Scope 2026-08-02

- Beim W3-Start wurde Host-Projekt `abnahme-block-c2` statt isolierter Kopie
  geoeffnet. App sofort graceful beendet; keine Audioanalyse gestartet.
- Host-DB aus beweisbarer Vor-Incident-Kopie logisch/schema-identisch
  wiederhergestellt; B-749 dokumentiert fehlende archivierte WAL/SHM-Rohbytes.
- Root Cause: kein Fail-Closed-Scope im Live-Harness/ProjectManager.
- Code-Fix: `PB_STABILITY_PROJECT`/`PB_STABILITY_PROJECT_ROOT` werden vor jeder
  Create/Open/Save-As-Arbeit erzwungen; GUI-Harness setzt Scope explizit.
- RED → GREEN `4 passed`; Syntax/Ruff gruen. Current-live Host-Pfad sichtbar
  blockiert; Pre/Post 6/6 geschuetzte Pfade unveraendert.
- B-748 Code+Live abgeschlossen, `fixed`-Usermarker offen.
- Nächste einzige Task:
  `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.

### B-752 Audio-Statuspanel None-Crash 2026-08-02

- Echter W3-Resume-Pfad lieferte fuer neun Checkpoint-Skips legitime None-
  Summaries; Formatter erzeugte neun `TypeError`-Crashdialoge.
- Fix: numerische Werte nur nach Konvertierung formatieren, None-Werte filtern,
  leere Summary als `—` anzeigen. Keine Ersatzmesswerte.
- RED/GREEN `4 passed`, Syntax/Ruff gruen. Current-live gleicher Skip-Pfad:
  null neue Exceptions/Crashdialoge, App responsive, graceful Shutdown.
- DB-Gate: Host-DB byte-identisch; isolierte W3-DB quick_check ok.
- Cancel selbst stoppte AV-Pacing kooperativ bei Chunk 1, wird aber falsch als
  `error`/`Worker-Fehler` behandelt.
- Naechste einzige Task:
  `ROOT-CAUSE / B-751 Audio-V2 User-Cancel als cancelled statt error/Erfolg`.

### B-751 Audio-V2 Cancel-Ehrlichkeit 2026-08-02

- Root Cause geschlossen: Worker-Cancelzweig, Legacy-Dispatcher-B-724-Pfad
  und Batch-Abschlusslogik getrennt von Produktfehler/Erfolg.
- RED → GREEN: 13/13 Fokustests inkl. B-713/B-724; Syntax/Ruff gruen.
- Current-live im isolierten STAB-W3: AV-Pacing stoppte bei Chunk 1; Task
  `cancelled`; persistierter Retry-Vertrag `status=error` plus
  `error_message=cancelled`; kein generischer Worker-/Analysis-Error; kein
  falscher Batch-Erfolg; keine neue UI-Exception.
- Hostschutz: 15/15 DB/WAL/SHM-Signaturen unveraendert. W3-DB quick_check ok,
  Alembic Head, WAL/SHM absent. Usermarker offen.
- Neue getrennte Bugs: B-753 Pre-Start-Cancel ohne Terminalsignal; B-754 stale
  `completed_at` nach Cancel.
- Naechste einzige Task:
  `ROOT-CAUSE / B-753 Audio-V2 Pre-Start-Cancel terminalisieren`.
- Danach B-750 optionaler Retry.

### B-753 Audio-V2 Pre-Start-Cancel 2026-08-02

- Root Cause: früher `should_stop()`-Return ohne Terminalsignal.
- RED 2/2 bestätigte fehlendes Worker-Signal und offenen Controller-Batch.
- Fix emittiert genau einen `User-Cancel vor Start`-Transport; keine Stage und
  kein DB-Statuswrite werden begonnen.
- Final: 15/15 fokussierte B-753/B-751/B-724-Tests, Syntax/Ruff und echtes
  QThread-Interleaving grün. Threadende binnen 2 s; kein App-GUI-Liveklick.
- B-753: `code-fix-pending-live-verification`; Usermarker offen.
- Nächste einzige Task:
  `ROOT-CAUSE / B-750 Audio-V2-Retry onset/AV-Pacing verdrahten`.

### B-750 Audio-V2-Retry optionale Stages 2026-08-02

- Root Cause: sichtbare optionale Step-Keys ohne MediaWorkspace-Dispatch;
  Full-Pipeline-Start allein hätte done/degraded Zielstage per Checkpoint
  erneut übersprungen.
- Fix: gezielter V2-Retry mit atomarem Zielstage-Reset. Onset nimmt
  `stem_gen` nur als rehydrierbare Prerequisite; AV-Pacing läuft isoliert.
- RED 5/5; final 13/13 fokussierte B-750/B-753/B-722-Tests, Syntax/Ruff grün.
- B-750: `code-fix-pending-live-verification`; App-GUI-/Medienbeweis offen.
- Nächste einzige Task:
  `ROOT-CAUSE / B-754 Analysis-Cancel muss stale completed_at löschen`.

#### B-750 Parallelreview-Follow-up 2026-08-02

- Commit `07161bb` nicht freigegeben: Cancel-Fehlertext, fehlende
  Stem-Selbstheilung und Retry-Single-Flight bleiben Medium-offen.
- B-750 zurück auf `in_progress`; B-754 wartet.
- Nächste einzige Task:
  `ROOT-CAUSE / B-750 Review-Follow-up: Cancel, Stem-Selbstheilung, Single-Flight`.

#### B-750 Review-Follow-up Fokus-PASS 2026-08-02

- Cancel- und Konflikttexte sind ehrlich; kein falsches `Error:`/Startsignal.
- Audio-Retry-all startet genau einen resumierbaren Strict-Sequential-Worker.
- Onset-Retry resettiert/läuft `stem_gen`; gültige Artefakte werden reused,
  fehlende werden durch Stem-Stage neu gebaut.
- WorkerDispatcher hält atomaren Projekt-/Track-Claim über Einzel-V2,
  Batch-V2, Retry und StemSeparation; Release erst im QThread-Cleanup.
- Review-RED 5/5, Cross-Path-RED 3/3; final 27 fokussierte Tests,
  `py_compile` und Ruff grün. Breite Suite/GPU/Medien bewusst später.
- B-750 bleibt bis unabhängigem Re-Review `in_progress`; App-Livebeweis offen.
- Nächste einzige Task:
  `REVIEW / B-750 Follow-up-Commit unabhängig auf Cross-Path-Single-Flight prüfen`.
- B-754 wartet.

#### B-750 Re-Review 8a4fef7 NOT PASS 2026-08-02

- 22/22 Reviewer-Fokus grün; Kernmechanik bestätigt.
- Rest-Medium: Full-/Batch-V2-Cancel, `Bereits aktiv` und Stem-Konflikt noch
  als Fehler/Fehlgeschlagen sichtbar.
- Rest-Low/Medium: Claim-Release unvollständig bei frühem Setupfehler,
  BG-`str` und Task ohne QThread-Cleanup.
- B-750 bleibt `in_progress`; B-754 wartet.
- Nächste einzige Task:
  `ROOT-CAUSE / B-750 Re-Review-Follow-up: UI-Klassifizierung und Claim-Leaks`.

#### B-750 Stand-6 Abschlussreview PASS 2026-08-02

- UI trennt Startkonflikt, Task-Cancel/`User-Cancel` und echten Fehler für
  Einzel-/Batch-V2 sowie Stems.
- Dispatcher-Claim-Release deckt frühen Setupfehler, Shutdown,
  terminal/no-thread, BG-`str`- und TaskInfo-Fast-Finish ab; Thread-Ref wird
  einmalig gesnapshottet und terminal nachgeprüft.
- Final notwendiger Fokus: `65 passed in 11.77s`; `py_compile`, Ruff und
  `git diff --check` grün.
- Unabhängiger Stand-6-Review PASS: keine Critical-/High-/Medium-Lücke. LOW
  Setup-QObject bleibt theoretisch ohne reproduzierbare Nutzerwirkung.
- B-750 → `code-fix-pending-live-verification`; App-GUI-/Medienbeweis W3 offen.
- Nächste einzige Task:
  `ROOT-CAUSE / B-754 Analysis-Cancel muss stale completed_at löschen`.

#### B-754 Cancel-Zeitsemantik Fokus-PASS 2026-08-02

- Root Cause: `mark_cancelled()` aktualisierte bei bestehender Done-Row nur
  Status/Fehlermeldung und behielt altes `completed_at`.
- Fix: `completed_at=None` im Conflict-Update.
- Echter Done→Started→Cancel-Vertrag RED→GREEN; drei direkte
  Cancel-/Idempotenztests, Syntax, Ruff und Diffcheck grün.
- Kein App-/DB-Live-Retry; B-754 `code-fix-pending-live-verification`.
- Neue getrennte Mediums: B-755 Running-Altzeit; B-756 Video-Cancel via
  `mark_error("cancelled")`.
- Nächste einzige Task:
  `ROOT-CAUSE / B-755 Analysis-Retry running muss stale completed_at löschen`.

#### B-755 Running-Zeitsemantik Fokus-PASS 2026-08-02

- Root Cause: `mark_started()` behielt `completed_at` einer früheren Done-Row.
- Fix: `completed_at=None` im Done→Running-Conflict-Update.
- Drei direkte Transitionstests, Syntax, Ruff und Diffcheck grün.
- B-755 `code-fix-pending-live-verification`; Live-Sichtung W3 offen.
- Nächste einzige Task:
  `ROOT-CAUSE / B-756 Video-Cancel muss stale completed_at löschen`.

#### B-756 Video-Cancel-Vertrag Fokus-PASS 2026-08-02

- Sieben explizite `should_stop()`-Zweige in Deferred-/Full-Videoanalyse auf
  kanonisches `mark_cancelled()` umgestellt; echte Fehler bleiben `mark_error()`.
- RED 7/7; Routing- plus Timestamp-Vertrag `2 passed in 8.65s`; Syntax, Ruff
  und Diffcheck grün.
- B-756 `code-fix-pending-live-verification`; Video-Live-Cancel W4 offen.
- Uservorgabe: breite/live Tests erst nach Codeaufgaben gebündelt.
- Nächste einzige Task:
  `ROOT-CAUSE / B-737 Memory-Updater Run-End-Flush und Feedback-Wiring`.

#### B-737 Memory-Updater/Lernkreis Fokus-PASS 2026-08-02

- Semantisches Brain-Timeline-Rating schreibt zuerst `mem_decision.user_rating`;
  erst danach wird Pattern-Aggregation benachrichtigt. Unverbundene
  state.db-Lernsample trainieren ehrlich nur Brain-Achsengewichte.
- Debounce unter 20 Events; Run-/Projekt-/App-End-Flush; Condition-basierte
  Generationen; Shutdown drainiert Feedback waehrend eigenem Flush.
- Aggregatorfehler stellen Pending-Events wieder her; strikte Lifecycle-Pfade
  propagieren; Best-Effort/atexit endet gebunden statt Log-/Retry-Endlosschleife.
- DB-Neustart-Beweis: ein Rating persistiert als `user_rating=1` und
  `mem_learned_pattern=(accept=0,reject=1,sample=1)`.
- Fokus: 27 Lernkreis/DB/Concurrency, 9 UI-Regressions, final 9 Review-Fixes;
  Ruff, Compileall und Diffcheck gruen. Unabhaengiger Abschlussreview:
  keine Critical-/High-/Medium-Luecke.
- Kein echter App-/Projektwechsel-/Shutdown-Livebeweis; B-737
  `code-fix-pending-live-verification`.
- Getrennter reproduzierter Medium-Bug B-757: StatsResponse max 17 bei
  18 kanonischen Achsen.
- Nächste einzige Task:
  `ROOT-CAUSE / B-757 Brain-Stats-Achszahl aus kanonischen Achsen ableiten`;
  danach B-738.

#### B-757 Brain-Stats-Achszahl Fokus-PASS 2026-08-02

- `BRIDGE_AXIS_COUNT = len(BRIDGE_AXES)` ersetzt veraltete feste 17 in
  `StatsResponse` und Stats-Panel; kanonische Achsenzahl bleibt D-080-gemaess 18.
- Sechs gezielte Service-/Schema-/UI-Belege gruen; verschaerfter Grenztest
  akzeptiert beide Felder bei 18 und lehnt beide bei 19 ab.
- Ruff, Compileall, Diffcheck gruen; unabhaengiger Abschlussreview ohne
  Critical-/High-/Medium-Finding.
- Kein App-Livebeweis; B-757 `code-fix-pending-live-verification`.
- Nächste einzige Task: `ROOT-CAUSE / B-738 Brain/Memory fuer alle LLM-Pfade`.

#### B-738 modellunabhaengiger Brain-Gateway Fokus-PASS 2026-08-02

- Tool- und Non-Tool-Orchestratorpfade erhalten frischen projektisolierten
  Recall-Kontext; Phi3/Gemma-Familien laufen ueber echten NO-TOOLS-Fallback.
- Non-Tool-Gateway ist fail-closed: eindeutiger `pb_brain_gateway=v1`-
  Envelope, strikte Brain-Allowlist und Parameterpruefung. Normales JSON bleibt
  Daten. Persistentes Learn braucht zusaetzlich reservierten User-Prefix mit
  Doppelpunkt; B-411 laesst nur diesen sicheren Control-Pfad passieren.
- Vision-Caption und Moondream erhalten Recall; spezifischer Miss faellt auf
  neuesten Projektsnapshot zurueck. Neueste Cut-Erklaerung wird read-only
  vorab geladen. Fachprompt/JSON-Schema bleibt letzte dominante Anweisung;
  Vision kann niemals Learn ausloesen.
- Fokus 44 Gateway-/Tool-/Non-Tool-/Action-/Pacing-/Vision-Vertraege plus
  persistenter Learn-Recall-Kreis gruen. Ruff, Compileall und Diffcheck gruen.
  Unabhaengiger Abschlussreview ohne Critical/High/Medium.
- Kein echter ChatDock-/Ollama-/App-Neustart-Livebeweis; B-738
  `code-fix-pending-live-verification`, nicht `fixed`.
- Naechste einzige Task:
  `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.

#### W3 Gate-Stopp B-758 2026-08-02

- Current-Appstart auf `e85a2c2`, isolierter AppData und exaktem
  `--stability-project`-Scope zeigt modal `CUDA GPU FAIL` und
  `NVENC Encode FAIL`; GPU-Anzeige `0/0 GB`.
- Degradierter Start nicht gewählt. Screenshot, Pre-/Post-Manifest und
  Prozesscleanup belegt. W3-/Hostprojekt-DBs unverändert.
- Repo-Root-WAL/SHM wurden beim Start neu erzeugt, extern als Evidenz gesichert
  und nach Prozessfreiheit recoverable entfernt; Zusammenhang noch ungeklärt.
- W3 bleibt 25 %. Erster Fehler stoppt Workflow.
- Naechste einzige Task:
  `ROOT-CAUSE / B-758 Systemcheck CUDA/NVENC FAIL im isolierten W3-Live-Run`.

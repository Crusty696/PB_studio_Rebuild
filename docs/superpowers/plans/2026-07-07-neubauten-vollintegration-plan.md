# NEUBAUTEN-VOLLINTEGRATIONS-PLAN — Studio-Brain, Slice-1-Pacing, Komfort-Features und DAG-Video-Engine komplett verdrahten

- **plan_id:** `PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07`
- **Priorität:** **HOCH** — verbindlicher Nachfolger. Startet **direkt nach**
  Abschluss UND Test des `PB-STUDIO-AUDIT-FIXPLAN-2026-07-07`. Kein anderer
  Plan darf sich dazwischenschieben (User-Anweisung 2026-07-07).
- **Auftraggeber-Entscheidung (User, 2026-07-07, wörtlich):** "ich will das
  alles davon vollständig in einem eigenen plan erledigt und fertig gebaut
  und implementiert wird, jedes paket vollständig."
- **Quelle der Findings:** `docs/superpowers/synthesis/audit-fehler-luecken-toter-code-verdrahtung-2026-07-07.md`
  (Kapitel C "Implementiert, aber vom Produktfluss abgeschnitten" + USE-/WIRE-/DEAD-IDs).
- **Ziel-Zustand:** Nach diesem Plan gibt es KEINE implementierte Komponente
  mehr, die vom Produktfluss abgeschnitten ist. Jedes Feature ist verdrahtet,
  erreichbar, getestet und wirkt nachweisbar im Produkt.

---

## Für den ausführenden Agenten (Pflicht-Lektüre, in dieser Reihenfolge)

Dieser Plan ist self-contained geschrieben. Du brauchst KEIN Wissen aus der
Chat-Session, in der er entstand. Lies vor Beginn:

1. `AGENTS.md` (Repo-Root) — vollständig. Governance ist bindend.
2. `docs/superpowers/PLAN_REGISTRY.md` + `docs/superpowers/ACTIVE_PLAN.md` —
   dieser Plan darf nur laufen, wenn `ACTIVE_PLAN.md` GENAU diesen Plan nennt.
3. Den Audit-Bericht (Quelle oben) — mindestens Kapitel C, E, F.
4. Den Vorgänger-Plan `docs/superpowers/plans/2026-07-07-audit-fixplan.md` —
   dessen Fixes (v.a. A2 Classify+Waveform, B-Track) sind Voraussetzungen.

### Harte Regeln (aus AGENTS.md / CLAUDE.md, hier wiederholt)

- **Eine Task nach der anderen.** Kein Parallel-Anfangen mehrerer Tasks.
- **Vault-Eintrag pro Sub-Schritt** mit Zeitstempel in
  `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\log.md`
  (Format: `## YYYY-MM-DD HH:MM <kategorie> | <kurz>`). Max. 1 Turn ungeloggt.
- **GPU-Regel:** ausschließlich NVIDIA GTX 1060 / `torch.device("cuda:0")` /
  FFmpeg `h264_nvenc`. Library ohne CUDA-Backend → CPU. Nie ein anderes
  GPU-Backend.
- **`fixed`-Marker setzt nur der User** nach eigener Live-Sichtung. Agent
  liefert `code-complete-live-pending` + Beweise.
- **Live-Verify Pflicht pro Task:** Code-Edit ≠ fertig. Standard-Testdaten:
  Video-Ordner `Solo_Natur` (103 Dateien), Audio
  `Crusty Progressive Psy Set2.mp3` (149 MB DJ-Mix).
- **Git:** ein Commit pro abgeschlossener Task, Worktree am Task-Ende clean.
  Vor jeder Task: `git status --short --branch` und sauberen Stand sichern.
- **LOCKED-Architektur nicht anfassen:** PySide6, SQLAlchemy+SQLite WAL,
  beat_this, Demucs htdemucs_ft, SigLIP-so400m (1152-dim), OTIO,
  ModelManager-Singleton, SessionManager. Integration JA, Austausch NEIN.

### Abhängigkeiten vom Audit-Fixplan (müssen vorher fertig sein)

| Voraussetzung | Warum |
|---|---|
| A2 (Classify+Waveform in V2, Langform-Strategie) | Paket 1 Scoring braucht mood/genre/is_dj_mix gefüllt; DB-004-Anschluss (`sub_genre`-Persistenz) liefert Scorer-Input |
| B1/B2 (SigLIP-/Beat-Fehler sichtbar) | Paket-1-Rollout darf nicht auf still-degradierten Daten lernen |
| B4 (V2 schreibt `analysis_status`) | SetupWizard/Statusanzeigen (T2.4) sonst inkonsistent |
| A0 (E2E-Render-Smoke-Test grün) | Basis-Verify-Werkzeug aller Pakete |

---

## PAKET 1 — Studio-Brain-Entscheidungspfad vollständig live schalten

**Grundsatz-Entscheidung (User 2026-07-07):** Das lernende Studio-Brain SOLL
den Schnitt mitentscheiden. Alle 5 Komponenten werden produktiv.

### T1.1 — Studio-Brain-Pacing-Pipeline aktivieren (USE-001)
- **Ist:** `services/pacing/pipeline.py` (PacingPipeline) + `services/pacing/bridge.py`
  laufen nur bei Env-Var `PB_USE_STUDIO_BRAIN_PIPELINE` (`bridge.py:15`) —
  die niemand setzt. Setup in `services/pacing_service.py:384,962-1005`,
  Lesen in `ui/controllers/edit_workspace.py:497-499`.
- **Soll:** Aktivierung als **persistentes Setting mit UI-Schalter**
  (SettingsStore + Checkbox im Auto-Edit-Panel oder SettingsDialog
  `ui/dialogs/settings_dialog.py`), nicht nur Env-Var. Env-Var bleibt als
  Override. Default nach Abnahme dieses Pakets: **AN**.
- **Verify:** Auto-Edit-Lauf mit Testdaten erzeugt `mem_pacing_run`- und
  `mem_decision`-Zeilen (vorher 0); `set_active_pacing_run`
  (`edit_workspace.py:499-509`) liefert Run-ID an Timeline; DecisionRecorder-
  Einträge im Decision-Explorer sichtbar.

### T1.2 — Brain-V3-Reranker im Cut-Entscheidungspfad (USE-002)
- **Ist:** `PacingPipeline(use_brain_v3=False)`-Default; die einzige
  Produkt-Instanzierung `services/pacing_service.py:980-991` übergibt kein
  `use_brain_v3=True`. Reranker: `services/brain/reranker.py`.
- **Soll:** `use_brain_v3=True` (+ Konfidenz-Parameter) an der Instanzierung
  durchreichen, gekoppelt an das T1.1-Setting. WeightStore
  (`services/brain/weight_store.py`) wirkt damit erstmals im Schnitt.
- **Verify:** Zwei Auto-Edit-Läufe (Reranker an/aus) unterscheiden sich
  nachweisbar in der Clip-Auswahl; Reranker-Scores im Log/Explorer sichtbar;
  VRAM-Budget GTX 1060 (6 GB) eingehalten (kein OOM bei Testdaten).

### T1.3 — SteerOverrideQueue-Consumer bauen (USE-004)
- **Ist:** UI schreibt (`ui/studio_brain/steer_tab.py`, `structure_tab.py`),
  KEIN Backend liest — Boost/Exclude/Pins wirkungslos. Queue:
  `services/steer_override_queue.py:73-141`. Eigenes Code-Eingeständnis
  `steer_tab.py:41`: "the consumer (pacing agent) ships later".
- **Soll:** Konsum der Queue in `pacing_service`/`PacingScorer`: Boost →
  Score-Bonus, Exclude → harter Ausschluss, Pins → fixe Zuordnung. Beim
  Auto-Edit-Lauf Queue lesen, anwenden, verbrauchte Overrides markieren.
- **Verify:** Clip im Steer-Tab excluden → Auto-Edit verwendet ihn nicht;
  Boost → messbar häufigere Verwendung; UI-Hinweis "ohne Wirkung" (falls in
  Zwischenzeit eingebaut) entfernen.

### T1.4 — RL-Stack v2 an Feedback anschließen (USE-006)
- **Ist:** `services/pacing/rl_memory_v2.py` (Verdict-Replay,
  Policy-Update-Hook), `rl_policy.py`, `variety_memory.py` — nur Tests.
  Produkt nutzt altes `services/pacing_memory.py`.
- **Soll:** v2-Replay/Policy-Update an FeedbackService-Events
  (`services/feedback_service.py`, Timeline-Verdicts `ui/timeline.py:2350/2360`)
  und an Scorer-Gewichte anschließen. Migration/Koexistenz mit
  `pacing_memory` explizit klären und dokumentieren (kein stiller
  Doppel-Writer).
- **Verify:** A/R/S-Verdict auf Timeline-Clip verändert nach Policy-Update
  nachweisbar die Gewichte (WeightStore-Diff vor/nach); kein Doppel-Write in
  alte und neue Memory gleichzeitig ohne Absicht.

### T1.5 — Lernschleife schließen: gelernte Patterns in den Scorer (USE-008)
- **Ist:** `mem_user_feedback_event` + `mem_learned_pattern` werden
  geschrieben (`ui/timeline.py:914`, `workers/memory_updater.py`,
  `services/pacing/pattern_aggregator.py`), aber gelesen nur von
  Anzeige (`ui/studio_brain/memory_tab.py:318`) und Backup-DELETE.
- **Soll:** Scorer konsumiert gelernte Patterns/Gewichte im Auto-Edit
  (über den T1.2-Reranker-Pfad bzw. direkte Score-Modifier).
- **Verify:** End-to-End-Lernbeweis: Feedback geben → memory_updater →
  Pattern → nächster Auto-Edit-Lauf entscheidet nachweisbar anders
  (dokumentierter Vorher/Nachher-Vergleich mit denselben Eingabedaten).

### T1.6 — UI-Ehrlichkeit + Dead-End-Signals des Brain-Bereichs
- **Ist:** Feedback ohne sichtbare Bestätigung (`feedback_event_emitted`
  ohne Subscriber, `ui/timeline.py:782`); Dead-End-Signals WIRE-004, -008,
  -009, -010, -011, -012 (GraphCockpit nodeSelected, SteerTab trackChanged,
  DecisionExplorer decisionSelected, MemoryTab patternsReset,
  StatsPanel stats_refreshed, LearningDialog session_finished).
- **Soll:** Feedback-Bestätigung sichtbar machen (Statusleiste/Toast);
  die geplanten Cross-Tab-Verbindungen nachrüsten (Explorer↔Graph-Navigation,
  Reset/Session-Ergebnis → Stats/Memory-Refresh). Signals, die danach immer
  noch keinen Zweck haben, entfernen.
- **Verify:** Jedes verbliebene `emit` hat ≥1 `connect`; Feedback-Tastendruck
  zeigt sichtbare Bestätigung; Verdict im Explorer refresht Memory-Tab.

---

## PAKET 2 — Kleine Verdrahtungen, jede vollständig

### T2.1 — LLM-Pacing per UI schaltbar (USE-007)
- **Ist:** `services/pacing_strategist.py` + `services/pacing/ollama_pacing.py`
  fertig; Gates `services/pacing_service.py:556` (`use_llm_strategist`) und
  `:832` (`use_llm_pacing`); Defaults False in
  `services/pacing_beat_grid.py:129-130`; kein Setter im Repo. Einzige
  Konstruktion `ui/controllers/edit_workspace.py:340-347`.
- **Soll:** Zwei Checkboxen (oder eine kombinierte) im Auto-Edit-Panel,
  persistiert im SettingsStore, durchgereicht in `AdvancedPacingSettings`.
  Default AUS. Voraussetzungs-Check: läuft Ollama nicht → Checkbox
  deaktiviert mit Tooltip (Ollama-Setup siehe `reference_ollama`-Notizen:
  GPU-Mode GTX 1060 funktioniert, notfalls `ollama serve` direkt).
- **Verify:** Checkbox an → Strategist-/EDL-Pfad läuft nachweisbar (Log +
  abweichendes Ergebnis); Checkbox aus → alter Pfad; Setting übersteht
  App-Neustart.

### T2.2 — `audio.v2_default` im Settings-Dialog (USE-012)
- **Ist:** `get_nested("audio","v2_default", default=True)` in
  `ui/controllers/audio_analysis.py:305,566`; kein `set_nested`-Aufrufer;
  SettingsDialog persistiert nur Ollama+Shortcuts
  (`ui/dialogs/settings_dialog.py:33-40`).
- **Soll:** Settings-UI-Eintrag "Audio-Analyse V2 als Standard" (Checkbox),
  schreibt `set_nested("audio","v2_default", …)`.
- **Verify:** Umschalten auf False → Komplett-Analyse nutzt den klassischen
  Sequenz-Pfad (`_analyze_all_sequential`), sichtbar im Log; True → V2.

### T2.3 — Timeline-Snapshots verdrahten (USE-009 / DB-005 + DB-016 + DB-019)
- **Ist:** `services/timeline_snapshot_service.py` + Tabelle
  `timeline_snapshots` fertig, kein Produkt-Caller. Model-Docstring
  (`database/models.py:627-634`) behauptet fälschlich automatische
  Persistenz. Latente Bugs: kein `UNIQUE(project_id, version)` bei
  max+1-Vergabe (`services/timeline_state.py:79-91`); `list_snapshots()`
  gibt detached ORM-Objekte zurück (`timeline_snapshot_service.py:24-30`).
- **Soll:** (a) Snapshot automatisch bei jedem Auto-Edit-Apply
  (`services/timeline_service.py:299-319` bzw. `ApplyAutoEditCommand`);
  (b) UI: Snapshot-Liste + "Wiederherstellen" im Schnitt-Workspace;
  (c) DB-016 fixen (UNIQUE-Constraint oder Upsert-Muster analog B-581);
  (d) DB-019 fixen (Dicts statt ORM über Session-Grenze);
  (e) Retention (z.B. letzte 20 pro Projekt) festlegen.
- **Verify:** Auto-Edit → App hart beenden → Neustart → Timeline über
  Snapshot wiederherstellbar; Docstring stimmt wieder; parallele
  Snapshot-Erzeugung erzeugt keine Duplikat-Versionen.

### T2.4 — SetupWizard beim First-Run (WIRE-001 / DEAD-002)
- **Ist:** `ui/dialogs/setup_wizard.py` (868 Zeilen, intern korrekt
  verdrahtet inkl. Download-Worker) wird nirgends aufgerufen.
- **Soll:** First-Run-Erkennung in `main.py` (Marker im SettingsStore oder
  `is_setup_complete`-Logik des Wizards nutzen) → Wizard modal vor dem
  MainWindow; "Überspringen" erlaubt; danach nie wieder automatisch.
  Koexistenz mit StartupCheck/NVENC-Gate (B-563-Test beachten:
  `tests/test_services/test_b563_startup_nvenc_gate.py`).
- **Verify:** Frisches Profil (Settings weg) → Wizard erscheint, Download
  eines kleinen Modells funktioniert; zweiter Start → kein Wizard;
  bestehende Installation → kein Wizard.

### T2.5 — Slice-1-Pacing-Cluster: ALLE 16 Module verdrahten (USE-005 / DEAD-001)
- **Ist:** `services/pacing/` — 16 Module nur von Tests/`scripts/demo_pacing_v2.py`
  erreicht: `cut_snapper`, `cut_density_modulator`, `vocal_hold_modifier`,
  `stem_section_aggregator`, `phrase_boundary_constraint`,
  `section_coherence`, `energy_match_reward`, `audio_video_curves`,
  `mood_match_score`, `audio_mood_vector`, `stem_class_bonus`,
  `shot_type_classifier`, `ab_runner`, `rl_memory_v2`*, `rl_policy`*,
  `variety_memory`* (*die drei RL-Module laufen über T1.4).
  `services/pacing/scorer.py` nutzt eigene, einfachere
  `mood_match`/`energy_match`-Funktionen (`scorer.py:204,260`).
- **Soll (vollständig, User-Anweisung):**
  1. **cut_snapper** in `finalize_cut_beats`/`auto_edit_phase3`: Cuts auf
     persistierte Onsets snappen (Daten liegen: `Beatgrid.onset_*`,
     Writer `services/onset_rhythm_service.py:616-620`). Dabei
     PIPE-016-Limit beachten: Onset-Analyse kappt bei 1800s
     (`onset_rhythm_service.py:28`) — Limit entfernen oder chunked
     verarbeiten, sonst snappt die zweite Hälfte langer Mixe nicht.
  2. **cut_density_modulator** (Drop-Burst) + **phrase_boundary_constraint**
     + **section_coherence** in die Cut-Erzeugung.
  3. **vocal_hold_modifier** + **stem_section_aggregator** (Vocal-Hold auf
     Basis der Demucs-Vocal-Stems).
  4. **energy_match_reward** + **audio_video_curves** + **mood_match_score**
     + **audio_mood_vector** + **stem_class_bonus** als Score-Komponenten in
     `PacingScorer` — die einfacheren Bestands-Funktionen ersetzen oder
     kombinieren (Entscheidung dokumentieren).
  5. **shot_type_classifier** in die Video-Analyse-Ergebnisse einspeisen
     (ClipFeatures), damit Scorer ihn nutzen kann.
  6. **ab_runner** als UI-Funktion: zwei Pacing-Läufe vergleichen
     (Studio-Brain-Fenster oder Auto-Edit-Panel).
- **Verify:** Pro Modul ein nachweisbarer Effekt-Test (z.B. cut_snapper:
  Cut-Zeitpunkte liegen auf Onsets ±Toleranz; vocal_hold: keine Cuts
  mitten in erkannten Vocal-Phrasen; ab_runner: UI zeigt zwei Läufe im
  Vergleich). Gesamt: Auto-Edit-Ergebnis mit Testdaten hörbar/sichtbar
  beat- und struktur-treuer; bestehende SCHNITT-Fixplan-Garantien
  (Beat-Sync 100%, exaktes Ende) bleiben erhalten (Regressions-Check).

---

## PAKET 3 — DAG-Video-Engine vollständig integrieren (USE-003 / PIPE-018 / DEAD-008)

- **Ist:** Zweite Video-Analyse-Pipeline (`services/video_pipeline/`,
  Orchestrator/Stages/Checkpoint-Resume) existiert komplett neben dem
  Monolith-Pfad (`services/video_analysis_service.py::run_full_pipeline`).
  Nur aktiv bei `PB_ENABLE_VIDEO_PIPELINE_ENGINE=1`
  (`app_integration.py:21`), das niemand setzt. Kritische Lücke PIPE-018:
  Die Engine schreibt eigene Artefakte (`embeddings_path`, `motion_path`,
  `Scene.scene_index`…), aber NICHT in VectorDB/`Scene.energy` → Matching
  sieht ihre Ergebnisse nicht. 6 Cross-Cutting-Module (DEAD-008:
  `trigger_queue`, `coverage_guard`, `status_reporter`, `observability`,
  `disk_budget`, `gpu_lock_aware`) sind auch engine-intern unverdrahtet.
- **Soll (Vollintegration):**
  1. **Ergebnis-Parität:** Engine-Stages schreiben zusätzlich in die vom
     Matching gelesenen Senken (VectorDB-Embeddings 1152-dim, `Scene.energy`,
     Motion-Scores in bestehender Skala) ODER Matching lernt die neuen
     Artefakt-Pfade lesen — Entscheidung dokumentieren, eine Richtung, nicht
     beide halb.
  2. **Cross-Cutting-Module einhängen:** GPU-Lock-Aware-Primitive an
     `GPU_EXECUTION_LOCK`, status_reporter an `analysis_status`,
     disk_budget/coverage_guard/trigger_queue/observability an den
     Orchestrator.
  3. **Paritäts-Nachweis:** Gleiches Testmaterial durch Legacy-Pfad und
     Engine → Szenen/Embeddings/Motion vergleichbar (dokumentierter Diff,
     Toleranzen definieren).
  4. **Umschaltung:** Setting/UI-Schalter statt nackter Env-Var; nach
     bestandener Parität Default auf Engine, Legacy-Pfad bleibt als
     Fallback wählbar (kein Löschen in diesem Plan).
- **Verify:** Kompletter Workflow (Import → Video-Analyse via Engine →
  Auto-Edit → Export) mit Testdaten liefert Ergebnis gleicher Qualität wie
  Legacy (Parität-Report); Checkpoint-Resume nachgewiesen (Analyse
  unterbrechen → fortsetzen); GTX-1060-VRAM stabil.

---

## Reihenfolge & Meilensteine

Empfohlene Ausführung (eine Task zur Zeit):

1. **M1 = Paket 2 zuerst** (T2.2 → T2.1 → T2.3 → T2.4 → T2.5). Grund:
   kleine, unabhängige Erfolge; T2.5 liefert die Pacing-Basis, auf der
   Paket 1 aufsetzt.
2. **M2 = Paket 1** (T1.1 → T1.2 → T1.3 → T1.5 → T1.4 → T1.6). Reihenfolge:
   erst Pipeline+Reranker live, dann Steuer-/Lern-Anschlüsse.
3. **M3 = Paket 3** (größter Block, klar abgegrenzt am Ende).

Nach jedem Meilenstein: Zwischen-Synthese in
`docs/superpowers/synthesis/` + Vault-Spiegel + User-Bericht.

## Nicht-Ziele dieses Plans

- Kein Löschen von Code (auch nicht Legacy-Pfade) — Löschentscheidungen
  liegen bei Track D des Audit-Fixplans bzw. beim User.
- Kein Austausch von LOCKED-Komponenten.
- Keine Arbeit an OTK-021-Release-Themen.
- Keine neuen Features außerhalb der 11 gelisteten Komponenten.

## Abschluss-Kriterium

Alle Tasks `code-complete-live-pending` mit dokumentierten Live-Beweisen
(Screenshots/Logs/DB-Dumps/Render-Outputs pro Verify-Punkt), Regressions-Check
gegen SCHNITT-Fixplan-Garantien grün, Abschluss-Synthese in Repo + Vault.
`fixed` setzt der User nach eigener Sichtung.

# PB Studio Agent Handoff

This file is a repository-local continuity checkpoint for all agents.

## STAB-5 aktiv — 2026-08-26

- Inventar: 103 UI-Dateien, 182 rohe Constructor-Sites, 636
  Signalverbindungen. 182 ist als Controlwert verworfen; Factory-Expansion
  ergibt 222 statische Deklarationsstellen, keine Runtime-Anzahl.
- B-900 `fixed`: echter First-Run-App-Pfad mit QThread und lokal verweigerter
  Verbindung; Modell/Gesamt 0, roter Fehlertext, Finish-Fehlermeldung, Exit 0.
- Evidenzreview: automatische Testrefs sind Kandidaten, keine Belege; 36 echte
  Element-Belegluecken, zwei Caveats, zwei voll belegte Controls.
- B-902: Code-Fix committed `8cb1e55`; Frozen-/Installer-Livetest bleibt
  STAB-6-Gate.
- Superseded-Planarchiv complete: 12 Moves plus byteidentische Gemini-Kopie;
  Registry/Repo/Vault-Linkpruefung gruen. Evidence:
  `docs/superpowers/synthesis/plan-archive-link-migration-2026-08-26.md`.
- Naechste einzige Task: B-901 Update-Controls Defaultpfad/Repo-Default;
  Minimaltest erst Endgate.
- Evidence: `docs/superpowers/synthesis/b900-setup-wizard-progress-truth-2026-08-26.md`.
- Evidence: `docs/superpowers/synthesis/stab5-ui-action-inventory-2026-08-26.md`.
- Evidence: `docs/superpowers/synthesis/stab5-ui-action-evidence-2026-08-26.md`.
- Evidence: `docs/superpowers/synthesis/stab5-ui-evidence-cleanup-2026-08-26.md`.
- User bestaetigte STAB-4 trotz offen ausgewiesener B-774-Grenze.
- Folgephasen autonom freigegeben; Statusmarker erst nach jeweiligem Nachweis.
- Tests: minimal, direkt betroffen, spaetestmoegliches Endgate.

## STAB-4 agent-complete-await-user-marker — 2026-08-26

- B-774: Current 9/9 Fault-Injection; Post-Fix-App-Dauerlast mindestens
  100 echte RAFT-/SigLIP-GPU-Clips, stabile VRAM-Marken, kein Kontextfehler.
- Echter gestorbener Kontext trat nicht erneut auf; kein riskanter GPU-Reset.
- STAB-4-DoD dokumentiert. Kein Agent-`fixed`.
- Naechste einzige Task: User-Phasenmarker; danach STAB-5.
- Evidence: `docs/superpowers/synthesis/phase-stab4-done-2026-08-26.md`.
  Kein Push. Keine weiteren STAB-4-Tests; kuenftig nur minimal betroffene
  Pfade am spaetestmoeglichen Endgate (Uservorgabe 2026-08-26).

## STAB-4 / B-899 agent-complete — 2026-08-26

- D-093-Gate +1024 MiB gezielt belegt: zwei echte htdemucs-Zyklen im selben
  Prozess, Baseline 402 MiB, Peaks 1944/1944, Cleanup 1020/1020 MiB
  (je +618), Torch allocated/reserved 0/0, kein Wachstum.
- Prozessende 396 MiB; 0 passende PB-/Demucs-/Ollama-/FFmpeg-Prozesse.
- B-899 `agent-complete-await-user-marker`; kein `fixed`/Push.
- Naechste einzige Task: B-774 realen CUDA-Kontextverlust-Dauerlastbeleg
  bewerten.

## STAB-4 / D-093 Gateentscheidung — 2026-08-26

- User genehmigt In-Process-VRAM-Gate `Baseline +1024 MiB`.
- Zusatzgates: Torch allocated/reserved nach Cleanup 0/0, kein wachsender
  Rest ueber Wiederholungsläufe, keine Zombies. Out-of-Process-Demucs entfällt.
- Naechste einzige Task: B-899 gezielter Wiederholungsbeleg; danach B-774.
  Kein Push/User-`fixed`-Marker.

## STAB-4 / B-899 blocked-needs-user-selection — 2026-08-26

- Isolierter echter Demucs-CUDA-Lauf: 0 -> Peak 1548 -> allocator-clean
  624 MiB; Torch allocated/reserved 0/0. `ipc_collect()` ohne Wirkung; erst
  Prozessende bringt 0 MiB.
- Aktives +512-MiB-Gate ist unter In-Process-Demucs um mindestens 112 MiB
  unerreichbar. Kein nachgewiesenes lebendes Torch-Tensorleck.
- Entscheidung noetig: Demucs-Out-of-Process oder hardware-/stackbasierte
  Anpassung des In-Process-Gates. Kein stiller Umbau/Thresholdwechsel.
- Evidence: `docs/superpowers/synthesis/b899-cold-vram-gate-decision-2026-08-26.md`.
  B-774-Realbeleg bleibt danach offen. Kein Push.

## STAB-4 / B-898 agent-complete — 2026-08-26

- Root Cause behoben: User-Cancel bleibt `ExportCancelled` statt generischem
  Renderfehler; damit kein B-603-Fallback. LUFS-Vor-/Zwischenchecks brechen
  ebenfalls typisiert ab.
- Vier gezielte Tests, PyCompile und fokussierter Ruff gruen. Zwei bestehende
  E731-Lambdas in `tests/test_services/test_ffmpeg_cancel.py` unveraendert.
- Echter GTX-1060-`h264_nvenc`-xfade-Export via TASKS abgebrochen:
  kooperativer Abbruch und Worker-Ende in derselben Sekunde, kein Fallback/
  Precheck, FFmpeg 0, kein Teilfile, App responsiv, DB `quick_check: ok`.
  Nativer Shutdown ohne App/Ollama/FFmpeg-Rest.
- Status `agent-fixed-await-user`; kein User-`fixed`-Marker. Evidence:
  `docs/superpowers/synthesis/b898-export-cancel-no-fallback-2026-08-26.md`.
- Naechste einzige Task:
  `STAB-4 / Kalt-VRAM-Gesamtgate (+813 > +512 MiB) ursächlich schließen`.
  B-774-Realbeleg bleibt danach offen. Kein Push.

## STAB-4 30-Minuten-Soak agent-complete — 2026-08-25

- Commit `2dacf90`: 361 Samples/30:00.5 min; UI-Heartbeat max. 3.3 ms,
  Threads +2, RSS max. 449.4 MiB, Idle-VRAM 0 MiB, keine DB-/Log-/
  Prozessfehler. Nativer Shutdown ohne App/Ollama/Runner/FFmpeg-Rest.
- Geschuetzter Scope: 15 Rohteile/5 DBs und 5 logische DBs ohne Differenz.
  Isolierte Test-DB konsistent; erwartete `project_sources.last_seen_at`-
  Updates plus WAL-Checkpoint. Exakter 22:57-Vor-Digest fehlt.
- STAB-4 gesamt bleibt rot/offen: aktives Kalt-VRAM +813 > +512 MiB,
  B-774 und B-898. Kein User-`fixed`-/Phasenmarker; kein Push.
- Evidence: `docs/superpowers/synthesis/stab4-30min-soak-2026-08-25.md`.
- Naechste einzige Task:
  `STAB-4 / B-898 Export-Cancel darf keinen Fallback/Precheck mehr starten`.

## STAB-4 Kombinationszyklus agent-complete — 2026-08-25

- Preview, qwen2.5-Chat, htdemucs-Cancel, SigLIP-/RAFT-Cancel, echter
  `h264_nvenc`-Export-Cancel, Projektwechsel und zwei native Shutdowns live.
- App/Ollama/Runner/FFmpeg null; keine Ziel-/Teilfiles; beide isolierten DBs
  `quick_check: ok`; Host-Settings-SHA unveraendert.
- B-898 neu `open`: User-Cancel startet noch xfade-Fallback/Precheck; rund
  13 Sekunden bis ExportWorker-Ende. Kein Produktcodefix in dieser Task.
- Kalt-VRAM-Gate (+813 > +512 MiB), B-774 und 30-Minuten-Soak offen.
- Evidence: `docs/superpowers/synthesis/stab4-combined-cycle-2026-08-25.md`.
- Naechste einzige Task: `STAB-4 / 30-Minuten-Soak mit GPU-/RAM-/Thread-/
  Prozess-/DB-Monitoring ausfuehren`. App/Ollama geschlossen; kein Push.

## STAB-4 Ollama-Ownership/Races agent-complete — 2026-08-25

- Current-App PID 3392 uebernahm externen Ollama-Serve PID 1464 ohne eigenen
  Popen. Nativer spontaneous Alt+F4 beendete App, liess externen Serve plus
  HTTP-200-API unangetastet; kein App-/FFmpeg-Rest.
- DB quick_check und Counts 125/147/3/102 vor/nach identisch; synchroner
  Scheduler-/ModelManager-/CUDA-/MemoryUpdater-Cleanup ohne Fehler.
- B-723/B-725 liefern aktuelle Cancel-/Projektwechsel-/Parallelbelege;
  B-762/B-883/B-884 reale Video-Shutdown-/Hardexit-Belege. Keine redundante
  Wiederholung gemaess D-078/User-Minimaltestvorgabe.
- Offen: einmaliger Kombinationszyklus, 30-Minuten-Soak, Kalt-VRAM-Gate und
  B-774-Realbeweis. App geschlossen. Ollama PID 1464 ueberlebte direkten
  Postcheck, war 22:09 beendet; spaeter Endzeitpunkt/Ursache unbekannt.
- Evidence: `docs/superpowers/synthesis/stab4-ollama-ownership-races-2026-08-25.md`.
- Naechste einzige Task: `STAB-4 / einen gezielten Kombinationszyklus Audio,
  Video, Ollama, Preview, Export, Cancel, Projektwechsel und Shutdown
  ausfuehren`.

## STAB-4 B-726 agent-complete — 2026-08-25

- Oeffentliche `compute_motion_scores()`-API mit echtem HEVC-10-Bit-Video;
  RAFT Small auf GTX 1060/cuda:0, motion=0.8859, kein CPU-Fallback.
- Lease `motion_scores` umfasste Load, drei Inferenzen, Cleanup und Unload
  fuer 7034.5 ms. Konkurrenzthread: 220 blockierte, 0 erfolgreiche
  Lock-Erwerbungen; Lock danach frei.
- Fokus `tests/test_services/test_b726_motion_execution_lock.py`: 2/2.
- Kein Produktcodefix; Vault-Userstatus unveraendert. Kombiniertes Cancel-/
  Soak-Endgate und Kalt-VRAM-Gate bleiben offen.
- Evidence: `docs/superpowers/synthesis/stab4-b726-raft-direct-live-2026-08-25.md`.
- Naechste einzige Task: `STAB-4 / Ollama-Prozessbesitz und Shutdown-/Cancel-/
  Projektwechsel-Races live verifizieren`.

## STAB-4 B-725 agent-complete — 2026-08-25

- UI-Stream-Copy real gestartet; FFmpeg PID 7732 lief zeitgleich zu htdemucs
  Chunk 1/12 auf GTX 1060/cuda:0. Copy haelt GPU_EXECUTION_LOCK nicht.
- TASKS-Cancel fuer Convert und Stem; kein FFmpeg-Rest, App PID 3392
  responsiv, DB quick_check ok. Zwei Outputs ffprobe-parsebar, Codec erhalten.
- B-725/B-401 Fokus `3 passed in 0.83s`; kein Produktcode geaendert.
- 142 lokale Testoutputs aus aktiven Outputpfaden entfernt und recoverable in
  vier `converted_b725_quarantine_*20260825`-Verzeichnisse verschoben
  (ca. 1.4 GB). Quellen unangetastet; nichts committed.
- Evidence: `docs/superpowers/synthesis/stab4-b725-copy-concurrency-2026-08-25.md`.
- Naechste einzige Task: `STAB-4 / B-726 oeffentlichen RAFT-Direktpfad unter
  Execution-Lease live verifizieren`.

## STAB-4 B-723 agent-complete, VRAM-Gesamtgate offen — 2026-08-25

- Echter htdemucs-Lauf auf GTX 1060/cuda:0: Projekt-Open waehrend Task
  blockiert; TASKS-Cancel kooperativ; danach Projektordner-Dialog wieder frei.
- Neuer RED/GREEN-Fix: Exception-Traceback-Frames werden samt GPU-Referenzen
  vor GC/empty_cache unter `GPU_EXECUTION_LOCK` geleert. Fokus 3/3,
  PyCompile/Ruff gruen.
- Neuer App-Prozess PID 3392; Cancelpfad responsiv; DB quick_check ok,
  Kernzaehler unveraendert, kanonischer `error/cancelled`-Status.
- Ehrliche Grenze: kalte GPU-Baseline 338 MiB, 81 s nach Cancel 1151 MiB;
  STAB-4-Gesamtgate +512 MiB bleibt rot. B-723-Lockordnung trotzdem real
  belegt; kein Agent-`fixed`-Marker.
- Evidence:
  `docs/superpowers/synthesis/stab4-b723-gpu-cancel-project-switch-2026-08-25.md`.
- Naechste einzige Task: `STAB-4 / B-725 CPU-/Copy-Konvertierung ausserhalb
  GPU-Lease live verifizieren`.

## STAB-3 LLM-Pfade agent-complete — 2026-08-25

- Konfiguriertes Chatmodell wird seit B-896 Commit `90e1472` durch
  LocalAgentService/Orchestrator respektiert.
- `qwen2.5:3b`, Ollama 0.21.2, GTX-1060/CUDA0: echter ChatDock-Pfad lieferte
  Learn, Recall, Stats und Explain. Learn persistierte Note #2; DB
  `quick_check=ok`; Recall fand exakten Marker; Explain Decision 821.
- B-897 Commit `50ce61d`: Learn-Toolargumente normalisiert; Fokus 7/7,
  PyCompile/Ruff/Diffcheck gruen.
- Ehrliche Grenze: aktueller Non-Tool-ChatDock-Lauf nicht bestanden. B-738
  besitzt User-`fixed`, echten headless Non-Tool-Beleg vom 11.08 und aktuellen
  Regressionstest; erneuter Livepfad wurde nach Useralternative uebersprungen.
- Evidence: `docs/superpowers/synthesis/stab3-llm-paths-2026-08-25.md`.
- STAB-3 `agent-complete-await-user-marker`; App PID 8660 responsiv;
  kein Push.
- Naechste einzige Task: `STAB-4 / B-723 echten GPU-/Cancel-/Projektwechsel-
  Pfad live verifizieren`.

## STAB-3 Auto-Edit B agent-complete — 2026-08-25

- Run 11: identische 112 Playback-Offsets, Seed 42, 101 Input-Kontexte und
  Kandidatenreihenfolgen gegen Referenz Run 9.
- Negativ Scene 127/Clip 106: Memory `0.1 -> 0.0793456709`, Rang
  `1/17 -> 4/17`; positiv Scene 32/Clip 19: Memory
  `0.1 -> 0.1206543292`, Brainfinal/Softscore ebenfalls hoeher.
- B-892 Commit `7ebdaf2`; 5 fokussierte Tests gruen. Run 11 live:
  101 Decisions/Cuts, 18 Achsen, 101/101 Brain V3, Timeline ohne
  Gaps/Overlaps/Medienwiederholung.
- Run 10/11 Clipauswahl identisch: Score-Richtung korrigiert, keine positive
  Endauswahl-Aenderung im Pool-1/1-Datensatz behauptet.
- `weights.db` unveraendert; B-893/B-894/B-895 separat offen.
- Evidence: `docs/superpowers/synthesis/stab3-auto-edit-b-2026-08-25.md`.
- Status `agent-complete-await-user-marker`; kein Push. App PID 4088 sauber
  beendet; kein PB-Studio-Stability-Prozessrest.
- Naechste einzige Task: `STAB-3 / Tool- und Non-Tool-LLM-Pfade muessen
  Recall/Stats/Explain/Learn erhalten`. LLM-AN bleibt wegen B-867/Modellwahl
  user-blockiert.

## STAB-3 Feedback/Persistenz agent-complete — 2026-08-25

- Echter Timeline-UI-Pfad: negativ Decision 795/Scene 127, positiv Decision
  821/Scene 32.
- Nach Flush, sauberem Shutdown und komplettem Neustart: 2 Feedbackevents,
  2 bewertete Decisions, 2 `mem_learned_pattern`, accept/reject je 1,
  138 globale Achsengewichte; beide DB-quick_checks ok.
- B-889 Overlay-Hit-Test, B-890 Qt-Lifecycle und B-891 Pacing-Run-
  Rehydration korrigiert; alle `agent-fixed-await-user`.
- Produktcommits: B-889/B-890 `ed13280`; B-891 `2ed783f`.
- Gezielte RED/GREEN-Fokuschecks, PyCompile, Ruff und Diffcheck gruen. Kein
  breiter Sweep. B-890 ohne nativen Dump; exakte Crashinstruktion unbewiesen.
- Evidence:
  `docs/superpowers/synthesis/stab3-feedback-persistence-2026-08-25.md`.
- App beendet. Kein Push. Kein User-`fixed`-/STAB-3-Phasenmarker.
- Naechste einzige Task: `STAB-3 / Auto-Edit B mit identischen Eingaben;
  erklaerbare Aenderung nur adressierter Beitraege und Kandidatenrangfolge
  beweisen`.

## STAB-3 Negativkontrolle agent-complete — 2026-08-24

- Direkter Run 6/7 rot; B-887 belegt Playback-Offset-Inputdrift statt Brain-
  oder RNG-Defekt. Produkt-F-001 blieb unveraendert.
- Kontrollpaar Run 8/9 mit exakt restaurierten 112 Offsets: Decisions,
  Timeline, Brain-Cuts und Post-Offsets digestidentisch.
- 101/101 Brain V3, Rang 1/109, 18 Achsen; keine Pattern-/Feedback-/Weight-
  Mutation; quick_checks/Errorgate gruen.
- B-887 `agent-fixed-await-user`; B-888 separates offenes Tie-Break-Risiko.
- Evidence: `tests/qa_artifacts/stab3_negative_control_20260824.json`.
- Naechste einzige Task: `STAB-3 / Gezieltes positives/negatives Feedback,
  Flush, kompletter App-Neustart`. App PID 3276 offen. Kein Push.

## STAB-3 Auto-Edit A agent-complete — 2026-08-24

- Echter PID-gebundener UI-Lauf 6: 101 Decisions/Cuts ueber exakt 337.137 s.
- 101/101 Brain V3, Rang 1 aus je 109 Kandidaten; je Decision exakt 18
  kanonische Brain-Achsen.
- Timeline ohne Gaps, Overlaps oder Medien-/Szenenwiederholung; Waveform,
  Marker, Thumbnails und Cutliste sichtbar; Crashscan 0.
- Ohne Feedback: Patterns 0, Feedback 0, `weights.db` unveraendert.
- B-886 Preflight-Modellbindung Commit `c34aa80`. Evidence:
  `tests/qa_artifacts/stab3_auto_edit_a_20260824.json`.
- Status `agent-complete`; Usermarker offen. Naechste einzige Task:
  `STAB-3 / Negativkontrolle ohne Feedback muss deterministisch bleiben`.
  Kein Push.

## STAB-3 Preflight agent-complete — 2026-08-24

- Stability-Projekt/DB, 28 Videoquellen, 96 Timelinezeilen und Audio per
  Digest fixiert; `PB_PACING_SEED=42`.
- Isolierte Settings: LLM AUS, Studio Brain AN; keine Modellwahl geaendert.
- Ollama 0.21.2 plus Manifest-/Model-/Projektor-Digests, SigLIP-HF-Revision,
  CLAP/Enricher-Versionen erfasst. CLAP-Cache fehlt lokal; kein Download.
- DB-Baseline: `mem_pacing_run=5`, `mem_decision=486`,
  `mem_learned_pattern=0`, Feedbackevents 0; quick_check ok.
- Evidence: `tests/qa_artifacts/stab3_preflight_freeze_20260824.json`.
- Naechste einzige Task: `STAB-3 / Auto-Edit A inklusive Rangfolge, 18
  Brain-Achsen, Pacing, Pattern und Gewichten`. Kein Push.

## W8 agent-complete / STAB-3 naechste Task — 2026-08-24

- No-Task, Running-Audio, Running-Video und Running-Export live bestanden.
- Final-Export bei 57 % und real aktivem GTX-1060-NVENC-FFmpeg per
  asynchronem WM_CLOSE plus sofortigem Task-Prompt-Yes kooperativ abgebrochen.
- Exit 0; App/FFmpeg/Ollama/Demucs 0; kein Partialoutput/Temp; WER 0;
  DB quick_check ok und Kerncounts 1/125/3/96/147/1053 unveraendert.
- Ehrliche Grenze: kein unmittelbarer Pre-Logical-Digest fuer Final-Lauf;
  verworfener Host-AppData-Zwischenstart neu serialisierte Host-Settings,
  Inhaltsdrift mangels Pre-Baseline unbekannt.
- W8 `agent-complete-await-user-marker`; User setzt Marker.
- Naechste einzige Task:
  `STAB-3 / Medien, Seed, Settings und Modellversion fixieren`.
  Keine Modellwahl eigenmaechtig aendern. Kein Push.

## B-879 agentseitig live gruen / W8 Export weiter offen — 2026-08-24

- W8-Exportstart abortete zweimal waehrend Projekt-Auto-Resume, bevor ein
  Export-Klick erfolgte. Verwaiste Ollama/Conhost/FFmpeg-Kinder wurden jeweils
  exakt beendet.
- Ursache 1: administrativer `pacing_curve.reset_curve()` emittierte
  `curve_changed` und startete ungewollt Cut-Worker mitten im Projektwechsel.
  Fix: `QSignalBlocker` nur um diesen Reset.
- Ursache 2: Produktions-Perf-Watchdog monkey-patchte
  `QApplication.notify` mit Python. Qt betrat Override auch aus QThreads;
  beide Fatal-Stacks endeten dort. Identischer A/B-Start ohne Patch blieb
  stabil.
- Produktionsfix: `install_watchdog()` belaesst Qt-Dispatcher nativ.
  Freeze-Probe (`logs/freeze_stacks.log`), App-Logging und UI-Action-Logging
  bleiben aktiv.
- Normaler Fixed-Start via `main.py`: sichtbares/responsives Fenster,
  Auto-Resume, Projekt, 96 Timeline-Records, Medien, vier Stems, CUDA und
  Ollama-GPU-Check gruen. Kein Fatal/Abort, kein ungewollter Cut-Worker.
- Weitere 20 s stabil; WM_CLOSE + Cleanup gruen; danach PB Studio/Ollama/
  FFmpeg/Kinder 0.
- Gezielt: 8 passed; `py_compile`, Ruff, `git diff --check` gruen. Review ohne
  Critical/Important Findings. B-879 `agent-fixed-await-user`; User setzt
  `fixed`.
- Beleg: `tests/qa_artifacts/b879_live_verdict_20260824.json`. W8
  Running-Export bleibt einzige offene Teilpruefung. Kein Push angeordnet.

## B-884 agentseitig live gruen / W8 Export weiter offen — 2026-08-24

- Korrektur: vorherige Aussage „PB Studio/Ollama/Kinder 0“ nach Running-Video-
  Shutdown war falsch/zu frueh. PB Studio PID 4220 und Frame-FFmpeg PID 10808
  lebten unsichtbar weiter.
- Root Cause: daemonischer Python-Hard-Exit wurde erst nach
  `super().closeEvent()` gestartet und strandete bei Qt/COM `0x80010108` selbst.
  Windows beendet App-Kinder beim Parent-Exit nicht automatisch.
- Fix: Bei Lingering-Tasks erfolgt Hard-Exit nach synchronem Cleanup direkt vor
  Qt-Basis-Close; rekursive psutil-Kinder werden vorher beendet/max. 2 s
  abgewartet.
- Ein FrameExtract-`Popen`/Cancel-Versuch erzeugte zweimal reproduzierbar
  Qt6Core-Startup-Access-Violations und wurde vollstaendig zurueckgenommen;
  `workers/video.py` und `ui/widgets/video_preview.py` bleiben unveraendert.
- RED/GREEN `2 passed`; PyCompile/Ruff gruen. Echter B-570-Prozess mit 30-s-
  stubborn QThread Exit 0. Temporaere 60-s-Kindprobe PID 6612 nach Parent-Exit
  `CHILD_ALIVE=False`; Fixture danach ohne Diff.
- Normaler echter W8-App-Shutdown: PB Studio/Ollama/Frame-FFmpeg 0, SQLite
  `quick_check=ok`, 125 Videos/147 Szenen/3 Audio/96 Timeline/1053 Status,
  kein neuer WER-Crash.
- Ehrlicher Status: B-884 `agent-fixed-await-user`; Fix, Test, Lesson und dieser
  Handoff liegen im selben Commit. W8
  Running-Export bleibt einzige offene Teilpruefung. Kein Push angeordnet.

## B-883 agentseitig live gruen / W8 Video-Branch gruen — 2026-08-24

- Root Cause: `VideoPreviewWidget._on_frame_thread_finished()` bereinigte
  mutable aktuelle Felder. Alter queued Cleanup konnte dadurch neuen laufenden
  Frame-QThread loeschen -> Qt6Core `c0000409`, Fast-Fail-Subcode 7.
- Fix: Jeder Frame-Job wird als QThread/Worker-Paar registriert; finished nimmt
  echten Sender und bereinigt nur dieses Paar. Aktuelle Felder nur bei
  Identitaet leeren; doppeltes hideEvent-`deleteLater` entfernt.
- Echter RED, danach Target `1 passed`; PyCompile, Ruff, Diffcheck gruen.
- Live: gleicher W8-Autoload `video 1097 -> 125`; Pipeline 112 Videos auf GTX
  1060/CUDA0 bis Clip 102 statt frueherem Crash nach ~7. Kein neuer WER-Event.
- Running-Video-Shutdown: physisches Fenster-X, Save-Yes, Active-Task-Yes;
  kooperativer Cancel, RAFT/SigLIP unload, Ollama/Scheduler cleanup, danach
  PB Studio/Ollama/Kinder 0. SQLite quick_check ok; 125 Videos/122 Szenen/
  3 Audio/96 Timeline.
- Ehrlicher Status: B-883 `agent-fixed-await-user`. W8 Running-Export bleibt
  offen. App beendet; kein Push angeordnet.

## B-882 agentseitig live gruen / W8 Audio-Branch gruen — 2026-08-24

- Root Cause: Audio-Aktionsbuttons wurden bei aktivem `audio_combo` enabled;
  `_get_selected_audio_track()` akzeptierte nur Checkbox/Maus-Selektion und
  beendete `Stems` still.
- Minimalfix: Checkbox zuerst, Maus-Selektion danach, aktiver Combo-Track als
  letzter Einzeltrack-Fallback. Batch-/Video-Pfade unveraendert.
- Echter RED vor Fix; danach Regression plus B-293-Prioritaet `2 passed`;
  PyCompile und Ruff gruen.
- Live nach Neustart im W8-Projekt: Checkbox leer, keine Mauszeile, Maceo Plex
  rechts aktiv; physischer `Stems`-Klick erzeugt sichtbaren Running-Task.
- W8 Audio-Shutdown: physischer Fenster-X bei Running/67 % (Chunk 9/12),
  Dirty-Dialog `Yes`; danach App/Ollama/Demucs/FFmpeg 0 Prozesse,
  DB `quick_check=ok`, Kerncounts 1/125/3/96/342/43 unveraendert.
- Vier bestehende Stems nach Abbruch ffprobe-lesbar und mit 337.137347 s
  vollstaendig; Quelle 337.137333 s. Kein partieller Output.
- Ehrlicher Status: B-882 `agent-fixed-await-user`; W8 insgesamt offen.
  Naechste W8-Branches: laufender Video-Task, laufender Export-Task.
- Belege: `tests/qa_artifacts/w8_shutdown_audio_task_20260824.png` und lokale
  W8-Prompt-/Cleanup-Screenshots. Kein Push angeordnet.

## B-881 agentseitig live gruen / W7-Matrix agent-complete — 2026-08-24

- Echter Standard-xfade-Export ueber UI mit 95 Video-/1 Audioeintrag;
  letzter Clip real HEVC Main10/yuv420p10le, 8.0 s/240 Frames.
- Root Causes fuer vorherige +38 Frames: seeked Inputs ohne PTS-Nullung und
  unabhaengige per-Input-`fps`-Ceils. Fix: `setpts=PTS-STARTPTS` je Input plus
  einmaliger Composite-Cap auf gerundete Timeline-Slot-Frames.
- Vor Fix 335.200 s/10056 Frames; nach Fix 333.933333 s/10018 Frames bei
  Video-Timelineende 333.9385 s. H.264 Main/yuv420p 1920x1080/30 fps, AAC
  48 kHz Stereo 333.930 s.
- CUDA0-Video- und Audioseeks bei 0/166/333 s jeweils Exit 0. UI-Task
  `Fertig` nach 87.5 s; App responsiv; kein B-603-Fallback/Exportfehler.
- Gezielt B-881/B-687/B-707: 8 Tests gruen; PyCompile, Ruff, Diffcheck gruen.
- Belege: `tests/qa_artifacts/w7_b881_10bit_verdict_20260824.json` und
  `tests/qa_artifacts/w7_b881_10bit_after_20260824.png`.
- Ehrlicher Status: B-881 `agent-fixed-await-user`; W7-Matrix agentseitig
  komplett. `fixed`-/Phasenmarker bleibt Userrecht.
- Naechste einzige Task: `LIVE-VERIFY / W8 Persistenz/Shutdown ohne und mit
  laufenden Audio-/Video-/Exporttasks`.
- Branch `main`; B-881 liegt in diesem Commit; kein Push angeordnet.

## Masterplan reaktiviert — 2026-08-23

- User brach Audit-Fortsetzung nach lokalem B-860-Commit `d365257` ab.
- Aktiv: `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16`.
- W4 autonomer Scope abgeschlossen; VLM/B-867 bleibt User-Modellentscheidung.
- B-873 Commit `ea98dbe`: sichtbare Video-Combo initialisiert Preview real.
- B-874 Commit `8ac512f`: Timeline-Reload ohne Fremdscene-Warnungen live belegt.
- W5 `agent-complete-await-user-marker`: Preview/Seek, Move, Trim, Lock,
  Anchor, Undo/Redo und Projektwechsel/Rueckkehr live; Verdict
  `tests/qa_artifacts/w5_schnitt_timeline_verdict_20260823.json`.
- B-875/B-876/B-877 Commits `818e45e`/`1e77c3a`/`460a960`.
- W6 autonom `agent-complete-non-llm`: Flat/Custom jeweils Brain AUS/AN bei
  LLM AUS live `pass_with_known_warnings`; vier Verdicts unter
  `tests/qa_artifacts/w6_*_verdict_20260823.json`. LLM-AN bleibt wegen B-867
  User-Modellentscheidung; kein W6-Gesamtmarker.
- Naechste einzige Task: `LIVE-VERIFY / W7 Export Hard-Cut/xfade, 8-/10-bit,
  alle Presets, Cancel/Retry; ffprobe prueft Dauer, Frames, Audio und Seek`;
  zuerst feste Timeline + Hard-Cut-Baseline.
- Auditplan bleibt pausiert. Readiness-Re-Gate und externe Trust-Authority offen;
  kein Audit-Snapshot oder Produktaudit ausgefuehrt.

## B-859 Code-final / Live-Verifikation offen — 2026-08-22

- B-859 Code-/Testcommit: `80c2c24`.
- Readiness validiert Artifact-Listen/-Rows samt sämtlichen set-/Git-/Basis-
  relevanten Skalaren vor Konsum; `bytes` muss echter nichtnegativer `int`
  sein. Hostile Struktur stoppt vor Bundle, Basis und Gates.
- Finalreview fand und derselbe Fix schloss zusätzlich High-TOCTOU: CLI las
  Manifest/Authority nach erfolgreichem Verify erneut und berechnete Basis aus
  ungeprüften neuen Bytes. Interner Resultkern liefert jetzt Basis + Authority
  aus genau einem validierten In-Memory-Snapshot; öffentliche Fehlerlisten-API
  bleibt kompatibel.
- Belege: echte REDs für `path={}`, Nicht-Dict-Row und erfolgreichen CLI-
  Zweitread nach hostile Dateiersatz; danach drei Fokusnodes `Ran 3 tests in
  0.232s — OK` mit sieben hostile Scalarfällen sowie valid/missing/duplicate/
  foreign/Snapshot; Ruff, Diffcheck sowie Compliance- und Code-RE-FINAL-GO
  ohne C/H/M/L.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: operationaler Readiness-Lauf mit real provisionierter externer
  Trust-Authority, Schlüsselpins und Live-Attestations.
- Nächster sequenzieller Phase--1-Schritt: Readiness-Re-Gate gegen aktuellen
  Stand; struktureller Status getrennt vom externen operationalen NO-GO.

## B-858 Code-final / Live-Verifikation offen — 2026-08-22

- B-858 Code-/Testcommit: `214b17d`.
- Runtime-Harness validiert `dependencies.stdlib_modules` und Scenario-
  `required_stdlib_modules` vollständig als Listen nichtleerer Strings, bevor
  Duplicate- oder Exact-Set-Prüfungen `set()` verwenden. Bestehende
  Duplicate-/Exact-Set-Semantik blieb unverändert.
- Belege: zwei echte RED-CLI-Typcrashfälle; danach gezielt `3 passed, 2
  subtests passed`; exakte feldspezifische Exit-2-Fehler ohne Traceback,
  stdout, Evidence-Mutation oder Run-Verzeichnis; B-850-Regression und
  gültiger nichtleerer Positivfall grün; Ruff, PyCompile, Diffcheck sowie
  Compliance- und Code-FINAL-GO ohne C/H/M/L.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: echter separater CLI-Prozess im produktionsnahen Authority-/Registry-
  Pfad.
- Nächster sequenzieller Phase--1-Fix: B-859 Readiness-Artefaktrows/-pfade vor
  Set- und Basis-Nutzung validieren.

## B-857 Code-final / Live-Verifikation offen — 2026-08-22

- B-857 Code-/Testcommit: `cb9c277`.
- Reviewer-Enrollment und Signoff-Finalisierung prüfen jetzt unter dem
  gemeinsamen Kernel-Lock zuerst den exakten B-852-Initialisierungsmarker am
  selben expliziten Git-Common-dir. Missing, invalid oder unlesbar endet als
  kontrolliertes JSON `ok:false`/Exit 2; kein Auto-Bootstrap.
- Belege: vier echte RED-CLI-Fälle; danach sechs Marker-/CLI-Tests und drei
  bestehende Markerregressionen grün; gesamte Reviewer-Komponente `51 passed,
  116 subtests passed`; Ruff, PyCompile, Diffcheck und zwei unabhängige
  Finalreviews grün ohne C/H/M/L.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: echter separater CLI-/Registry-Mehrprozesslauf.
- Nächster sequenzieller Phase--1-Fix: B-858 Runtime-stdlib-Modultypen vor
  Set-Nutzung validieren; danach B-859 Readiness-Artefaktrow-Typgate.

## B-854 Code-final / Live-Verifikation offen — 2026-08-22

- B-854 Code-/Testcommit: `682ba2f`.
- `_Lock.__exit__` prueft Ownership vor dem Leeren von `self._fd`, leert nur
  eigenen Token/PID/Path-gebundenen Payload und garantiert Descriptor-Close
  auch bei erwartetem oder unerwartetem Cleanupfehler. Body-Primaerfehler
  bleibt vorrangig; fremder Payload/Replacement bleibt unveraendert.
- Belege: echter RED fuer uebersprungenes Close; sechs gezielte Cleanuptests
  `6 passed`; gesamte Registry-Komponente `67 passed`; Ruff, PyCompile,
  Diffcheck sowie Compliance- und unabhaengiger Code-Review gruen ohne
  verbleibendes C/H/M/L-Finding.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: echter separater Mehrprozess-/CLI-Lockpfad.
- Naechster sequenzieller Phase--1-Schritt: autoritative Restfinding-Inventur
  und Readiness-Re-Gate. Produkt-Audit/App-Fixes bleiben bis gruener Phase--1
  plus real provisionierter Trust-Authority gesperrt.

## B-856 Code-final / Live-Verifikation offen — 2026-08-22

- B-856 Code-/Testcommit: `559aceb`.
- Reviewer-CLI normalisiert konkret erwartete OSError-/Unicode-/JSON-Decode-
  Fehler als JSON `ok:false` mit Exit 2; Programmer-/Validatorfehler bleiben
  sichtbar. Signier-Cleanup versucht beide eigenen Pfade best-effort und
  bewahrt das exakte Primaerfehlerobjekt.
- Belege: acht echte RED-Faelle; danach Fokus `3 passed, 6 subtests passed`,
  gesamte betroffene Datei `45 passed, 116 subtests passed`; Ruff, PyCompile,
  Diffcheck sowie Compliance- und unabhaengiger Code-Review gruen.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: echter separater CLI-Prozess mit realem I/O-Fehler.
- Naechster sequenzieller Phase--1-Fix: B-854 stale eigener Agent-Session-
  Lock-Payload (low). Produkt-Audit/App-Fixes bleiben bis Phase--1-Gate plus
  realer Trust-Authority gesperrt.

## B-855 Code-final / Live-Verifikation offen — 2026-08-22

- B-855 Code-/Testcommit: `ca46946`.
- Reviewer-Harness validiert signierte Spawn-Rolle/Parent vor Membership,
  delegiert Registry-Schema an `agent_session._validate_registry` und
  preflightet direkte Finalize-Inputs vor Lock/I/O.
- Belege: sieben echte RED-Faelle; danach Fokus `3 passed, 6 subtests passed`,
  gesamte betroffene Datei `42 passed, 110 subtests passed`; Ruff, PyCompile,
  Diffcheck sowie Compliance- und unabhaengiger Code-Review gruen.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: echter separater CLI-Prozesspfad.
- Naechster sequenzieller Phase--1-Fix nach Auswirkung: B-856 rohe erwartbare
  Reviewer-CLI-I/O-Fehler. Danach B-854 low. Produkt-Audit/App-Fixes bleiben
  bis Phase--1-Gate plus realer Trust-Authority gesperrt.

## B-853 Code-final / Live-Verifikation offen — 2026-08-22

- B-853 Code-/Testcommit: `16db4d8`, synchron auf `main` und `origin/main`.
- Reviewer-Contract validiert Pattern-Elemente und skalare Reviewer-/Pair-/
  Assignment-/Signoff-Felder vor jeder Set-/Dict-Membership. Unhashbare,
  authority-signierte Werte enden kontrolliert als `ContractError`/CLI-Exit 2.
- Belege: RED-Matrix mit 12 hostile Typfaellen; danach Fokus `2 passed, 12
  subtests passed`, gesamte betroffene Datei `39 passed, 104 subtests passed`;
  Ruff, PyCompile, Diffcheck sowie Code- und Compliance-Review gruen.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: echter signierter CLI-Prozesspfad.
- Naechster sequenzieller Phase--1-Fix nach Auswirkung: B-855 weitere
  Reviewer-Roster-Typcrashflaechen. Danach B-856, danach B-854. Keine neue
  Branch; Produkt-Audit/App-Fixes bleiben bis Phase--1-Gate plus realer
  Trust-Authority gesperrt.

## B-852 Code-final / Live-Verifikation offen — 2026-08-22

- B-852 fachlich reviewter Code-Snapshot: `5cdbb1a`. Governance-Handoff und
  Pflichtlektion liegen im aktuellen `HEAD` (`git log -1 --oneline`).
- B-852 verhindert False-PASS/Claim-Verlust bei Registry-Lese-, Schema- und
  Missing-Fehlern. Operative Befehle verlangen gültigen Marker + Registry.
- Erstzustand nur explizit: `agent_session.py bootstrap --initialize-empty`;
  Legacy nur `--migrate-existing`. Kein Auto-Bootstrap in Start/Handoff.
- Registry/Marker: unique Temp, vollständiger Write, fsync, kontrollierter
  Close, no-overwrite Hardlink. Migration descriptor-/identity-gebunden.
- Belege: direkte Registry-Komponente 62/62 grün; PyCompile, Ruff,
  PowerShell-Parser, Diffcheck grün; Compliance/Code/Runtime FINAL-GO ohne
  Critical/High/Medium/Low-Rest.
- Ehrlicher Status: `code-fix-pending-live-verification`, nicht `fixed`.
  Offen: isolierte echte CLI-Prozesspfade für beschädigte/missing Registry,
  Start/Handoff und beide Bootstrapmodi.
- Nächster sequenzieller Phase--1-Fix: B-853 Reviewer-Contract-Typcrash bei
  Enrollment. Produkt-Audit/App-Fixes bleiben bis Phase--1-Gate und realer
  Trust-Authority gesperrt.

> ## AKTUELLSTE ÜBERGABE — Claude Code an Codex, 2026-08-15
>
> **Vollständige Übergabe:
> [`HANDOFF-CLAUDE-AN-CODEX-2026-08-15.md`](./HANDOFF-CLAUDE-AN-CODEX-2026-08-15.md)**
>
> Wer nach dem 15.08.2026 an diesem Repository arbeitet, liest **zuerst** jenes
> Dokument. Es enthält den Stand der Pacing-/Schnitt-Architektur (musik-
> getriebener Schnitt statt Beat-Raster), alle 16 Commits der Sitzung mit
> Messwerten, die offenen Entscheidungen des Nutzers — und einen Abschnitt mit
> den Fehlern, die ich selbst gemacht habe, damit sie sich nicht wiederholen.
>
> Kopf-Stand: `d242987` auf `main`, synchron mit `origin/main` (26 Commits
> dieser Sitzung, inkl. B-844 nach einem Bluescreen — nichts verloren).
> Die fünf untrackten Pfade im Worktree gehören einer fremden Sitzung (D-089)
> und wurden bewusst nicht angefasst.

## B-821/B-823/B-824 gefixt / B-825 aktiv 2026-08-14 (newest)

- **B-824**: Stem-Pfade werden jetzt PROJEKTRELATIV gespeichert
  (`storage/stems/...`, POSIX-Trenner). Neu in `services/stem_router.py`:
  `to_project_relative()`; `resolve_stem_path()` loest relative Werte gegen
  `APP_ROOT` auf. Schreiber umgestellt in `audio_pipeline/stages.py`,
  `ai_audio_service.py` und `storage_provenance/cross_project_reuse.py`.
- **Datenmigration** Alembic `b4c5d6e7f8a9` (down_revision `a3b4c5d6e7f8`),
  bewusst konservativ: relativiert wird nur, was unter `projects.path` des
  eigenen Tracks liegt; Fremdpfade bleiben stehen; relative Werte und NULL
  unangetastet; Vergleich normalisiert Trenner und Gross-/Kleinschreibung.
  `downgrade()` macht relative Werte wieder absolut.
- **Livebeleg** (Run `20260814T0930-b824-verify`):
  `B-824: 4 Stem-Pfade projektrelativ gemacht, 4 ausserhalb des Projekts
  bewusst unveraendert gelassen`. Track im Projekt wurde relativ, Track auf ein
  fremdes Projekt blieb absolut. Alle zehn Analyse-Schritte blieben `done`,
  Stem-Selbstheilung lief weiter.
- **Wichtiger Nachzug**: der erste Livelauf zeigte `[StemPlayer] 0 Stems
  geoeffnet` — eine echte Regression. Eine systematische Suche fand ELF
  ungeschuetzte Stem-Leser (StemPlayer, Auto-Ducking, Vocal-Aktivitaet, SNR,
  DJ-Mix-Erkennung, Drum-Onsets, Storage-Migration) plus einen Schreiber
  (Cross-Project-Reuse). Alle nachgezogen. Wer kuenftig eine Stem-Spalte liest,
  MUSS durch `resolve_stem_path()`.
- **B-821**: drei `logger.warning` fuer verworfene Analyse-Klicks in
  `ui/controllers/audio_analysis.py`. **B-823**: fester RNG-Seed im
  Pacing-Vocal-Test.
- **Neu offen B-825** (high): `test_full_roundtrip_empty_db` bricht mit
  `no such column: last_used_at` beim `CREATE INDEX idx_model_registry_last_used`.
  Per Baseline-Lauf als VORBESTEHEND belegt — nicht durch B-822/B-824
  verursacht. Herkunft vermutlich der B-819-Index aus `database/models.py:564`
  (Merge `22f96b8`). Nicht mitgefixt.
- Naechste einzige Task: `ROOT-CAUSE / B-825`, danach W4.

## B-822 gefixt und live bestaetigt 2026-08-14

- `services/stem_router.py` bekam `resolve_stem_path()`/`resolve_stem_paths()`
  fuer Stellen mit echtem Dateizugriff und `points_outside_project()` fuer
  reine Zugehoerigkeitspruefungen. Angewandt an fuenf Konsumenten
  (Stem-Reuse, rehydrate, Stem-Energie, auto_ducking, Statusinferenz).
- RED 6/6 -> GREEN 6/6. Regressionslauf 721 passed, 1 failed; der Fehlschlag
  ist vorbestehend (B-823, Test ohne RNG-Seed) und per Baseline-Lauf mit
  gestashtem Fix belegt.
- **Livebeleg**: die vier Stem-Spalten wurden gezielt auf den Host-Ordner
  gesetzt, wo die Dateien real liegen. Die App meldete `stem_separation`
  daraufhin NICHT als vorhanden und separierte beim Stems-Schritt neu in den
  isolierten Projektordner statt die Host-Dateien zu benutzen. Host-Ordner
  unveraendert, Post-Manifest `pass`, fuenf Host-/Repo-DBs byte-identisch.
- Bewusst nicht geaendert: die Spalten speichern weiter absolute Pfade. Eine
  Umstellung auf projektrelative Speicherung braeuchte eine Datenmigration und
  ist eine eigene Entscheidung.
- Naechste einzige Task: `LIVE-VERIFY / W4 Videoanalyse inklusive defektem
  Clip und Reanalyse`. Daneben offen: B-821 (low), B-823 (low).

## W3 Audio V2 komplett durchlaufen 2026-08-14

- Der letzte offene Teilschritt **"fehlendes Stem" ist nachgeholt und pass**
  (Run `20260814T0610-w3-stem-heal`, Baseline `f46d2eb`).
  `vocals.wav` geloescht, waehrend `stem_separation` auf `done` stand. Die App
  erkannte das fehlende Artefakt und heilte sich durch vollstaendige
  Neuseparation: `htdemucs` auf `cuda:0`, 2 Chunks, VRAM frei vor/nach
  4.91/3.39 GB, alle vier Stems neu geschrieben,
  `Analysis completed: audio/2/stem_separation (summary: {'stems': 4})`,
  Stem-SNR berechnet. Ein einziger Klick genuegte.
- Der fruehere Fehlschlag lag am **Fensterfokus**, nicht an der App: ein
  fremdes Fenster lag deckungsgleich ueber PB Studio und fing die
  Koordinatenklicks ab. Nach dem Minimieren kam der Klick sofort an.
- **Damit sind alle geplanten W3-Teilschritte live durchlaufen.** Alle drei
  Runs mit Pre-/Post-Manifest `pass`, alle fuenf Host-/Repo-DBs byte-identisch,
  Host-Stems unveraendert, 0 Prozessreste. Usermarker fuer W3 offen.
- Teil-Entlastung fuer B-822: die Regenerierung schrieb in den Projektordner.
  KEIN Beweis — die Stem-Spalten zeigten in diesem Lauf bereits dorthin. Der
  Gegentest mit Host-Pfad wurde bewusst nicht gefahren. B-822 bleibt offen.
- **B-821 entlastet und auf `low` gesenkt**: die fruehen Fehlklicks waren nicht
  zugestellt, nicht von der App verworfen. Es bleibt der Codebefund, dass ein
  leerer Auswahlzustand nur ins Konsolen-Widget geht und nie ins Logfile.
- Naechste einzige Task: `ROOT-CAUSE / B-822`, danach B-821, dann W4.

## B-820 gefixt und live bestaetigt 2026-08-14

- **B-820 gefixt**, TDD RED 3/4 -> GREEN 16, breitere Gegenprobe 125 passed,
  py_compile und Ruff gruen. `_ensure_status_done()` laesst einen bewussten
  User-Cancel (`status='error'` + `error_message=CANCELLED_MARKER`) jetzt
  stehen; der B-461-Reconcile-Pfad fuer echte Fehler bleibt erhalten.
  Der RED-Lauf bewies nebenbei, dass B-820 Audio UND Video betraf.
- **Live bestaetigt** in Run `20260814T0530-w3-b820-verify`: Cancel blieb
  `error`/`cancelled`/`completed_at=None`, kein `Reconciled status='done'`
  mehr. Vorschlag `fixed`, Marker bleibt Userrecht.
- **W3 weiter abgearbeitet**: Retry nach Cancel pass (10 Schritte `done`,
  `bpm_detection` sauber von `cancelled` auf `done`), Neustartvergleich pass
  (alle 10 Schritte ueberleben den Neustart unveraendert).
- **Offen aus W3: nur noch "fehlendes Stem"**. Drei Klickversuche auf den
  `Stems`-Button loesten nichts aus. Wahrscheinlichste Erklaerung ist ein nicht
  angekommener Koordinatenklick (fremdes Fenster im Vordergrund, `focus`
  schlug mit `Error code from Windows: 0` fehl) — nicht bewiesen.
- **Zwei neue Bugs**: B-821 (medium, Analyse-Button nach Cancel tot, meldet
  nichts ins Logfile) und B-822 (high, `audio_tracks.stem_*_path` zeigt aus
  dem isolierten Projekt heraus in einen Host-Ordner; Lesezugriff belegt,
  Schreibzugriff nicht provoziert).
- **Requirements nachgezogen**: `pywinauto`, `pyautogui`, `pygetwindow`, `mss`
  sind jetzt in `requirements-py310-cu113.txt` gepinnt, mit Begruendung im
  Kommentar. `environment.yml` zieht die Datei bereits.
- Hostschutz beider Runs: Pre-/Post-Manifest `pass`, alle fuenf Host-/Repo-DBs
  byte-identisch, graceful Shutdown, 0 Prozessreste.
- Naechste einzige Task: `ROOT-CAUSE / B-821`, danach B-822, dann W3 schliessen.

## W3 Audio V2 Live-Session / B-820 gefunden 2026-08-14

- Run `20260814T0405-w3-audio-v2` auf HEAD `22f96b8`, isolierter Root
  `C:\Users\David_Lochmann\AppData\Local\PBStudioW3AudioV2\`, Projekt als
  245-MB-Kopie von `W3-runde4-s1` (Original unangetastet).
- Live pass: App-Start und Systemcheck, Projekt-Load im isolierten Scope,
  Fehlerpfad bei fehlender Audio-Quelldatei, Cancel-Mechanik (GPU-Lock nach
  10915 ms sauber freigegeben, B-724-Vertrag griff), graceful Shutdown.
- Pre- und Post-Manifest `pass`. Alle fuenf Host-/Repo-DBs byte-identisch,
  0 Python-Prozessreste, `ollama.exe` PID 1592 war Vorbestand.
- B-758 damit erstmals in dieser Session selbst live belegt: CUDA available
  true, GTX 1060 6143 MB, kein CUDA-/NVENC-FAIL-Modal. `fixed` bleibt Userrecht.
- Gestoppt nach Erste-Fehler-Regel durch **B-820**: ein per User-Cancel
  abgebrochener Schritt wird in derselben Sekunde vom Status-Reconciler
  (`_ensure_status_done`, `services/analysis_status_service.py:750-754`) auf
  `status='done'` zurueckgesetzt, `error_message` geloescht. Der
  B-751-Cancelvertrag ueberlebt den naechsten Status-Refresh nicht.
- Offen aus W3: Retry, Neustartvergleich, fehlendes Stem.
- Umgebung: GUI-Automations-Deps (`pywinauto`, `pyautogui`, `pygetwindow`,
  `mss`) fehlten im conda-env und wurden auf Userentscheidung nachinstalliert.
  Torch/numpy/pillow/PySide6 nachweislich unveraendert. Sie stehen weiterhin
  in KEINER Requirements-Datei — ohne Userfreigabe kein Eintrag, also nach dem
  naechsten Env-Neuaufbau wieder weg.
- Synthese: `docs/superpowers/synthesis/functional-test-w3-audio-v2-2026-08-14.md`
  (in Vault gespiegelt). Bugfile: Vault `wiki/bugs/B-820-*.md`.
- Naechste einzige Task: `ROOT-CAUSE / B-820`.

## B-758/B-819 Branch-Integration 2026-08-14

- Uebernahme durch Claude Code CLI. Vor jeder Codeaenderung geprueft; zwei
  Aussagen des vorherigen Handoff-Eintrags waren nicht zutreffend und werden
  hier korrigiert:
  - Der Worktree war **nicht** clean: fuenf untrackte Pfade
    (`tests/test_clip_children.py`, `tests/test_clip_drag_diag.py`,
    `tests/test_drag_multi_step.py`, `tests/test_map_and_click.py`,
    `tests/qa_material/solo_natur_subset12/`, 113 MB). Laut D-089 dokumentierter
    Fremdbestand; unveraendert gelassen.
  - Nicht alle Arbeit lag auf `main`: der lokale Branch
    `codex/B-758-w3-recheck` (`f091108`, Fork-Punkt `6b2ce85`, ohne Remote)
    trug den B-819-Produktfix plus die B-758-Recheck-Evidenz.
- Auf Userentscheidung 2026-08-14 wurde dieser Branch per `--no-ff` nach `main`
  gemergt. Einziger Konflikt war dieser Handoff-Kopf; beide Historien bleiben
  erhalten.
- Sachstand B-758: Root Cause ist extern und belegt (Surface-HotPlug
  `DGPUPresent=0` plus `nvlddmkm`-TDR am 2026-08-02); der Systemcheck war
  korrekt rot, weil die dGPU real abwesend war. Isolierter W3-Recheck
  `20260812T1323` gruen. Vault-Status `obsolete-code-entfernt`. Keine offene
  Root-Cause-Arbeit.
- Naechste einzige Task: `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und
  fehlendes Stem`.
- Die fuenf Performance-Optimierungen (`51164df`, `89f76b3`, `d67b425`) liegen
  unabhaengig davon auf `main`.

## B-819 Live-Manifest PASS / W3 aktiv 2026-08-12

- Fix `532165f`: Legacy-Indizes werden nach Spaltenfolge/Unique-Semantik
  abgeglichen; sieben beabsichtigte Indizes leben kanonisch in ORM-Metadata.
- Fokus-Suite 4 passed; PyCompile/Ruff gruen; externer zweiter `init_db()`-
  Lauf schema- und zeilenstabil.
- Sichtbarer Run `20260812T1354-b819-live-manifest`: Manifest `pass`, Gate
  `passed: true`, App/Screenshot/Shutdown gruen, GTX-1060-CUDA-Marker komplett.
- Bootstrap-DB vor/nach exakt identisch: 442368 B, Datei-SHA-256
  `3eb0a5a2ef8722adde325506b2a07329c7c56b1317e974ecb1bf9b35a0aa43f9`,
  Schema-SHA-256
  `9984c139377ffa2e4b66482d8a4ad6183845ca56e43a14c32d961a0e7ad5240b`.
- B-819 bleibt bis Userfreigabe ohne `fixed`-Marker. Naechste einzige Task:
  W3 Audio V2 komplett, Cancel, Retry, Neustart im isolierten Projekt.
- Evidence:
  `C:/Users/David_Lochmann/AppData/Local/PBStudioB819LiveIsolated/PBStudioStability/20260812T1354-b819-live-manifest/`.

## B-758 App-Gate gruen / B-819 blockiert Manifest 2026-08-12

- Run `20260812T1323-b758-w3-recheck`, HEAD `6b2ce85`, sauberer isolierter
  W3-Harness: GTX 1060/CUDA-Appmarker komplett, Screenshot, kein CUDA-/NVENC-
  FAIL, graceful Shutdown, keine Prozessreste. Gate-JSON `passed: true`.
- Gesamtmanifest `fail`: nur isolierte Bootstrap-DB driftete 425984→512000 B.
  Inhalte identisch; 20 Indizes neu, inklusive durch Alembic
  `f0a1b2c3d4e5` entfernten Duplikaten.
- Neuer Bug B-819; Host-DBs unveraendert. Erste-Fehler-Regel stoppt W3.
- Aktuelle einzige Task: `ROOT-CAUSE / B-819 Appstart rekreiert von Alembic
  entfernte SQLite-Indizes`. Danach B-758-Manifest-Recheck, dann W3.
- Evidence extern unter
  `C:/Users/David_Lochmann/AppData/Local/PBStudioB758Isolated/PBStudioStability/20260812T1323-b758-w3-recheck/`.

## D-089 AGY-Rest abgeschlossen / B-758 aktiv 2026-08-12 (newest)

- AGY-Dirty-Stand abgeschlossen. Auto-Edit-Cache-Fix `6c1857a`; B-817-Fix
  `48a7f1c`; B-818-Fix `edb7de3`; Live-Diagnose `6867d4a`.
- Normaler Current-Appstart und Shutdown auf GTX 1060/CUDA live gruen.
  Spezielle OOM/DB-Lock/PnP-Code-45/47-Faelle nicht erzwungen; kein
  User-`fixed`-Marker.
- Fuenf Timeline-/QA-Untracked-Pfade sind Fremdbestand und unveraendert.
- Aktuelle einzige Task: `ROOT-CAUSE / B-758 Systemcheck CUDA/NVENC FAIL im
  isolierten W3-Live-Run`.
- Decision: Vault `wiki/decisions/D-089-agy-rest-vor-b758.md`; Abschluss:
  `wiki/synthesis/agy-rest-complete-2026-08-12.md`.

## B-758 blockiert W3 2026-08-02 (newest)

- Current HEAD `e85a2c2`, isolierte APPDATA/LOCALAPPDATA und exakter
  `--stability-project`-Scope.
- Systemcheck modal: `CUDA GPU FAIL`, `NVENC Encode FAIL`, GPU `0/0 GB`.
- Degradierter Start bewusst nicht gewählt; W3 muss GTX-1060-CUDA beweisen.
- Screenshot `w3-missing-stem-project-nav_20260802_213113.png`.
- Pre-Manifest `20260802T2126-w3-final-pre`; Post `20260802T2134-w3-b758-post`.
- W3-/Hostprojekt-DBs unverändert. Neu erzeugte Repo-Root-WAL/SHM extern
  gesichert und nach Prozessfreiheit recoverable entfernt.
- Damals nächste einzige Task:
  `ROOT-CAUSE / B-758 Systemcheck CUDA/NVENC FAIL im isolierten W3-Live-Run`.

## B-738 Fokus-PASS / W3 Liveverify aktiv 2026-08-02 (newest)

- Echter Orchestrator-Tool-/Non-Tool-Pfad erhaelt projektisolierten Recall.
- Non-Tool-Gateway akzeptiert nur `pb_brain_gateway=v1`; persistentes Learn
  zusaetzlich nur mit reserviertem User-Prefix wie `Merke dir:`/`Save:`.
- B-411 bleibt fuer alle anderen unerreichbaren Action-Kommandos aktiv.
- Vision-Caption und Moondream erhalten read-only Recall-Fallback plus neueste
  Cut-Erklaerung; urspruenglicher Fachprompt bleibt letzte Anweisung.
- Fokus 44 Tests plus Learn-Recall-Kreis, Ruff, Compileall und Diffcheck gruen;
  unabhaengiger Abschlussreview ohne Critical/High/Medium.
- Kein echter ChatDock-/Ollama-/Neustart-Livebeweis; B-738
  `code-fix-pending-live-verification`.
- Naechste einzige Task:
  `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.

## B-757 Fokus-PASS / B-738 aktiv 2026-08-02 (newest)

- `BRIDGE_AXIS_COUNT = len(BRIDGE_AXES)` ist kanonische Stats-Grenze 18.
- `StatsResponse`, Stats-Label und Progressbar nutzen dieselbe Grenze.
- Sechs Kernbelege plus verschaerfter 18/19-Grenztest, Ruff, Compileall und
  Diffcheck gruen. Abschlussreview ohne Critical/High/Medium.
- Kein echter App-/Stats-Panel-Livebeweis; B-757
  `code-fix-pending-live-verification`.
- Nächste einzige Task: `ROOT-CAUSE / B-738 Brain/Memory fuer alle LLM-Pfade`.

## B-737 Fokus-PASS / B-757 aktiv 2026-08-02 (newest)

- Brain-Timeline-Rating persistiert semantisch vor Pattern-Notifier; ein
  Feedback erzeugt nach Flush und DB-Neustart ein `mem_learned_pattern`.
- MemoryUpdater nutzt Debounce, Run-/Projekt-/App-End-Drain und
  Condition-Generationen; Sync-Shutdown drainiert Nachfolgefeedback.
- Fehler bleiben retrybar; atexit-Best-Effort hat keine Endlosschleife.
- Learning-Session trainiert mangels sicherer Run-/Scene-Verknuepfung ehrlich
  nur Brain-Achsengewichte. Keine ID geraten.
- Fokus 27 + 9 + 9 Tests; Ruff/Compileall/Diffcheck gruen; Abschlussreview
  ohne Critical/High/Medium. Kein App-Livebeweis; B-737 live-pending.
- Nächste einzige Task:
  `ROOT-CAUSE / B-757 Brain-Stats-Achszahl aus kanonischen Achsen ableiten`;
  danach B-738.

## B-756 Fokus-PASS / B-737 aktiv 2026-08-02 (newest)

- Sieben explizite Video-Cancelzweige nutzen `mark_cancelled()`; echte
  Exception-/Storage-Fehler bleiben `mark_error()`.
- RED 7/7; Routing plus zentraler Timestamp-Vertrag `2 passed`; Syntax, Ruff,
  Diffcheck grün. Kein Video-Live-Cancel; B-756 live-pending.
- Breite/live Tests bleiben gemäß Uservorgabe bis nach Codeaufgaben gebündelt.
- Nächste einzige Task:
  `ROOT-CAUSE / B-737 Memory-Updater Run-End-Flush und Feedback-Wiring`.

## B-755 Fokus-PASS / B-756 aktiv 2026-08-02

- Root Cause: `mark_started()` behielt bei Done→Running altes `completed_at`.
- Fix: Conflict-Update setzt `completed_at=None`.
- Drei direkte Transitionstests, Syntax, Ruff und Diffcheck grün.
- Kein UI-/Worker-Livebeweis; B-755 `code-fix-pending-live-verification`.
- Nächste einzige Task:
  `ROOT-CAUSE / B-756 Video-Cancel muss stale completed_at löschen`.

## B-754 Fokus-PASS / B-755 aktiv 2026-08-02

- Root Cause: `mark_cancelled()`-Conflict-Update behielt `completed_at` einer
  früheren Done-Row.
- Fix: `completed_at=None`; echter Done→Started→Cancel-RED/GREEN-Vertrag.
- Minimalbeweis: drei direkte Cancel-/Idempotenztests, Syntax, Ruff, Diffcheck
  grün. Kein App-/DB-Live-Retry; B-754 `code-fix-pending-live-verification`.
- Separat entdeckt: B-755 stale Altzeit während `running`; B-756 Video-Cancel
  via `mark_error("cancelled")`. Keine Mitfixes.
- Nächste einzige Task:
  `ROOT-CAUSE / B-755 Analysis-Retry running muss stale completed_at löschen`.

## B-750 Stand-6 Abschlussreview PASS 2026-08-02

- Re-Review-Lücken geschlossen: ehrliche Cancel-/Konfliktklassifizierung;
  Claim-Release bei Setupfehler, Shutdown, terminal/no-thread und Fast-Finish.
- Deterministische Race-Verträge decken BG-`str`, TaskInfo-Thread-Snapshot,
  Teilstart und terminal-before-return ab.
- Final: 65 direkte B-750/Lifecycle-Regressionen, `py_compile`, Ruff und
  `git diff --check` grün.
- Unabhängiger Read-only-Abschlussreview: PASS, keine verbleibende
  Critical-/High-/Medium-Lücke. LOW Setup-QObject nur theoretisch.
- Kein App-GUI-/Medien-Livebeweis; B-750 bleibt
  `code-fix-pending-live-verification`.
- Nächste einzige Task:
  `ROOT-CAUSE / B-754 Analysis-Cancel muss stale completed_at löschen`.

## B-750 Re-Review 8a4fef7 NOT PASS 2026-08-02

- 22/22 Reviewer-Fokus grün; Claims/Stem-Heal/Retry-all-Grundmechanik korrekt.
- Medium: Einzel-/Batch-V2 und Stem melden `User-Cancel`/`Bereits aktiv`
  weiterhin als Fehler/Fehlgeschlagen.
- Low/Medium: Claim kann bei QThread-/Signal-Setup-Exception vor Start,
  BG-`str` oder Task ohne Thread-Cleanup leaken.
- Nächste einzige Task:
  `ROOT-CAUSE / B-750 Re-Review-Follow-up: UI-Klassifizierung und Claim-Leaks`.
- B-754 wartet.

## B-750 Review-Follow-up Fokus-PASS 2026-08-02

- Review-RED: Cancel-Ehrlichkeit, Stem-Selbstheilung, Retry-all und
  Single-Flight reproduziert.
- Fix: Audio-Retry-all genau ein Full-Resume-Worker; Onset läuft `stem_gen`
  selbstheilend vor Onset; Cancel/Startkonflikt ehrlich sichtbar.
- Zentraler WorkerDispatcher-Claim: pro Projekt/Track V2↔V2 sowie
  Full/Onset↔Stem blockiert; Release erst im echten QThread-Cleanup.
- Review-RED 5/5 plus Cross-Path-RED 3/3; final 27 fokussierte Tests,
  `py_compile` und Ruff grün.
- Kein App-GUI-/Medien-Livebeweis; kein `fixed`.
- Nächste einzige Task:
  `REVIEW / B-750 Follow-up-Commit unabhängig auf Cross-Path-Single-Flight prüfen`.
- B-754 wartet.

## B-750 Review-Fund 2026-08-02

- Unabhängiger Review auf `07161bb`: 13/13 Fokus grün, aber kein PASS.
- Medium 1: Cancel wird im neuen MediaWorkspace-Handler als `Error` gemeldet.
- Medium 2: done `stem_gen` mit fehlendem Artefakt wird nur rehydriert;
  Onset-Retry baut Stem nicht selbstheilend neu.
- Medium 3: Doppelklick/Retry-all startet konkurrierende gleiche oder abhängige
  Trackworker; Checkpoint-Lock schützt nicht Stage-/DB-/Artefaktraces.
- Nächste einzige Task:
  `ROOT-CAUSE / B-750 Review-Follow-up: Cancel, Stem-Selbstheilung, Single-Flight`.
- B-754 wartet.

## B-750 Fokus-PASS / B-754 geplant 2026-08-02

- Root Cause: Statuspanel emittierte `onset_detection`/`av_pacing_curves`,
  MediaWorkspace besaß keine Dispatch-Branches. Vollpipeline-Retry hätte bei
  bereits done/degraded Stage wegen Checkpoint erneut übersprungen.
- Fix: gezielter V2-Retryworker, atomarer Zielstage-Reset, Onset mit
  rehydrierbarer Stem-Prerequisite, AV-Pacing allein.
- RED 5/5; final 13/13 fokussierte B-750/B-753/B-722-Tests, Syntax/Ruff grün.
- Kein App-GUI-/Medien-Livebeweis; Status
  `code-fix-pending-live-verification`, Usermarker offen.
- Damals geplante nächste Task:
  `ROOT-CAUSE / B-754 Analysis-Cancel muss stale completed_at löschen`.

## B-753 QThread-PASS / B-750 Next 2026-08-02

- Root Cause: `AudioPipelineV2Worker.run()` kehrte bei vor Start gesetztem
  Cancel ohne `finished`/`error` zurück; Dispatcher/QThread/UI-Batch konnten
  offen bleiben.
- Fix: genau ein terminaler `User-Cancel vor Start`-Transport; keine Stage,
  kein AnalysisStatus-Write.
- RED 2/2 exakt reproduziert; final 15/15 fokussierte B-753/B-751/B-724-
  Tests sowie Syntax/Ruff grün.
- Erzwungenes echtes QThread-Interleaving: Thread endet binnen 2 s, exakt ein
  Terminalsignal. Kein App-GUI-Liveklick; `fixed`-Usermarker offen.
- Nächste einzige Task:
  `ROOT-CAUSE / B-750 Audio-V2-Retry onset/AV-Pacing verdrahten`.

## B-751 Live-PASS / B-753 Next 2026-08-02

- Audio-V2 AV-Pacing wurde im isolierten STAB-W3 bei Chunk 1 sichtbar
  abgebrochen.
- Worker markiert Cancel retry-faehig; Task bleibt `cancelled`; B-724 loggt
  INFO statt `Worker-Fehler`.
- Batch stoppt ohne `_v2_done`-Erhoehung und ohne falsches `Fertig`.
- 13/13 Fokus + angrenzende B-713/B-724, Syntax/Ruff gruen.
- Current-live: kein Worker-/Analysis-Error, kein Batch-Erfolg, keine neue
  UI-Exception; App responsive und graceful beendet.
- Host-DB/WAL/SHM: 15/15 Pre/Post-Signaturen unveraendert. Isolierte W3-DB:
  quick_check ok, Alembic Head, WAL/SHM absent.
- B-751 Code+Live abgeschlossen; `fixed`-Usermarker offen.
- Neue getrennte Befunde: B-753 Pre-Start-Cancel ohne Terminalsignal; B-754
  stale `completed_at` nach Cancel.
- Damalige nächste Task:
  `ROOT-CAUSE / B-753 Audio-V2 Pre-Start-Cancel terminalisieren`.

## B-752 Live-PASS / B-751 Next 2026-08-02 (newest)

- Audio-V2 Resume mit neun geskippten Stages erzeugte neun Crashdialoge:
  `bpm=None` wurde als Float formatiert.
- B-752 Fix filtert None/nichtnumerische Werte; RED/GREEN 4/4, Syntax/Ruff.
- Echter Resume-Pfad: null neue Exceptions/Crashdialoge, App responsive,
  Screenshot und graceful Shutdown gruen; Host-DB unveraendert.
- Cancel stoppte AV-Pacing bei Chunk 1 nach 29.8 s kooperativ.
- B-751 bleibt: Cancel wird als Analysis `error` und Task `Worker-Fehler`
  behandelt; Controller-Erfolgstextpfad ist ebenfalls offen.
- Naechste einzige Task:
  `ROOT-CAUSE / B-751 Audio-V2 User-Cancel als cancelled statt error/Erfolg`.

## B-748 Stability-Projektsperre Current-live 2026-08-02 (newest)

- W3-Start oeffnete versehentlich Host-Projekt `abnahme-block-c2`; App sofort
  graceful beendet, keine Audioanalyse gestartet.
- Host-DB aus bewiesener Vor-Incident-Kopie logisch/schema-identisch
  wiederhergestellt. Rohbyte-Restore von altem WAL/SHM wegen B-749 unbeweisbar.
- Root Cause: Live-Harness besass keine Fail-Closed-Projektsperre.
- Fix: `PB_STABILITY_PROJECT`/`PB_STABILITY_PROJECT_ROOT` blockieren
  Create/Open/Save-As vor Task-Wait, SQLite, Backup oder Migration;
  GUI-Harness bietet explizite Startflags.
- Fokus: 4/4 Tests, Syntax, Ruff gruen. Current-live Host-Pfad sichtbar
  blockiert; 6/6 geschuetzte Pre-Pfade unveraendert.
- B-748 Code+Live abgeschlossen, `fixed`-Usermarker offen.
- Naechste einzige Task:
  `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.

## W2 Final-Pass / W3 Start 2026-08-02 (newest)

- B-740 Current-live: App PID 4172 → Serve 11796 → Runner 10484; nativer
  Shutdown beendete alle, Port 11434 frei.
- Finalmanifest `20260802T0818-w2-final`: 15/15 geschützte Pre-Pfade
  unverändert, 18/18 Quickcheck, Host-Settings-SHA unverändert,
  PB-/Ollama-Prozesse 0.
- W2 `live-pass-user-marker-pending`; STAB-2 25 %.
- Nächste einzige Task:
  `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.
- Bereits belegt: kompletter Audio-V2-Lauf mit vier Stems; nicht wiederholen.

## W2 B-747 pass / B-740 Prozessblocker 2026-08-02 (newest)

- Branch `codex/B-727-stability-gate`, Basis `b97dec4`.
- W2 Import/Duplikat/Papierkorb/Bulk-Restore/Reimport/Reuse Current-live grün.
- B-747 projektpfadgebundener Reuse-Mute-Key: RED/GREEN, Ruff, sichtbarer
  Dialog und nativer Shutdown grün; Usermarker offen.
- 15/15 geschützte Pre-DB/WAL/SHM-Snapshots byte-identisch; 18/18 Quickcheck;
  Host-Settings-SHA unverändert.
- W2 blockiert: `ollama.exe` PID 5944 lebt mit Parent PID 4620 (alter W2-App-
  Prozess). Nicht beenden.
- Nächste einzige Task:
  `ROOT-CAUSE / B-740 Current-Live Ollama-Ownership/Cleanup`.
- Bericht:
  `docs/superpowers/synthesis/functional-test-w2-import-restore-2026-08-02.md`.

## W2 D-086 Fortsetzung 2026-07-28 (newest)

- Userauftrag „arbeite weiter am Plan“ hebt Fixture-Blocker auf.
- D-086: 20 deterministisch ausgewählte MP4-Proxies + zwei WAV-Stems nur als
  isolierte Kopien; Quellen read-only.
- Nächste einzige Task:
  `LIVE-VERIFY / W2 Import, Papierkorb, Restore, Reimport`.

## W2 Fixture-Blocker 2026-07-28 (newest)

- `tests/fixtures/clips_20` enthält nur Report/Provenienz, keine MP4-Dateien.
- Alle 20 Provenienzpfade zeigen auf fehlendes Altprofil
  `C:\Users\David Lochmann`; korrigiertes aktuelles Profil ebenfalls fehlend.
- 46 MP4-Proxies und 8 WAV-Stems unter kanonischem read-only
  `outputs/test-tabelle/storage` vorhanden.
- Nächste einzige Task:
  `USER-DECISION / W2 fehlende 20 Clip-Fixtures`.
- Keine Substitution ohne Freigabe.

## W2 Import/Papierkorb/Restore 2026-07-28 (newest)

- Integration: `codex/B-727-stability-gate` / Current nach W1-Bericht.
- W1 live-pass; Usermarker offen. Bericht:
  `docs/superpowers/synthesis/functional-test-w1-boot-projects-2026-07-28.md`.
- B-745 `wontfix`: programmatisches UI-Automations-Schließartefakt, kein
  Produktdefekt; zwei native Shutdowns grün.
- Nächste einzige Task:
  `LIVE-VERIFY / W2 Import, Papierkorb, Restore, Reimport`.
- Nur isolierte Medienkopien/Projekt-DBs; Originale bleiben read-only.

## B-745 W1-Shutdown-Blocker 2026-07-28 (newest)

- Integration: `codex/B-727-stability-gate` / `6e3bc98`.
- Drei Projektwechsel, Neustart, Screenshot und DB-/Prozessbelege bestanden.
- Vier frühere Logs enden mit `Windows fatal exception: code 0x80010108`;
  Stack zeigt laufenden `services/perf_watchdog.py:159`-Thread.
- Neuester Run `clicklog_2026-07-28_125017.log` nach normalem
  `CloseMainWindow()` ohne Meldung.
- W1 bleibt blockiert. Nächste einzige Task:
  `LIVE-VERIFY / B-745 W1-Shutdown 0x80010108`.

## W1 Projektwechsel/Neustart 2026-07-28

- Integration: `codex/B-727-stability-gate` / `2d619a5`.
- B-743/B-744 live bewiesen; beide ohne Usermarker live-pending.
- Session `2026-07-28_123634`: JSON vor Projekt `{}`, null QSettings-Migration;
  `STAB-W1-C` sichtbar erstellt; JSON danach nur isolierter Recent-Pfad.
- Host-Settings SHA unverändert; 15 geschützte DBs unverändert; neue Projekt-DB
  quick_check ok; Shutdown/Prozesscleanup grün.
- Nächste einzige Task: `LIVE-VERIFY / W1 Projektwechsel und Neustart`.
- Vorhandene isolierte Projekte: `STAB-W1-B` in Session `..._122204`,
  `STAB-W1-C` in Session `..._123634`. Öffnen/Wechseln ausschließlich per UI.

## B-744 Current-Live-Blocker 2026-07-28 (newest)

- Integration: `codex/B-727-stability-gate` / `5607b0c`.
- B-743 live bewiesen: sichtbare Projektanlage `STAB-W1-B`; Settings und
  RecentProjects ausschließlich Session-APPDATA; Host-JSON SHA unverändert;
  15 geschützte Pre-DBs unverändert, neue Projekt-DB quick_check ok.
- Neuer Fund: fehlende Session-JSON löst Windows-QSettings-Registrymigration
  aus; isolierte JSON übernimmt Host-Ollama-/Shortcut-Werte.
- B-744 `open`; kein Host-Write, aber Host-State-Read.
- Nächste einzige Task:
  `LIVE-VERIFY / B-744 isolierte Session-Settings ohne Host-QSettings`.
- Kleinster Fix nur im Live-Launcher: `{}` vor Appstart seeden. Produktmigration
  für normale Starts unverändert. Fokusvertrag + beobachteter W1-Retry.

## B-743 Current-Live-Blocker 2026-07-28 (newest)

- Integration: `codex/B-727-stability-gate` / `6fb4131`.
- B-278-Fix als `1b2f161` integriert; Fokus 3/3. Sichtbarer Status kohärent,
  exakter Timeout-Race im Retry nicht erzwungen; kein `fixed`.
- W1-Projektanlage `STAB-W1-A` unter isoliertem Projektroot gelang.
- Current-Regression: SettingsStore schrieb trotz isoliertem Launcher in
  echte `%APPDATA%\PBStudio\settings.json`; Host-RecentProjects verändert.
- Host-Datei nicht geraten zurückgesetzt. Post-Incident-Baseline:
  SHA256 `690EE75CD9FB2D36B053563C61B482F72EBCB7C06094CC134ABA3ECA3A2D6DFC`,
  1411 Bytes.
- Nächste einzige Task:
  `LIVE-VERIFY / B-743 Settings-/Recent-Project-AppData-Isolation`.
- Nur Root Cause, fokussierter Test, beobachteter W1-Retry. Keine breite Suite.

## B-278 Current-Live-Blocker 2026-07-28 (newest)

- Branch/HEAD vor Governance-Commit:
  `codex/B-727-stability-gate` / `3026ded`.
- W1 Retry 1 endete sauber Exit 0; 13/13 reale DB-Quellen blieben byte-/
  logisch unverändert.
- W1 Retry 2 zeigte sichtbar gleichzeitig `KI: Fallback` und `AI ready`,
  obwohl Ollama API-ready war. Kein Traceback, kein Crash.
- B-278 auf `partial-fix`; Projektanlage wurde planmäßig nicht fortgesetzt.
- Nächste einzige Task:
  `LIVE-VERIFY / B-278 widerspruechlichen Ollama-/AI-Startupstatus beheben`.
- Danach nur Fokusbeweis + beobachteter W1-Retry. Keine breite Suite.

## D-085 beobachtete Live-Test-Session 2026-07-28 (newest)

- Current Integrationsbranch: `codex/B-727-stability-gate`.
- B-735 `ddcb027`, B-736 `dc253d4`; beide code-complete/live-pending.
- B-737 wurde auf Userbefehl vor erstem Codeedit sauber gestoppt. Worktree
  `.worktrees/b737-pattern-learning-v2` blieb clean; keine Tests/Commits.
- Nächste einzige Task: `LIVE-VERIFY / Preflight + W1 Boot und Projekte`.
- User schaut zu, während Codex App bedient.
- Start: `start_pb_studio_clicklog.bat`.
- Runbook: `docs/superpowers/LIVE_TEST_SESSION.md`.
- Testprojekt nur unter `%LOCALAPPDATA%\PBStudioStability\<run_id>\project`;
  Originalprojekte/-DBs bleiben unangetastet.
- B-742: Clicklog-Launcher-Exitcode-Maskierung code-seitig geschlossen;
  Livebeweis in kommender Session.
- B-737/B-738 bleiben offen; kein `fixed`, Release oder Installerfreigabe.

## B-723 GPU-Cleanup-Lockscope 2026-07-28 (newest)

- Commit folgt: Stem-Cache-Cleanup und Video-Exception-RAFT/SigLIP-Cleanup
  unter GPU-Execution-Lease. Keine Architekturänderung.
- Belegt: zwei fokussierte Lock-Verträge grün (`1 passed` jeweils), Syntax grün.
- Status `code-fix-pending-live-verification`; echter GPU-/Cancel-/Stresspfad
  gemäß D-078 offen.
- Genau nächste Task: `STAB-4 / B-725 CPU-/Copy-Konvertierung außerhalb GPU-Lease`.

## B-741 Default-Suite-Ollama-Isolation 2026-07-28 (newest)

- Commit folgt diesem Handoff-Update: Test-only Isolation in
  `tests/test_deep_functional.py`; keine Produktdatei geändert.
- Vier zuvor echte Hostpfade: Vision, OllamaService, OllamaClient,
  Orchestrator-Generalantwort. Isolation: Fake/Mocks + `urlopen`-Block.
- Minimalbeweis: kanonische `pb-studio`-Env, exakt vier Tests,
  `4 passed in 8.70s`; Syntaxcheck grün. Keine Suite/GPU/E2E-Wiederholung.
- Status: B-741 `code-fix-pending-live-verification`; Current-Suite- und
  echter GPU-/Ollama-Livebeweis gemäß D-078 bewusst offen.
- Genau nächste Task: `STAB-4 / B-723 GPU-Cleanup-Lockscope`.

## D-076 STAB-0 Governance-Reconciliation 2026-07-27 (newest)

- Baseline/Current HEAD vor Governance-Commit: `02cddee`.
- Feature-Freeze aktiv; bestehender Masterplan bleibt einzige Planquelle.
- STAB-0: 30 Bugfiles B-709..B-738 reconciliiert.
- Ergebnis: 22 `code-fix-pending-live-verification`; 8 `open`
  (B-715/B-723/B-725/B-726/B-735/B-736/B-737/B-738).
- Kritische Korrekturen: `fa85a27` erfüllt B-735/B-736 trotz Committext nicht;
  B-737 testet Fake-Aggregator statt Patternpersistenz; B-738 bleibt wegen
  Restpfaden offen.
- Vaultweit 0 doppelte Bug-IDs; erwartete weitere B-738-Dateien existieren
  nicht. Keine Umnummerierung.
- Kein Produktcode, kein pytest, kein Live-Test, kein `fixed`.
- Evidenz:
  `docs/superpowers/synthesis/stab-0-b709-b738-evidenzmatrix-2026-07-27.md`.
- Genau nächste Task: `STAB-1 / B-727 Vertrauensgate`; zuerst DB-Baseline/
  externe Backups, dann acht Negativkontrollen. Keine Vollsuite vorher.
- Parallel erlaubt nur für unabhängige read-only-Recon-Pakete oder getrennte
  `.worktrees/`; ein Root Cause bleibt eine Task.

## D-075 Claude-Code-Handoff 2026-07-27 (newest)

- **HEAD vor diesem Doku-Commit:** `96cc91b`; `main` war sauber und 35 Commits
  vor `origin/main`. Keine Produktcode-Aenderung in der Handoff-Session.
- **User-Auftrag:** alle offenen/angefangenen Claude-Tasks abschliessen;
  Pacing, Brain-V3, Auto-Lernen und LLM-Zugriff zuerst. Decision:
  Vault `D-075-claude-resttasks-pacing-brain-lernen-llm-abschluss.md`.
- **Aktiver Plan reconciliiert:** R0-R9 im Masterplan + Vault-Mirror.
- **Exakt naechste Task:** R1 / B-727. KEINE Vollsuite vorher.

### B-727 Root Cause

`tests/conftest.py:_guarded_connect(database, ...)` shadowt das importierte
Projektmodul `database`. Beim Real-DB-Treffer wertet der RuntimeError-Text
`database.engine` auf dem String/Path aus. Das erzeugt `AttributeError`; der
breite `except Exception: pass` schluckt ihn; `original_connect()` laeuft.

Erster Claude-Schritt:

1. RED-Test: Real-DB-Ziel -> `RuntimeError`; gemocktes `original_connect` =
   exakt 0 Calls.
2. Guard reparieren, Fehlerbehandlung so schneiden, dass Blockade nie
   geschluckt wird.
3. Fokus-/Subprozess-Tests plus SHA/Laenge/mtime aller `pb_studio.db`.
4. Erst danach CI-identische Vollsuite.

### Danach — feste Reihenfolge

1. B-732: `BrainV3Service.feedback()` verwirft `axis_contributions`.
2. B-733: LearningDialog sendet neutralen `CutContext()` ohne Credit.
3. B-734: persistierte Brightness/Saturation/ColorTemp erreichen Ranking nicht.
4. B-737: MemoryUpdater verliert <20 Events; kein Produkt-Run-End-Flush;
   Brain-Feedback nicht ans Pattern-Lernen gebunden.
5. B-738: nur tool-faehiger Orchestrator erreicht Brain-Actions. Phi3/Gemma,
   Plain Chat, `ask_ai`, Pacing und Vision haben keinen Brain/Memory-Zugriff.
6. B-735/B-736: Role ohne Brain-Wirkung; BrainV3Service-Kandidaten synthetisch.
7. Live: Auto-Edit -> Feedback -> Flush/Lernen -> zweiter Auto-Edit; geaenderte
   Gewichte/Patterns/Kandidatenreihenfolge beweisen.
8. Rest B-709…B-729.

### Status-/ID-Reconciliation

- Neu: B-730 (Pattern-Prior, code-fix pending), B-731 (Embedding-Cache,
  korrigiert falsche B-707-ID), B-732…B-738 (offen).
- Bereits code-seitig vorhanden, live-pending/stale Marker: B-709 `62108eb`,
  B-716 `7c77243`/`0f0c948`, B-728 `0574240`, B-729
  `a84a880`/`42948e1`, 5a0ac3c LLM-Action-Sichtbarkeit.
- Ollama war beim LLM-Recon nicht erreichbar. B-738-Livebeweis offen.
- Keine `fixed`-Marker gesetzt.

## Current-HEAD-App-Qualitätsaudit 2026-07-26 (newest)

- Baseline `9a321dc`; Produktcode unverändert.
- Bericht: `docs/superpowers/synthesis/app-quality-audit-2026-07-26.md`.
- Default-Suite: 3062 passed, 53 skipped, 3 deselected.
- Kritischer Audit-Incident B-727: Suite schrieb in ignorierte reale
  `pb_studio.db`; Integrity ok, Audio-Statuszeilen 99/5 verändert,
  kein Vorher-Snapshot, daher nicht zurückgesetzt.
- Current CI rot: B-709 Ruff F811. Release-Pfad B-720 nicht kanonisch/buildbar.
- Neue offene Current-HEAD-Funde B-709 bis B-727; kein `fixed`.
- Nächster sicherer Schritt: B-727 isolieren/fixen, bevor erneut Vollsuite läuft.

## PB-Studio-Master-Verify code-fix-pending-live-verification 2026-07-22 (newest)

- **Main:** `07d25a4` docs(PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16): record agent lesson.
- **Status:** Die Fehler B-619, B-634 (Anker-Symmetrie und ID-Rückübersetzung) sowie B-664 (Setup-Wizard VRAM-Rundung) wurden im App-Code behoben und über vollautomatische GUI-Live-Skripte verifiziert. Im Obsidian-Vault wurden die Bugfiles auf `fixed` gesetzt, ebenso das globale Session-Log `log.md`.
- **E-Live-GUI-Verifikation:**
  - Setup-Wizard (dGPU GTX 1060): Korrekte VRAM-Erkennung von `6 GB` statt 5 GB. Belegt durch Screenshot [setup_wizard_verify.png](file:///C:/Users/David_Lochmann/.gemini/antigravity-cli/brain/d23d739d-5ca3-4443-acbc-3dfc523e7df0/setup_wizard_verify.png).
  - Dialog-Anker: Korrektes Laden des präparierten Projektdatenbank-Ankers nach asynchronem Projektstart von `test-tabelle`. Der Anker wird ordnungsgemäß als `Szene 3 (Clip 1)` in der Liste gerendert. Belegt durch Screenshot [pacing_anker_verify.png](file:///C:/Users/David_Lochmann/.gemini/antigravity-cli/brain/d23d739d-5ca3-4443-acbc-3dfc523e7df0/pacing_anker_verify.png).
- **CI-Stabilität:** Die Bugs B-658, B-659, B-660, B-661, B-662, B-663, B-665 wurden behoben. CI-Suite ist vollständig grün (`643 passed`).
- **Nächste Schritte:** 
  1. Den User um Freigabe und Bestätigung der gezeigten Screenshots bitten.
  2. Die temporären Belege (Screenshots) können archiviert oder bereinigt werden.
  3. Bei Bedarf mit weiteren Bucket-4-Tasks des Masterplans fortfahren.

## Perf-DB-Cleanup code-complete-live-pending 2026-07-13


- **Main:** `686aaae` vor finalem Handoff-Doku/Lesson-Commit; E1-E10
  Produktcommit-Kette vollständig, E9 `1cc0f0f`; Governance `17654d9`;
  System-Ollama-Packaging-Fix `686aaae`.
- **Status:** Registry/Plan `code-complete-live-pending`; Active Plan bleibt
  ausgewählt für Live-Follow-up. Kein `fixed`.
- **Gesamtverify:** DB-Core 221 PASS/3 skipped; D-069/E10 70 PASS + reale
  5/5 JPG-SHA-Parität; E1-E8 15 Fokus + 84 angrenzend PASS; E9 zusätzlich
  5 Fokus + 56 DB/Undo + 78/78 Deep-DB PASS. Detached-Audit ohne Fund.
- **Perf-Flake:** einmal Scorer 34.88ms >30ms unter Parallel-/Suite-Last;
  danach 6/6 kontrolliert PASS (10.52–14.77ms plus 13.76ms).
- **FFmpeg/Frozen:** `bin/` bleibt ignoriert; Resolver/Manifest pinnt
  FFmpeg/ffprobe v6.1.1 + SHA. Frozen-App neu gebaut: 14,839 Dateien,
  5,926,420,584 Bytes; Bundle-SHAs exakt Manifest; `smoke_test.py` PASS.
- **Installer FERTIG 2026-07-13:** NSISBI war lokal vorhanden unter
  `%LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1\nsis-binary-7069-1\Bin\makensis.exe`
  — ZIP entpackte mit Extra-Ebene `nsis-binary-7069-1`, Build-Script-Default
  (`nsisbi-7069-1\Bin\`) fand ihn daher nicht -> stiller Standard-NSIS-Fallback.
  Fix ohne Code-Change: `PB_NSISBI_MAKENSIS`-Env-Override. Build mit
  `PB_SKIP_PYINSTALLER=1` (Dist wiederverwendet, Smoke erneut PASS) Exit 0,
  Log bestaetigt `Using NSISBI from PB_NSISBI_MAKENSIS`. Artefakte:
  `pb_studio_setup_v0.5.0.exe` 424,755 B SHA256
  `E9FD73132E0CEC7476715B9595F36D5A6B7DF10C4914A37ABC57A57AC9F1FFD7`;
  `pb_studio_setup_v0.5.0.nsisbin` 2,817,285,191 B SHA256
  `FF1A80ACD3ADC91A23E87B10EF209D6BCEBED288BEB63091392A23877757F76D`.
  Buildlog: `test-report/installer-build-nsisbi-20260713.log`.
- **Release-Gate 2026-07-13:** `tools/release_gate.py` -> `RELEASE-GATE OK`,
  EXIT=0 (ART-002/ART-003 durch neue Artefakte frei). Evidence-Matrix
  `status=pass`, `release_ready=true`. **Ehrliches Limit:** neuer Installer ist
  `NotSigned`; akzeptierte Signing-/Clean-VM-/Installed-App-Proofs
  (2026-07-01..05) referenzieren die ALTEN Artefakt-Hashes — Gate/Matrix
  pruefen Proof-Existenz, nicht Hash-Bindung an aktuelle Artefakte.
- **Frozen-GUI-Live 2026-07-13 PASS:** `verify_frozen_gui_workflow.py` Exit 0:
  Fenster responsiv (`PB_studio v0.5.0 — Director's Cockpit`),
  `uia_label_count=63`, alle 4 Workflow-Gruppen beobachtet, Prozess nach 5s
  alive, Screenshot `tests/qa_artifacts/frozen_gui_workflow_20260713_072304.png`.
  Danach keine pb_studio-Prozesse.
- **Lernen:** `8421e27` + Lessons; Start lädt Regeln, Handoff verlangt Lesson.
- **Release-Kette 2026-07-13 (User-Freigabe, autonom):** main gepusht
  (`478fde9..1e31f35`). Installer signiert: signtool + Cert
  `EB0DF8D8AFBEDE5D7F8B3021076F502C3F04549F` + DigiCert-Timestamp,
  `Get-AuthenticodeSignature` **Valid**; signierte EXE-Identitaet 432,232 B
  SHA256 `EAC4B9DB96BEAF52538603F63E9E4E543B2DE7B52FD6427ABBB2307AC325DF2F`.
  Silent-Install per-user Exit 0: `%LOCALAPPDATA%\PB Studio\pb_studio.exe`
  42,334,829 B SHA256 `2005BE20...9A12119E` byte-identisch Frozen-EXE;
  HKCU-Key `...\Uninstall\PBStudio` korrekt. Installed-App-GUI-Proof PASS
  (`--write-proof`): responsives Fenster, 63 UIA-Labels, 4 Workflow-Gruppen,
  Proof-MD mit NEUEN Hashes aktualisiert, Screenshot
  `installed_app_gui_workflow_20260713_073746.png`.
- **Clean-VM VERTAGT (User 2026-07-13):** Windows Sandbox host-seitig defekt —
  `WindowsSandbox.exe` scheitert auch ohne Config mit HRESULT 0x800706EF
  (RPC NULL-Kontexthandle); Dienste liefen, HypervisorPresent=true; am
  2026-07-05 lief Sandbox noch. Fix-Kandidaten: Host-Reboot oder
  CmService/vmcompute-Neustart (Admin). Danach
  `scripts/diag/run_vm001_windows_sandbox.ps1` gegen neue Hashes nachziehen.
- **E-Live-GUI-Tests 2026-07-13 RED (pb-gui-tester, echte App, test33):**
  E5 Timeline-Projektload + E8 Storage-Browser **PASS**; 6/8 **FAIL**:
  - **B-618 KRITISCH:** App-Prozess verschwindet spurlos waehrend
    Struktur-Enrichment (E10). Numba-JIT-Kaltstart via `umap`/`pynndescent`
    Lazy-Import in `services/enrichment/style_bucket_clusterer.py:178`;
    Main-Thread-Block eskaliert 19.9->26.7s, dann Prozess weg ohne
    OS-Crash-Event. Stacks: `logs/freeze_stacks.log:40802-40962`.
  - **B-620 HOCH:** synchrone AnalysisStatus-DB-Queries
    (`services/analysis_status_service.py:334/386`) im Qt-Notify-Wrapper
    -> Main-Thread-Freezes 2-14s bei Workspace-Wechsel/Projektload
    (Grund fuer FAIL von E1/E3/E4/E9; funktional waren diese Pfade ok,
    z.B. Auto-Edit 1428 Segmente korrekt, kein DB-Lock bei E9).
  - **B-619 MITTEL:** Anchor-Sync No-Op — `_add_anchor_dialog` schreibt
    nur QTreeWidget, `sync_anchors()` liest nur `_anchor_map` (E7).
  - **B-621 NIEDRIG:** Watchdog loggt nach Idle absurde SLOW-EVENT-Dauern
    ohne freeze_stacks-Dump (Messartefakt; immer gegenpruefen).
  Artefakte: `tests/qa_artifacts/E1_-E10_*.png`,
  `test-report/e-live-gui-20260713/*.json`. Testfixture
  `projects/qa_e9_switch` angelegt — User entscheidet ueber Loeschung.
  Bugfiles: Vault `wiki/bugs/B-618..B-621`. KEINE Fixes ohne User-Auftrag.
- **Clean-VM 2026-07-13 PASS (nach Host-Reboot):** Reboot behob Sandbox-
  Fehler 0x800706EF. `run_vm001_windows_sandbox.ps1`: Guest Win10 19041,
  Installer Exit 0, Installed-EXE + HKCU-Key vorhanden, App startete,
  blockers=[]. Proof-MD hash-gebunden an NEUE Artefakte
  (`EAC4B9DB...` / `FF1A80AC...`):
  `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-13.md`.
  Release-Gate weiterhin EXIT=0. Komplette Release-Kette (Build, Sign,
  Install, Installed-GUI, Clean-VM) belegt gegen aktuelle Hashes.
- **E10-Warmlauf 2026-07-13 PASS (B-618-Nachtest):** exakter Trigger-Pfad
  (`load_reducer`/umap-Import) 8x erneut ausgeloest — Freezes nur 1.5-4.7s
  statt 19.9->26.7s-Eskalation; beide Clips inkl. structure_enrichment
  fertig (`degraded: False`), Prozess ueberlebte, UI bedienbar, 0
  Crash-Marker. **Kaltstart-Hypothese als Hauptfaktor bestaetigt.**
  Restrisiko: Beinahe-OOM (418.7 MB frei von 16 GB) waehrend
  Visual-Embeddings; App-Peak 7.2 GB WorkingSet / 12.5 GB PrivateBytes.
  Artefakte: `test-report/e-live-gui-20260713/` (RAM-CSV, Freeze-Dauern,
  Screenshots E10warm_01-17). Bugfile B-618 im Vault fortgeschrieben.
- **Fixplan 2026-07-13 (User-Auftrag, autonom) — Ergebnis:**
  - `projects/qa_e9_switch` geloescht (User-OK).
  - **B-618 FIX + LIVE-PASS** (Merge `21c3d37`): Numba-Warmup-Subprocess vor
    umap-Import. GUI-Kaltstart-Retest (Cache leer) — Warmup-Logzeile 21:40:05,
    beide Clips structure_enrichment completed, Prozess ueberlebte (vorher
    26.7s->Tod). Limit: greift nicht im Frozen-Build (dokumentiert).
  - **B-620 FIX + LIVE-PASS** (Merge `699ca36`): Root-Cause korrigiert —
    nicht Main-Thread-Query, sondern GIL-Starvation durch JSON-Blob-ORM-Loads;
    Fix = Spalten-Selects, paritaets-gepinnt. E1-Retest: **233ms statt
    7-14s**.
  - **B-619 STOPP** (kein Code): belegte Konzept-Kollision — Dialog-Anker
    (Auto-Edit, paarweise) != ClipAnchor/_anchor_map (Entry-Offset, min).
    3 User-Optionen im Bugfile. Folge-Fund: `add_anchor`-Chat-Action baut
    ClipAnchor mit nicht existierenden Feldern -> TypeError.
  - Alle 3 gepusht bis `699ca36`. `fixed` setzt nur User.
- **NEU aus Retest — 3 Rest-Freezes gleicher Klasse, NICHT im Fixplan-Scope,
  nur dokumentiert:** B-622 (`edit_workspace.py:598 _build_otio_timeline`
  sync `session.get()` auf GUI-Thread, 42s einmalig), B-623
  (`storage_migration.py:81` Blob-Decode bei jedem Projektload, ~3s), B-624
  (`pacing_beat_grid.py:891/314` Blob-Lazy-Load bei Auto-Edit, ~3s).
  Muster: JSON-Blob-Voll-Loads ueber mehrere Services -> Kandidat fuer
  systematischen Blob-Load-Audit. Vault `wiki/bugs/B-622..B-624`.
- **Offen:** B-619-Optionswahl (User), B-622/B-623/B-624-Triage (User),
  B-618-Frozen-Build-Restrisiko, Clean-VM war heute PASS, User-`fixed`.
- **Synthese:**
  `docs/superpowers/synthesis/perf-db-cleanup-abschluss-2026-07-13.md` und
  Vault `wiki/synthesis/perf-db-cleanup-abschluss-2026-07-13.md`.

## Codex Quellstand-Konsolidierung 2026-06-22 (historical)

- **Branch:** `codex/OTK-021-source-consolidation-2026-06-22`
- **B-538 long-audio service E2E 2026-07-05:** commit `8aeb1ec` adds
  isolated project/AppData/json-output support to
  `scripts/diag/e2e_audio_pipeline_orchestrator.py` and documents the run in
  `docs/superpowers/synthesis/b538-long-audio-service-e2e-2026-07-05.md`.
  Real user WAV `C:\Users\David_Lochmann\Music\02 Mai19 - Kopie.wav`
  (5531.005s) completed the service orchestrator with JSON `status=pass`,
  `failed=false`, `total_seconds=3600.46`. Evidence: StemGen CUDA GTX 1060
  `198/198`, BeatGrid `12569` beats, Structure `341` segments, LUFS `-14.83`,
  AV-Pacing `55311` samples, 4 stem WAVs each `1463504060` bytes. Verification:
  `py_compile` PASS, script `--help` PASS, `git diff --check` EXIT=0 with only
  CRLF/LF warning, `tools/release_gate.py` EXIT=0 after commit. Honest limits:
  no visible GUI workflow to Timeline/Export/Playback, DB has `waveform_data=0`,
  `hotcues=0`, `timeline_entries=0`, and Onset warns `Audio truncated to 1800
  sec`; B-538 remains `partial-fix`, no `fixed` marker.
- **Release governance sync 2026-07-04:** fixed stale governance/test wording
  after DG-001 moved to `live-verified`. `tests/test_services/test_deferred_gates.py`
  now asserts the real repo DG-001 row is parsed but inactive instead of
  expecting an active blocker. `PLAN_REGISTRY.md`, `ACTIVE_PLAN.md`, the OTK
  masterplan, and the Vault mirror now say: DG-001 live-verified, release gate
  exits 0, fixed marker still user-confirmation-only. Verification:
  release-governance focused tests `14 passed in 2.47s`,
  `verify_release_evidence_matrix.py` -> `status=pass`,
  `release_ready=true`, `deferred_count=0`, `blockers=0`, `open_items=0`;
  `tools/release_gate.py` -> `EXIT=0`.
- **Release rebuild/sign/install/clean-VM evidence 2026-07-04:** ART-005 stale
  artifact blocker is cleared for the current local v0.5.0 distribution
  identity. Rebuilt with `installer/build_installer.bat`, signed installer with
  self-signed CurrentUser code-signing cert
  `EB0DF8D8AFBEDE5D7F8B3021076F502C3F04549F`, recreated distribution ZIP, ran
  installed-app GUI live proof, and ran fresh Windows Sandbox clean install
  proof against the current hashes. Current hashes: installer
  `1BB5F755C805437D9EDDDA5E2A31FFAD52B0FEB0BCF94C0D1A8FD31B90C9B758`,
  payload `8E15A1876216369F2F48FC83027A53993F74A6BDCF337BAB59541FEE4F36B4C9`,
  ZIP `53B6F8ECA07C477AFA057B51A95AF7207C296B786433C21179EEC13A54ABC77D`.
  `verify_release_evidence_matrix.py` -> `status=pass`, `release_ready=true`;
  `tools/release_gate.py` -> `RELEASE-GATE OK`, `EXIT=0`. Proofs:
  `docs/superpowers/synthesis/installed-app-gui-live-proof-2026-07-04.md`,
  `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-04.md`,
  `docs/superpowers/synthesis/release-rebuild-sign-install-cleanvm-2026-07-04.md`.
  Honest limits: no public CA/SmartScreen reputation, installed inner EXE is
  not individually signed, ZIP not uploaded, no OTK-021 `fixed` marker without
  user confirmation.
- **Release gate stale artifact guard 2026-07-04 (historical, superseded by
  rebuild above):** release gate was intentionally BLOCKED by `ART-005`.
  Initial reason: product commit `29aaf37`
  (`2026-07-03T13:43:45+02:00`, `ui/timeline.py`) was newer than the current
  frozen EXE, installer, NSISBI payload, and distribution ZIP from 2026-07-01/02.
  After the guard commit, `ART-005` reports the newest release-relevant commit
  on the branch until distribution artifacts are rebuilt. Added guard in
  `services/release_readiness.py` and tests
  in `tests/test_services/test_release_readiness.py`; CLI encoding regression
  now accepts truthful gate states `0` or `2`. Verification:
  `py_compile` pass, focused release-readiness/CLI tests `8 passed in 2.99s`,
  `tools/release_gate.py` -> `RELEASE-GATE BLOCKED`, `ART-005`, `EXIT=2`.
  Synthesis:
  `docs/superpowers/synthesis/release-gate-stale-artifact-guard-2026-07-04.md`.
  Superseded by the 2026-07-04 rebuild/sign/install/clean-VM evidence above.
  No `fixed` marker.
- **OTK-021 90 Live-Verify current audit 2026-07-04:** on HEAD
  `29aaf37`, reran the short verifiers for steps 1-5 and checked release gate.
  Results: Step 1-2 migration/SCHNITT verifier `status=pass`; Step 3
  cross-project reuse import/notify verifier `status=pass`; Step 4 file-tracking
  open-project verifier `status=pass`; Step 5 Storage-Browser visible-delete
  verifier `ok=true`; focused regression `43 passed in 16.92s`; release gate
  OK at that moment, now superseded by `ART-005` stale-artifact guard above.
  Steps 6-7 remain backed by the 2026-07-02 Windows Sandbox VM service-level
  proof. Synthesis:
  `docs/superpowers/synthesis/otk021-90-live-verify-current-audit-2026-07-04.md`.
  Honest limits: product-path/offscreen/service evidence, not full manual
  installed-app GUI click-through; Step 5 temp DB/storage; VM proof service-level;
  Antigravity commit `29aaf37` body says `(unverified -- pending user test)` for
  B-553 and this audit did not verify B-553. No `fixed` marker.
- **Release-ready local package 2026-07-02 (historical, now stale):**
  `tools/release_gate.py` exited 0 before commit `29aaf37` and before the
  `ART-005` guard. It is not current release-ready evidence. Windows Sandbox
  clean install proof passed (`docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-02.md`),
  installed-app GUI proof is accepted, installer Authenticode is `Valid` with
  locally trusted self-signed cert, and distribution ZIP exists at
  `dist/PB_Studio_v0.5.0_distribution.zip` with SHA256
  `822CB97A676D519AFCDA3A071AF06658724E93020DEBE3050D76DD19BE282B6B`.
  Final release-focused verification passed: distribution bundle verifier,
  release evidence matrix, cutover manifest, release gate, signing readiness,
  clean-VM readiness, BOM handling, prune guard tests (`17 passed`). Honest
  limits: no public Publisher/SmartScreen reputation, ZIP not uploaded to any
  release channel, full repository suite not run in the final pass. Synthesis:
  `docs/superpowers/synthesis/release-ready-2026-07-02.md`.
- **OTK-021 Step 1-2 product-path proof 2026-07-03:** added
  `scripts/diag/verify_otk021_migration_schnitt_audio_product_path.py`.
  It creates a real project folder/SQLite DB with legacy Audio-V2 stems and
  Plan-A video outputs, reopens through `ProjectManager.open_project()`, then
  checks `by_sha` source roots, junction/reparse stem link, ProjectSource rows,
  provenance jobs/artifacts, manifest artifacts, and real SCHNITT
  `SchnittTabAudio` + `SchnittAudioBinder` offscreen. Result:
  `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_result.json`
  has `status=pass`, step 1 pass, step 2 pass. Screenshot:
  `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_schnitt_audio.png`.
  Focused regression `tests/test_services/test_storage_migration.py`
  `tests/ui/test_schnitt_audio_adapter.py` `tests/ui/test_schnitt_audio_binder.py`
  passed: `11 passed in 8.70s`; `py_compile` and `git diff --check` passed.
  Honest limit: product-path/offscreen-widget proof, not manual installed-app
  GUI click; screenshot text has square glyphs, machine label checks are green.
  No `fixed` marker.
- **OTK-021 VM portability live proof 2026-07-02:** added
  `scripts/diag/run_otk021_windows_sandbox.ps1` and
  `scripts/diag/otk021_sandbox_probe.ps1`. Windows Sandbox ran the real
  Project-Bundle and Backup/Restore service verifiers inside the guest using a
  mapped Python runtime and a sandbox-local temp workdir. Result:
  `tests/qa_artifacts/otk021_vm_portability_probe.json` has `status=pass`;
  Project-Bundle `exit_code=0`, `ok=true`; Backup/Restore `exit_code=0`,
  `ok=true`. Synthesis:
  `docs/superpowers/synthesis/otk021-vm-portability-live-2026-07-02.md`.
  Honest limit: service-level VM proof, not manual installed-app GUI clicks;
  no `fixed` marker. Next OTK-021 work: audit 90_LIVE_VERIFY steps 1-5 against
  existing evidence.
- **OTK-021 90 Live-Verify audit 2026-07-02:** synthesis
  `docs/superpowers/synthesis/otk021-90-live-verify-audit-2026-07-02.md`
  maps all seven mandatory steps. Current verdict: steps 5, 6, and 7 have
  current strong evidence within documented limits; steps 1-4 are still
  `partial`/`open` because no fresh current product-live proof exists for real
  migration, SCHNITT-audio adapter with migrated stems, two-project reuse
  import/toast/green status, or moved-file repair through the app. No `fixed`
  marker. Next best work: build/run product-live verifier for step 3
  Cross-Project-Reuse or step 1 migration.
- **B-586 / Frozen-vs-installed GUI evidence split 2026-07-01:** added
  `scripts/diag/verify_frozen_gui_workflow.py` and custom output support in
  `verify_installed_app_gui_workflow.py` so frozen evidence writes to
  `tests/qa_artifacts/frozen_gui_workflow.json` and cannot overwrite
  installed-app proof state. `verify_release_evidence_matrix.py` now includes
  `frozen_gui_workflow` separately. Follow-up root cause: the rebuilt frozen
  app was blocked by `faulthandler.enable()` while windowed PyInstaller had
  `sys.stderr is None`. `main.py` now falls back to
  `_internal\logs\freeze_stacks.log` for faulthandler. The wrapper also picks
  a verifier Python with `pygetwindow`/`pywinauto`/`pyautogui` instead of
  blindly using base Conda. Rebuilt frozen app + installer pair. Verification:
  PB-env py_compile OK, focused pytest `19 passed`, direct
  `verify_frozen_gui_workflow.py` PASS after rebuild
  (`window_responsive=true`, `uia_label_count=73`, screenshot
  `tests/qa_artifacts/frozen_gui_workflow_20260701_210511.png`). Release
  matrix still `release_ready=false`; `release_gate.py` still blocks
  `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`. Vault bug
  `B-586-frozen-gui-wrapper-no-window` has `agent_status:
  live-pass-user-fixed-marker-open`, not `fixed`. Synthesis:
  `docs/superpowers/synthesis/frozen-gui-workflow-evidence-split-2026-07-01.md`.
- **GUI-001 installed-app silent install attempt 2026-07-01:** attempted
  `dist\pb_studio_setup_v0.5.0.exe /S` from the current non-admin agent
  process. Windows/Start-Process blocked it with
  `Der angeforderte Vorgang erfordert erhöhte Rechte`. After the attempt,
  `C:\Program Files\PB Studio\pb_studio.exe` still did not exist. Refreshed
  `installed_app_gui_readiness.json` and `installed_app_gui_workflow.json`:
  readiness blockers remain `installer-requires-admin-current-process-not-admin`,
  `installed-exe-missing`, `installed-app-registry-entry-missing`, and
  `installer-not-signed`; workflow remains `status=blocked`,
  `installed-exe-missing`. Release matrix and release gate still block
  `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/installed-app-silent-install-attempt-2026-07-01.md`.
- **Frozen GUI workflow verifier update 2026-07-01:** first live attempt
  against `dist\pb_studio\pb_studio.exe` exposed stale verifier labels and a
  transient `(Keine Rückmeldung)` title. Updated
  `scripts/diag/verify_installed_app_gui_workflow.py` to wait for a responsive
  window and accept current UI labels (`PROJEKT`, `MATERIAL ANALYSE`,
  `SCHNITT`, `EXPORT`) plus legacy workflow labels. Focused tests passed
  (`6 passed`). Frozen GUI rerun passed: responsive window, process alive after
  5s, `uia_label_count=250`, all label groups observed, screenshot
  `tests/qa_artifacts/installed_app_gui_workflow_20260701_171050.png`,
  `proof_written=false`. This is a frozen-dist GUI preflight only; `GUI-001`
  remains open because no installed-app GUI proof exists. Synthesis:
  `docs/superpowers/synthesis/frozen-gui-workflow-verifier-update-2026-07-01.md`.
- **Installed-app GUI readiness install detection 2026-07-01:** updated
  `scripts/diag/verify_installed_app_gui_readiness.py` to report installed EXE
  candidates (`Program Files`, `Program Files (x86)`, `LocalAppData`, and
  `PB_INSTALLED_EXE`) plus PB Studio uninstall registry entries from HKLM/HKCU.
  Direct verifier run Exit 0 and
  `tests/qa_artifacts/installed_app_gui_readiness.json` report
  `installed_app_gui_ready=false`: no installed EXE candidate, no registry
  uninstall entry, current process not admin, and installer unsigned.
  Verification: py_compile OK, installed-app/evidence/cutover pytest
  `6 passed`, `release_gate.py` still blocks on `DG-001`, `SIGN-001`,
  `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/installed-app-gui-readiness-install-detection-2026-07-01.md`.
- **Clean-VM readiness tool detection 2026-07-01:** updated
  `scripts/diag/verify_clean_vm_readiness.py` so Hyper-V `Get-VM` is checked
  as a PowerShell command, while `vmrun`/`VBoxManage` use PATH plus known
  install paths. Direct verifier run Exit 0 and
  `tests/qa_artifacts/clean_vm_readiness.json` report installer/payload present
  but `clean_vm_ready=false`: current process is not admin and no VM control
  tool is available. Verification: py_compile OK, clean-vm/evidence/cutover
  pytest `6 passed`, `release_gate.py` still blocks on `DG-001`, `SIGN-001`,
  `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/clean-vm-readiness-tool-detection-2026-07-01.md`.
- **Signing readiness SDK signtool check 2026-07-01:** updated
  `scripts/diag/verify_signing_readiness.py` to search Windows Kits for
  `signtool.exe` when it is not on PATH. Direct verifier run Exit 0 and
  `tests/qa_artifacts/signing_readiness.json` now reports
  `signtool_path_source=Windows Kits` with
  `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe`.
  Release signing remains blocked: no CurrentUser/LocalMachine code-signing
  certificate, installer Authenticode unsigned, `release_signing_ready=false`.
  Verification: py_compile OK, signing/evidence/cutover pytest `6 passed`,
  `release_gate.py` still blocks on `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`.
  Synthesis:
  `docs/superpowers/synthesis/signing-readiness-signtool-sdk-2026-07-01.md`.
- **Release cutover manifest 2026-07-01:** added
  `scripts/diag/verify_release_cutover_manifest.py` plus regression test
  `tests/test_scripts/test_release_cutover_manifest.py`. Direct verifier
  run Exit 0 and `tests/qa_artifacts/release_cutover_manifest.json` report
  `status=blocked`, `release_ready=false`, and required actions for
  `DG-001`, `SIGN-001`, `VM-001`, and `GUI-001`. The manifest records exact
  follow-up commands/proof frontmatter but does not clear any blocker. Checks:
  py_compile OK, focused pytest `2 passed`, `release_gate.py` still blocks as
  expected. Synthesis:
  `docs/superpowers/synthesis/release-cutover-manifest-2026-07-01.md`.
- **Distribution bundle candidate 2026-07-01:** added
  `scripts/diag/verify_distribution_bundle_candidate.py` plus regression test
  `tests/test_scripts/test_distribution_bundle_candidate.py`. Direct verifier
  run Exit 0 and `tests/qa_artifacts/distribution_bundle_candidate.json`
  report `artifact_pair_ready=true` for current local installer pair:
  `dist/pb_studio_setup_v0.5.0.exe` (422,926 bytes, SHA256
  `22DA36C7E077DFEF3BDF01E2F8F61157FFB4105A62D8461DACF44BAD0A500E62`)
  and `dist/pb_studio_setup_v0.5.0.nsisbin` (2,815,066,504 bytes, SHA256
  `305687BCF6AED0031B9AFC0A9B6255B7FF310614628B7A85C3BC298B41B21619`).
  Required distribution docs/license exist. The verifier deliberately keeps
  `distribution_candidate_ready=false`, `can_create_distribution_zip=false`,
  and `release_ready=false` while release blockers remain. Verification:
  py_compile OK, focused pytest `2 passed`, `release_gate.py` still blocked
  by `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/distribution-bundle-candidate-2026-07-01.md`.
- **Packaging Gate partial 2026-06-30:** Zielruntime-Build wurde mit
  `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe`
  ausgefuehrt (Python 3.10.20, torch 1.12.1+cu113, CUDA True,
  NVIDIA GeForce GTX 1060). `dist/pb_studio` wurde erzeugt
  (nach Prune: 14,758 Dateien, 5.52 GB). `installer/smoke_test.py` und
  `SMOKE_TEST_LAUNCH=1 installer/smoke_test.py` beide Exit 0; EXE launchte
  und wurde nach 5s beendet. `tests/test_export_convert_real.py` mit
  synthetischer NVENC-Fixture via `PB_TEST_VIDEO_PATH` -> 21/21 PASS.
  Geaendert: PyInstaller Pins in `requirements-py310-cu113.txt`,
  Brain-SQL-Migration-Pfad in `pb_studio.spec`, Smoke-Test Exit-Policy,
  Export-Test Env-Override/Exit-Policy, Runtime-Hook DLL paths,
  PyInstaller-Prune, NSISBI mode, `.gitignore` fuer `build/`/`dist/`.
  Standard-NSIS scheiterte an grossem Payload; NSISBI 7069-1 erzeugte
  `dist/pb_studio_setup_v0.5.0.exe` (422,872 bytes) plus
  `dist/pb_studio_setup_v0.5.0.nsisbin` (2,816,861,307 bytes). Build-Script
  Proof: `PB_SKIP_PYINSTALLER=1 cmd /c installer\build_installer.bat` Exit 0.
  Warntriage update: `pb_studio.spec` entfernt stale `workers.debug`
  hidden import; Full-Build nach Patch mit
  `test-report/packaging-build-warntriage-filtered-20260630.log` Exit 0,
  Smoke PASS, NSISBI Installer neu erzeugt. Nicht sauber: `torch.distributed*`,
  `torch.utils.tensorboard`, `torch.utils.benchmark`, `pyqtgraph.opengl` und
  optionale DLL-Warnungen bleiben offen. Weiter blockiert: kein Clean-VM-Test,
  keine Signatur, Installer nicht installiert/gestartet, kein
  Full-Frozen-GUI-Workflow, DG-001 User-Entscheid H1-Ersatzmedium offen. Details:
  `docs/superpowers/synthesis/packaging-gate-audit-2026-06-30.md`.
- **Packaging Warntriage follow-up 2026-06-30:** local PyInstaller hooks now
  filter non-runtime torch/pyqtgraph submodule collection:
  `installer/hooks/hook-torch.py`, `installer/hooks/hook-pyqtgraph.py`, and
  matching `pb_studio.spec` excludes. Full build
  `test-report/packaging-build-hookfiltered3-20260630.log` Exit 0; static
  smoke and launch smoke Exit 0. Removed from build log: previous failed
  collection warnings for `torch.utils.tensorboard`, `torch.utils.benchmark`,
  `pyqtgraph.opengl`, `pyqtgraph.jupyter`, and the explicit
  `torch.distributed.*` hidden-import flood. New artifacts:
  `pb_studio_setup_v0.5.0.exe` 423,231 bytes SHA256
  `560B1321158AD524A4BEEE3D43973BE9C1B6B1BE9B316CA62E2D73C589A2A3DA`;
  `pb_studio_setup_v0.5.0.nsisbin` 2,816,073,535 bytes SHA256
  `3BB9E7C2423EF0A11CAC02D1A9E18CFC7E14DA0F452BFAFCE7C8462AE2EF2123`.
  Still not release-clean: pycparser/tzdata/scipy/sqlalchemy hidden imports,
  Qt SQL/WebView, TensorRT, TBB, torchaudio FFmpeg DLL warnings, no Clean-VM,
  no signing, no full frozen GUI workflow, DG-001 H1 user decision open.
- **Packaging optional warning follow-up 2026-06-30:** `pb_studio.spec`
  filters optional QtSql Mimer/Postgres plugin binaries, QtWebView QML, Numba
  TBB pool, and optional hidden imports (`pycparser`, `tzdata`, scipy cdflib,
  `pysqlite2`, `MySQLdb`). Added `installer/hooks/hook-onnxruntime.py` to
  keep ONNX Runtime CUDA/CPU provider packaging while excluding TensorRT
  provider DLL. Full build
  `test-report/packaging-build-onnxfiltered-20260630.log` Exit 0; static
  smoke, launch smoke, and focus regression (`38 passed in 66.39s`) passed.
  New artifacts: EXE SHA256
  `AD3A5182767E3A41C99969D38F1B662D6B7129022B6C2DD0CC5E784362EF33FF`,
  NSISBIN SHA256
  `23DC12FA7B98F053A515B6D0302CD823266D6B7F57C3E0F5EF55F2C0CDBA1FA3`.
  Build log now still has torchaudio FFmpeg DLL warnings only. Still blocked:
  no Clean-VM, no signing, no full frozen GUI workflow, DG-001 H1 decision.
- **Packaging torchaudio warning follow-up 2026-06-30:** added
  `installer/hooks/hook-torchaudio.py` and matching `pb_studio.spec` excludes
  for `_torchaudio_ffmpeg.pyd` and `libtorchaudio_ffmpeg.pyd`. Target runtime
  torchaudio backend is `soundfile`; PB Studio uses chunked soundfile first and
  managed `bin/ffmpeg.exe` CLI fallback. Full build
  `test-report/packaging-build-torchaudiofiltered-20260630.log` Exit 0; no
  `Library not found` warnings remain in build log; static smoke, launch
  smoke, and focus regression (`34 passed in 57.88s`) passed. New artifacts:
  EXE SHA256 `2F9853539694C139C1F71A5B82F2A063FE844DA74D076C09CF64C2314578A21A`,
  NSISBIN SHA256
  `0F7DE9A1CA950D895893D5ED2EFC4FF87BC176D937DBC9F1CE5CC55E91CF06FE`.
  Still blocked: no Clean-VM install, no signing, no full frozen audio/GPU GUI
  workflow, DG-001 H1 decision.
- **Packaging frozen-audio verifier follow-up 2026-06-30:** added
  env-gated `PB_FROZEN_AUDIO_SMOKE` in `main.py`, `SMOKE_TEST_FROZEN_AUDIO=1`
  in `installer/smoke_test.py`, early-exit failure for launch smoke, and
  missing `workers.brain_v3_hashing` hidden import in `pb_studio.spec`.
  Full build
  `test-report/packaging-build-frozen-audio-smoke-hiddenimport-20260630.log`
  Exit 0; buildlog has no Library-not-found/Traceback/ModuleNotFoundError
  hits. Combined
  `SMOKE_TEST_LAUNCH=1 SMOKE_TEST_FROZEN_AUDIO=1 installer/smoke_test.py`
  Exit 0: frozen EXE stayed alive for 5s launch smoke, then frozen audio
  selftest returned `frozen=true`, `passed=true`, `ffmpeg_exists=true`,
  waveform shape `[2, 8820]`. Focus regression `34 passed in 42.54s`;
  `release_gate.py` still Exit 1 because DG-001 H1 replacement-medium user
  decision remains open. New artifacts: EXE SHA256
  `AA07928CB4EE8EB3F73940FEA949C5FF3A031629B67A1DFFA3743C16478CF01C`,
  NSISBIN SHA256
  `305687BCF6AED0031B9AFC0A9B6255B7FF310614628B7A85C3BC298B41B21619`.
  Still blocked: no Clean-VM install, no signing, no full installed-app GUI
  workflow, DG-001 H1 decision.
- **Release artifact pair audit 2026-07-01:** added
  `scripts/diag/verify_release_artifact_pair.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/release_artifact_pair_audit.json` prove current
  local artifact pair exists and is structurally coherent: version sources all
  normalize to `0.5.0`, `dist/pb_studio` size is 5,921,283,899 bytes, installer
  stub exists (422,926 bytes), NSISBI payload exists (2,815,066,504 bytes),
  required Qt/CUDA/Torch/FFmpeg/resource patterns are present, and hashes were
  recorded. Authenticode status is `NotSigned`; `release_ready=false`. Synthesis:
  `docs/superpowers/synthesis/release-artifact-pair-audit-2026-07-01.md`.
  Still blocked: no code signing, no Clean-VM install, no installed-app full GUI
  workflow, DG-001 H1 replacement-medium user decision open.
- **Release-Gate production blocker expansion 2026-07-01:** added
  `services/release_readiness.py`, updated `tools/release_gate.py`, and added
  tests. The gate now blocks on Deferred Gates plus production blockers:
  missing/invalid artifact pair, unsigned installer, missing clean-VM install
  proof, and missing installed-app full GUI proof. Verification:
  `tests/test_services/test_release_readiness.py tests/test_scripts/test_release_gate_cli.py`
  -> `3 passed in 4.38s`; direct `release_gate.py` reports DG-001 plus
  `SIGN-001`, `VM-001`, and `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/release-gate-production-blockers-2026-07-01.md`.
- **Release-Gate proof-schema hardening 2026-07-01:** `services/release_readiness.py`
  now requires explicit synthesis frontmatter for VM/App-GUI proof:
  `release_gate_proof: true`, matching `proof_type`, `status: pass`, and
  `evidence_level: live`. Random Markdown with "PASS" no longer clears a
  production blocker. Verification:
  `tests/test_services/test_release_readiness.py tests/test_scripts/test_release_gate_cli.py`
  -> `5 passed in 3.68s`; direct `release_gate.py` still reports DG-001,
  `SIGN-001`, `VM-001`, and `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/release-gate-proof-schema-2026-07-01.md`.
- **Signing readiness preflight 2026-07-01:** added
  `scripts/diag/verify_signing_readiness.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/signing_readiness.json` show:
  `signtool` missing, CurrentUser/LocalMachine code-signing certificate count
  is 0, installer Authenticode is not signed (`SignerCertificate=null`), and
  `release_signing_ready=false`. Synthesis:
  `docs/superpowers/synthesis/signing-readiness-preflight-2026-07-01.md`.
  `SIGN-001` remains valid; signing cannot be completed here without a signing
  tool and certificate.
- **Clean-VM readiness preflight 2026-07-01:** added
  `scripts/diag/verify_clean_vm_readiness.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/clean_vm_readiness.json` show:
  current process is not admin, `Get-VM`/`vmrun`/`VBoxManage` are missing,
  Hyper-V feature query requires elevated rights, while installer stub and
  NSISBI payload exist. `clean_vm_ready=false`; blockers are
  `not-running-as-admin` and `no-vm-control-tool-found`. Synthesis:
  `docs/superpowers/synthesis/clean-vm-readiness-preflight-2026-07-01.md`.
  `VM-001` remains valid.
- **Installed-app GUI readiness preflight 2026-07-01:** added
  `scripts/diag/verify_installed_app_gui_readiness.py`. Direct run Exit 0 and
  JSON artifact `tests/qa_artifacts/installed_app_gui_readiness.json` show:
  installer stub and NSISBI payload exist, but current process is not admin,
  default installed EXE `C:\Program Files\PB Studio\pb_studio.exe` is missing,
  installer policy requests admin / Program Files / HKLM uninstall key, and
  installer Authenticode is not signed. `installed_app_gui_ready=false`;
  blockers are `installer-requires-admin-current-process-not-admin`,
  `installed-exe-missing`, and `installer-not-signed`. Synthesis:
  `docs/superpowers/synthesis/installed-app-gui-readiness-preflight-2026-07-01.md`.
  `GUI-001` remains valid.
- **Installed-app GUI workflow verifier 2026-07-01:** added
  `scripts/diag/verify_installed_app_gui_workflow.py`. The verifier launches
  the installed EXE, waits for a visible GUI window, records a screenshot,
  checks the four workflow tabs via UIA, and writes a schema-valid
  `release_gate_proof` only on real PASS with explicit `--write-proof`.
  Current direct run blocks with `installed-exe-missing` because
  `C:\Program Files\PB Studio\pb_studio.exe` does not exist; JSON artifact:
  `tests/qa_artifacts/installed_app_gui_workflow.json`.
  `proof_written=false`. Synthesis:
  `docs/superpowers/synthesis/installed-app-gui-workflow-verifier-2026-07-01.md`.
  `GUI-001` remains valid.
- **Release evidence matrix 2026-07-01:** added
  `scripts/diag/verify_release_evidence_matrix.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/release_evidence_matrix.json` aggregate active
  Deferred Gates, production blockers, release-proof frontmatter, and QA JSON
  artifacts for artifact pair, signing, clean VM, installed-app GUI readiness,
  and installed-app GUI workflow. Current result: `release_ready=false`,
  `status=blocked`, accepted release proofs `0`, open items `DG-001`,
  `SIGN-001`, `VM-001`, `GUI-001`. Added regression
  `tests/test_scripts/test_release_evidence_matrix.py`; focused run
  `2 passed`. Synthesis:
  `docs/superpowers/synthesis/release-evidence-matrix-2026-07-01.md`.
- **B-547 Storage-Browser delete live follow-up 2026-06-30:** added
  `scripts/diag/verify_b547_storage_browser_delete_visible.py`. Direct run
  Exit 0 with a visible real `StorageBrowserDialog`, temporary real SQLite DB,
  temporary real `storage/by_sha`, physical-delete checkbox enabled, and real
  QMessageBox confirmation/success dialogs clicked. Evidence: row count
  `1 -> 0`, summary `1 Quellen / 4.0 KB -> 0 Quellen / 0 B`,
  source root existed before and was gone after, `analysis_jobs=0`,
  `analysis_artifacts=0`, `project_sources=1`, success text reported
  `1 Speicherordner geloescht, 4.0 KB freigegeben`. Regression:
  `tests/test_services/test_storage_browser.py tests/test_ui/test_storage_browser.py`
  -> `10 passed in 2.34s`; synthesis
  `docs/superpowers/synthesis/b547-storage-browser-delete-live-2026-06-30.md`.
  Honest limit: not clean-VM, not full OTK-021 7-step live verify, no agent
  `fixed` marker.
- **OTK-021 Backup/Restore portable follow-up 2026-06-30:** added
  `scripts/diag/verify_otk021_backup_restore_portable.py`. Direct run Exit 0
  with real `StoragePortabilityBackupService`, temporary WAL-mode SQLite DB,
  real `storage/by_sha` files, ZIP manifest, restore into a second temp project
  root, DB content check, and SHA256 comparison of restored files. Evidence:
  `backup_storage_file_count=2`, `restore_storage_file_count=2`,
  restored DB `user_version=21`, restored value `wal-visible`, storage hashes
  matched, manifest schema/model/storage fields correct. Regression:
  `tests/test_services/test_backup.py` -> `2 passed in 1.09s`; synthesis
  `docs/superpowers/synthesis/otk021-backup-restore-portable-2026-06-30.md`.
  Honest limit: local roundtrip only; Backup/Restore on VM still open.
- **OTK-021 Project-Bundle follow-up 2026-06-30:** added
  `scripts/diag/verify_otk021_project_bundle_roundtrip.py`. Direct run Exit 0
  with real `ProjectBundleService`, separate file-backed export/import SQLite
  DBs, separate source/target `storage/by_sha` roots, real `.pbbundle`, two
  sources, two jobs, two artifacts, two files, manifest verification, imported
  DB verification, and restored file SHA256 comparison. Regression:
  `tests/test_services/test_project_export.py` -> `3 passed in 1.36s`;
  synthesis
  `docs/superpowers/synthesis/otk021-project-bundle-roundtrip-2026-06-30.md`.
  Honest limit: local roundtrip only; Project-Export + Import on another VM
  still open.
- **OTK-021 Disk-Budget follow-up 2026-06-30:** added
  `scripts/diag/verify_otk021_disk_budget_real.py`. Direct run Exit 0 with
  real `DiskBudgetService`, file-backed SQLite DB, real `storage/by_sha`
  files, two projects, two used sources, one old unused source, one recent
  unused source, summary/project usage check, cleanup estimate check, and real
  free-space probe. Evidence:
  `tests/qa_artifacts/otk021_disk_budget_real_result.json` reports
  `total_bytes=10000`, `source_count=4`, cleanup `reclaimable_bytes=3000`,
  and real disk free-space probe passed. Low-space guard uses patched
  `disk_usage(free=10)`; disk filling was intentionally not done. Regression:
  `tests/test_services/test_disk_budget_global.py` -> `3 passed in 1.17s`;
  synthesis
  `docs/superpowers/synthesis/otk021-disk-budget-real-2026-06-30.md`.
  Honest limit: local service verification only; installed-app/VM path still
  open.
- **DG-001 G.* neu belegt 2026-06-30:** added
  `scripts/diag/verify_dg001_g_schnitt_gui.py` and versioned synthesis
  `docs/superpowers/synthesis/dg001-g-schnitt-gui-live-2026-06-30.md`.
  Direct run with `pb-studio` env exited 0 / `passed=True`: visible
  `SchnittWorkspace`, editor state, tabs `Schnitt`, `Pacing & Anker`,
  `Audio`, `RL & Notes`, 2 timeline clips, 1 locked video clip, 1 waveform,
  RL Notes DB roundtrip, real `QMessageBox` Re-Generate warning, and `No`
  emitted no regenerate signal. Honest limit: synthetic minimal project, not
  historical `test55655`, not a full all-workspaces product run. Release-Gate
  still blocks: DG-001 now waits on the User decision whether the H1 looped
  medium is accepted as replacement for the lost historical H1 original.
- **Latest B-564 code-fix 2026-06-29:** branch contains B-564 work after
  `d69115f`. Completion-Bridge now refreshes the active Video/Audio analysis
  status panel when its `media_type` and `media_id` match the completed step.
  Verification: B-564 focus `2 passed in 2.27s`; affected Statuspanel/
  Completion regression `16 passed in 9.54s`; `py_compile` PASS;
  `git diff --check` PASS. No GUI pipeline live retest yet; status remains
  `code-fix-pending-live-verification`, not `fixed`.
- **B-569 status 2026-06-29:** current code already contains the A1-lane
  audio dropdown fix in `MediaTableController._a1_audio_combo_index()` and
  uses it in both sync `_refresh_director_combos()` and async
  `_apply_refreshed_data()`. Focus tests are green:
  `tests/ui/test_b569_audio_dropdown_reflects_a1.py`
  `tests/ui/test_b577_async_dropdown_reflects_a1.py` -> `2 passed in 6.66s`.
  Vault status moved to `code-fix-pending-live-verification`; no fresh visible
  GUI retest in this session, not `fixed`.
- **B-562 status 2026-06-30:** current code already contains the Cockpit
  full-refresh fix in `ProjectManagementController._on_project_changed()`.
  Focus test refreshed:
  `tests/ui/test_b562_project_open_refreshes_cockpit.py -q` ->
  `2 passed in 3.70s`. Vault frontmatter moved from stale `open` to
  `code-fix-pending-live-verification`. No fresh visible GUI retest in this
  session, not `fixed`.
- **B-567 status 2026-06-30:** current code contains the persistent
  `PBWindow.show_status_error()` path and Brain-V3 error bridge. Focus tests:
  `tests/test_ui/test_b567_brain_v3_error_statusbar.py`
  plus
  `tests/test_services/test_brain_v3_embedding_scheduler.py::test_failed_job_emits_error_text`
  -> `3 passed in 10.16s`. Vault frontmatter moved from stale `open` to
  `code-fix-pending-live-verification`. The exact AudioPipelineV2/Demucs GUI
  path was not freshly live-triggered in this session, not `fixed`.
- **B-573 status 2026-06-30:** current code already contains the frame-sampler
  EOF prevention for late RAFT timestamps. Focus test refreshed:
  `tests/test_services/test_video_frame_sampler.py -q` ->
  `8 passed in 0.67s`. Vault frontmatter moved from stale `open` to
  `code-fix-pending-live-verification`. Prior Agent-Live-PASS remains noted in
  the bugfile; no new 4h RAFT product live retest in this session, not
  `fixed`.
- **Previous push 2026-06-29:** `d69115f test(OTK-021): fix storage browser UI test hang`
  is pushed to origin.
- **Current OTK-021 preflight 2026-06-29:** Startup system check with
  `pb-studio` env and start-script env vars is green: local
  `bin/ffmpeg.exe` 6.1.1, `ffprobe`, real `h264_nvenc`, CUDA on
  GTX 1060, Python 3.10.20, Ollama, `beat_this`, and Demucs all OK.
  Earlier NVENC failure was PATH/WinGet FFmpeg, not the app-resolved binary.
- **Current OTK-021 regression 2026-06-29:** OTK-021 combined non-live slice
  is green: `66 passed in 21.13s`. Storage-Browser UI hang was test-only:
  the test patched the wrong `QMessageBox` object and opened a real offscreen
  modal. Product code unchanged.
- **Current release status 2026-06-30:** `python tools\release_gate.py`
  exits 1. DG-001 remains active
  (`h1-3-h3-g-reverified-PLUS-h1-user-decision-open`): H1
  replacement-medium decision still prevents `fixed` or release status.
- **Worktree:** `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild`
- **Basis:** `origin/main=9570374` (Agent_Tests PR #5).
- **Merge:** `5f428ec` integriert 16 Commits aus
  `origin/claude/B-539-cross-project-reuse-by-sha-2026-06-18`, inkl.
  B-539, B-543..B-546, B-548, Recovery-/Dependency-/beat_this-Arbeit.
- **B-549:** `91d62c1` — Audio-V2 cooperative cancellation aus Fremdrepo-Commit
  `0f7fc3e` diffgenau rekonstruiert. Fokus: `3 passed`.
- **B-554:** `d833492` — dirty Originaldiff byteidentisch übernommen:
  lokaler HF-Cache zuerst, persistente Embedder, Unload beim Scheduler-Stop.
  Fokus: `8 passed`; frühere GUI-Live-Evidenz 52 Clips/1 Modell-Load/76 s.
- **BUG-A:** `7de108a` — SCHNITT-State nach Auto-Edit refresht; dirty
  Originaldatei byteidentisch übernommen. Fokus: `30 passed`.
- **B-570 status 2026-06-30:** codefix is still in place and now has a
  visible verifier. Added `scripts/diag/verify_b570_shutdown_visible.py`, which
  launches a real visible Qt window with `PBWindow.closeEvent`, creates a
  cancelled-but-still-running QThread, closes the window, clicks the real
  `Laufende Tasks` QMessageBox via pywinauto, and checks process exit. Clean
  run: `python scripts/diag/verify_b570_shutdown_visible.py --timeout-s 60`
  -> exit 0; result artifact says `clicked_dialog=true`,
  `clicked_button=Yes`, `returncode=0`, `alive_after=false`. Focus regression
  after that:
  `tests/test_services/test_b570_shutdown_tasks.py`
  `tests/test_services/test_b570_shutdown_process.py` -> `3 passed in 14.80s`.
  Versioned evidence:
  `docs/superpowers/synthesis/b570-visible-shutdown-2026-06-30.md`.
  Honest limit: this is a minimal PBWindow/live-QThread verifier, not the full
  original production case with five concurrent analysis pipelines. Status
  remains `code-fix-pending-live-verification`, not `fixed`.
- **DG-001 H3 neu belegt 2026-06-23:** finaler Run `20260623-050437`
  auf GTX1060. Echter `htdemucs_ft`-Lauf (`reused=False`, vier Stems,
  Audio 8/8) parallel zur echten SigLIP+RAFT-Video-Pipeline (7/7).
  Beide Threads beendet, Wall 36.375 s, Peak 4534/6144 MiB, kein
  Deadlock/OOM. Runner:
  `scripts/diag/verify_dg001_h3_concurrency.py`; versionierter Beleg:
  `docs/superpowers/synthesis/dg001-h3-concurrency-live-2026-06-23.md`.
  DG-001 bleibt wegen H1-Ersatzmedium-User-Entscheid blockiert.
- **Kombinierte Suite:** `80 passed in 9.07s`; `compileall`, Ruff und
  `git diff --check` grün.
- **Vollsuite-Gate BLOCKIERT:** `pytest -q -m "not gui and not e2e and not
  live_gpu and not long_form"` bricht während Collection ab:
  `tests/test_video_analysis_real.py:93` ruft import-time `sys.exit(1)` auf.
  Kein Vollsuite-Testverdikt; nicht als Regression des Integrationsdiffs
  eingeordnet oder gefixt.
- **Originalrepo:** dirty Zustand nicht verändert.
- **Statussprache:** Integration test-grün; kein neuer vollständiger GUI-/GPU-E2E,
  keine neuen `fixed`-Marker.
- **Push:** Branch auf `origin` vorhanden.
- **Nächster Schritt:** offene OTK-021 Live-Bugs weiter triagieren/fixen.
  B-570 braucht weiter sichtbaren GUI-Klickpfad; B-562/B-567 haben bereits
  Code-/Live-Hinweise im Bugfile, aber keine User-`fixed`-Freigabe.

## ⛔ VERIFIKATIONS-AUDIT 2026-06-18 — viele „fixed/PASS"-Marker sind NICHT gedeckt
Ein 4-Agenten-Audit (read-only) ergab: von 23 geprüften OTK/DG-001/Bug-Markern sind nur **7
nachprüfbar, 12 nicht überprüfbar (Evidenz gelöscht/nie im Clone), 4 ehrlich offen**.
NICHT überprüfbar (reine Doku, NICHT als grün behandeln, vor Release neu fahren):
**DG-001 H1/H1.3/H2.1-alt/H3/G.\***, **OTK-016/017/018/019**, **B-505, B-520**.
Einzeln nachgeprüft 2026-06-18: **B-512** (fixed widerspricht eigenem Body „Live offen", kein Test) + **B-532**
(nur Linter, defensives try-except) = belegfrei, geflaggt. **B-527 + B-528 sind belegt** (existierende Tests
`test_backup_service.py` 15p / `test_project_save_action.py` 4p selbst grün, ehrliche Vorbehalte, User-Freigabe) —
der Pauschal-Verdacht des Forensik-Agenten war für diese beiden falsch.
Echt gedeckt (Screenshots vorhanden): **OTK-003/004/008/009/010** (09.06.).
Per DB-Seed statt voll-E2E verifiziert (Integration NICHT bewiesen): **B-539 T32, Tier 31, Block 1**
(Backup-70 + Disk-Budget-71 sind sogar toter Code ohne App-Aufruf).
**B-539 `fixed` wurde zurückgezogen** → `fixed-with-critical-gaps` (siehe B-543..B-546).
Vollständig: `wiki/synthesis/verifikations-gesamtaudit-2026-06-18.md`. OTK-021 ist NICHT release-/fixed-reif.

## Codex Recovery Session 2026-06-16 (newest)

- **Scope:** Restore local-only progress from the non-git folder
  `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild`
  into a clean GitHub clone without overwriting the old folder.
- **Current working repo:** `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild_github_compare`.
  Use this repo/worktree, not the old non-git folder.
- **Branch:** `codex/recover-local-analysis-percent-2026-06-16`.
- **Commit:** `137c15e chore(recovery): restore local analysis percent progress`.
- **Remote:** branch pushed to
  `origin/codex/recover-local-analysis-percent-2026-06-16`.
- **Recovered files:** `services/analysis_status_service.py`,
  `services/ingest_service.py`, `tests/conftest.py`,
  `tests/test_services/test_ingest_service.py`.
- **Recovered behavior:** bulk analysis-status inference and percent map,
  bulk media-list `analysis_percent` refresh, and regression coverage for
  video metadata not showing as `0%`.
- **Verification:** `git diff --check` passed; `py_compile` passed for the
  four recovered files. Targeted regression test passed in a temporary local
  Python 3.10 conda env:
  `tests\test_services\test_ingest_service.py::TestGetAllMedia::test_get_all_video_backfills_metadata_analysis_percent`
  -> `1 passed in 6.80s`. The temporary `.conda-test` env was removed after
  the run.
- **Full small-data audio E2E 2026-06-16:** User requested a full test run
  with few data and a 4-minute audio. A local `.conda-pb-full` env was created
  from Python 3.10 plus `requirements-py310-cu113.txt`. Smoke check reported
  `torch 1.12.1+cu113`, `cuda_available True`, GPU `NVIDIA GeForce GTX 1060`,
  and `pipeline_import_ok 8`. Synthetic 4-minute WAV:
  `test-report\e2e-audio-4min-20260616\synthetic_4min.wav`.
  Command:
  `.\.conda-pb-full\python.exe scripts\diag\e2e_audio_pipeline_orchestrator.py --audio test-report\e2e-audio-4min-20260616\synthetic_4min.wav`.
  Result: `EXITCODE=0`; orchestrator log reports `failed=False`,
  `total=274.3s`; stages completed: `stem_gen`, `beat_grid`, `onset`, `key`,
  `structure`, `lufs`, `spectral`, `av_pacing`. Evidence log:
  `test-report\e2e-audio-4min-20260616\e2e_audio_pipeline.log` (ignored by
  git).
- **Full small-data audio E2E limits:** `vendor/beat_this` submodule cannot be
  initialized because remote commit `7ecf41375b9be919099b1ea2ecdd9fe5df937fa3`
  is not available from `https://github.com/CPJKU/beat_this.git`. Therefore
  beat detection used the built-in librosa fallback and returned `bpm=0.0` for
  the synthetic test file. This is not proof that the `beat_this` path works.
- **Current request follow-up:** Added context-budget clean-stop discipline
  to `AGENTS.md`: when context/capacity is low, stop starting new work,
  finish only the smallest safe unit, write exact handoff, run
  `tools\agent_handoff.ps1`, and leave no hidden dirty state.
- **Vault path correction:** use
  `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio`
  for current Vault logging. Older docs may still mention
  `C:\Brain-Bug\projects\pb-studio`.
- **Open:** Recovery branch has not been merged to `main`. Full PB Studio test
  environment is still not restored; only the targeted regression test above
  passed. DG-001 remains open; no release/fixed claim allowed.
- **Next safe step:** create/review PR for the recovery branch, then decide
  whether to merge after broader test coverage or restore the full
  `pb-studio` Python environment.

## Cowork-Agent-Session 2026-06-15 (newest)

- **Scope:** Status-Review-Folgearbeit + Release-Gate + E2E-Live-Abnahme + DG-001 Teil-Live-Verify.
  Alle Aenderungen committet + auf `origin/main` gepusht (head `855ae32` zum Schreibzeitpunkt; H1-Lauf laeuft noch).
- **Alembic-CRITICAL (13.06.) = bereits gefixt + test-abgesichert** (11 passed); Orphan-Index-Drop-Revision
  `f0a1b2c3d4e5` hinzugefuegt (idempotent, gegen Live-DB verifiziert). Commit `cbfbca4`.
- **Release-Gate (neu):** `services/deferred_gates.py`, `tools/release_gate.py` (Exit 2 bei offenen Gates),
  `tools/agent_handoff.ps1 -ReleaseGate`, weiches Start-Banner in `services/startup_checks.py`
  (LIVE in GUI bestaetigt). Pflicht-Checklisten: `docs/superpowers/E2E_LIVE_ACCEPTANCE.md`,
  `docs/superpowers/DG-001_LIVE_VERIFY.md`.
- **E2E-Live-Abnahme** (Service + GUI, GTX 1060): Phasen 1-4 PASS. Beleg
  `test-report/e2e-live-acceptance-20260615/RESULT.md`. **DG-001 H3** (Demucs+Video parallel) PASS,
  **G.\*** SCHNITT-GUI live PASS, **H2.1** NVENC-Export. **H1** 62-Min-Scale-Lauf laeuft (VRAM stabil).
- **Neue Bugs gefixt:** **B-536** PacingStrategist Fence-Parse-Mislabel (Commit `dd90d87`),
  **B-537** Diag-Skripte Repo-Root (Commit `2fb7f4d`). Status beide `code-fix-pending-live-verification`.
- **OTK-008:** Audio-"fehlt"-Blockade ist nur Such-String-Fehler (`Crusty_Progressive Psy Set2.mp3`
  mit Unterstrich existiert) -> aufhebbar. Doku `docs/superpowers/E2E_FINDINGS_2026-06-15.md` (`b162015d`).
- **Next agent:** H1-Endergebnis aus `outputs/h1_scale.log` (`H1_EXIT`) lesen; offen bleiben user-only
  H1.3 (4h), H2.2 (Playback-Verdikt), CRF-D1/D2/D3. KEIN `fixed`-Marker gesetzt.

## Latest Governance Update

- **Date:** 2026-06-14
- **Active plan:** `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`
- **Repo plan:** `docs/superpowers/archive/superseded-plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md`
- **Vault mirror:** `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md`
- **Decision:** `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md`
- **Status:** CRF executable fix waves are complete per CRF Vault mirror; B-498..B-520 and B-523..B-529 are recorded fixed after live/user confirmation. `ACTIVE_PLAN.md` selects the OTK masterplan only. OTK-018 was live-verified-complete on 2026-06-14 after user broad autonomous release. OTK-019 technical rest-probe passed; user decided to defer the heavy 4h live gate for later.
- **CRF remaining:** CRF-D1 Brain deprecation, CRF-D2 Vault sync, CRF-D3 cu121/torch-2.x migration remain user decisions, not agent app-code tasks.
- **Next task:** `OTK-021 90 Live-Verify`. User approved prerequisite waiver on 2026-06-14, with deferred gates tracked in `docs/superpowers/DEFERRED_GATES.md`.
- **Parallel work rule:** user gave broad release on 2026-06-14, but AGENTS.md still forbids parallel half-finished app-code work in the same repo. Parallel teams may only do read-only analysis or work in isolated worktrees after one task is selected.
- **OTK-018 verification:** focused Audio-V2 package `82 passed`; fresh GTX-1060 service E2E ran stem_gen, beat_grid, onset, key, structure, lufs, spectral, av_pacing with `failed=False` in 276.4s; real GUI selected audio and clicked `Audio analysieren`, console showed V2 default route start and completion with no V2 error. Evidence: `test-report/e2e-audio-v2-otk018-2026-06-14-fresh.log`, `test-report/otk018-audio-v2-gui-live-2026-06-14.log`, `test_reports/otk018_audio_v2_gui_live_20260614.py`.
- **OTK-019 2026-06-14:** focused technical tests `39 passed`; `test_reports/otk019_remaining_verify_20260614.py` exit 0. Passed: proxy generation/decode (size ratio 0.1301, 5s decode in 0.344s), 3-keyframe contact sheet, process-kill resume from checkpoint, synthetic 4h coverage guard 100%, GPU-lock wait behind simulated Audio-V2 holder. Honest limits: no human/QMediaPlayer smoothness verdict, no full 4h video through all model stages, no real concurrent Demucs+Video run. User decision: defer heavy 4h gate for later, status `deferred-heavy-live-gate`.
- **OTK-021 2026-06-14:** prerequisite re-check only. Audio-V2 is now agent-live-verified-complete, but Plan A heavy live gate is deferred, Plan B Tier-1/2 completion is not proven, and no explicit Plan-C prerequisite waiver/user V2 acceptance exists. Status remains `blocked-prerequisite-rechecked-2026-06-14`.
- **OTK-022 2026-06-14:** Phase-2 review completed. Read `_lib/build_edl_v7.py` and PB pacing counterparts. Thematic Chapter Sequencing is useful design pattern, but port would introduce new PB feature/architecture surface. No code port. Status `completed-no-port-design-pattern`.
- **OTK-021 waiver 2026-06-14:** user approved proceeding despite missing OTK-019 heavy gate, explicitly requiring the deferred work not be forgotten. DG-001 tracks full 4h model-pipeline, human playback acceptance, and real Demucs+Video coexistence before fixed/release status.
- **OTK-021 Tier 1 2026-06-14:** DB-Provenance tables and Storage-Layout helper are code/tests complete. Added Alembic revision `e5f6a7b8c9d0`, ORM models, `services/storage_provenance/layout.py`, and focused tests. Verification: `6 passed` focused, `5 passed` migration regressions, `2 passed` Alembic roundtrip, py_compile, `git diff --check`. No fixed marker.
- **OTK-021 Tier 2 2026-06-14:** Building blocks are code/tests complete: `source_identity.py`, `file_tracking.py`, `dedup_lookup.py`, `adapter_layer.py`, plus focused tests. Verification: Tier-2 `9 passed`; Tier1+Tier2 combined `15 passed`; py_compile; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 Tier 3/30 2026-06-14:** Storage-Migration-Service code/tests complete. Registers existing V2 stems and Plan-A video outputs into provenance tables; audio stems use Junction/Symlink under `by_sha`. Verification: storage migration/layout `6 passed`; OTK-021 service suite `18 passed`; py_compile; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 Tier 3/31 2026-06-14:** SCHNITT-Audio-Adapter code/tests complete. `ProjectManager.open_project()` runs adapter defensively after DB init; service builds missing stem Junctions idempotently. Verification: adapter/storage-migration `5 passed`; OTK-021 Slice `20 passed`; py_compile; `git diff --check`. No GUI live click; no fixed marker.
- **OTK-021 Tier 3/32 2026-06-15:** Cross-Project-Reuse UX code/tests complete. Added `services/storage_provenance/cross_project_reuse.py`; import path applies reusable provenance to `analysis_status`; status panel shows provenance tooltips; import controller shows non-modal reuse notice with project-scoped "Nicht mehr fragen". Verification: cross-project reuse focus `5 passed`; OTK-021 Slice `20 passed`; py_compile; `git diff --check`. No product live re-import verification; no fixed marker.
- **OTK-021 Tier 3/33 2026-06-15:** Storage-Browser UI code/tests complete. Added `services/storage_provenance/storage_browser.py`, `ui/dialogs/storage_browser_dialog.py`, and Settings button. Browser lists sources sorted with project usage, stage count, byte total, last-used, unused/age filters, per-row delete, and bulk delete with confirm. Verification: storage-browser focus `5 passed`; OTK-021 Slice `27 passed`; py_compile; `git diff --check`. No Settings GUI live click; no fixed marker.
- **OTK-021 Tier 3/34 2026-06-15:** Project-Export + Import code/tests complete. Added `services/storage_provenance/project_bundle.py` and tests. Exports `.pbbundle` zip with manifest, project subset, project_sources, analysis_jobs/artifacts, and referenced `by_sha` files; import validates manifest/file SHA, preserves existing artifacts on conflict, creates project and sources. Verification: project-export focus `3 passed`; OTK-021 Slice `30 passed`; py_compile; `git diff --check`. No real same-machine/other-machine export-import live verification; no fixed marker.
- **OTK-021 40 Caller-Migration 2026-06-15:** Caller-Migration code/tests complete. Added `services/storage_provenance/caller_migration.py`; Audio V2 `StemGenStage` writes `analysis_jobs`/`analysis_artifacts` for generated or reused stems; Plan-A `VideoAnalysisPipeline` writes done-stage provenance artifacts. Verification: caller-migration focus `3 passed`; OTK-021 Slice `33 passed`; py_compile; `git diff --check`. No product live V2/Plan-A GUI workflow verification; no fixed marker.
- **OTK-021 50 Service-Coverage 2026-06-15:** Service-Coverage code/tests complete for `services/storage_provenance/*`. Added tests only in `tests/test_services/test_cross_project_reuse.py`, `tests/test_services/test_file_tracking.py`, `tests/test_services/test_storage_browser.py`, and `tests/ui/test_schnitt_audio_adapter.py`. Verification on `pb-studio` env: `41 passed`; total storage provenance coverage `93.31%`; every `services/storage_provenance` file at least `87%`; `compileall`; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 51 Controller-Coverage 2026-06-15:** Controller-Coverage code/tests complete. Added `ui/widgets/cross_project_reuse_toast.py`, delegated `ImportMediaController._show_cross_project_reuse_notice()` to it, and added real Qt tests for storage browser dialog, reuse toast, and SCHNITT audio binder. Verification: UI focused `15 passed`; coverage total `90.24%`; `ui/dialogs/storage_browser_dialog.py` 88%, `ui/widgets/cross_project_reuse_toast.py` 88%, `ui/controllers/schnitt_audio_binder.py` 96%, `services/storage_provenance/schnitt_audio_adapter.py` 100%; OTK-021 Slice `48 passed`; `compileall`; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 60 Test-Infra 2026-06-15:** Test-Infra code/tests complete. Added `tmp_storage_root`, `mock_v2_stems`, `mock_project_with_artifacts`, and `directory_link_factory` fixtures in `tests/conftest.py`, plus offline proof test `tests/test_services/test_storage_provenance_test_infra.py`. Verification: infra focus `1 passed`; OTK-021 Slice `49 passed`; `compileall`; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 70 Backup-Portability 2026-06-15:** Backup-Portability code/tests complete. Added `services/storage_provenance/backup_portability.py` with portable ZIP backup manifest, SQLite backup API snapshot, `storage/by_sha` full-copy payload, restore extraction, and frequency settings validation. Verification: `tests/test_services/test_backup.py` `2 passed`; OTK-021 Slice later `51 passed`; `compileall`; `git diff --check`. No VM restore/live verification; no fixed marker.
- **OTK-021 71 Disk-Budget Global 2026-06-15:** Disk-Budget code/tests complete. Added `services/storage_provenance/disk_budget.py` with total/project usage summary, unused-old cleanup estimate, and free-space migration probe; Storage-Browser summary now shows total bytes. Verification: disk-budget + storage-browser focus `7 passed`; OTK-021 Slice `54 passed`; `compileall`; `git diff --check`. No product live verification; no fixed marker.

## Previous Governance Update

- **Date:** 2026-06-09
- **Active plan:** `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`
- **Repo plan:** `docs/superpowers/archive/superseded-plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md`
- **Vault mirror:** `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md`
- **Decision:** `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md`
- **Status:** previous registry plans with open work were marked `superseded` and transferred into OTK tasks. No app-code change. No product bug marked `fixed`.
- **OTK-001:** Governance drift in this handoff file was cleaned on 2026-06-09. Older FFmpeg/B-471/B-458/B-462/B-463 details remain represented in the OTK masterplan, not as active-plan authority here.
- **OTK-002:** Completed by user continuation release plus agent review. No blocking issue found in `.agents/skills/pb-agent-team-architect`, `pb-live-verify-orchestrator`, `pb-concurrency-strike-team`, or `pb-release-readiness-team`. No claim that the user read every file line-by-line.
- **OTK-003:** Agent-side check ran on 2026-06-09 and later autonomous GUI verification passed for project `test55655`: waveform, thumbnails, zoom controls, cut list, and clip inspector observed. User explicitly approved `fixed` marker on 2026-06-09.
- **OTK-020/B-473:** User authorized switching focus on 2026-06-09. Root cause evidence: app settings pointed at `http://legacy:8080` with `legacy-model`, while local Ollama answered on `localhost:11434`; full PB system prompt caused `OllamaClient.chat()` timeout beyond 120s; ChatDock watchdog was 60s. Code now falls back from stale configured URL to localhost, reselects missing model, caps LocalAgent system prompt for GTX-1060 latency, and uses a 180s ChatDock watchdog. User settings were reset to `http://localhost:11434` / `gemma3:4b` after backup. Standalone agent smoke returned `OK` in 67.34s. Autonomous GUI verification passed and user approved `fixed` marker on 2026-06-09.
- **Filled checklist update 2026-06-09:** `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md` reports OTK-020, OTK-003, OTK-004, OTK-008 as GUI PASS; OTK-010, OTK-015, OTK-019 as PARTIAL; remaining listed tasks as decision/scope. The checklist explicitly says no agent-side `fixed` marker.
- **Autonomous GUI verification 2026-06-09:** Agent used real PB Studio GUI with `pywinauto`. OTK-020 PASS (ChatDock/Ollama UI answer, KI-Agent tasks finished); OTK-003 PASS (project `test55655`, SCHNITT timeline/waveform/thumbnails/zoom/cut list/inspector); OTK-004 PARTIAL PASS (media table and analyzed clips observed, no new import); OTK-008 PASS for GUI navigation (Pacing/Anker, Audio, RL Notes, Schnitt tabs). Evidence: `test_reports/live_autonomous_20260609_*.png`; Vault synthesis `wiki/synthesis/functional-test-otk-autonomous-gui-2026-06-09.md`. `fixed` markers were set only after explicit user approval.
- **OTK-020/B-473:** User explicitly approved `fixed` marker on 2026-06-09 after autonomous GUI verification.
- **OTK-004:** User gave broad release, then agent executed missing GUI import/live resolver path. Video import dialog opened, 1 MP4 selected, FolderImport and BrainV3Hashing finished, media table stayed populated, no checked Traceback/ERROR/resolver failure. OTK-004 marked `fixed`.
- **OTK-008:** User selected `test55655` and wrote `freigegeben`. Agent ran substitute GUI verification on existing project `test55655`: SCHNITT opened, RL Notes text was written, app restarted, project reopened, and the same RL Notes text was still present. Agent also checked `cut_rate_combo` wheel protection by hover+wheel-scroll; combo crop stayed pixel-identical (`diff_sum=0.0`). Notes-editor undo also passed: suffix appended, `Ctrl+Z`, exact original text returned. Pacing regenerate mouse-automation attempts did not show the dialog, but UIA `Invoke()` on the same visible enabled button showed the expected QMessageBox; B-474 corrected to `cannot-reproduce` as app bug. Evidence: `test_reports/live_autonomous_20260609_otk008_rl_notes_after_reload.png`, `test_reports/live_autonomous_20260609_otk008_cut_rate_after_wheel.png`, `test_reports/live_autonomous_20260609_otk008_undo_notes_after_ctrlz.png`, `test_reports/live_autonomous_20260609_otk008_regenerate_dialog_invoke.png`; repo synthesis `docs/superpowers/synthesis/functional-test-otk008-test55655-substitute-2026-06-09.md`. Honest status: partial substitute verification only; formal Phase-12 criteria still open, so no `fixed` marker.
- **OTK-008 autonomous limit:** Formal Phase-12 completion is blocked because `Crusty Progressive Psy Set2.mp3` was not found and the available Solo_Natur folder contains 124 MP4 files instead of the plan's 103. Substitute checks passed only for `test55655` navigation, RL Notes persistence, combo-wheel protection, notes-editor undo, and regenerate dialog via UIA Invoke. No `fixed` marker.
- **OTK-009:** Completed on 2026-06-09. B-310 and B-313 live-verified on `test55655`; SCHNITT timeline, thumbnails, cut list, audio metadata/stems/waveform, and sub-tab tooltip were observed. B-316..B-320 current Vault state is fixed; no remaining contradiction found.
- **OTK-010:** Fixed on 2026-06-09 for masterplan scope. Brain V3 boot health, GpuSerializer init, EmbeddingScheduler active, Brain V3 GUI panel, Brain V3 tests (`37 passed`), isolated NVENC 1-frame encode, existing B-276 Brain+NVENC serializer live evidence, adopted D-035 Pacing decision, and B-370 GUI Auto-Edit with Studio-Brain flag were verified. GUI Auto-Edit on `test55655` produced 767 segments / 767 cuts and 1447 `mem_decision` rows.
- **OTK-011:** Completed on 2026-06-09 as decision/transfer task. Original area audit completed all 10 audit areas and final synthesis; user-approved follow-up fixplan already exists as `PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25`. Remaining B-348..B-430 fix/live work is tracked as OTK-007.
- **OTK-012:** Completed on 2026-06-09 as decision/transfer task. Full project file audit completed as read-only static audit; user-approved follow-up fixplan exists as `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31` via D-055. Remaining fixplan work is tracked as OTK-005.
- **OTK-013:** Completed on 2026-06-09 as decision/transfer task. Conflict-quality audit completed as static audit; user decision exists as D-058 for FFmpeg resolver fix CQ-004/CQ-005. That follow-up was transferred to OTK-004 and live-verified there. No new broad fixplan was invented for candidate-only findings.
- **OTK-016:** Completed on 2026-06-09. B-327 fixed (M4A FFmpeg fallback E2E), B-332 fixed (preview anchored to first video), B-197/B-198 fixed (live via OTK-010 + guard tests), B-331 cannot-reproduce (chunk-51 hang), B-265 wontfix (SB2 dGPU intermittent, no code bug). No agent `fixed` marker on product bugs without user.
- **OTK-017:** Completed on 2026-06-10. 11 bugs user-confirmed fixed after GUI live-verify (B-458/459/460/463/464/465/466/467/468/470/472); B-469 stays parked-monitoring. Commits 88fd73b/b9d6b63/a7776d2/8075a92/683f048. New findings B-490/B-491 filed open (out of scope).
- **Next task:** `OTK-017 completed. User selects next among open OTK tasks (OTK-005/007/018/019/021/022) or triage B-490/B-491.`

## Current Protocol

1. Start every agent session with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\agent_start.ps1
   ```

2. End or switch every agent session with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\agent_handoff.ps1
   ```

3. Source of truth order:

   - Git commits on the current branch.
   - `docs/superpowers/ACTIVE_PLAN.md`.
   - Vault living plan and `C:\Brain-Bug\projects\pb-studio\log.md`.
   - This file.

4. Chat history is not source of truth. If it is not in Git or Vault, next
   agent must treat it as unknown.

## Current Branch

`codex/OTK-021-source-consolidation-2026-06-22`

Latest pushed product/tool commit:

```text
d37e710 fix(B-555): make release gate console-safe
```

Push status: `origin/codex/OTK-021-source-consolidation-2026-06-22...HEAD 0 0`
after commit `d37e710`.

## Current Active Plan

See `docs/superpowers/ACTIVE_PLAN.md`.

Active plan:

```text
PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
```

## Current B-885 status (2026-08-24)

```text
agent-fixed-await-user: intermittent Shiboken access violation during
auto-resume traced to two owners starting the same timeline DB load:
ProjectManager.project_changed and StartupCheck.on_done. StartupCheck no
longer calls timeline.load_from_db directly; an identical in-flight project
load is coalesced before teardown. Targeted regression suite: 9 passed;
PyCompile, Ruff, and diff check green. Two controlled root-fix auto-resume runs
each had exactly one timeline teardown and one build, exit code 0, no
Fatal/Traceback/new WER, process count zero, and SQLite quick_check ok. User
has not set fixed. Next masterplan work remains W8 running-export
shutdown/cancel verification. No push.
```

Current next task:

```text
Quellstand konsolidiert. Folgeblocker B-556/B-559/B-557/B-560/B-561
sequenziell korrigiert. Finale vollständige Nicht-Live-Suite:
2762 passed, 45 skipped, 5 deselected, 0 failed.
OTK-021 Live-Preflight 2026-06-22 ist BLOCKED:
GTX 1060 `CM_PROB_PHANTOM`, CUDA false, H.264/HEVC NVENC
`CUDA_ERROR_NO_DEVICE`. App nicht gestartet; Intel/CPU-Ersatz verboten.
Nach Hardware-Recovery Preflight wiederholen, dann GUI/DG-001 fortsetzen.
Main-Integration/Release bleiben gestoppt.
```

Current OTK-021 Step 3 status:

```text
2026-07-03 product-path live pass, manual GUI click pending.
Real ProjectManager project A/B, real ingest_audio import into both projects,
global by_sha manifest + real stem artifacts, Project B AnalysisStatus
stem_separation=done, stem paths exist, and ImportMediaController
_notify_cross_project_reuse() created the reuse message and non-modal notice.
Evidence:
docs/superpowers/synthesis/otk021-step3-cross-project-reuse-import-notify-2026-07-03.md
and tests/qa_artifacts/otk021_cross_project_reuse_import_notify_result.json.
Verifier: scripts/diag/verify_otk021_cross_project_reuse_import_notify.py status=pass.
Focused tests: cross-project reuse 17 passed; manifest robustness 8 passed.
Honest limit: no manual import-dialog GUI click. OTK-021 overall remains open;
Steps 1-2 still need current product-live evidence.
```

Current OTK-021 Step 4 status:

```text
2026-07-03 product-path live pass, GUI live pending.
ProjectManager.open_project() now repairs stale ProjectSource paths by SHA
inside the opened project folder. Evidence:
docs/superpowers/synthesis/otk021-step4-file-tracking-open-project-live-2026-07-03.md
and tests/qa_artifacts/otk021_file_tracking_open_project_result.json.
Verifier: scripts/diag/verify_otk021_file_tracking_open_project.py status=pass.
Unit: tests/test_services/test_file_tracking.py 3 passed.
Syntax: py_compile Exit 0.
Honest limit: no manual GUI click. OTK-021 overall remains open; Steps 1-2
still need product-live evidence.
```

Current OTK-003 status:

```text
fixed: autonomous GUI SCHNITT/timeline workflow passed, and user explicitly approved `fixed` marker on 2026-06-09.
```

Current OTK-020 status:

```text
fixed: standalone service smoke green, autonomous GUI ChatDock/Ollama test passed, and user explicitly approved `fixed` marker on 2026-06-09.
```

Current OTK-004 status:

```text
fixed: autonomous GUI media/import workflow passed after user broad release; FolderImport and BrainV3Hashing finished, no checked resolver failure.
```

Current OTK-008 status:

```text
partial-substitute-live-verification-formal-open: `test55655` SCHNITT/RL Notes persistence passed after restart/reload; `cut_rate_combo` wheel protection passed by crop diff; notes-editor undo passed; Pacing regenerate dialog appeared via UIA Invoke; B-474 now `cannot-reproduce`; formal Phase-12 guide remains open.
```

Current OTK-009 status:

```text
fixed: contradiction check found B-316..B-320 current fixed; B-310/B-313 live-verified on test55655 and marked fixed.
```

## Consolidated Open Work

All older active/inactive plan work is consolidated in:

```text
docs/superpowers/archive/superseded-plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md
```

Use OTK task order only. Do not resume old registry plans directly.

## Required Handoff State

Handoff must be one of:

- clean commit;
- named stash with exact reason and path list;
- explicit user-approved dirty state documented in Vault and chat.

Unknown dirty changes block work.

# PB Studio Rebuild — Code- und Projekt-Audit

**Datum:** 2026-05-01
**Branch:** `codex/full-app-green-fix-2026-04-29`
**Letzter Commit:** `d2c9133 feat: rebuild PB Studio workflow UI`
**Auditor:** PB Commander (autonom, keine Code-Änderungen)
**Methode:** statische Inspektion, gezielte `pytest`-Läufe, Brain-Bug-Wiki-Cross-Check

---

## 0. Audit-Skopus und Beweis-Basis

- Es wurde **kein Code geändert**. Alle Aussagen verweisen auf konkrete
  Datei- und Zeilenstände.
- Geprüft wurde Branch-Diff `master…HEAD` (55 Dateien, +3488/-354) plus die
  `M`-Files des Working-Tree (14 Dateien) und 4 untracked Files
  (`services/cockpit_orchestrator.py`, 3 neue Tests, `docs/ui_mockups/`).
- Tests:
  - Gezielte Suite `tests/test_services/test_cockpit_orchestrator.py`,
    `test_cockpit_ui_contract_static.py`, `test_gpu_pipeline_stability.py`,
    `tests/ui/test_frontend_rebuild_contract.py`,
    `tests/ui/test_workspaces_smoke.py` mit conda-Env `pb-studio` (Py 3.10):
    **26/26 grün** (6.85 s).
  - Voll-Collect: **1469 Tests** sammelbar, **1 PytestCollectionWarning**
    in `tests/test_audio_analysis_real.py:46` (Klasse `TestResult` mit
    `__init__`).
- **Live-Verifikation der App** wurde **nicht** ausgeführt. Befunde sind
  Code-Beweise; Worte wie „funktioniert" werden nur dort genutzt, wo sie
  durch Tests oder Code unmittelbar belegbar sind. Wo nur Code-Inspektion
  vorliegt, steht „Code-Beweis" oder „nicht live verifiziert".

---

## 1. Branch-Stand (Fakten)

- Branch ist **27 Commits vor master** auf Audio/Video/Pacing-Pipelines
  und kompletten **Workflow-UI-Rebuild** (5 Workspaces im Cockpit-Modell).
- Working-Tree hat **14 unstaged M-Files** und **5 untracked Files** —
  diese sind der eigentliche Kern dieses Audits, weil sie noch nicht
  committet sind:

  ```
  M  CLAUDE.md
  M  services/ai_audio_service.py
  M  services/beat_analysis_service.py
  M  services/model_manager.py
  M  services/pacing_edit_helpers.py
  M  services/video_analysis_service.py
  M  tests/ui/test_frontend_rebuild_contract.py
  M  tests/ui/test_workspaces_smoke.py
  M  ui/controllers/workspace_setup.py
  M  ui/widgets/nav_bar.py
  M  ui/workspaces/__init__.py
  M  ui/workspaces/edit_workspace.py
  M  ui/workspaces/media_workspace.py
  M  ui/workspaces/workflow_pages.py
  M  workers/video.py
  ?? CLAUDE.original.md
  ?? docs/ui_mockups/
  ?? services/cockpit_orchestrator.py
  ?? tests/test_services/test_cockpit_orchestrator.py
  ?? tests/test_services/test_cockpit_ui_contract_static.py
  ?? tests/test_services/test_gpu_pipeline_stability.py
  ```

- 14 M-Files erzeugen je eine `LF→CRLF`-Warnung von Git. Kein Funktional-
  Effekt, aber `core.autocrlf`-Setup nicht final.

---

## 2. Befunde nach Schweregrad

### P0 — Blocker / User-sichtbar kaputt

#### F-01 — `StemsWorkspace` ist im UI nicht eingebunden
- **Datei:** `ui/controllers/workspace_setup.py:318` und
  `:408–411` (Workspace-Stack).
- **Beweis:**
  - `_create_workspaces` baut **fünf** Workspaces (Project Dashboard,
    MaterialAnalysis, Edit, Stems, Convert, Deliver), packt aber nur
    **vier** in `workspace_stack`:
    ```text
    workspace_stack.addWidget(_project_dashboard)
    workspace_stack.addWidget(_material_analysis_ws)
    workspace_stack.addWidget(_edit_ws)
    workspace_stack.addWidget(_deliver_ws)
    ```
  - `self.window._stems_ws = StemsWorkspace()` (Zeile 318) wird nirgendwo
    sichtbar gemacht (weder in `workspace_stack` noch in `right_panel`,
    `panel_setup.py:44/77/101` zeigt nur CHAT/TASKS/LOG).
  - `_stems_ws.stem_widget` wird **nur** für Signal-Wiring zum
    `stem_player` verwendet (Z. 320–327).
- **Konsequenz:** Das DAW-artige Stem-Mixer/Transport-Panel ist im UI
  unsichtbar. `StemsController._update_stem_workspace` und
  `panel_setup._on_analysis_done` (Z. 233) feuern Refreshes auf ein
  Widget, das niemand sieht. Stems lassen sich starten (über Side-Panel-
  Button), aber das Mix/Player-Surface fehlt.
- **Status laut Wiki:** B-253 markiert „Stem-UI-Refresh-Bridge fixed".
  Die Bridge ist da; **das Ziel-Widget ist es nicht**. Sehr wahrscheinlich
  Regression durch Workflow-Rebuild, weil Stems im alten 5-Workspace-Modell
  einen eigenen Tab hatte und in der neuen Nav-Leiste
  (`WORKSPACE_NAMES`, `nav_bar.py:40–46`) explizit gestrichen wurde
  ohne Ersatzplatz.

#### F-02 — `btn_clear_all` (Sammlung bereinigen) ist nicht erreichbar
- **Datei:** `ui/workspaces/media_workspace.py:588–597`,
  Wiring `ui/controllers/workspace_setup.py:193`.
- **Beweis:**
  - `btn_clear_all` lebt im `filt`-Widget des `_video_sub_tabs`
    (`media_workspace.py:588–594`).
  - `_video_sub_tabs.setVisible(False)` (Z. 597) und
    `_audio_sub_tabs.setVisible(False)` (Z. 867).
  - Beide Sub-Tab-Container werden **nirgends** ans Page-Layout
    gehängt — `grep _video_sub_tabs` zeigt nur Konstruktion und das
    `setVisible(False)`. Sie werden Eltern-los geboren und nie sichtbar.
  - Trotzdem connectet `workspace_setup.py:193`
    `btn_clear_all.clicked` → `import_media._clear_all_media`.
- **Konsequenz:** „Sammlung bereinigen" ist im neuen UI nicht
  klickbar. Funktion ist verkabelt aber tot. Der gleiche Mechanismus
  betrifft den Filter-Hinweis-Tab.
- **Status laut Wiki:** Kein offener Bug deckt das ab. **Neuer Befund.**

#### F-03 — `LegacyAnalysisWorkspace` ist toter Code, aber ein Test blockt seine Entfernung nicht mehr
- **Datei:** `ui/workspaces/workflow_pages.py:322–523`.
- **Beweis:**
  - `LegacyAnalysisWorkspace` wird in `__init__.py:8` **nicht**
    exportiert; `AnalysisWorkspace = MaterialAnalysisWorkspace`
    (Z. 526). `grep LegacyAnalysisWorkspace` findet keinen
    Konsumenten.
  - `tests/ui/test_workspaces_smoke.py` ersetzt den vorherigen Test
    `test_analysis_workspace_owns_audio_video_steps` durch
    `test_material_analysis_workspace_keeps_selection_and_actions_together`
    — Legacy-Klasse ist nicht mehr abgedeckt.
- **Konsequenz:** ~200 Zeilen toter Code (UI-Konstruktion, Tooltips,
  Buttons, die nichts erreichen). Kein Crash, aber Pflege- und Audit-Risiko.

### P1 — Funktional unklar, hoher Verdachtsgrad

#### F-04 — UI-Sub-Tabs `_video_sub_tabs` / `_audio_sub_tabs` sind durchgehend unsichtbarer Müll
- **Datei:** `ui/workspaces/media_workspace.py:538–597, 807–867`.
- **Beweis:** Beide `SectionTabs` werden komplett aufgebaut (ANALYSE +
  FILTER), Tab-Tooltips gesetzt, dann unsichtbar geschaltet und nie
  einem Layout zugewiesen. Buttons im ANALYSE-Tab werden später per
  Re-Parenting aus dem Side-Panel gerettet (`_configure_analysis_button`
  wird in `_build_video_analysis_side_panel` aufgerufen). Der FILTER-Tab
  bleibt mitsamt `btn_clear_all` (siehe F-02) verloren.
- **Konsequenz:** Konstruktions-Overhead, irreführender Code (Tooltips
  und Tab-Titel suggerieren erreichbare Funktion), F-02 ist die direkte
  User-Wirkung.

#### F-05 — `defer_captioning`-Pfad doppelt-schreibt Scene-Rows
- **Datei:** `services/video_analysis_service.py:1101–1338`,
  `workers/video.py:295–410`.
- **Beweis:**
  - Im Batch-Modus läuft `run_full_pipeline(... defer_captioning=True)`,
    schreibt Szenen ohne Captions per `store_scenes_in_db` (Z. 1308),
    markiert `scene_db_storage` als `done` mit `{"scenes": N}` (Z. 1310).
  - Nach dem Batch ruft Worker `run_deferred_captioning`
    (`workers/video.py:399–410`), das erneut `store_scenes_in_db`
    aufruft (`video_analysis_service.py:1115`) und `scene_db_storage`
    erneut auf `done` setzt mit `{"scenes": N, "captions_updated": True}`.
  - `store_scenes_in_db` macht `Scene.delete + insert` (Z. 883),
    d. h. die ersten Inserts werden komplett verworfen.
- **Konsequenz:**
  - Doppelter SQLite-Schreib-Roundtrip pro Clip (kostet bei großen
    Clip-Mengen messbar Zeit).
  - Zwischenzeitlich liegen Scenes ohne Captions in der DB —
    nachgelagerte Konsumenten (`structure_enrichment`, Cockpit-Status)
    sehen `done`, obwohl der finale Status erst nach Captioning kommt.
  - `analysis_status_service.mark_done(...)` wird zweimal mit
    abweichendem Payload gefeuert. Der Cockpit-Listener
    (`workspace_setup.py:401`) feuert dadurch zwei Refreshes.
- **Status laut Wiki:** Kein offener Bug. **Neuer Befund.**

#### F-06 — Stems-DAW-Refresh-Pfad funkt ins Leere
- **Datei:** `ui/controllers/panel_setup.py:230–235`,
  `ui/controllers/audio_analysis.py:137–151`,
  `ui/controllers/stems.py:42–117`.
- **Beweis:** Diese Pfade rufen `self.window.stem_workspace.update_*`
  auf — exakt das Widget, das laut F-01 niemand sieht. Logisch korrekt
  verkabelt, aber wirkungslos solange F-01 offen ist.

#### F-07 — Captioning-Status springt zwischen `mark_done` und `mark_started`
- **Datei:** `services/video_analysis_service.py:1280–1299` vs.
  `1056–1108` (`run_deferred_captioning`).
- **Beweis:** Im defer-Pfad wird `ai_scene_caption` erst beim deferred
  Lauf `mark_started` und `mark_done`. Wer in der Zwischenzeit
  `analysis_status_service.get_status(...)` liest, sieht
  `ai_scene_caption` als `pending`/`unknown`, obwohl die Pipeline gerade
  rennt. Cockpit-Readiness behandelt Captioning explizit als
  „nicht required" (`cockpit_orchestrator.py:177`), daher kein Blocker —
  aber der Status-Flow ist nicht stabil.

### P2 — Aufräumarbeit

#### F-08 — Toter Konstanten-Block `_COCKPIT_ACTION_LABELS`
- **Datei:** `ui/workspaces/workflow_pages.py:19–27`. Tupel wird
  definiert, aber nirgends importiert. `test_cockpit_primary_labels_are_user_facing_not_model_names`
  prüft die einzelnen Strings im Source — das deckt das Tupel nicht ab.
  Reine Doppelung der `ACTIONS`-Labels in `cockpit_orchestrator.py`.

#### F-09 — `btn_video_pipeline` wird zweimal mit Text+ObjectName gestaltet
- **Datei:** `ui/workspaces/media_workspace.py:562–574` (Erstkonfiguration im
  unsichtbaren Sub-Tab) gegen `:631–639` (Re-Parent ins Side-Panel).
  Funktional OK (Qt re-parented bei `addWidget`), aber der erste Block
  ist Konfigurations-Müll, der nur dazu dient, die Lese-Reihenfolge
  zu erschweren.

#### F-10 — `core.autocrlf` nicht final
- 14 Modify-Files sind im LF-Format gespeichert, Git warnt bei jedem
  Diff. Keine Funktionswirkung, aber jeder weitere Commit wird die
  Datei als „komplett geändert" anzeigen, sobald jemand mit
  `core.autocrlf=true` checkt.

#### F-11 — Pytest-Sammelwarnung in `tests/test_audio_analysis_real.py:46`
- Klasse `TestResult` mit `__init__` ⇒ Pytest sammelt sie nicht und
  warnt. Test-Ergebnis nicht gefährdet, aber Sammel-Output bleibt
  laut.

### P3 — Beobachtungen / Drift

- **B-175** (offen, severity HOCH): Soft-Delete-Unique-Constraint
  blockt Re-Import. Nicht Teil dieses Branches, aber im Wiki noch
  `status: open`.
- **B-219** (open, medium): WinError 32 nach Pipeline. Nicht
  Teil des Diffs.
- **B-229 / B-231** (open, medium): Audio-Audit-Restposten.
- **B-196 … B-199, B-240 … B-252**: Sieben Bugs auf
  `code-fix-pending-(gui|live)-verification`. Davon trifft B-252
  (DockWidget-Ghosts) thematisch denselben UI-Rebuild und sollte
  parallel zu F-01 mit Live-Test verifiziert werden, sonst fällt der
  Stems-Befund nochmal auf.
- **Wiki vs Branch:** `feat: rebuild PB Studio workflow UI` (d2c9133)
  hat **kein** zugehöriges ADR oder Synthesis-File im Vault gefunden
  (`grep -rl "workflow rebuild" C:/Brain-Bug/projects/pb-studio` läuft,
  ohne dass aktuelles Material auftaucht). Laut CLAUDE.md ist das
  Vault-Pflege-Pflicht. **Eintrag fehlt.** Das wird aber nicht in diesem
  Audit nachgereicht — Aufgabe für den nächsten Commander-Lauf.

---

## 3. Was definitiv funktioniert (Code-Beweis, getestet)

- **GPU-Lock-Zentralisierung:** Neuer
  `gpu_resource_lease(reason=...)`-Kontext (`services/model_manager.py:50–57`)
  serialisiert Load+Inference. Belegt durch
  `test_model_manager_load_runs_under_single_gpu_resource_lease` und
  `test_demucs_apply_helper_uses_execution_lock`.
- **VRAM-Reading nutzt `torch.cuda.mem_get_info`:** Belegt durch
  `test_model_manager_uses_cuda_mem_get_info_for_free_vram`.
- **Beat-this-Inferenz unter `GPU_EXECUTION_LOCK`:**
  Belegt durch `test_beatthis_full_analysis_inference_uses_execution_lock`.
- **Downbeat-Tolerance Fix in Pacing:** `_is_downbeat_near` (Toleranz
  30 ms) ersetzt strikten Set-Match. Belegt durch
  `test_downbeat_matching_tolerates_rounding_drift`.
- **Cockpit-Readiness-Logik:** Vollständig durch acht Tests in
  `test_cockpit_orchestrator.py` abgedeckt (Projekt-leer, Audio-fehlt,
  Audio-ready/Video-fehlt, beide ready → AutoEdit, Timeline → Review,
  Captioning bleibt non-blocking, Worker-Dispatch-Pfade).
- **UI-Smoke der vier sichtbaren Workspaces:** Tests
  `test_workspaces_smoke.py` — Convert, Deliver, Stems-Workspace-Konstruktion
  (sic; nur Konstruktion, kein Sicht-Test), Edit-Workspace-Stage-Switch,
  Media-Workspace-Mode-Switch, MaterialAnalysisWorkspace-Komposition
  laufen alle grün.
- **Video-Batch defer_captioning:** Test
  `test_video_batch_defers_captioning_until_after_gpu_models_unloaded`
  zeigt, dass Captioning erst nach `siglip:unload` und `raft:cpu`
  läuft. Die in F-05 beschriebene Doppel-Schreibung ist davon **nicht**
  abgedeckt — das Test-Mock von `run_full_pipeline` ersetzt
  `store_scenes_in_db`, prüft also nicht den DB-Pfad.

---

## 4. Empfehlungen (rein dokumentarisch — keine Änderungen vorgenommen)

| ID | Vorschlag | Wirkung |
|----|-----------|---------|
| F-01 | Stems wieder in Nav-Bar als 6. Workspace **oder** als Dock im Edit/Material-Workspace einhängen. Test ergänzen. | Stems-DAW-Surface zurück |
| F-02 | `btn_clear_all` ins Toolbar des MediaWorkspace ziehen (z. B. neben „Loeschen"-Button). | Funktion erreichbar |
| F-03 | `LegacyAnalysisWorkspace` löschen + `AnalysisWorkspace`-Alias entscheiden (entweder kompletter Drop oder Re-Export). | Toter Code weg |
| F-04 | `_video_sub_tabs` / `_audio_sub_tabs` ganz entfernen oder ans Layout hängen. | Code-Klarheit |
| F-05 | In `run_deferred_captioning` nur `Scene.update(...)` für `ai_caption/ai_mood/ai_tags` machen, nicht `store_scenes_in_db` neu aufrufen. | DB-Roundtrip halbiert, Status sauber |
| F-07 | `analysis_status_service.mark_started("ai_scene_caption", ...)` schon im defer-Branch im Pipeline-Worker absetzen, nicht erst in `run_deferred_captioning`. | Status-Flow konsistent |
| F-08 | `_COCKPIT_ACTION_LABELS` löschen oder produktiv nutzen. | – |
| F-09 | Erstes `btn_video_pipeline`-Setup im Sub-Tab streichen — alles im Side-Panel konfigurieren. | Lesbarkeit |
| F-10 | `git config core.autocrlf input` projektweit oder `.gitattributes` mit `* text=auto eol=lf`. | Saubere Diffs |
| F-11 | `TestResult`-Klasse umbenennen oder mit `__test__ = False` markieren. | Stille Sammler-Phase |
| Vault | ADR oder Synthesis für `feat: rebuild PB Studio workflow UI` (d2c9133) anlegen. | CLAUDE.md-Konformität |

---

## 5. Methode und Ehrlichkeits-Vorbehalt

- Statisch analysiert, **nicht** in einer laufenden App verifiziert.
  F-01, F-02, F-04, F-06 sind in mein erst durch den Code beweisbar
  („Widget existiert, ist aber an keinem sichtbaren Layout") — die
  visuelle Bestätigung, dass die App tatsächlich kein Stems-Panel zeigt,
  steht aus.
- F-05 / F-07 sind aus dem Code- und Test-Mock ableitbar; ein realer
  Batch-Lauf wurde nicht ausgeführt.
- Tests gegen die geänderten Module sind grün, das beweist nur den
  abgedeckten Verhaltens-Kontrakt — nicht „die App funktioniert".
- Bug-Wiki wurde gelesen, aber keine offenen Pending-Bugs in dieser
  Session live verifiziert.

Wenn ein Punkt für deinen nächsten Schritt geblockt wirkt, gib Bescheid —
sonst ist das hier der vollständige Befund-Stand zum genannten Branch und
Commit, ohne Schönrede und ohne Code-Änderungen.

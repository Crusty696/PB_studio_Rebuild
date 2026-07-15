---
title: Dr.-Level Dead-Code-Sweep 2026-07-15
date: 2026-07-15
type: synthesis
status: offen
tags: [sweep, toter-code, doppelter-code, speicher, b-090, threading, multi-agent]
---

# Dr.-Level-Sweep: toter Code / doppelter Code / tote Daten / Speicher

**Auftrag (User 2026-07-15):** "beginnst du nach totem oder doppeltem code funktionen
pipelines speicher und so weiter auf die suche und dokumentierst alles was du finden kannst
... ein team das speziell und auf dr. level alles was nicht gut ist finden kann ...
in allen bereichen der app"

**Methode:** Multi-Agent-Workflow, 12 Achsen (toter Code services/UI, doppelter Code
services/UI+utils, tote DB-Daten, berechnet-und-verworfen, tote Pipelines, Speicher-Blobs,
Speicher-Leaks, Threading/GIL, tote Configs+Deps, GPU-Norm). Read-only.
Jeder Kandidat wurde von **3 unabhaengigen Skeptikern** mit unterschiedlichen Linsen
(korrektheit / erreichbarkeit / absicht) angegriffen — Auftrag: WIDERLEGEN. Ueberlebt nur,
wenn hoechstens einer widerlegen konnte (>=2 von 3 hielten dagegen).

**Ergebnis: 97 Agenten, 28 Kandidaten -> 4 bestaetigt, 24 verworfen (86% aussortiert).**

Die hohe Ausschuss-Quote ist das eigentliche Resultat: Ein Sweep ohne adversariale Pruefung
haette zwei Dutzend Phantom-Fixes produziert. Mehrere verworfene Kandidaten waeren beim
"Fixen" zu **echten Regressionen** geworden (siehe Abschnitt "Nicht bestaetigt", besonders
AnalysisStatusMiniWidget = N+1-Freeze, ModelManager cuda-Sentinel = 4 gebrochene Tests,
gpu_lock_aware = TOCTOU-Downgrade).

**Vorgabe war FINDEN + DOKUMENTIEREN, nicht fixen.** Kein Code wurde durch diesen Sweep
geaendert. Fixes entscheidet der User.

**Kontext:** Der Sweep lief NACH den Fixes dieser Session (AV-Pacing-Integration,
at_rms_curve, StemsWorkspace, btn_clear_all, trash_dialog, WeightStore, deleted_at) —
diese Befunde waren dem Team als "bereits erledigt" vorgegeben und sind nicht enthalten.

---

## Kurzfassung

- **`_analyze_all_v2_batch` laedt pro Track ein volles AudioTrack-ORM-Objekt inkl. eager Beatgrid/WaveformData-JSON-Blobs auf dem Qt-Main-Thread, braucht aber nur `file_path`/`title`** — B-090-Muster, GUI-Freeze skaliert linear mit Trackzahl (`ui/controllers/audio_analysis.py:479`).
- **Der SCHNITT-Preflight-Guard zieht volle AudioTrack- + VideoClip-Objekte (inkl. aller Scenes) synchron im GUI-Thread, nur um zwei IDs zu lesen** (`ui/controllers/edit_workspace.py:1035`).
- **StorageBrowserDialog fuehrt seine projektuebergreifende DB-Abfrage synchron im GUI-Thread aus — im `__init__` und bei jedem Filter-Signal** (`ui/dialogs/storage_browser_dialog.py:36`); Schwere umstritten, siehe Eintrag.
- **`key_mood_gate.condition` in `config/pacing_rules.yaml` wird nie geparst — der Schwellwert 0.7 ist im Python-Code hart dupliziert**, d. h. Tuning ueber die YAML ist wirkungslos (`config/pacing_rules.yaml:22`).
- **24 weitere Kandidaten wurden verworfen** — fast alle sind bereits als DEAD-008 / USE-016 / DB-004 dokumentiert oder bewusst geparkt; die Liste unten existiert genau dafuer, dass sie nicht erneut „gefixt" werden.

---

## Speicher / Blobs (B-090-Klasse)

### GUI-Thread laedt volle AudioTrack-ORM-Objekte in Schleife, nutzt nur file_path/title

- **Ort:** `ui/controllers/audio_analysis.py:470-481` (Schleife bei :479), Aufrufer `_analyze_all_sequential` :542/:581
- **Beleg:** `with Session(engine) as s:` + `for tid in track_ids: t = s.query(AudioTrack).filter(AudioTrack.id == tid).first()` — kein column-select, kein `lazyload()`, kein Worker. `AudioTrack.beatgrid` und `AudioTrack.waveform_data` sind in `database/models.py:201-202` `lazy='joined'`, werden also bei jedem `.first()` eager mitgezogen (JSON-Blob-Decode im ORM-Row-Processing). Danach genutzt: nur `t.file_path` / `t.title` (:480-481). `_analyze_all_sequential` ist direkter Button-Klick-Handler ohne Worker-Wrapping → Qt-Main-Thread. Nachbar-Methoden derselben Datei (:51, :648) tragen explizite B-625-Kommentare „column-select statt session.get() — vermeidet eager Blobs"; hier fehlt der Hinweis, also keine erkennbare bewusste Ausnahme.
- **Auswirkung:** Bei „Komplett-Analyse" ueber mehrere Tracks haelt `json.loads` den GIL und blockiert den Main-Thread — Freeze skaliert linear mit Trackzahl. Deckungsgleich mit dem B-090/E-Live-Muster (2-14 s pro Track laut `freeze_stacks.log`). User merkt es direkt.
- **Konfidenz:** hoch (3/3 Skeptiker konnten nicht widerlegen). Achse: speicher-blobs.
- **Vorschlag:** Die Schleife auf column-select (`s.query(AudioTrack.file_path, AudioTrack.title).filter(...)`) umstellen — analog zum bestehenden B-625-Muster in derselben Datei.

### Preflight-Guard laedt volle AudioTrack-/VideoClip-Objekte nur fuer deren .id

- **Ort:** `ui/controllers/edit_workspace.py:1018-1056` (Queries :1035-1039 und :1047-1051), Aufrufer `_guard_combos_or_notify` :1078-1092 (Call :1086)
- **Beleg:** `_ensure_combos_filled_from_project` oeffnet `with DBSession(engine) as s:` und macht Voll-ORM-Queries ohne `.options(lazyload/defer)`, obwohl direkt danach nur `first_audio.id` / `first_video.id` fuer `findData()` benutzt werden (:1042/:1053). `AudioTrack.beatgrid`/`waveform_data` = `lazy='joined'` (`database/models.py:201-202`), `VideoClip.scenes` = `lazy='selectin'` (`database/models.py:243`) → zieht alle Scene-Rows inkl. keyframe_paths/embedding_indices mit. Der Guard ist per Docstring als Pre-Flight VOR dem Worker-Start deklariert („Adapter MUSS sofort returnen, ohne den Worker-Pfad zu starten") — laeuft also zwingend auf dem Main-Thread.
- **Auswirkung:** Jeder SCHNITT-Adapter-Slot-Aufruf mit leeren Combos (Preset-Klick etc.) blockiert den Main-Thread mit vollem Blob-Load, obwohl nur IDs gebraucht werden. Frequenz haengt daran, wie oft der Guard leere Combos sieht — nicht live gemessen.
- **Konfidenz:** hoch fuer den Mechanismus (3/3), Haeufigkeit ungemessen. Achse: speicher-blobs.
- **Vorschlag:** Beide Queries auf `s.query(AudioTrack.id)` bzw. `s.query(VideoClip.id)` reduzieren — die ID ist alles, was der Guard konsumiert.

---

## Threading / GIL

### StorageBrowserDialog fuehrt DB-Query synchron im GUI-Thread aus

- **Ort:** `ui/dialogs/storage_browser_dialog.py:36` (`__init__` → `self.refresh()`), `refresh()` :94-106, Signal-Bindings :44/:52/:57; Service `services/storage_provenance/storage_browser.py:46-129`
- **Beleg:** `refresh()` oeffnet `with nullpool_session() as session:` und ruft `StorageBrowserService(session).list_sources(...)` synchron — kein QThread/QRunnable/`run_worker`. Zusaetzlich an drei GUI-Signale gebunden (`toggled`, `valueChanged`, `clicked`), jeder Filter-Wechsel blockt erneut. `list_sources()` laedt alle AnalysisJob-Zeilen projektuebergreifend (`.query(AnalysisJob).options(lazyload('*')).order_by(...).all()`, :54-59) plus Joins ueber alle Quellen, ohne Limit. Aufruf via `ui/dialogs/settings_dialog.py:636-639` (`dlg.exec()`), kein Feature-Flag.
- **Auswirkung:** **Umstritten.** Ein Skeptiker hat die Schwere-Behauptung belegt angegriffen: Task E8 (`docs/superpowers/plans/2026-07-12-perf-db-cleanup-plan.md:109-119`, Commit `0a32b1f`) hat genau diese Funktion auf 3 konstante Bulk-Queries reduziert (421→3), die beteiligten Tabellen (AnalysisJob/AnalysisArtifact/ProjectSource) haben nur skalare Spalten — kein B-090-Blob-Vektor — und der Live-Verify bei 105 Quellen/5.7 GB war freeze-frei (`docs/superpowers/synthesis/perf-db-cleanup-abschluss-2026-07-13.md:16,48`), waehrend Geschwister-Tasks im selben Lauf wegen Main-Thread-Freezes durchfielen. Ehrlich: der strukturelle Mangel (synchron, kein Cancel, kein Progress, unbeschraenkte Historie) bleibt bestehen, aber es gibt **keinen gemessenen Freeze**. Bei 10-facher Historie ungetestet.
- **Konfidenz:** Fakten sicher; Auswirkung niedrig bis unbelegt (1/3 Skeptiker widerlegt die Schwere ueberzeugend). Achse: threading-gil.
- **Vorschlag:** Als Beobachtung notieren, nicht fixen — falls doch, `refresh()` auf `run_worker` umstellen und die Jobs-Query mit einem Limit versehen.

---

## Config + Deps

### key_mood_gate.condition wird geschrieben und dokumentiert, aber nie geparst

- **Ort:** `config/pacing_rules.yaml:20-23` (Feld :22), Leser `services/pacing/pipeline.py:450-454`
- **Beleg:** YAML definiert `key_mood_gate.condition: "at_harmonic_tension > 0.7"`. `pipeline.py:450` liest das gate-dict, wertet aber nur `gate.get("enabled")` (:451) und `gate.get("forbidden_moods", [])` (:454) aus. Der Schwellwert steht als Literal `ctx.at_harmonic_tension > 0.7` im Code (:453). Grep nach `gate.get("condition")` ueber `services/` → kein Treffer; kein Expression-Evaluator im Repo; der zweite Default-Block (`pipeline.py:164/175`) laesst den Key ganz weg. Tests (`tests/pacing/test_pacing_configs.py:44-50`) pruefen `condition` nur als Schema-Pflichtfeld, nicht als Verhalten.
- **Auswirkung:** **Kein Laufzeit-Defekt** — YAML (0.7) und Code (0.7) sind konsistent, `enabled: false` haelt den Pfad ohnehin inert, und bei Aktivierung entspricht das Verhalten exakt dem Spec-Beispiel. Ein Skeptiker hat zusaetzlich belegt, dass die Entscheidung im Code dokumentiert ist (`pipeline.py:452`: `# Simple tension > 0.7 check (matches spec example)`) und `condition` als bewusstes Spec-Mirror-Feld gehalten wird (wortgleich aus `docs/superpowers/specs/2026-04-23-studio-brain-design.md:346-349`). Bleibt: ein Wartungs-Footgun — wer die YAML auf 0.5 tunt, bekommt still 0.7.
- **Konfidenz:** Fakten sicher; als Defekt eingestuft nur mit Vorbehalt (1/3 Skeptiker widerlegt den Bug-Charakter schluessig). Achse: tote-configs-deps.
- **Vorschlag:** Einen klarstellenden Kommentar in `config/pacing_rules.yaml` neben `condition` — z. B. „Spec-Mirror, nicht geparst; Schwelle liegt in pipeline.py:453". Kosmetik, kein Fix.

---

## Nicht bestaetigt

Diese 24 Kandidaten haben die adversarische Pruefung **nicht** ueberstanden. Bitte nicht erneut melden und nicht „fixen":

**Bereits als DEAD-008 dokumentiert und bewusst geparkt** (`docs/superpowers/synthesis/neubau-vollintegration-m3-progress-2026-07-08.md:56-64` — „Bewusst offen (ehrlich, kein stiller Skip)", plus Plan-Task in `docs/superpowers/plans/2026-07-07-neubauten-vollintegration-plan.md:245-257`):

- **TriggerQueue/TriggerJob** (`services/video_pipeline/trigger_queue.py:56`, 2× gemeldet) — unverdrahtet ist korrekt, aber explizit als M3-Rest dokumentiert; Verdrahtung ohne echten Konsumenten wuerde neue Dead-Ends schaffen.
- **StatusReporter/StageStatus** (`services/video_pipeline/status_reporter.py:30`, 2× gemeldet) — dito; zusaetzlich ist die behauptete Auswirkung („UI-Fortschritt tot") falsch: der Engine-Pfad hat eigene Qt-Signals (`workers/video.py:696/733/742/749` → `ui/controllers/video_analysis.py:268-277`).
- **gpu_lock_aware.py** (`services/video_pipeline/primitives/gpu_lock_aware.py:38`) — Schutz existiert, nur ueber einen staerkeren Mechanismus: beide GPU-Stages halten `get_default_serializer().acquire(...)` (`siglip_embed_stage.py:71`, `raft_motion_stage.py:110`), was den legacy `GPU_EXECUTION_LOCK` mitnimmt (`gpu_serializer.py:74-82,157-160`). Die Probe waere ein Downgrade (TOCTOU-Race).
- **coverage_guard.py** (`.../primitives/coverage_guard.py:94`) — ungenutzt ist korrekt, aber die Engine ist per Default aus (`app_integration.py:23-36`); der Produktivpfad (Monolith) hatte den Guard nie.
- **disk_budget.py** (`services/video_pipeline/disk_budget.py:48`) — dito; Auswirkung waere hoechstens „roher OSError statt DiskFull" in einem deaktivierten Pfad.

**Bereits als Loeschkandidat inventarisiert, User-Entscheidung ausstehend** (`audit-fehler-luecken-toter-code-verdrahtung-2026-07-07.md:139`, `2026-07-08-aufraeum-refactor-plan.md:55-62`):

- **PrepareWorkspace** (`ui/workspaces/workflow_pages.py:324`) — nie instanziiert stimmt, ist aber als USE-016 explizit auf User-Entscheid geparkt.
- **PrimaryActionBar** (`ui/widgets/workflow_components.py:49`) — WIRE-007, bereits als „sicher loeschbar" gelistet; ungenutzte Primitive in einer Primitiven-Bibliothek, null Laufzeit-Impact.
- **AnalysisStatusMiniWidget** (`ui/widgets/analysis_status_panel.py:639`) — bereits als BU-004 „not a bug" triagiert. Wichtiger: die behauptete Auswirkung ist **falsch** — die Fortschrittsanzeige existiert als Spalte „Analyse %" (`ui/models/media_table_model.py:31-35,57-61`). Verdrahten waere eine **Regression** (per-Row `get_completion_percent()` = der als P8-FREEZE-FIX behobene N+1, `services/ingest_service.py:574-580`).

**Tote Daten — bereits als DB-004/DB-007 dokumentiert und vertagt:**

- **`AudioTrack.spectral_hash`** (`database/models.py:196`) — kein Writer stimmt, aber `scorer.py:290-291` liefert bei None einen dokumentierten neutralen Prior 0.5, kein „kein Score"; Gewicht `w_spectral=0.05` kuerzt sich im Ranking raus. Vertagt in `2026-07-07-audit-fixplan.md:220`.
- **`AudioTrack.harmonic_tension`** (Skalar, `database/models.py:197`) — als optionale Quelle #1 einer dokumentierten 3-stufigen Fallback-Kette designed (`services/pacing/bridge_mapping.py:199-217`); Stufe 2 (Curve) liefert korrekte Werte. Ebenfalls DB-004.
- **StepDep** (`database/models.py:120`) — DB-007, Tier-1-Schema-Deliverable ohne geplanten Consumer; leere Tabelle, null Laufzeit-Folge.
- **`AgentFeedback.session_id/model_id/backend/user_comment`** (`database/models.py:574`) — **Praemisse falsch**: die Spalten werden gar nicht geschrieben, `record_feedback` (`services/local_agent_service.py:495`) hat null Produktiv-Aufrufer. Das produktiv genutzte Feedback-System ist ein anderes (`services/brain/feedback_logger.py:37`).
- **`AIPacingMemory.bass_energy/drum_energy/siglip_tags`** (`database/models.py:473`) — es gibt auch keinen **Leser** (`_get_ai_memory_bias`, `services/pacing_memory.py:194-245`, liest sie nie); Tabelle ist per Decision als Legacy eingefroren (`2026-04-23-studio-brain-plan.md:373`).
- **`AudioTrack.transcription`** (`database/models.py:179`) — der Fund raeumt selbst ein „kein Bug sondern dokumentierte Absicht"; Kommentar sagt „kept for DB compatibility", ein Test wacht aktiv ueber das Nicht-Laden (`tests/test_services/test_b620_infer_no_blob_load.py:55`).

**Doppelter Code / DRY-Nitpicks ohne Failure-Szenario:**

- **`_format_mmss` doppelt** (`ui/story_map_dialog.py:107` / `ui/studio_brain/audit_tab.py:107`) — Duplikat real, aber beide liefern identischen Output; das Repo hat sechs weitere bewusst divergente Zeit-Formatter. Reine Zukunfts-Hypothese.
- **MB→GB-Formatierung doppelt** (`ui/dialogs/model_manager_dialog.py:473`/`:760`) — Kernargument des Finders **falsch**: `storage_browser_dialog.py:180 _format_bytes(value: int)` nimmt **Bytes**, nicht MB; ein Import waere um Faktor 1024² daneben. Es existiert kein MB-Helper, der umgangen wuerde.
- **Zwei FFmpeg-Timeout-Formeln** (`services/video_pipeline/primitives/proxy_generator.py:101` vs. `services/timeout_constants.py:34`) — Divergenz real, aber `_encode_timeout_seconds` ist ein dokumentierter, live-verifizierter, test-gepinnter B-571-Fix (`tests/test_services/test_video_proxy_generator.py:131-156`); das behauptete Fehlerfenster (100-300 s) ist genau der Bereich, den der 300-s-Floor am besten schuetzt.

**Fehldiagnosen:**

- **`SpectralAnalysisService.analyze_extended()`** (`services/spectral_analysis_service.py:480`) — kein Produktiv-Caller stimmt, aber der Finder raeumt selbst ein: „kein Bug im Sinne von Ergebnis-Verwurf zur Laufzeit". Null Aufrufe = null Kosten. Standalone-Kompatibilitaet wurde unter B-231 per User-Gate bewusst erhalten.
- **RaftMotionStage verwirft Flow-Feld** (`services/video_pipeline/stages/raft_motion_stage.py:120`) — beschreibt die Spec (`docs/superpowers/archive/2026-05-19-video-pipeline-engine/32_RAFT_MOTION_SERVICE.md:8-24`). Die 3 Skalare sind vollstaendig verdrahtet (→ `db_persist_stage.py:78-93` → `Scene.energy`); das dichte Feld ist notwendiges Zwischenprodukt, nicht verworfener Ertrag.
- **QUndoStack ohne `setUndoLimit`** (`ui/timeline.py:1193`) — Tatsache stimmt, Mechanismus **falsch**: Moves werden per 200-ms-Debounce gebuendelt (`ui/timeline.py:1268-1271`) und per `mergeWith()` verschmolzen (`ui/undo_commands.py:111-122`). Payloads sind Skalare (hunderte Bytes), nicht „hunderte MB".
- **ABCompareDialog `_on_run()` synchron** (`ui/dialogs/ab_compare_dialog.py:162`) — bekannter, dokumentierter Rest-Freeze (B-625/F1, `docs/GUI_NAVIGATION_PLAYBOOK.md:117-119`, `2026-07-14-freeze-crash-sanierung-konsolidiert.md:39`); die Kostenbehauptung („doppeltes Scoring") faellt, weil ohne `pattern_lookup` alle teuren Pfade auf konstante 0.5 kurzschliessen (`scorer.py:513-517`). Dialog ist ohnehin modal.
- **`ModelManager.self.device = "cuda"`** (`services/model_manager.py:295`) — wortwoertlicher Regel-Treffer, aber `self.device` ist ein zweiwertiger **State-Sentinel** („cuda"/„cpu"), kein torch-Device-Spec. Der naive Fix auf `"cuda:0"` bricht `:398` (B-218-Health-Logik invertiert), `:941` (fp16-Cast entfaellt) und vier Tests. Kein `torch.cuda.set_device()` existiert im Repo; `CUDA_VISIBLE_DEVICES='0'` ist fuer Ollama gesetzt (`services/ollama_service.py:235`).
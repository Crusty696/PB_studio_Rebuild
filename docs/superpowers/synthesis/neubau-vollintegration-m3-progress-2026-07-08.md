# NEUBAU-VOLLINTEGRATION — M3 (Paket 3: DAG-Video-Engine) Fortschritt

- **Plan:** PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07
- **Decision:** D-065 (Richtung 1: Engine schreibt in Scene+VectorDB)
- **Datum:** 2026-07-08
- **Worktree/Branch:** `.worktrees/vollintegration` / `claude/NEUBAU-VOLLINTEGRATION-2026-07-07`

## Ausgangs-Audit (verifiziert)

Die DAG-Engine (`services/video_pipeline/`) schrieb nur Datei-Artefakte,
nie in Scene/LanceDB → nach einem Engine-Lauf sah UI/Suche/Pacing/
Studio-Brain nichts (kritische Lücke PIPE-018). Motion roh statt
normalisiert, VLM-Caption als Stub, 6 Cross-Cutting-Module unverdrahtet.

## Erledigt (code-complete)

| Schritt | Inhalt | Commit |
|---|---|---|
| DbPersistStage | Neue Stage (läuft zuletzt): liest Artefakte, baut SceneInfo, ruft bewährte Monolith-Writer `store_scenes_in_db` + `store_embeddings` (Scene.energy normalisiert wie Monolith, VectorDB). Guards (Projekt-Token, FK) reused. Scene-Skip blockt Embeds. | d0b7f19 |
| Setting-Schalter | `engine_enabled()` liest `video.use_pipeline_engine` (SettingsStore), Env-Var bleibt Override (1/true/yes/on). UI-Checkbox im Settings-Dialog Tab „Analyse" mit ehrlichem Experimentell-Hinweis. Default AUS. | ebb9c49 |
| Paritäts-Harness | `scripts/diag/video_engine_parity.py`: sequentieller Monolith-vs-Engine-Vergleich (Scene+LanceDB, Toleranzen dokumentiert). | 2bb9488 |
| Observability | `JsonlObserver` als Default-Listener (DEAD-008 Teil 1) — Engine-Events als Audit-Trail. | a87d15e |

## Paritäts-Nachweis (GPU-Lauf 2026-07-08, GTX 1060) — GEMISCHT

Ausgeführt auf DB-Kopie von `outputs/6262626` (Original unberührt), 2 Clips:

| Clip | Szenen | VectorDB | Energy-Diff | Ergebnis |
|---|---|---|---|---|
| 1 (langsam) | 1=1 ✓ | ✓ | 0.031 | PARITÄT |
| 3 (bewegt) | 1=1 ✓ | ✓ | **0.630** | **ABWEICHUNG** |

**Befund:** Szenen-Struktur + Embeddings sind paritätisch. **`Scene.energy`
ist es NICHT** — echte Motion-Skalen-Drift.

**Ursache (verifiziert):** Der Monolith skaliert Frames auf **fest 520×320**
vor RAFT (`_raft_motion_score`, Z.196); die Engine-`RaftMotionService`
rechnet mit `resolution_scale=1.0` auf **voller Auflösung**. Gleiche
Normalisierung `_normalize_motion` → verschiedene Werte. Bei langsamen
Clips nahe 0 (unauffällig), bei bewegten stark divergent.

**Konsequenz:** Die Engine ist **kein Drop-in für das Pacing**, solange
`Scene.energy` divergiert (Pacing liest genau diesen Wert). Engine-Default
bleibt AUS (ist es). Persistenz (Scene-Write + VectorDB) funktioniert live.

**Fix-Option (Entscheidung offen):** Engine-Flow ebenfalls auf 520×320
skalieren (RaftMotionStage/Service) → ändert bestehendes Engine-Verhalten
→ braucht User-OK (HARTREGEL). Danach Paritäts-Lauf wiederholen.

**Harness-Caveat:** VectorDB-Count ist global (kumulativ), nicht per-Clip —
misst „Embeddings werden geschrieben", nicht die exakte Pro-Clip-Zahl.

Weiterhin offen: Checkpoint-Resume-Verify (VRAM stabil).

## Bewusst offen (ehrlich, kein stiller Skip)

- **VLM-Backend**: `VlmCaptionStage` läuft als Stub (kein Ollama verdrahtet).
  `ai_mood`/`ai_tags` bleiben nach Engine-Lauf leer. Caption-Parität ist
  damit erst nach echter VLM-Verdrahtung möglich (eigener Schritt).
- **DEAD-008 Rest**: `status_reporter`, `coverage_guard`, `disk_budget`,
  `trigger_queue`, `gpu_lock_aware` bleiben unverdrahtet — sie brauchen
  echte Konsumenten (UI-Panel / Orchestrator-Policy), sonst neue
  Dead-Ends. Als M3-Rest dokumentiert.
- **analysis_status-Tracking** für den Engine-Pfad (Monolith nutzt
  `mark_started/done/error`) — noch nicht nachgezogen.

## Motion-Semantik (Toleranz-Hinweis)

Engine-`mean_magnitude` entsteht auf anderer Auflösung als die
Monolith-520×320-Referenz. DbPersistStage aggregiert je Szene + wendet die
identische Normalisierung `_normalize_motion` (1−exp(−raw/40)) an; die
ABSOLUTE Skala kann abweichen → Toleranz-Item, kein Byte-Match.

## Volle-Suite-Regression (3007 passed / 50 failed) — kategorisiert

Ehrlich analysiert, keine offene echte Regression aus dieser Arbeit:

- **~45 Failures = Windows-MAX_PATH** (WinError 206): tiefe by_sha-Content-
  Storage-Pfade im Worktree (`.worktrees/vollintegration/...tests/qa_artifacts/
  .../by_sha/<64-hex>/`). Mit kurzem basetemp (`C:/t`) laufen dieselben
  Tests grün (55 passed). Kein Code-Fehler, keine meiner Änderungen; im
  Haupt-Worktree (kürzerer Pfad) grün.
- **3 Failures = eigene M1-Regressionen → GEFIXT** (Commit cc4c9b5):
  - B-359-RAM: `_analyze_long_chunked` (T2.5.1) chunkte das Spektrogramm
    nicht wirklich → echtes per-Chunk-Slicing (RAM ≤ alter Cap).
  - 2× `timeline_snapshot_service` (T2.3): Test-Kontrakt auf DB-019-Dicts.
- **2 Failures = geerbt aus SCHNITT-FIXPLAN** (Commit 8d03b57, main-Merge):
  Vision-Caption-Timeout 30→240s + strengere Caption-Echo-Validierung
  (User-verifiziert). `test_video_caption_timeout`/`_model_selection` sind
  relativ dazu veraltet. NICHT meine Domäne — gehört zum Audit-Fixplan/
  anderen Agenten.

## Nächste Schritte bis zum verbindlichen Abschluss

1. GPU-Paritäts-Lauf (koordiniert) → Report.
2. A2-Nachmerge vom Haupt-Branch (V2 Classify+Waveform).
3. Volle Testsuite grün inkl. SCHNITT-Garantien (Beat-Sync 100 %, Ende exakt).
4. Automatischer Merge zurück in `codex/OTK-021-source-consolidation-2026-06-22`
   + Push (User-Auftrag). `fixed` setzt der User.

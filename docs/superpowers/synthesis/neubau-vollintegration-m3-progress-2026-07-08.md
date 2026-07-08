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

## Live-Pending (Verify braucht echte GPU + Projekt)

1. **Paritäts-Nachweis-Lauf**: `video_engine_parity.py` auf realem Clip
   ausführen (GTX 1060, sequentiell — mit Haupt-Worktree koordinieren).
   Toleranzen: Szenen-Anzahl exakt, Energy-Mittel ≤0.20 (Skala-Drift),
   Embedding-Anzahl exakt.
2. **Checkpoint-Resume**: Analyse unterbrechen → fortsetzen, VRAM stabil.

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

## Nächste Schritte bis zum verbindlichen Abschluss

1. GPU-Paritäts-Lauf (koordiniert) → Report.
2. A2-Nachmerge vom Haupt-Branch (V2 Classify+Waveform).
3. Volle Testsuite grün inkl. SCHNITT-Garantien (Beat-Sync 100 %, Ende exakt).
4. Automatischer Merge zurück in `codex/OTK-021-source-consolidation-2026-06-22`
   + Push (User-Auftrag). `fixed` setzt der User.

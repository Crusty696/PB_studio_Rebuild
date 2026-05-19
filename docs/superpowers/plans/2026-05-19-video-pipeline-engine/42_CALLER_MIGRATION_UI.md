# 42 — Caller-Migration: UI

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

UI-Konsumenten auf neuen Pipeline-Orchestrator.

## Reihenfolge

1. `ui/media_pool.py` — Status-Panel pro Video.
2. `ui/timeline.py` — Proxy-Anzeige, Cut-Plan-Visualisierung.
3. `ui/controllers/edit_workspace.py` — Trigger-Buttons.
4. `ui/controllers/project_management.py` — Auto-Indexing optional.
5. `ui/dialogs/model_manager_dialog.py` — SigLIP / RAFT / VLM-Modelle anzeigen.

## Verifikation

- Status-Panel live-Updates
- Tier-5-Coverage ≥ 85 %

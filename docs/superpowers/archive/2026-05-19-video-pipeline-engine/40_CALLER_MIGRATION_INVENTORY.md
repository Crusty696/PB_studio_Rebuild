# 40 — Caller-Migration Inventar

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

Liste aller heutigen Video-Analyse-Aufrufer.

## Scope

Audit-Ziel-Verzeichnisse:

- `services/video_analysis_service.py`
- `services/model_manager.py` (Video-relevante Modelle)
- `ui/controllers/edit_workspace.py`
- `ui/controllers/project_management.py`
- `ui/timeline.py`
- `ui/dialogs/model_manager_dialog.py`
- `ui/media_pool.py`

## Deliverable

`docs/superpowers/plans/2026-05-19-video-pipeline-engine/_artifacts/caller_inventory_video.md` mit Datei:Zeile + Aufruf-Methode + Migration-Aufwand.

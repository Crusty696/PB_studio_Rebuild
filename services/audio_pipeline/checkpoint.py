"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T4.1: Checkpoint - Stage-Completion-Tracking.

A-4: JSON pro Track unter ``storage/pipeline_state/<track_id>.json``
(ueberlappend mit stem_cache.cache_meta - gleiches File).
Stage-Done als ``stages_done: list[str]`` Array.

Grenze zu ``AnalysisStatusService`` (DB): JSON = pipeline-interner Detail,
DB-Service = UI-Status-Quelle. Orchestrator-Heal:
- JSON.done aber DB fehlt -> DB nachschreiben (Heal).
- DB.done aber JSON fehlt -> Warn-Log, kein Re-Run (Resume betrachtet als done).
"""
from __future__ import annotations

from services.audio_pipeline import stem_cache


def _ensure_meta(track_id: int) -> dict:
    meta = stem_cache.load_cache_meta(track_id) or {
        "version": 1,
        "original_hash": None,
        "stem_hashes": {},
        "demucs_version": None,
        "wav_subtype": None,
        "stages_done": [],
    }
    if "stages_done" not in meta:
        meta["stages_done"] = []
    return meta


def mark_stage_done(track_id: int, stage_name: str) -> None:
    """Atomic-write via stem_cache.save_cache_meta. Idempotent."""
    meta = _ensure_meta(track_id)
    if stage_name not in meta["stages_done"]:
        meta["stages_done"].append(stage_name)
        stem_cache.save_cache_meta(track_id, meta)


def is_stage_done(track_id: int, stage_name: str) -> bool:
    meta = stem_cache.load_cache_meta(track_id)
    if not meta:
        return False
    return stage_name in meta.get("stages_done", [])


def stages_done(track_id: int) -> list[str]:
    meta = stem_cache.load_cache_meta(track_id)
    if not meta:
        return []
    return list(meta.get("stages_done", []))

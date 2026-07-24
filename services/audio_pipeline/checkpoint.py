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

import logging

from services.audio_pipeline import stem_cache

logger = logging.getLogger(__name__)


def invalidate_if_stale(track_id: int, original_path: str) -> bool:
    """OTK-018 / BUG-1: Verwirft den Checkpoint, wenn die gespeicherte
    ``original_hash`` nicht zur aktuellen Audio-Datei passt.

    Der Checkpoint liegt global unter ``storage/pipeline_state/<track_id>.json``.
    Verschiedene Projekte vergeben track_id=1 -> ohne diese Pruefung erbt ein
    neuer Track die stage-done-Flags eines fremden Tracks und alle Stages werden
    faelschlich uebersprungen (keine Analyse, keine DB-Writes). Bei Hash-Mismatch
    wird das Meta-File geloescht (frischer Lauf: stages_done + Stem-Reuse weg).

    Returns True wenn verworfen, sonst False. Bei nicht lesbarer Datei
    (z.B. Tests mit Fake-Pfad) konservativ False (Checkpoint behalten).
    """
    meta = stem_cache.load_cache_meta(track_id)
    if not meta:
        return False
    stored = meta.get("original_hash")
    if not stored:
        # Ein hashloser Checkpoint ist legitim (Resume nach stem_gen ohne echten
        # Demucs-Hash, z.B. Stem-Reuse). Die eigentliche B-602-Kollision wird an
        # der Wurzel verhindert: der Checkpoint liegt jetzt projekt-relativ
        # (stem_cache._storage_root via APP_ROOT), nicht mehr CWD-global.
        return False
    try:
        current = stem_cache.compute_audio_hash(original_path)
    except OSError:
        return False  # nicht validierbar -> Checkpoint unveraendert lassen
    if stored == current:
        return False
    try:
        stem_cache.cache_meta_path(track_id).unlink()
    except OSError:
        pass
    # B-702: Der Audio-Inhalt hat sich geaendert -> die stem_*_path-Spalten in
    # der DB zeigen definitiv auf Stems des ALTEN Inhalts. Ohne dieses Clearing
    # griff der StemGen-DB-Fallback (_try_db_stem_references) nach der
    # Invalidierung die alten Pfade ohne jede Hash-Pruefung wieder auf und
    # Demucs wurde uebersprungen -> alle Folge-Stages (Onset/Key/Structure)
    # liefen still auf veralteten Stems. Nach dem Re-Run schreibt StemGenStage
    # die Spalten neu (stages.py). Best-effort: DB-Fehler blockieren die
    # Invalidierung nicht.
    try:
        from database import AudioTrack, nullpool_session
        with nullpool_session() as sess:
            row = sess.query(AudioTrack).filter(AudioTrack.id == track_id).first()
            if row is not None:
                row.stem_drums_path = None
                row.stem_bass_path = None
                row.stem_vocals_path = None
                row.stem_other_path = None
                sess.commit()
                logger.info("B-702: stale Stem-DB-Referenzen fuer track=%s geleert", track_id)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("B-702: Stem-Referenz-Clearing track=%s fehlgeschlagen: %s", track_id, exc)
    logger.info("Checkpoint track=%s verworfen (Datei geaendert: %s != %s)",
                track_id, str(current)[:8], str(stored)[:8])
    return True


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

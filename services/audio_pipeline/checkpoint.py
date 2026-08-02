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

import json
import logging
import os
import threading
import time
from pathlib import Path

from services.audio_pipeline import stem_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# B-722: Serialisierter + atomarer Checkpoint-Write.
#
# Zwei gleichzeitige Audio-V2-Laeufe auf demselben Track machten beide ein
# read-modify-write auf ``storage/pipeline_state/<track_id>.json``:
#   1. ``stem_cache.save_cache_meta`` benutzt einen FESTEN Temp-Namen
#      (``<id>.json.tmp``). Zwei Writer greifen auf dieselbe Temp-Datei zu ->
#      auf Windows ``PermissionError``/WinError 32.
#   2. Selbst ohne Crash ist load->append->save nicht atomar: der zweite
#      Writer ueberschreibt die ``stages_done`` des ersten (lost update) ->
#      Stage-Fortschritt geht verloren und Stages laufen doppelt.
#
# Fix nach dem Vorbild von ``services/storage_provenance/source_manifest.py``:
# prozess-interner Lock pro Checkpoint-Datei + prozess-uebergreifender
# O_CREAT|O_EXCL-Lockfile, und ein eigener atomarer Write mit EINDEUTIGEM
# Temp-Namen (pid+thread) statt des geteilten ``.tmp``.
# ---------------------------------------------------------------------------

_LOCK_TIMEOUT_SEC = 10.0
_LOCK_STALE_SEC = 60.0
_REPLACE_RETRIES = 10
_REPLACE_RETRY_SLEEP = 0.05

_LOCAL_LOCKS_GUARD = threading.Lock()
_local_locks: dict[str, threading.RLock] = {}


def _lock_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _local_lock_for(path: Path) -> threading.RLock:
    """Ein RLock pro Checkpoint-Datei (Threads im selben Prozess)."""
    key = _lock_key(path)
    with _LOCAL_LOCKS_GUARD:
        lock = _local_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _local_locks[key] = lock
        return lock


class _CheckpointLock:
    """Best-effort Lock fuer genau eine ``<track_id>.json``.

    Kombiniert einen prozess-internen RLock (Threads, z.B. zwei Worker im
    selben App-Prozess) mit einem Lockfile (zweiter Prozess, z.B. Diag-Skript
    parallel zur App). ``_acquired`` merkt sich, ob der Lockfile wirklich uns
    gehoert — nur dann wird er beim Verlassen geloescht. Ein Timeout laeuft
    bewusst weiter (Verfuegbarkeit vor Strenge), aber mit Warn-Log.
    """

    def __init__(self, meta_path: Path):
        self._meta_path = meta_path
        self._lock_path = meta_path.with_suffix(meta_path.suffix + ".lock")
        self._local = _local_lock_for(meta_path)
        self._fd: int | None = None
        self._acquired = False

    def __enter__(self) -> "_CheckpointLock":
        self._local.acquire()
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Checkpoint-Lock-Ordner nicht anlegbar (%s): %s",
                           self._lock_path.parent, e)
            return self
        start = time.monotonic()
        while True:
            try:
                self._fd = os.open(
                    str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR
                )
                self._acquired = True
                return self
            except (FileExistsError, PermissionError):
                try:
                    age = time.time() - os.stat(str(self._lock_path)).st_mtime
                    if age > _LOCK_STALE_SEC:
                        logger.warning(
                            "Checkpoint-Lock stale (%.0fs), wird gebrochen: %s",
                            age, self._lock_path,
                        )
                        try:
                            os.unlink(str(self._lock_path))
                        except FileNotFoundError:
                            pass
                        continue
                except OSError:
                    pass
                if time.monotonic() - start > _LOCK_TIMEOUT_SEC:
                    logger.warning(
                        "Checkpoint-Lock Timeout, fahre ungelockt fort: %s",
                        self._lock_path,
                    )
                    return self
                time.sleep(0.05)
            except OSError as e:
                logger.warning("Checkpoint-Lock nicht erstellbar (%s): %s",
                               self._lock_path, e)
                return self

    def __exit__(self, *exc) -> None:
        try:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            if self._acquired:
                self._acquired = False
                try:
                    os.unlink(str(self._lock_path))
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.warning("Checkpoint-Lock-Freigabe fehlgeschlagen %s: %s",
                                   self._lock_path, e)
        finally:
            self._local.release()


def _save_meta_atomic(track_id: int, meta: dict) -> None:
    """Atomarer Write mit prozess-/thread-eindeutigem Temp-Namen.

    Ersetzt ``stem_cache.save_cache_meta`` NUR fuer den Checkpoint-Pfad; der
    geteilte feste ``.tmp``-Name dort war die WinError-32-Quelle. ``os.replace``
    kann auf Windows kurzzeitig ``PermissionError`` liefern, wenn ein Reader
    die Zieldatei offen hat -> kurzer Retry statt Fortschrittsverlust.
    """
    p = stem_cache.cache_meta_path(track_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}.{threading.get_ident()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    last_err: Exception | None = None
    for _ in range(_REPLACE_RETRIES):
        try:
            os.replace(str(tmp), str(p))
            return
        except PermissionError as e:  # Windows: Ziel gerade offen
            last_err = e
            time.sleep(_REPLACE_RETRY_SLEEP)
    try:
        os.unlink(str(tmp))
    except OSError:
        pass
    raise OSError(
        f"Checkpoint-Write fuer track={track_id} nach {_REPLACE_RETRIES} "
        f"Versuchen fehlgeschlagen: {last_err}"
    )


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
    # B-722: Lesen + Loeschen unter demselben Lock wie mark_stage_done, sonst
    # kann ein paralleler Lauf die Datei zwischen Check und unlink neu
    # schreiben (bzw. der unlink reisst frisch geschriebene Stages mit).
    with _CheckpointLock(stem_cache.cache_meta_path(track_id)):
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
    """Atomarer, serialisierter Write. Idempotent.

    B-722: load->append->save laeuft komplett unter ``_CheckpointLock``, damit
    parallele Laeufe sich weder gegenseitig ``stages_done`` ueberschreiben noch
    auf derselben Temp-Datei kollidieren.
    """
    with _CheckpointLock(stem_cache.cache_meta_path(track_id)):
        meta = _ensure_meta(track_id)
        if stage_name not in meta["stages_done"]:
            meta["stages_done"].append(stage_name)
            _save_meta_atomic(track_id, meta)


def reset_stages(track_id: int, stage_names: tuple[str, ...]) -> None:
    """Entfernt gezielt Stage-Done-Marker für einen sichtbaren Retry.

    B-750: Ein kompletter V2-Worker würde eine bereits erfolgreiche Stage
    sonst per Checkpoint überspringen. Der Read-Modify-Write nutzt denselben
    Lock und atomaren Writer wie ``mark_stage_done``; andere Stage-Marker
    bleiben in ihrer Reihenfolge erhalten.
    """
    requested = set(stage_names)
    if not requested:
        return
    with _CheckpointLock(stem_cache.cache_meta_path(track_id)):
        meta = _ensure_meta(track_id)
        current = list(meta.get("stages_done", []))
        remaining = [name for name in current if name not in requested]
        if remaining == current:
            return
        meta["stages_done"] = remaining
        _save_meta_atomic(track_id, meta)


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

"""anchor_sync_service — B-619.

Persistiert Dialog-Anker (aus dem "+Anker"-Dialog in Pacing & Anker) in das
bestehende Schema ``AudioVideoAnchor``. Dieser Pfad ist NEU und getrennt vom
M-Tasten-Anker-Sync (``ui/timeline.py:sync_anchors`` -> ClipAnchor/_anchor_map).

Dialog-Anker haben das Format ``{"audio_time": float, "scene_id": str}``. Die
``scene_id`` stammt aus ``edit_workspace._add_anchor_dialog`` und ist entweder

- die String-Form einer ``Scene.id`` (z.B. ``"5"``)  -> paarweise Szene, oder
- ``"clip_<VideoClip.id>"`` (z.B. ``"clip_3"``)      -> ganzer Clip ohne Szenen.

Mapping-Entscheidung (belegt in database/models.py):
- Scene.id      -> video_clip_id = Scene.video_clip_id, video_time = Scene.start_time
- "clip_<id>"   -> video_clip_id = <id>,                 video_time = 0.0 (Clip-Start)
"""

from __future__ import annotations

import logging
import random as _random
import time as _time

from sqlalchemy import select  # B-090: column-select statt Blob-Voll-Load
from sqlalchemy import text as _sa_text  # B-628: busy_timeout aus Restbudget

from database import AudioVideoAnchor, Scene, nullpool_session

logger = logging.getLogger(__name__)

# Eigener anchor_type, damit der Dialog-Sync idempotent nur seine eigenen Rows
# ersetzt und M-Tasten-/Beat-Anker unberuehrt bleiben.
DIALOG_ANCHOR_TYPE = "dialog"

# B-779: Retry-Budget fuer "database is locked" (B-073-Pattern, identisch zu
# services/onset_rhythm_service.py:726 und services/ai_audio_service.py:1435).
_MAX_RETRIES = 3

# B-779 Nachtrag: Deckel fuer die Gesamtdauer aller Versuche zusammen.
# Der Callsite (ui/controllers/edit_workspace.py::_sync_anchors) laeuft im
# GUI-Thread; ohne Deckel wuerden 3 Versuche x busy_timeout (120 s) die App
# im Extremfall 6 Minuten einfrieren. 150 s liegt knapp ueber einem
# einzelnen busy_timeout — Retries kosten damit praktisch keine zusaetzliche
# Blockadezeit gegenueber dem Zustand vor diesem Fix.
_TOTAL_RETRY_BUDGET_SEC = 150.0


class AnchorSyncLockedError(RuntimeError):
    """B-779: Anker-Sync konnte den DB-Write wegen Lock-Contention nicht ablegen.

    Wird erst nach erschoepften Retries geworfen (busy_timeout + Backoff),
    damit der Aufrufer Lock-Contention von echten Datenfehlern unterscheiden
    kann statt einen rohen ``OperationalError`` zu sehen.
    """


def _resolve_scene_id(session, scene_id_raw: str):
    """Loest eine Dialog-scene_id auf (video_clip_id, video_time) auf.

    Returns None, wenn scene_id leer oder nicht aufloesbar ist.
    """
    if not scene_id_raw:
        return None
    scene_id_raw = str(scene_id_raw).strip()
    if not scene_id_raw:
        return None

    # Form 2: "clip_<VideoClip.id>" — ganzer Clip ohne erkannte Szenen.
    if scene_id_raw.startswith("clip_"):
        try:
            clip_id = int(scene_id_raw[len("clip_"):])
        except ValueError:
            logger.warning("anchor_sync: ungueltige clip-scene_id %r", scene_id_raw)
            return None
        return clip_id, 0.0

    # Form 1: Scene.id — paarweise Szene.
    try:
        scene_id = int(scene_id_raw)
    except ValueError:
        logger.warning("anchor_sync: ungueltige scene_id %r", scene_id_raw)
        return None
    # B-090: column-select statt ORM-Voll-Laden (keyframe_paths/embedding_indices/ai_caption/ai_tags JSON); nutzt nur video_clip_id, start_time
    scene = session.execute(
        select(Scene.video_clip_id, Scene.start_time).where(Scene.id == scene_id)
    ).first()
    if scene is None:
        logger.warning("anchor_sync: Scene id=%s nicht gefunden", scene_id)
        return None
    return scene.video_clip_id, float(scene.start_time or 0.0)


def sync_dialog_anchors(audio_track_id: int, anchors: list[dict]) -> int:
    """Persistiert Dialog-Anker fuer ``audio_track_id`` in AudioVideoAnchor.

    Idempotent: bestehende Dialog-Anker (anchor_type="dialog") dieses Tracks
    werden geloescht und durch die uebergebene Liste ersetzt. Beat-/M-Tasten-
    Anker anderer anchor_types bleiben unberuehrt.

    Args:
        audio_track_id: AudioTrack.id, zu dem die Anker gehoeren.
        anchors: Liste ``[{"audio_time": float, "scene_id": str}, ...]``.

    Returns:
        Anzahl tatsaechlich persistierter Anker-Rows (aufloesbar).

    Raises:
        AnchorSyncLockedError: Der Write blieb ueber alle Retries hinweg von
            "database is locked" blockiert (B-779).
    """
    if audio_track_id is None:
        raise ValueError("audio_track_id darf nicht None sein")

    # B-628: nullpool_session() statt nacktem DBSession(engine). Die
    # NullPool-Engine setzt busy_timeout=120s (database/session.py:198) und
    # liefert eine frische Connection pro Session — das etablierte robuste
    # Write-Muster gegen "database is locked" unter Multi-Worker-Last
    # (Vorbild: services/analysis_status_service.py). Zuvor crashte der
    # gepoolte Zugriff bei Lock-Contention waehrend Massen-Imports.
    #
    # B-779: busy_timeout allein ist kein Absolutschutz — unter Dauer-Saettigung
    # laeuft er ab und derselbe OperationalError kehrt zurueck. Deshalb
    # zusaetzlich Retry mit exponential backoff + jitter (B-073-Pattern, siehe
    # onset_rhythm_service._store). Ohne Contention faellt kein Extra-Delay an:
    # der erste Versuch bricht die Schleife sofort.
    #
    # B-779 Nachtrag: der einzige Callsite ist ui/controllers/edit_workspace.py
    # ``_sync_anchors`` — der laeuft im GUI-Thread. Ohne Deckel wuerde der
    # Retry das Worst-Case-Budget von einem busy_timeout (120 s) auf drei
    # verdreifachen und die App im Extremfall minutenlang einfrieren. Deshalb
    # ein GESAMT-Budget: sobald es aufgebraucht ist, wird nicht mehr neu
    # versucht. Retries nutzen damit nur Zeit, die ein einzelner
    # busy_timeout-Lauf ohnehin verbraucht haette.
    _deadline = _time.monotonic() + _TOTAL_RETRY_BUDGET_SEC
    for attempt in range(_MAX_RETRIES):
        try:
            with nullpool_session() as session:
                # B-628: Das Budget deckelte bisher nur den START eines
                # Versuchs, nicht seine DAUER. Ein begonnener Versuch lief
                # danach in den vollen busy_timeout von 120 s — auch wenn nur
                # noch 30 s Budget uebrig waren. Gemessen (skaliert, echte
                # WAL-DB mit BEGIN EXCLUSIVE als Blocker): Abbruch nach
                # Budget + einem ganzen busy_timeout. Real waren das rund
                # 240 s GUI-Blockade statt der zugesagten 150 s.
                # Deshalb den busy_timeout aus dem RESTBUDGET ableiten: ein
                # Versuch darf nie laenger warten, als insgesamt noch erlaubt
                # ist. Damit haelt die Konstante, was ihr Name verspricht.
                _rest_ms = max(
                    250, int((_deadline - _time.monotonic()) * 1000)
                )
                try:
                    session.execute(_sa_text(f"PRAGMA busy_timeout={_rest_ms}"))
                except Exception as _pragma_exc:  # broad: Pragma darf nie kippen
                    logger.debug(
                        "[AnchorSync] busy_timeout nicht setzbar (%s) — "
                        "es gilt der Vorgabewert.", _pragma_exc,
                    )
                # Idempotenz: alte Dialog-Anker dieses Tracks entfernen.
                session.query(AudioVideoAnchor).filter(
                    AudioVideoAnchor.audio_track_id == audio_track_id,
                    AudioVideoAnchor.anchor_type == DIALOG_ANCHOR_TYPE,
                ).delete(synchronize_session=False)

                persisted = 0
                for entry in anchors or []:
                    audio_time = entry.get("audio_time")
                    scene_id_raw = entry.get("scene_id")
                    if audio_time is None:
                        continue
                    resolved = _resolve_scene_id(session, scene_id_raw)
                    if resolved is None:
                        continue
                    video_clip_id, video_time = resolved
                    session.add(AudioVideoAnchor(
                        audio_track_id=audio_track_id,
                        video_clip_id=video_clip_id,
                        audio_time=float(audio_time),
                        video_time=float(video_time),
                        anchor_type=DIALOG_ANCHOR_TYPE,
                    ))
                    persisted += 1

                session.commit()
                return persisted
        except Exception as e:  # broad catch intentional — nur Lock-Fehler werden retried
            if "database is locked" not in str(e):
                raise
            _remaining = _deadline - _time.monotonic()
            if attempt < _MAX_RETRIES - 1 and _remaining > 0:
                base_wait = 2 ** attempt
                jitter = _random.uniform(0.5, 1.5)
                wait = min(base_wait * jitter, _remaining)
                logger.warning(
                    "[AnchorSync] DB locked bei Dialog-Anker-Write "
                    "audio_track_id=%s, Retry %d/%d (warte %.2fs, "
                    "Restbudget %.1fs)...",
                    audio_track_id, attempt + 1, _MAX_RETRIES, wait, _remaining,
                )
                _time.sleep(wait)
            else:
                if _remaining <= 0:
                    logger.warning(
                        "[AnchorSync] Retry-Gesamtbudget (%.0fs) erschoepft "
                        "nach %d Versuch(en) — kein weiterer Versuch.",
                        _TOTAL_RETRY_BUDGET_SEC, attempt + 1,
                    )
                raise AnchorSyncLockedError(
                    f"Anker-Sync fuer audio_track_id={audio_track_id} "
                    f"abgebrochen: DB-Schreib-Lock blieb nach {_MAX_RETRIES} "
                    f"Versuchen (inkl. busy_timeout) belegt — "
                    f"'database is locked'. Laeuft parallel ein Massen-Import? "
                    f"Bitte erneut versuchen, wenn die Analyse-Last sinkt."
                ) from e

    # Unerreichbar: die Schleife endet immer per return oder raise.
    raise AssertionError("unreachable")  # pragma: no cover

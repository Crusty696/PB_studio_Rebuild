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

from sqlalchemy import select  # B-090: column-select statt Blob-Voll-Load

from database import AudioVideoAnchor, Scene, nullpool_session

logger = logging.getLogger(__name__)

# Eigener anchor_type, damit der Dialog-Sync idempotent nur seine eigenen Rows
# ersetzt und M-Tasten-/Beat-Anker unberuehrt bleiben.
DIALOG_ANCHOR_TYPE = "dialog"


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
    """
    if audio_track_id is None:
        raise ValueError("audio_track_id darf nicht None sein")

    # B-628: nullpool_session() statt nacktem DBSession(engine). Die
    # NullPool-Engine setzt busy_timeout=120s (database/session.py:198) und
    # liefert eine frische Connection pro Session — das etablierte robuste
    # Write-Muster gegen "database is locked" unter Multi-Worker-Last
    # (Vorbild: services/analysis_status_service.py). Zuvor crashte der
    # gepoolte Zugriff bei Lock-Contention waehrend Massen-Imports.
    with nullpool_session() as session:
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

"""B-490: store_scenes_in_db darf nicht am Foreign-Key crashen, wenn der
VideoClip in der aktiven DB fehlt (Projekt-Wechsel mid-pipeline / stale id).

Frueher rief die Funktion direkt INSERT INTO scenes(video_clip_id=...) und der
SQLite-FK schlug beim Commit fehl (sqlite3.IntegrityError 'FOREIGN KEY
constraint failed') -> ganze Pipeline-Task abgebrochen. Fix: Existenz pruefen
und sonst ueberspringen.
"""

from __future__ import annotations


def test_b490_missing_clip_skips_without_raising(test_engine):
    from services.video_analysis_service import store_scenes_in_db, SceneInfo

    scenes = [SceneInfo(index=0, start_time=0.0, end_time=5.0)]
    # VideoClip 99999 existiert nicht -> frueher FK-Crash, jetzt graceful skip
    store_scenes_in_db(99999, scenes)  # darf NICHT raisen


def test_b490_existing_clip_stores_scenes(test_engine, video_clip, db_session):
    from services.video_analysis_service import store_scenes_in_db, SceneInfo
    import database

    scenes = [
        SceneInfo(index=0, start_time=0.0, end_time=5.0, motion_score=0.3),
        SceneInfo(index=1, start_time=5.0, end_time=10.0, motion_score=0.6),
    ]
    store_scenes_in_db(video_clip.id, scenes)  # darf NICHT raisen

    stored = (
        db_session.query(database.Scene)
        .filter_by(video_clip_id=video_clip.id)
        .all()
    )
    assert len(stored) == 2

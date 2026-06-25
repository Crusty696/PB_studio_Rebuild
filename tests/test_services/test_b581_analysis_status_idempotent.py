"""B-581: analysis_status mark_* idempotent gegen UNIQUE-Race.

Race-Szenario: zwei parallele Worker fuer denselben
(media_type, media_id, step_key) lesen beide ``None`` (Schritt existiert
noch nicht) und INSERTen beide -> der zweite ``commit()`` crasht am
UNIQUE-Constraint ``uq_analysis_status_media_step`` (database/models.py).

Test 1 beweist das deterministisch ueber zwei Sessions die beide das
rohe read-then-insert-Pattern fahren (ROT vor Fix: IntegrityError).
Test 2-6 pruefen das gewuenschte Endverhalten der gefixten mark_*-
Funktionen: kein Crash bei Doppel-Aufruf, genau 1 Row, korrekter Status.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
from database import AnalysisStatus


def _patch_status_service(status_service, monkeypatch):
    """analysis_status_service ist nicht in conftest-Autopatch-Liste."""
    monkeypatch.setattr(status_service, "nullpool_session", database.nullpool_session)


def _count_rows(engine, media_type, media_id, step_key) -> int:
    with Session(engine) as s:
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
            AnalysisStatus.step_key == step_key,
        )
        return len(s.execute(stmt).scalars().all())


def test_raw_double_insert_demonstrates_race(test_engine):
    """Beweist die Race: rohes read-then-insert aus zwei Sessions -> IntegrityError.

    Das ist exakt das Muster, das die UNGEFIXTE mark_*-Funktion fuer
    zwei parallele Worker erzeugt: beide sehen None, beide INSERT.
    """
    s1 = Session(test_engine)
    s2 = Session(test_engine)
    try:
        # Beide lesen None (Schritt existiert noch nicht)
        stmt = select(AnalysisStatus).where(
            AnalysisStatus.media_type == "audio",
            AnalysisStatus.media_id == 99,
            AnalysisStatus.step_key == "stem_separation",
        )
        assert s1.execute(stmt).scalar_one_or_none() is None
        assert s2.execute(stmt).scalar_one_or_none() is None

        # Worker 1 committet zuerst
        s1.add(AnalysisStatus(
            media_type="audio", media_id=99, step_key="stem_separation",
            status="running",
        ))
        s1.commit()

        # Worker 2 INSERTet ebenfalls -> UNIQUE-Constraint-Verletzung
        s2.add(AnalysisStatus(
            media_type="audio", media_id=99, step_key="stem_separation",
            status="running",
        ))
        with pytest.raises(IntegrityError):
            s2.commit()
    finally:
        s1.close()
        s2.close()


def _force_insert_path(status_service, monkeypatch):
    """Zwingt mark_* in den INSERT-Pfad: scalar_one_or_none liefert immer None.

    Das reproduziert die Race deterministisch ueber die echte Funktion:
    ein zweiter Worker, der die bereits committete Row noch nicht sieht
    (None liest), nimmt den INSERT-Zweig -> UNIQUE-Collision beim
    ungefixten Code, Upsert beim gefixten Code.
    """
    from sqlalchemy.engine.result import Result

    orig = Result.scalar_one_or_none

    def _always_none(self):
        return None

    monkeypatch.setattr(Result, "scalar_one_or_none", _always_none)
    return orig


def test_concurrent_mark_started_no_integrityerror(test_engine, monkeypatch):
    """Gefixte mark_started: zweiter Worker sieht None -> Upsert statt IntegrityError.

    Reproduziert die Race deterministisch ueber die echte Funktion, indem
    der SELECT immer None liefert (beide Worker glauben, der Schritt
    existiere noch nicht). Mit dem ungefixten add+commit crasht der zweite
    Aufruf am UNIQUE-Constraint; mit Upsert nicht.
    """
    from services import analysis_status_service as status_service
    _patch_status_service(status_service, monkeypatch)
    _force_insert_path(status_service, monkeypatch)

    # Worker A (INSERT-Pfad)
    status_service.mark_started("audio", 7, "bpm_detection")
    # Worker B sieht ebenfalls None -> INSERT-Pfad -> ohne Fix: IntegrityError
    status_service.mark_started("audio", 7, "bpm_detection")

    assert _count_rows(test_engine, "audio", 7, "bpm_detection") == 1
    statuses = status_service.get_status("audio", 7)
    assert statuses["bpm_detection"].status == "running"


def test_double_mark_done_single_row(test_engine, monkeypatch):
    from services import analysis_status_service as status_service
    _patch_status_service(status_service, monkeypatch)

    status_service.mark_done("video", 5, "scene_detection", {"scenes": 3})
    status_service.mark_done("video", 5, "scene_detection", {"scenes": 4})

    assert _count_rows(test_engine, "video", 5, "scene_detection") == 1
    statuses = status_service.get_status("video", 5)
    entry = statuses["scene_detection"]
    assert entry.status == "done"
    assert entry.value_summary == {"scenes": 4}
    assert entry.completed_at is not None


def test_double_mark_error_single_row(test_engine, monkeypatch):
    from services import analysis_status_service as status_service
    _patch_status_service(status_service, monkeypatch)

    status_service.mark_error("audio", 8, "key_detection", "boom1")
    status_service.mark_error("audio", 8, "key_detection", "boom2")

    assert _count_rows(test_engine, "audio", 8, "key_detection") == 1
    statuses = status_service.get_status("audio", 8)
    entry = statuses["key_detection"]
    assert entry.status == "error"
    assert entry.error_message == "boom2"


def test_double_mark_cancelled_single_row(test_engine, monkeypatch):
    from services import analysis_status_service as status_service
    _patch_status_service(status_service, monkeypatch)

    status_service.mark_cancelled("audio", 9, "stem_separation")
    status_service.mark_cancelled("audio", 9, "stem_separation")

    assert _count_rows(test_engine, "audio", 9, "stem_separation") == 1
    statuses = status_service.get_status("audio", 9)
    entry = statuses["stem_separation"]
    assert entry.status == "error"
    assert entry.error_message == "cancelled"


def test_mark_started_then_done_preserves_started_at(test_engine, monkeypatch):
    """Endverhalten-Erhalt: started_at bleibt vom mark_started erhalten."""
    from services import analysis_status_service as status_service
    _patch_status_service(status_service, monkeypatch)

    status_service.mark_started("video", 11, "motion_scores")
    statuses = status_service.get_status("video", 11)
    started_at = statuses["motion_scores"].started_at
    assert started_at is not None

    status_service.mark_done("video", 11, "motion_scores", {"avg": 0.5})
    statuses = status_service.get_status("video", 11)
    entry = statuses["motion_scores"]
    assert entry.status == "done"
    assert entry.started_at == started_at
    assert entry.completed_at is not None

"""B-771: store_scenes_in_db crashte bei Re-Analyse mit IntegrityError.

Live-Session 2026-08-07 04:56: 9 von 251 Clips schlugen fehl —
``mem_decision.scene_id`` (NOT NULL, kein CASCADE, Design: "deleted clips
must not wipe history") referenzierte die Szenen, der alte
delete+insert-Pfad loeschte sie trotzdem per Bulk-Delete ->
``sqlite3.IntegrityError: FOREIGN KEY constraint failed``.

Fix-Vertrag (Upsert mit stabilen Scene-IDs):
1. Re-Analyse eines referenzierten Clips crasht NICHT mehr.
2. Scene-IDs bleiben stabil, mem_decision-Referenzen bleiben gueltig.
3. Alt-Nebeneffekte repliziert: struct_clip_tags/struct_compat_edge der
   Szenen geloescht (frueher CASCADE), ai_pacing_memory.scene_id NULL
   (frueher SET NULL).
4. Schrumpf-Fall: ueberzaehlige Szenen werden geloescht, deren
   mem_decision-Referenzen auf eine ueberlebende Szene desselben Clips
   umgehaengt — Historie bleibt vollstaendig.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database.models import Base, Project, Scene, VideoClip


@dataclass
class _FakeScene:
    index: int
    start_time: float
    end_time: float
    motion_score: float = 0.5
    ai_caption: dict | None = None
    ai_mood: str | None = None
    ai_tags: list | None = field(default_factory=list)


@pytest.fixture()
def fk_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # Nicht-ORM-Tabellen (nur Alembic): minimal mit den echten FKs.
        conn.execute(text(
            "CREATE TABLE mem_decision ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " scene_id INTEGER NOT NULL REFERENCES scenes(id),"
            " agent_score FLOAT NOT NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE struct_clip_tags ("
            " scene_id INTEGER PRIMARY KEY "
            "  REFERENCES scenes(id) ON DELETE CASCADE,"
            " role TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE struct_compat_edge ("
            " scene_id_a INTEGER NOT NULL "
            "  REFERENCES scenes(id) ON DELETE CASCADE,"
            " scene_id_b INTEGER NOT NULL "
            "  REFERENCES scenes(id) ON DELETE CASCADE,"
            " PRIMARY KEY (scene_id_a, scene_id_b))"
        ))
        # ai_pacing_memory ist ORM-Modell (models.py) — bereits via
        # Base.metadata.create_all angelegt.

    factory = sessionmaker(bind=engine)

    class _Ctx:
        def __enter__(self):
            self._s = factory()
            return self._s

        def __exit__(self, *exc):
            self._s.close()
            return False

    monkeypatch.setattr(database, "nullpool_session", lambda: _Ctx())
    return engine, factory


def _seed_clip_with_scenes(factory, n_scenes: int) -> tuple[int, list[int]]:
    s = factory()
    project = Project(name="b771", path="C:/fake/b771")
    s.add(project)
    s.flush()
    clip = VideoClip(project_id=project.id, file_path="C:/fake/clip.mp4")
    s.add(clip)
    s.flush()
    ids = []
    for i in range(n_scenes):
        sc = Scene(video_clip_id=clip.id, start_time=float(i), end_time=i + 1.0)
        s.add(sc)
        s.flush()
        ids.append(sc.id)
    s.commit()
    clip_id = clip.id
    s.close()
    return clip_id, ids


def test_reanalysis_with_mem_decision_reference_does_not_crash(fk_engine):
    """Kernrepro: referenzierte Szene + Re-Analyse -> frueher IntegrityError."""
    from services.video_analysis_service import store_scenes_in_db

    engine, factory = fk_engine
    clip_id, scene_ids = _seed_clip_with_scenes(factory, 2)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO mem_decision (scene_id, agent_score) VALUES (:sid, 1.0)"
        ), {"sid": scene_ids[0]})

    ok = store_scenes_in_db(
        clip_id,
        [_FakeScene(0, 0.0, 1.5), _FakeScene(1, 1.5, 3.0)],
    )
    assert ok is True

    with engine.connect() as conn:
        # Scene-IDs stabil, Referenz weiterhin gueltig.
        rows = conn.execute(text(
            "SELECT id, start_time, end_time FROM scenes ORDER BY id"
        )).fetchall()
        assert [r[0] for r in rows] == scene_ids
        assert rows[0][2] == 1.5  # Inhalt wirklich aktualisiert
        ref = conn.execute(text("SELECT scene_id FROM mem_decision")).scalar()
        assert ref == scene_ids[0]


def test_upsert_replicates_old_cascade_side_effects(fk_engine):
    """struct-Tabellen geleert, ai_pacing_memory auf NULL (Alt-Verhalten)."""
    from services.video_analysis_service import store_scenes_in_db

    engine, factory = fk_engine
    clip_id, scene_ids = _seed_clip_with_scenes(factory, 2)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO struct_clip_tags (scene_id, role) VALUES (:a, 'hero')"
        ), {"a": scene_ids[0]})
        conn.execute(text(
            "INSERT INTO struct_compat_edge (scene_id_a, scene_id_b) "
            "VALUES (:a, :b)"
        ), {"a": scene_ids[0], "b": scene_ids[1]})
        conn.execute(text(
            "INSERT INTO ai_pacing_memory (scene_id) VALUES (:a)"
        ), {"a": scene_ids[1]})

    assert store_scenes_in_db(
        clip_id, [_FakeScene(0, 0.0, 1.0), _FakeScene(1, 1.0, 2.0)]
    ) is True

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM struct_clip_tags")).scalar() == 0
        assert conn.execute(
            text("SELECT COUNT(*) FROM struct_compat_edge")).scalar() == 0
        assert conn.execute(
            text("SELECT scene_id FROM ai_pacing_memory")).scalar() is None


def test_shrinking_scene_count_remaps_references(fk_engine):
    """3 alte Szenen -> 1 neue: Referenz auf geloeschte Szene wird auf die
    ueberlebende Szene desselben Clips umgehaengt, keine Row verloren."""
    from services.video_analysis_service import store_scenes_in_db

    engine, factory = fk_engine
    clip_id, scene_ids = _seed_clip_with_scenes(factory, 3)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO mem_decision (scene_id, agent_score) VALUES (:sid, 2.0)"
        ), {"sid": scene_ids[2]})

    assert store_scenes_in_db(clip_id, [_FakeScene(0, 0.0, 4.0)]) is True

    with engine.connect() as conn:
        remaining = [r[0] for r in conn.execute(
            text("SELECT id FROM scenes ORDER BY id"))]
        assert remaining == [scene_ids[0]]
        assert conn.execute(
            text("SELECT COUNT(*) FROM mem_decision")).scalar() == 1
        assert conn.execute(
            text("SELECT scene_id FROM mem_decision")).scalar() == scene_ids[0]


def test_growing_scene_count_inserts_new_rows(fk_engine):
    """1 alte Szene -> 3 neue: Upsert + 2 Inserts, keine FK-Fehler."""
    from services.video_analysis_service import store_scenes_in_db

    engine, factory = fk_engine
    clip_id, scene_ids = _seed_clip_with_scenes(factory, 1)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO mem_decision (scene_id, agent_score) VALUES (:sid, 1.0)"
        ), {"sid": scene_ids[0]})

    assert store_scenes_in_db(
        clip_id,
        [_FakeScene(i, float(i), i + 1.0) for i in range(3)],
    ) is True

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM scenes")).scalar() == 3
        assert conn.execute(
            text("SELECT scene_id FROM mem_decision")).scalar() == scene_ids[0]

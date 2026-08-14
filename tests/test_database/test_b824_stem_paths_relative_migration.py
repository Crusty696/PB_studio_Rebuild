"""B-824: Datenmigration der Stem-Pfade auf projektrelative Speicherung.

Geprueft wird die Revision ``b4c5d6e7f8a9`` gegen eine echte SQLite-DB mit
kanonischem Schema. Die Migration soll genau drei Dinge tun:

- absolute Pfade UNTERHALB des eigenen Projekts relativ machen,
- Pfade ausserhalb des Projekts unangetastet lassen (raten waere schlimmer als
  stehenlassen — zur Laufzeit entscheidet ``resolve_stem_path``),
- bereits relative Werte und NULL nicht anfassen.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from database.models import Base

_REVISION = (
    Path(__file__).resolve().parents[2]
    / "database" / "alembic" / "versions"
    / "2026_08_14_b4c5d6e7f8a9_stem_paths_project_relative.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location("b824_revision", _REVISION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(conn, project_path: str, stem_paths: dict[str, str | None]) -> int:
    conn.execute(
        text(
            "INSERT INTO projects (id, name, path, resolution, fps) "
            "VALUES (1, 'p', :path, '1920x1080', 30.0)"
        ),
        {"path": project_path},
    )
    conn.execute(
        text(
            "INSERT INTO audio_tracks "
            "(id, project_id, file_path, title, stem_vocals_path, stem_drums_path, "
            " stem_bass_path, stem_other_path) "
            "VALUES (1, 1, 'x.wav', 'x', :v, :d, :b, :o)"
        ),
        {
            "v": stem_paths.get("vocals"),
            "d": stem_paths.get("drums"),
            "b": stem_paths.get("bass"),
            "o": stem_paths.get("other"),
        },
    )
    return 1


def _run_upgrade(conn):
    module = _load_revision()
    module.op = SimpleNamespace(get_bind=lambda: conn)
    module.upgrade()


def _read(conn) -> dict[str, str | None]:
    row = conn.execute(
        text(
            "SELECT stem_vocals_path, stem_drums_path, stem_bass_path, stem_other_path "
            "FROM audio_tracks WHERE id = 1"
        )
    ).first()
    return dict(zip(("vocals", "drums", "bass", "other"), row))


def test_b824_absolute_paths_inside_project_become_relative():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = r"C:\Projekte\meinprojekt"
    with engine.begin() as conn:
        _seed(conn, root, {
            "vocals": root + r"\storage\stems\htdemucs\lv3\vocals.wav",
            "drums": root + r"\storage\stems\htdemucs\lv3\drums.wav",
            "bass": root + r"\storage\stems\htdemucs\lv3\bass.wav",
            "other": root + r"\storage\stems\htdemucs\lv3\other.wav",
        })
        _run_upgrade(conn)
        result = _read(conn)

    for name in ("vocals", "drums", "bass", "other"):
        assert result[name] == f"storage/stems/htdemucs/lv3/{name}.wav"


def test_b824_foreign_paths_are_left_alone():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = r"C:\Projekte\meinprojekt"
    foreign = r"C:\woanders\storage\stems\htdemucs\lv3\vocals.wav"
    with engine.begin() as conn:
        _seed(conn, root, {"vocals": foreign})
        _run_upgrade(conn)
        result = _read(conn)

    assert result["vocals"] == foreign


def test_b824_relative_and_null_values_untouched():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _seed(conn, r"C:\Projekte\meinprojekt", {
            "vocals": "storage/stems/htdemucs/lv3/vocals.wav",
            "drums": None,
        })
        _run_upgrade(conn)
        result = _read(conn)

    assert result["vocals"] == "storage/stems/htdemucs/lv3/vocals.wav"
    assert result["drums"] is None


def test_b824_case_and_separator_differences_still_match():
    """Windows mischt Trenner und ist case-insensitiv — der Prefix-Vergleich
    darf daran nicht scheitern."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _seed(conn, r"C:\Projekte\MeinProjekt\\", {
            "vocals": r"c:/projekte/meinprojekt\storage\stems\lv3\vocals.wav",
        })
        _run_upgrade(conn)
        result = _read(conn)

    assert result["vocals"] == "storage/stems/lv3/vocals.wav"


def test_b824_migration_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = r"C:\Projekte\meinprojekt"
    with engine.begin() as conn:
        _seed(conn, root, {"vocals": root + r"\storage\stems\lv3\vocals.wav"})
        _run_upgrade(conn)
        first = _read(conn)
        _run_upgrade(conn)
        second = _read(conn)

    assert first == second == {
        "vocals": "storage/stems/lv3/vocals.wav",
        "drums": None, "bass": None, "other": None,
    }


def test_b824_downgrade_restores_absolute_paths():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = r"C:\Projekte\meinprojekt"
    module = _load_revision()
    with engine.begin() as conn:
        _seed(conn, root, {"vocals": root + r"\storage\stems\lv3\vocals.wav"})
        module.op = SimpleNamespace(get_bind=lambda: conn)
        module.upgrade()
        module.downgrade()
        result = _read(conn)

    assert result["vocals"] == "C:/Projekte/meinprojekt/storage/stems/lv3/vocals.wav"

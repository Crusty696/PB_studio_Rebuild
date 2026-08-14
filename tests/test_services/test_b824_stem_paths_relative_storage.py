"""B-824: Stem-Pfade werden projektrelativ gespeichert.

Follow-up zu B-822. Dort wurde die *Auslegung* der Pfade ans aktive Projekt
gebunden, das Speicherformat blieb absolut. Damit bleibt jede Projektkopie eine
Zeitbombe: die Spalten zeigen weiter nach draussen und funktionieren nur, weil
die Aufloesung sie zurechtbiegt.

Hier wird das Format selbst umgestellt — neu geschriebene Pfade sind relativ
zum Projekt-Root, mit ``/`` als Trenner, damit sie auch beim Verschieben
zwischen Laufwerken gueltig bleiben. Bestandsdaten zieht eine Alembic-Revision
nach.
"""

from __future__ import annotations

from pathlib import Path


def _make_stems(root: Path, track: str = "lv3") -> Path:
    d = root / "storage" / "stems" / "htdemucs" / track
    d.mkdir(parents=True, exist_ok=True)
    for name in ("vocals", "drums", "bass", "other"):
        (d / f"{name}.wav").write_bytes(b"RIFF")
    return d


def test_b824_to_project_relative_strips_project_root(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    d = _make_stems(project)
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    rel = stem_router.to_project_relative(str(d / "vocals.wav"))

    assert rel == "storage/stems/htdemucs/lv3/vocals.wav"
    assert "\\" not in rel, "Trenner muss POSIX sein, sonst bricht der Pfad plattformuebergreifend"


def test_b824_to_project_relative_keeps_foreign_path_absolute(tmp_path, monkeypatch):
    """Was nicht zum Projekt gehoert, wird nicht faelschlich relativ gemacht."""
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    project.mkdir()
    foreign = tmp_path / "woanders" / "vocals.wav"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"RIFF")
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    assert stem_router.to_project_relative(str(foreign)) == str(foreign)


def test_b824_to_project_relative_passes_through_relative_input(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    assert stem_router.to_project_relative("storage/stems/x/vocals.wav") == \
        "storage/stems/x/vocals.wav"
    assert stem_router.to_project_relative(None) is None
    assert stem_router.to_project_relative("") is None


def test_b824_resolve_reads_relative_path_against_active_project(tmp_path, monkeypatch):
    """Der eigentliche Gewinn: derselbe relative Wert funktioniert in jeder Kopie."""
    import database.session as db_session
    from services import stem_router

    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    dir_a = _make_stems(project_a)
    dir_b = _make_stems(project_b)
    stored = "storage/stems/htdemucs/lv3/vocals.wav"

    monkeypatch.setattr(db_session, "APP_ROOT", project_a)
    assert Path(stem_router.resolve_stem_path(stored)) == dir_a / "vocals.wav"

    monkeypatch.setattr(db_session, "APP_ROOT", project_b)
    assert Path(stem_router.resolve_stem_path(stored)) == dir_b / "vocals.wav"


def test_b824_relative_path_without_file_is_none(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    assert stem_router.resolve_stem_path("storage/stems/fehlt/vocals.wav") is None


def test_b824_relative_path_never_counts_as_outside(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    assert stem_router.points_outside_project("storage/stems/x/vocals.wav") is False


def test_b824_persist_writes_relative_paths(tmp_path, monkeypatch, db_session, audio_track):
    """Der Schreiber selbst legt ab jetzt relativ ab."""
    import database.session as db_sess
    import services.audio_pipeline.stages as stages
    from contextlib import contextmanager

    project = tmp_path / "proj"
    d = _make_stems(project)
    monkeypatch.setattr(db_sess, "APP_ROOT", project)

    @contextmanager
    def _session():
        yield db_session

    monkeypatch.setattr(stages, "nullpool_session", _session)

    stages.StemGenStage._persist_stem_paths_to_db(
        audio_track.id,
        {name: str(d / f"{name}.wav") for name in ("vocals", "drums", "bass", "other")},
    )

    db_session.expire_all()
    assert audio_track.stem_vocals_path == "storage/stems/htdemucs/lv3/vocals.wav"
    assert audio_track.stem_drums_path == "storage/stems/htdemucs/lv3/drums.wav"
    assert audio_track.stem_bass_path == "storage/stems/htdemucs/lv3/bass.wav"
    assert audio_track.stem_other_path == "storage/stems/htdemucs/lv3/other.wav"

"""B-822: Gespeicherte Stem-Pfade duerfen nicht aus dem aktiven Projekt herausfuehren.

Live-Befund 2026-08-14 (W3 Audio V2): in einem isolierten Testprojekt zeigten
alle vier ``audio_tracks.stem_*_path`` auf einen Ordner ausserhalb des
Projekts. Die Dateien lagen dort tatsaechlich, also griffen alle Leser per
``Path(p).exists()`` beherzt zu — obwohl im Projekt selbst dieselben Stems
lagen. Der Stability-Scope war damit umgangen.

Ursache: die Spalten speichern absolute Pfade. Wird ein Projekt kopiert oder
verschoben, zeigen sie weiterhin auf den alten Ort. Existiert der noch, faellt
das niemandem auf.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from database import AnalysisStatus


def _make_stems(root: Path, track: str = "lv3") -> Path:
    d = root / "storage" / "stems" / "htdemucs" / track
    d.mkdir(parents=True, exist_ok=True)
    for name in ("vocals", "drums", "bass", "other"):
        (d / f"{name}.wav").write_bytes(b"RIFF")
    return d


def test_b822_resolves_foreign_path_into_active_project(tmp_path, monkeypatch):
    """Der Klassiker: Projekt kopiert, DB zeigt noch auf den alten Ort."""
    import database.session as db_session
    from services import stem_router

    old_project = tmp_path / "old"
    new_project = tmp_path / "new"
    _make_stems(old_project)
    new_dir = _make_stems(new_project)
    monkeypatch.setattr(db_session, "APP_ROOT", new_project)

    stored = str(old_project / "storage" / "stems" / "htdemucs" / "lv3" / "vocals.wav")
    resolved = stem_router.resolve_stem_path(stored)

    assert resolved is not None
    assert Path(resolved) == new_dir / "vocals.wav"


def test_b822_foreign_path_without_local_copy_is_not_used(tmp_path, monkeypatch):
    """Kein stiller Zugriff nach draussen, wenn das Projekt die Datei nicht hat."""
    import database.session as db_session
    from services import stem_router

    old_project = tmp_path / "old"
    new_project = tmp_path / "new"
    _make_stems(old_project)
    new_project.mkdir()
    monkeypatch.setattr(db_session, "APP_ROOT", new_project)

    stored = str(old_project / "storage" / "stems" / "htdemucs" / "lv3" / "vocals.wav")

    assert stem_router.resolve_stem_path(stored) is None


def test_b822_path_inside_project_is_kept(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    d = _make_stems(project)
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    stored = str(d / "drums.wav")

    assert Path(stem_router.resolve_stem_path(stored)) == d / "drums.wav"


def test_b822_missing_and_empty_inputs(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(db_session, "APP_ROOT", project)

    assert stem_router.resolve_stem_path(None) is None
    assert stem_router.resolve_stem_path("") is None
    assert stem_router.resolve_stem_path(str(project / "nichts.wav")) is None


def test_b822_resolve_mapping_drops_unusable_entries(tmp_path, monkeypatch):
    import database.session as db_session
    from services import stem_router

    old_project = tmp_path / "old"
    new_project = tmp_path / "new"
    _make_stems(old_project)
    new_dir = _make_stems(new_project)
    (new_dir / "vocals.wav").unlink()
    monkeypatch.setattr(db_session, "APP_ROOT", new_project)

    stored = {
        name: str(old_project / "storage" / "stems" / "htdemucs" / "lv3" / f"{name}.wav")
        for name in ("vocals", "drums", "bass", "other")
    }
    resolved = stem_router.resolve_stem_paths(stored)

    # vocals fehlt im aktiven Projekt -> darf NICHT aus dem Fremdordner kommen
    assert "vocals" not in resolved
    assert set(resolved) == {"drums", "bass", "other"}
    for path in resolved.values():
        assert Path(path).is_relative_to(new_project)


def test_b822_status_infer_does_not_claim_stems_from_foreign_dir(
    tmp_path, monkeypatch, db_session, audio_track
):
    """Statusehrlichkeit: Stems ausserhalb des Projekts sind keine Stems."""
    import database.session as db_sess
    from services.analysis_status_service import _infer_audio_status

    old_project = tmp_path / "old"
    new_project = tmp_path / "new"
    _make_stems(old_project)
    new_project.mkdir()
    monkeypatch.setattr(db_sess, "APP_ROOT", new_project)

    base = old_project / "storage" / "stems" / "htdemucs" / "lv3"
    audio_track.stem_vocals_path = str(base / "vocals.wav")
    audio_track.stem_drums_path = str(base / "drums.wav")
    audio_track.stem_bass_path = str(base / "bass.wav")
    audio_track.stem_other_path = str(base / "other.wav")
    db_session.commit()

    _infer_audio_status(db_session, audio_track.id)
    db_session.commit()
    db_session.expire_all()

    row = (
        db_session.query(AnalysisStatus)
        .filter(
            AnalysisStatus.media_type == "audio",
            AnalysisStatus.media_id == audio_track.id,
            AnalysisStatus.step_key == "stem_separation",
        )
        .one_or_none()
    )
    assert row is None, (
        "stem_separation wurde als vorhanden gemeldet, obwohl die Stems "
        "ausserhalb des aktiven Projekts liegen"
    )

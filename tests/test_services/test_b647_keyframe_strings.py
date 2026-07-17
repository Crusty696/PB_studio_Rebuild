"""B-647: generate_keyframe_strings_for_project fror GUI ~6s ein.

Fixes:
1. column-select statt joinedload(VideoClip.scenes) — keine Scene-Blob-Spalten.
2. _show_keyframe_strings laeuft via run_worker off-thread (Source-Pin).
"""
from __future__ import annotations

import inspect

from sqlalchemy.orm import Session as DBSession

from database.models import Project, Scene, VideoClip


def _seed(test_engine) -> int:
    with DBSession(test_engine) as s:
        p = Project(name="b647", path="/tmp/b647")
        s.add(p)
        s.commit()
        pid = p.id
        c1 = VideoClip(project_id=pid, file_path="/vids/alpha.mp4",
                       duration=10.0, width=1920, height=1080)
        c2 = VideoClip(project_id=pid, file_path="/vids/beta.mp4", duration=7.5)
        s.add_all([c1, c2])
        s.commit()
        s.add_all([
            Scene(video_clip_id=c1.id, start_time=0.0, end_time=4.0, energy=0.8),
            Scene(video_clip_id=c1.id, start_time=4.0, end_time=10.0, energy=0.2),
        ])
        s.commit()
        return pid


def test_keyframe_strings_content(test_engine, monkeypatch):
    import services.pacing_edit_helpers as peh
    monkeypatch.setattr(peh, "engine", test_engine)

    pid = _seed(test_engine)
    out = peh.generate_keyframe_strings_for_project(project_id=pid)

    # Clip mit Szenen: Header + Szenen-Teile mit Aufloesung
    assert "Video: 'alpha' (2 Szenen)" in out
    assert "1920x1080" in out
    assert "[Szene 1:" in out and "[Szene 2:" in out
    # Clip ohne Szenen: Fallback-Zeile
    assert "[Video 'beta': Keine Szenen erkannt, Laenge: 7.5s]" in out


def test_keyframe_strings_empty_project(test_engine, monkeypatch):
    import services.pacing_edit_helpers as peh
    monkeypatch.setattr(peh, "engine", test_engine)

    pid = _seed(test_engine)
    assert peh.generate_keyframe_strings_for_project(project_id=pid + 999) == \
        "[Keine Video-Clips im Projekt]"


def test_no_scene_blob_load_pin():
    import services.pacing_edit_helpers as peh
    src = inspect.getsource(peh.generate_keyframe_strings_for_project)
    assert ".options(joinedload" not in src, (
        "B-647: joinedload(VideoClip.scenes) zieht Scene-Blob-Spalten eager")
    assert "select(" in src


def test_show_keyframe_strings_runs_off_thread_pin():
    from ui.controllers.edit_workspace import EditWorkspaceController
    src = inspect.getsource(EditWorkspaceController._show_keyframe_strings)
    assert "run_worker" in src, (
        "B-647: _show_keyframe_strings muss off-thread laufen (run_worker)")

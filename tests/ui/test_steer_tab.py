"""T11.3 headless tests: SteerTab (track selector + profile picker + overrides
lists + Run button) and the BrainService reads backing it.

Follows the offscreen-Qt + on-disk-SQLite pattern from the other
tests/ui/test_*_tab.py files; ``_build_struct_db`` from
``tests/ui/test_structure_tab.py`` is reused directly.  The bootstrap there
creates a minimal ``audio_tracks`` schema without the production ``duration``
/ ``bpm`` columns; ``_add_audio_track_bpm_and_duration`` extends the table so
the BrainService's ``list_audio_tracks`` query can exercise both optional
columns when the test seeds them.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QInputDialog

from services.brain_service import BrainService
from services.steer_override_queue import SteerOverrideQueue
from tests.ui.test_structure_tab import _build_struct_db
from ui.studio_brain.steer_tab import SteerTab
from ui.studio_brain_window import StudioBrainWindow


# ── Qt + singleton hygiene ────────────────────────────────────────────────────


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    StudioBrainWindow._instance = None
    yield
    inst = StudioBrainWindow._instance
    if inst is not None:
        try:
            inst.close()
            inst.deleteLater()
        except Exception:
            pass
    StudioBrainWindow._instance = None


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _add_audio_track_bpm_and_duration(engine) -> None:
    """Extend the test bootstrap's ``audio_tracks`` with ``bpm`` +
    ``duration`` columns so the BrainService's optional-column path is
    exercised. Matches the production schema fields read by the Steer tab
    (see ``database/models.py::AudioTrack``)."""
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(audio_tracks)")).all()
        names = {row[1] for row in cols}
        if "bpm" not in names:
            conn.execute(text("ALTER TABLE audio_tracks ADD COLUMN bpm REAL"))
        if "duration" not in names:
            conn.execute(
                text("ALTER TABLE audio_tracks ADD COLUMN duration REAL")
            )


def _seed_audio_track(
    conn,
    *,
    track_id: int,
    file_path: str = "/mixes/track.mp3",
    created_at: datetime | None = None,
    bpm: float | None = None,
    duration: float | None = None,
) -> None:
    ts = created_at or datetime.now(timezone.utc)
    conn.execute(
        text(
            "INSERT INTO audio_tracks "
            "(id, file_path, original_filename, sha256, status, created_at, "
            " bpm, duration) "
            "VALUES (:id, :fp, :fn, :sha, 'ready', :ts, :bpm, :dur)"
        ),
        {
            "id": track_id,
            "fp": file_path,
            "fn": os.path.basename(file_path),
            "sha": f"a-sha-{track_id}",
            "ts": ts,
            "bpm": bpm,
            "dur": duration,
        },
    )


# ── BrainService unit tests ───────────────────────────────────────────────────


def test_list_audio_tracks_sorted_newest_first(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _add_audio_track_bpm_and_duration(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audio_track(
            conn,
            track_id=1,
            file_path="/mixes/old.mp3",
            created_at=now - timedelta(hours=3),
        )
        _seed_audio_track(
            conn,
            track_id=2,
            file_path="/mixes/mid.mp3",
            created_at=now - timedelta(hours=1),
        )
        _seed_audio_track(
            conn,
            track_id=3,
            file_path="/mixes/new.mp3",
            created_at=now,
        )

    svc = BrainService(session_factory=Session)
    rows = svc.list_audio_tracks()
    ids = [r["id"] for r in rows]
    assert ids == [3, 2, 1]
    assert [r["file_basename"] for r in rows] == [
        "new.mp3",
        "mid.mp3",
        "old.mp3",
    ]


def test_list_weights_profiles_scans_yaml_dir(tmp_path: Path) -> None:
    _engine, Session = _build_struct_db(tmp_path)
    svc = BrainService(session_factory=Session)
    profiles = svc.list_weights_profiles()
    names = {p["name"] for p in profiles}
    # The real config/pacing_weights/ dir must contain these four.
    assert {"default", "psytrance", "house", "dj_mix_auto"}.issubset(names)
    # Every entry must carry an absolute YAML path.
    for p in profiles:
        assert p["path"].endswith(".yaml")
        assert Path(p["path"]).is_file()


def test_list_weights_profiles_missing_dir_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine, Session = _build_struct_db(tmp_path)
    # Point the module-level pacing-weights dir at a guaranteed-missing path.
    ghost = tmp_path / "nonexistent_pacing_weights"
    monkeypatch.setattr(
        "services.brain_service._PACING_WEIGHTS_DIR", ghost
    )
    svc = BrainService(session_factory=Session)
    assert svc.list_weights_profiles() == []


# ── SteerTab widget tests ─────────────────────────────────────────────────────


def _build_tab(
    tmp_path: Path,
    *,
    seed_tracks: int = 2,
    queue: SteerOverrideQueue | None = None,
    with_bpm_duration: bool = True,
) -> tuple[SteerTab, BrainService, SteerOverrideQueue, Any]:
    """Fully-assembled SteerTab with a fresh override queue per test.

    Returns (tab, brain_service, queue, engine) so the caller can mutate
    the DB and queue after construction.
    """
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    if with_bpm_duration:
        _add_audio_track_bpm_and_duration(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for i in range(1, seed_tracks + 1):
            _seed_audio_track(
                conn,
                track_id=i,
                file_path=f"/mixes/track_{i:02d}.mp3",
                created_at=now - timedelta(minutes=seed_tracks - i),
                bpm=124.0 + i,
                duration=180.0 + i * 10,
            )

    svc = BrainService(session_factory=Session)
    # Fresh per-test queue so tests don't leak state via the module-wide
    # singleton.
    q = queue if queue is not None else SteerOverrideQueue()
    tab = SteerTab(brain_service=svc, override_queue=q)
    return tab, svc, q, engine


def test_steer_tab_track_combo_populated_from_brain_service(
    tmp_path: Path,
) -> None:
    tab, _svc, _q, _engine = _build_tab(tmp_path, seed_tracks=2)
    assert tab._track_selector.item_count() == 2


def test_steer_tab_profile_combo_populated_with_default(
    tmp_path: Path,
) -> None:
    tab, _svc, _q, _engine = _build_tab(tmp_path, seed_tracks=1)
    # Every profile name is an itemText; assert "default" is one of them.
    names = [
        tab._profile_picker._combo.itemText(i)
        for i in range(tab._profile_picker._combo.count())
    ]
    assert "default" in names


def test_steer_tab_edit_profile_opens_openurl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tab, _svc, _q, _engine = _build_tab(tmp_path, seed_tracks=1)
    captured: list[QUrl] = []

    def _spy(url: QUrl) -> bool:
        captured.append(url)
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", _spy)
    tab._profile_picker._edit_btn.click()
    assert len(captured) == 1
    url = captured[0]
    assert url.isLocalFile()
    assert url.toLocalFile().endswith(".yaml")


def test_steer_tab_boosts_list_reflects_queue(tmp_path: Path) -> None:
    queue = SteerOverrideQueue()
    queue.add(11, "boost", source="structure")
    queue.add(12, "boost", source="inspector")
    tab, _svc, q, _engine = _build_tab(
        tmp_path, seed_tracks=1, queue=queue
    )
    assert tab._overrides.boost_count() == 2
    q.remove(11)
    # The pendingChanged signal should have cascaded into the tab.
    assert tab._overrides.boost_count() == 1


def test_steer_tab_excludes_list_reflects_queue(tmp_path: Path) -> None:
    queue = SteerOverrideQueue()
    queue.add(21, "exclude", source="graph")
    queue.add(22, "exclude", source="inspector")
    tab, _svc, q, _engine = _build_tab(
        tmp_path, seed_tracks=1, queue=queue
    )
    assert tab._overrides.exclude_count() == 2
    q.remove(21)
    assert tab._overrides.exclude_count() == 1


def test_steer_tab_remove_button_drops_entry_from_queue(
    tmp_path: Path,
) -> None:
    queue = SteerOverrideQueue()
    queue.add(5, "boost", source="structure")
    tab, _svc, q, _engine = _build_tab(
        tmp_path, seed_tracks=1, queue=queue
    )
    # Select the only boost row, then click its Remove button.
    tab._overrides.select_first_boost()
    tab._overrides._boost_remove_btn.click()
    remaining_ids = {entry.scene_id for entry in q.list()}
    assert 5 not in remaining_ids


def test_steer_tab_pin_add_button_adds_scene_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tab, _svc, _q, _engine = _build_tab(tmp_path, seed_tracks=1)
    monkeypatch.setattr(
        "PySide6.QtWidgets.QInputDialog.getInt",
        lambda *a, **k: (42, True),
    )
    tab._overrides._pin_add_btn.click()
    assert tab._overrides.pin_count() == 1
    # Scene #42 should be listed in the snapshot pins payload.
    assert 42 in tab._overrides.pin_scene_ids()


def test_steer_tab_current_snapshot_contains_all_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = SteerOverrideQueue()
    queue.add(100, "boost", source="structure")
    queue.add(200, "exclude", source="graph")
    tab, _svc, _q, _engine = _build_tab(
        tmp_path, seed_tracks=2, queue=queue
    )
    # Point at track #1 + profile "default" (first alphabetical entry that
    # includes "default"); then add a pin.
    tab._track_selector._combo.setCurrentIndex(0)
    # Find and select "default" in the profile combo.
    for i in range(tab._profile_picker._combo.count()):
        if tab._profile_picker._combo.itemText(i) == "default":
            tab._profile_picker._combo.setCurrentIndex(i)
            break
    monkeypatch.setattr(
        "PySide6.QtWidgets.QInputDialog.getInt",
        lambda *a, **k: (7, True),
    )
    tab._overrides._pin_add_btn.click()

    snap = tab.current_snapshot()
    assert set(snap.keys()) == {
        "audio_track_id",
        "weights_profile",
        "pins",
        "boosts",
        "excludes",
        "created_at",
    }
    assert snap["audio_track_id"] is not None
    assert snap["weights_profile"] == "default"
    assert snap["pins"] == [7]
    assert snap["boosts"] == [100]
    assert snap["excludes"] == [200]
    # ISO timestamp — parse-round-trip to validate.
    parsed = datetime.fromisoformat(snap["created_at"])
    assert parsed.tzinfo is not None


def test_steer_tab_run_button_emits_runRequested_with_snapshot(
    tmp_path: Path,
) -> None:
    queue = SteerOverrideQueue()
    queue.add(1, "boost", source="structure")
    tab, _svc, _q, _engine = _build_tab(
        tmp_path, seed_tracks=1, queue=queue
    )
    received: list[dict] = []
    tab.runRequested.connect(received.append)
    # Reference snapshot before the click.
    expected = tab.current_snapshot()
    tab._run_bar._run_btn.click()
    assert len(received) == 1
    got = received[0]
    # All scalar / list fields match exactly.
    for key in ("audio_track_id", "weights_profile", "pins", "boosts", "excludes"):
        assert got[key] == expected[key]
    # created_at must be within a second of expected — timers fire
    # sub-microsecond apart in the same test thread.
    got_ts = datetime.fromisoformat(got["created_at"])
    exp_ts = datetime.fromisoformat(expected["created_at"])
    assert abs((got_ts - exp_ts).total_seconds()) < 1.0


def test_steer_tab_run_button_shows_status_toast(tmp_path: Path) -> None:
    tab, _svc, _q, _engine = _build_tab(tmp_path, seed_tracks=1)
    tab._run_bar._run_btn.click()
    assert tab._run_bar.status_visible()
    assert tab._run_bar.status_text() != ""
    # Simulate the auto-clear by firing the internal status timer.
    tab._status_timer.timeout.emit()
    assert not tab._run_bar.status_visible()
    assert tab._run_bar.status_text() == ""


def test_steer_tab_trackChanged_signal_fires_on_combo_change(
    tmp_path: Path,
) -> None:
    tab, _svc, _q, _engine = _build_tab(tmp_path, seed_tracks=2)
    received: list[int] = []
    tab.trackChanged.connect(received.append)
    # Flip from index 0 (current) to index 1 — the second track.
    expected_id = tab._track_selector._combo.itemData(1)
    tab._track_selector._combo.setCurrentIndex(1)
    assert expected_id in received
    assert received[-1] == expected_id


def test_studio_brain_window_index_3_is_steer_tab(tmp_path: Path) -> None:
    _ensure_qapp()
    _engine, Session = _build_struct_db(tmp_path)
    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    window = StudioBrainWindow.reset_for_test(
        brain_service=svc,
        override_queue=queue,
        backup_service=None,
    )
    assert type(window._tabs.widget(3)).__name__ == "SteerTab"
    assert window._tabs.tabText(3) == "Steer"

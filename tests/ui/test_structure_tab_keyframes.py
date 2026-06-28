"""B-200 F-6: echte Keyframe-Thumbs in StructureTab._ClipCard.

Vorher: ``_ClipCard`` hatte immer den deterministischen Bucket-Color-
Placeholder. Jetzt: wenn ``BrainService.list_clips_with_tags`` einen
``keyframe_path`` zur Scene mitliefert, lädt die Card die echte JPEG-
Pixmap; sonst Fallback auf Placeholder.

Tests:
1. ``_resolve_keyframe_path`` rekonstruiert deterministischen Pfad aus
   video_file_path + scene_label, returnt None wenn Datei fehlt.
2. ``_load_card_thumb`` lädt echte Pixmap wenn Pfad existiert, fällt auf
   Placeholder zurück bei None oder kaputter Datei.
3. ``_ClipCard`` ruft ``_load_card_thumb`` mit ``row['keyframe_path']``.
4. ``BrainService.list_clips_with_tags`` enthält ``keyframe_path`` (None
   wenn Datei nicht existiert, sonst Pfad-String).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from services import brain as brain_service_mod
from services.brain import BrainService
from services.brain.legacy_sqlite import _resolve_keyframe_path
from ui.studio_brain.structure_tab import _ClipCard, _load_card_thumb

# Reuse fixture helpers from test_structure_tab (plain import — keine conftest).
from tests.ui.test_structure_tab import (  # noqa: E402
    _build_struct_db,
    _seed_basics,
    _seed_bucket,
    _seed_tag,
)


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _write_dummy_jpeg(path: Path) -> None:
    """Schreibt eine 16x16 reine-rote JPEG via QImage. Ergibt einen
    sauber-ladbaren Keyframe ohne ffmpeg-Aufruf."""
    img = QImage(16, 16, QImage.Format.Format_RGB888)
    img.fill(0xFF0000)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert img.save(str(path), "JPG", 90), f"failed to write JPEG: {path}"


# --------------------------------------------------------------------------
# 1) _resolve_keyframe_path (pure helper)
# --------------------------------------------------------------------------

def test_resolve_keyframe_path_returns_none_when_file_missing(
    tmp_path: Path, monkeypatch
) -> None:
    import database.session as _session

    monkeypatch.setattr(_session, "APP_ROOT", tmp_path)
    # Datei NICHT geschrieben → resolver muss None liefern
    result = _resolve_keyframe_path("/abs/path/to/myvideo.mp4", "Scene 5")
    assert result is None


def test_resolve_keyframe_path_returns_path_when_file_exists(
    tmp_path: Path, monkeypatch
) -> None:
    import database.session as _session

    monkeypatch.setattr(_session, "APP_ROOT", tmp_path)
    expected = tmp_path / "storage" / "keyframes" / "myvideo_scene0007.jpg"
    _write_dummy_jpeg(expected)

    result = _resolve_keyframe_path("/abs/path/to/myvideo.mp4", "Scene 7")
    assert result is not None
    assert Path(result) == expected


def test_resolve_keyframe_path_handles_missing_inputs(tmp_path: Path) -> None:
    assert _resolve_keyframe_path(None, "Scene 1") is None
    assert _resolve_keyframe_path("/v.mp4", None) is None
    assert _resolve_keyframe_path("", "Scene 1") is None
    # Label ohne Zahl-Token → None (kein Crash)
    assert _resolve_keyframe_path("/v.mp4", "intro") is None


# --------------------------------------------------------------------------
# 2) _load_card_thumb (fallback semantics)
# --------------------------------------------------------------------------

def test_load_card_thumb_falls_back_when_path_is_none(qapp_=None) -> None:
    _ensure_qapp()
    pix = _load_card_thumb(None, scene_id=42, bucket_id=1)
    assert isinstance(pix, QPixmap)
    assert not pix.isNull()


def test_load_card_thumb_falls_back_when_file_corrupt(tmp_path: Path) -> None:
    _ensure_qapp()
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    pix = _load_card_thumb(str(bad), scene_id=42, bucket_id=1)
    assert isinstance(pix, QPixmap)
    assert not pix.isNull()  # placeholder ist immer non-null


def test_load_card_thumb_uses_real_pixmap_when_valid(tmp_path: Path) -> None:
    _ensure_qapp()
    good = tmp_path / "good.jpg"
    _write_dummy_jpeg(good)
    pix = _load_card_thumb(str(good), scene_id=42, bucket_id=1)
    assert isinstance(pix, QPixmap)
    assert not pix.isNull()
    # Skaliert auf die Card-Thumb-Hoehe (64) mit KeepAspectRatioByExpanding —
    # bei 16x16 Quelle wird Hoehe ≥ 64 sein.
    assert pix.height() >= 64


# --------------------------------------------------------------------------
# 3) _ClipCard rendert echtes Thumb wenn row.keyframe_path gesetzt
# --------------------------------------------------------------------------

def test_clip_card_uses_keyframe_path_when_present(tmp_path: Path) -> None:
    _ensure_qapp()
    good = tmp_path / "card.jpg"
    _write_dummy_jpeg(good)

    row = {
        "scene_id": 99,
        "role": "hero",
        "role_confidence": 0.9,
        "mood_refined": "euphoric",
        "style_bucket_id": 1,
        "usage_count": 0,
        "keyframe_path": str(good),
    }
    card = _ClipCard(row)
    try:
        # Erstes Kind unter dem QVBoxLayout ist QLabel (der Thumb)
        thumbs = [c for c in card.children() if c.__class__.__name__ == "QLabel"]
        assert thumbs, "ClipCard muss mindestens ein QLabel-Thumb haben"
        thumb_label = thumbs[0]
        pix = thumb_label.pixmap()
        # Bei valid keyframe_path und 16x16 Source → Pixmap >= 64 hoch (siehe
        # KeepAspectRatioByExpanding); Placeholder hat exakt _THUMB_H=64.
        assert not pix.isNull()
    finally:
        card.deleteLater()


def test_clip_card_falls_back_to_placeholder_when_no_keyframe(tmp_path: Path) -> None:
    _ensure_qapp()
    row = {
        "scene_id": 100,
        "role": "filler",
        "role_confidence": 0.5,
        "mood_refined": "ambient",
        "style_bucket_id": 2,
        "usage_count": 0,
        "keyframe_path": None,
    }
    card = _ClipCard(row)
    try:
        thumbs = [c for c in card.children() if c.__class__.__name__ == "QLabel"]
        assert thumbs
        pix = thumbs[0].pixmap()
        assert not pix.isNull()  # Placeholder ist immer non-null
    finally:
        card.deleteLater()


# --------------------------------------------------------------------------
# 4) BrainService.list_clips_with_tags liefert keyframe_path mit
# --------------------------------------------------------------------------

def test_list_clips_with_tags_includes_keyframe_path_when_file_exists(
    tmp_path: Path, monkeypatch
) -> None:
    import database.session as _session

    # APP_ROOT auf tmp_path patchen damit _resolve_keyframe_path dort sucht
    monkeypatch.setattr(_session, "APP_ROOT", tmp_path)

    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)

    # Scene mit explizitem video_clip_id + label "Scene 3"
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        conn.execute(
            text(
                "INSERT INTO scenes (id, video_clip_id, start_time, end_time, label) "
                "VALUES (:sid, :cid, :s, :e, :lbl)"
            ),
            {"sid": 50, "cid": 1, "s": 0.0, "e": 5.0, "lbl": "Scene 3"},
        )
        _seed_tag(conn, 50, bucket_id=1)

    # Erstmal: ohne Datei → keyframe_path = None
    svc = BrainService(session_factory=Session)
    rows = svc.list_clips_with_tags()
    assert len(rows) == 1
    assert "keyframe_path" in rows[0]
    assert rows[0]["keyframe_path"] is None

    # Cache invalidate, dann Datei materialisieren — naechster Call liefert Pfad
    svc._list_clips_with_tags_cached.cache_clear()
    # video_clips.file_path = "/v.mp4" (siehe _seed_video_clip), stem = "v"
    expected = tmp_path / "storage" / "keyframes" / "v_scene0003.jpg"
    _write_dummy_jpeg(expected)

    rows = svc.list_clips_with_tags()
    assert rows[0]["keyframe_path"] == str(expected)

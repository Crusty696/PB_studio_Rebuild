"""M1 Timeline-Virtualisierung (D-066): Guards fuer die Record-Schicht.

Invarianten:
- Build erzeugt leichte ClipRecords, KEINE Video-Items (Audio sofort, da
  permanent sichtbar + Waveform-Parent).
- _update_virtualization materialisiert nur Viewport ± Puffer und
  entmaterialisiert ausserhalb der Hysterese (Item-Count << Record-Count).
- Undo-/Lock-/Trim-Syncs sind record-first: wirken auch auf
  entmaterialisierte Clips; Re-Materialisierung stellt den Zustand
  identisch wieder her.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _make_timeline():
    from ui.timeline import InteractiveTimeline
    tl = InteractiveTimeline()
    tl._brain_v3_timeline_meta = {}
    tl._anchor_map = {}
    return tl


def _video_entries(n: int, spacing_s: float = 10.0, dur_s: float = 5.0):
    entries = []
    video_map = {}
    for i in range(n):
        entries.append(SimpleNamespace(
            id=1000 + i, media_id=100 + i, track="video",
            start_time=i * spacing_s, end_time=i * spacing_s + dur_s,
            locked=False,
        ))
        video_map[100 + i] = SimpleNamespace(
            id=100 + i, file_path=f"/tmp/v{i}.mp4", duration=dur_s,
        )
    return entries, video_map


def test_build_creates_records_not_video_items():
    _qapp()
    tl = _make_timeline()
    try:
        entries, video_map = _video_entries(40)
        tl._build_entries(entries, {}, video_map, {})
        assert len(tl.clip_records) == 40
        assert tl.clip_items == []  # Video-Items entstehen erst viewport-getrieben
        assert all(r.item is None for r in tl.clip_records)
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_update_virtualization_materializes_window_only():
    _qapp()
    from ui.timeline import PIXELS_PER_SECOND
    tl = _make_timeline()
    try:
        entries, video_map = _video_entries(40)
        tl._build_entries(entries, {}, video_map, {})

        view = QRectF(0.0, 0.0, 300.0, 200.0)
        tl._update_virtualization(view)

        span = max(200.0, view.width())
        keep_right = view.right() + tl._virt_keep_screens * span
        expected = [r for r in tl.clip_records if r.x < keep_right]
        assert 0 < len(expected) < 40
        assert len(tl.clip_items) == len(expected)
        for rec in tl.clip_records:
            if rec in expected:
                assert rec.item is not None
            else:
                assert rec.item is None
        # Idempotent: zweiter Lauf mit gleichem Fenster aendert nichts.
        tl._update_virtualization(QRectF(view))
        assert len(tl.clip_items) == len(expected)
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_dematerialize_outside_hysteresis_and_state_roundtrip():
    _qapp()
    tl = _make_timeline()
    try:
        entries, video_map = _video_entries(40)
        tl._build_entries(entries, {}, video_map, {})

        near = QRectF(0.0, 0.0, 300.0, 200.0)
        tl._update_virtualization(near)
        assert len(tl.clip_items) > 0
        first = tl.clip_records[0]
        assert first.item is not None

        # Lock am materialisierten Item setzen -> muss den Roundtrip ueberleben.
        tl._sync_clip_lock_visual(first.entry_id, True)
        assert first.item.is_locked()

        # Fenster weit nach rechts -> linke Items fallen aus der Hysterese.
        far = QRectF(1_000_000.0, 0.0, 300.0, 200.0)
        tl._update_virtualization(far)
        assert first.item is None  # entmaterialisiert
        assert first.locked is True  # Zustand in den Record gespiegelt

        # Zurueck -> Re-Materialisierung stellt Lock identisch wieder her.
        tl._update_virtualization(near)
        assert first.item is not None
        assert first.item.is_locked()
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_record_first_syncs_apply_without_item():
    _qapp()
    from ui.timeline import PIXELS_PER_SECOND
    tl = _make_timeline()
    try:
        entries, video_map = _video_entries(5)
        tl._build_entries(entries, {}, video_map, {})
        rec = tl.clip_records[3]
        assert rec.item is None

        # Undo-/Trim-Sync auf entmaterialisiertem Clip: landet im Record.
        tl._sync_clip_position(rec.entry_id, 99.0)
        assert rec.x == 99.0 * PIXELS_PER_SECOND
        tl._sync_clip_after_trim(rec.entry_id, 99.0, 101.5)
        assert rec.width == 2.5 * PIXELS_PER_SECOND
        tl._sync_clip_lock_visual(rec.entry_id, True)
        assert rec.locked is True

        # Materialisierung uebernimmt den Record-Zustand 1:1.
        item = tl._materialize_record(rec)
        assert item.pos().x() == 99.0 * PIXELS_PER_SECOND
        assert item._clip_width == 2.5 * PIXELS_PER_SECOND
        assert item.is_locked()

        # _remove_clip_item raeumt Record UND Item ab.
        tl._remove_clip_item(rec.entry_id)
        assert tl._find_clip_record(rec.entry_id) is None
        assert tl._find_clip_item(rec.entry_id) is None
        assert rec not in tl.clip_records
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_cut_points_use_single_item_not_per_cut_lines():
    """M1.3: set_cut_points erzeugt KEINE QGraphicsLineItems pro Cut mehr —
    alle Cuts leben als Daten im einen CutLinesItem (exposedRect-Culling)."""
    _qapp()
    tl = _make_timeline()
    try:
        cuts = [SimpleNamespace(time=float(i), source="beat", strength=1.0)
                for i in range(500)]
        tl.set_cut_points(cuts, total_duration=500.0)
        assert tl.cut_lines == []  # keine Einzel-Items
        assert len(tl._cut_lines_item._cuts) == 500
        assert not tl._cut_lines_item.boundingRect().isEmpty()

        # Signature-No-op (B-598) bleibt erhalten.
        tl.set_cut_points(cuts, total_duration=500.0)
        assert len(tl._cut_lines_item._cuts) == 500

        # Paint-Smoke mit kleinem exposedRect (Culling-Pfad).
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem
        img = QImage(200, 100, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        opt = QStyleOptionGraphicsItem()
        opt.exposedRect = QRectF(0.0, 0.0, 200.0, 100.0)
        tl._cut_lines_item.paint(p, opt, None)
        p.end()
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_beat_markers_use_single_item_not_per_beat_lines():
    """M1.3: set_beat_markers erzeugt KEINE QGraphicsLineItems pro Beat mehr."""
    _qapp()
    tl = _make_timeline()
    try:
        beats = [i * 0.5 for i in range(2000)]
        tl.set_beat_markers(beats)
        assert tl._beat_markers == []  # keine Einzel-Items
        assert len(tl._beat_markers_item._beat_times) == 2000
        assert tl._beat_times  # Snap-Datenbasis weiterhin gesetzt
        assert not tl._beat_markers_item.boundingRect().isEmpty()

        # Teardown-Aequivalent: Daten leeren.
        tl._beat_markers_item.set_data([])
        assert tl._beat_markers_item.boundingRect().isEmpty()
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_m2_large_materialization_runs_in_qtimer_batches():
    """M2 Show-Entkopplung: > _VIRT_MAT_BATCH Records werden nicht in einem
    Rutsch materialisiert — erster Batch sofort, Rest via QTimer(0)-Kette
    (progressiv, Event-Loop kommt zwischendurch dran)."""
    app = _qapp()
    tl = _make_timeline()
    try:
        entries, video_map = _video_entries(400, spacing_s=1.0, dur_s=0.5)
        tl._build_entries(entries, {}, video_map, {})

        # Fenster, das ALLE 400 Clips einschliesst (wie fit_to_content).
        wide = QRectF(0.0, 0.0, 500.0 * 25.0, 200.0)
        tl._update_virtualization(wide)

        # M4-Haertung: Sync-Pass ist stueckzahl- UND zeitbudget-begrenzt —
        # exakte Anzahl haengt von der Maschinenlast ab. Invariante: nicht
        # alles sofort, Rest liegt vollstaendig in der Queue.
        assert 0 < len(tl.clip_items) <= tl._VIRT_MAT_BATCH
        assert len(tl._virt_mat_queue) == 400 - len(tl.clip_items)

        # QTimer(0)-Kette abarbeiten lassen.
        for _ in range(20):
            app.processEvents()
            if not tl._virt_mat_queue:
                break
        assert tl._virt_mat_queue == []
        assert len(tl.clip_items) == 400
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_m2_hidden_timeline_materializes_nothing():
    """M2 Show-Entkopplung: eine versteckte Timeline baut ueber den
    Polling-Anker (_request_visible_thumbnails) keine Items — erst nach
    show() fuellt sich die Scene."""
    app = _qapp()
    tl = _make_timeline()
    tl.resize(900, 220)
    try:
        entries, video_map = _video_entries(10, spacing_s=1.0, dur_s=0.5)
        tl._build_entries(entries, {}, video_map, {})

        assert not tl.isVisible()
        tl._request_visible_thumbnails()
        assert tl.clip_items == []  # versteckt -> nichts materialisiert

        tl.show()
        app.processEvents()
        tl._request_visible_thumbnails()
        for _ in range(20):
            app.processEvents()
            if not tl._virt_mat_queue:
                break
        assert len(tl.clip_items) > 0  # sichtbar -> Fenster materialisiert
    finally:
        tl.deleteLater()
        _qapp().processEvents()


def test_audio_clip_stays_materialized():
    _qapp()
    tl = _make_timeline()
    try:
        audio_entry = SimpleNamespace(
            id=1, media_id=7, track="audio",
            start_time=0.0, end_time=60.0, locked=False,
        )
        audio_map = {7: SimpleNamespace(
            id=7, title="master", duration=60.0,
            waveform_data=None, beatgrid=None,
        )}
        tl._build_entries([audio_entry], audio_map, {}, {})
        rec = tl.clip_records[0]
        assert rec.item is not None  # Audio sofort materialisiert

        far = QRectF(1_000_000.0, 0.0, 300.0, 200.0)
        tl._update_virtualization(far)
        assert rec.item is not None  # Audio wird NIE entmaterialisiert
    finally:
        tl.deleteLater()
        _qapp().processEvents()

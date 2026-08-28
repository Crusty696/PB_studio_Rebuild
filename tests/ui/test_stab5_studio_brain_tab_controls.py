"""STAB-5 Controls #82-#106: Studio-Brain-Tab-Controls elementgenau belegen.

Offscreen-Qt + tmp-SQLite (Alembic head) wie tests/ui/test_stab5_gpu_recovery_controls.py
+ tests/ui/test_audit_tab.py.

Mapping-Hinweis (verifiziert gegen git show 4bea226^):
Die Inventar-Zeilennummern fuer steer_tab.py / structure_tab.py stammen aus dem
Stand VOR der Brain-Bereinigung 2026-08-27 (Commit 4bea226).
  - #90 (_ProfilePicker._combo), #91 ("Profil bearbeiten"), #92 (+ Pin),
    #93 (Pin entfernen): entfernt -> nicht testbar (Widgets existieren nicht mehr).
  - #97/#98 (QActions in _ClipCard._build_context_menu): entfernt (tote
    Doppel-Implementierung); produktive Entsprechung sind #105/#106
    (StructureTab._build_override_menu).
Ein Dokumentations-Test unten belegt die Abwesenheit.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QPushButton,
    QWidget,
)

from services.backup_service import BackupService
from services.brain import BrainService
from services.steer_override_queue import SteerOverrideQueue
from tests.ui.test_audit_tab import (
    _seed_audio_track as _seed_audit_audio_track,
    _seed_decision as _seed_audit_decision,
    _seed_run as _seed_audit_run,
    _seed_scene as _seed_audit_scene,
    _seed_video_clip as _seed_audit_video_clip,
)
from tests.ui.test_memory_tab import _seed_pattern
from tests.ui.test_steer_tab import (
    _add_audio_track_bpm_and_duration,
    _seed_audio_track as _seed_steer_track,
)
from tests.ui.test_structure_tab import (
    _build_struct_db,
    _seed_basics,
    _seed_bucket,
    _seed_five_scenes,
    _seed_scene,
    _seed_tag,
)
from ui.studio_brain.audit_tab import AuditTab
from ui.studio_brain.memory_tab import MemoryTab
from ui.studio_brain.steer_tab import SteerTab, _RUN_BUTTON_TOAST
from ui.studio_brain.structure_tab import StructureTab, _ClipCard


# ── Helpers ───────────────────────────────────────────────────────────────────


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _cleanup(app: QApplication, *widgets: QWidget) -> None:
    for w in widgets:
        try:
            w.close()
            w.deleteLater()
        except Exception:
            pass
    app.processEvents()


def _single_button(root: QWidget, text_: str) -> QPushButton:
    buttons = [b for b in root.findChildren(QPushButton) if b.text() == text_]
    assert len(buttons) == 1
    btn = buttons[0]
    assert btn.isVisibleTo(root) is True
    return btn


def _single_checkbox(root: QWidget, text_: str) -> QCheckBox:
    boxes = [c for c in root.findChildren(QCheckBox) if c.text() == text_]
    assert len(boxes) == 1
    box = boxes[0]
    assert box.isVisibleTo(root) is True
    assert box.isEnabled() is True
    return box


def _combo_index_for(combo: QComboBox, data) -> int:
    for i in range(combo.count()):
        if combo.itemData(i) == data:
            return i
    raise AssertionError(f"itemData {data!r} not in combo")


def _backup_service(tmp_path: Path) -> BackupService:
    return BackupService(
        db_path=tmp_path / "struct.db", backup_dir=tmp_path / "backups"
    )


# ── AuditTab #82-#85 ──────────────────────────────────────────────────────────


def test_control_82_audit_run_combo_switch_reloads_cut_table(
    tmp_path: Path,
) -> None:
    """#82 audit_tab.py:148 _RunSelector._combo: Index-Wechsel -> runChanged
    -> _on_run_changed -> _current_run_id + Cut-Table neu geladen."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audit_audio_track(conn, 1)
        _seed_audit_video_clip(conn, 1)
        for sid in range(1, 6):
            _seed_audit_scene(conn, sid)
        _seed_audit_run(
            conn, 1,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=1),
        )
        _seed_audit_run(
            conn, 2,
            started_at=now - timedelta(minutes=30),
            completed_at=now - timedelta(minutes=10),
        )
        # Run 1: 2 Cuts. Run 2: 3 Cuts.
        _seed_audit_decision(conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0)
        _seed_audit_decision(conn, decision_id=2, run_id=1, scene_id=2, sequence_idx=1)
        for i, did in enumerate((3, 4, 5)):
            _seed_audit_decision(
                conn, decision_id=did, run_id=2, scene_id=i + 3, sequence_idx=i
            )

    tab = AuditTab(brain_service=BrainService(session_factory=Session))
    try:
        combos = tab._run_selector.findChildren(QComboBox)
        assert len(combos) == 1
        combo = combos[0]
        assert combo is tab._run_selector._combo
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True
        # Initial: neuester abgeschlossener Run (id 2) -> 3 Zeilen.
        assert tab._current_run_id == 2
        assert tab._cut_table.row_count() == 3

        combo.setCurrentIndex(_combo_index_for(combo, 1))
        app.processEvents()

        assert tab._current_run_id == 1
        assert tab._cut_table.row_count() == 2
    finally:
        _cleanup(app, tab)


def test_control_83_rejected_checkbox_filters_cut_table(tmp_path: Path) -> None:
    """#83 audit_tab.py:352 'Nur abgelehnte': Klick -> filterChanged ->
    _reload_cuts mit rejected_only."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audit_audio_track(conn, 1)
        _seed_audit_video_clip(conn, 1)
        for sid in range(1, 5):
            _seed_audit_scene(conn, sid)
        _seed_audit_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_audit_decision(conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0)
        _seed_audit_decision(
            conn, decision_id=2, run_id=1, scene_id=2, sequence_idx=1,
            user_verdict="reject",
        )
        _seed_audit_decision(conn, decision_id=3, run_id=1, scene_id=3, sequence_idx=2)
        _seed_audit_decision(
            conn, decision_id=4, run_id=1, scene_id=4, sequence_idx=3,
            user_verdict="reject",
        )

    tab = AuditTab(brain_service=BrainService(session_factory=Session))
    try:
        tab.show()
        app.processEvents()
        assert tab._cut_table.row_count() == 4

        chk = _single_checkbox(tab._cut_table, "Nur abgelehnte")
        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert chk.isChecked() is True
        assert tab._cut_table.current_filter()["rejected_only"] is True
        assert tab._cut_table.row_count() == 2

        # Zurueckschalten -> alle 4 wieder da.
        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert tab._cut_table.row_count() == 4
    finally:
        _cleanup(app, tab)


def test_control_84_fallback_checkbox_filters_cut_table(tmp_path: Path) -> None:
    """#84 audit_tab.py:360 'Nur Fallback': Klick -> nur Fallback-Cuts."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audit_audio_track(conn, 1)
        _seed_audit_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_audit_scene(conn, sid)
        _seed_audit_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_audit_decision(
            conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0,
            rationale={"fallback": True, "contribs": {"w_role": 0.1}},
        )
        _seed_audit_decision(
            conn, decision_id=2, run_id=1, scene_id=2, sequence_idx=1,
            rationale={"contribs": {"w_role": 0.2}},
        )
        _seed_audit_decision(
            conn, decision_id=3, run_id=1, scene_id=3, sequence_idx=2,
            rationale={"contribs": {"w_role": 0.3}},
        )

    tab = AuditTab(brain_service=BrainService(session_factory=Session))
    try:
        tab.show()
        app.processEvents()
        assert tab._cut_table.row_count() == 3

        chk = _single_checkbox(tab._cut_table, "Nur Fallback")
        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert chk.isChecked() is True
        assert tab._cut_table.current_filter()["fallback_only"] is True
        assert tab._cut_table.row_count() == 1
    finally:
        _cleanup(app, tab)


def test_control_85_story_map_button_invokes_async_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#85 audit_tab.py:760 'Story Map öffnen…': Klick -> _on_story_map_clicked
    -> open_story_map_async(svc, run_id, parent=tab).

    open_story_map_async startet real einen QThreadPool-Job (B-765) — deshalb
    an der Modulgrenze ui.story_map_dialog gemockt; belegt wird die
    Handler-Wirkung (korrekter Aufruf mit selektiertem Run)."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audit_audio_track(conn, 1)
        _seed_audit_run(conn, 1, completed_at=datetime.now(timezone.utc))

    svc = BrainService(session_factory=Session)

    calls: list[tuple] = []
    import ui.story_map_dialog as story_map_dialog

    monkeypatch.setattr(
        story_map_dialog,
        "open_story_map_async",
        lambda svc_, run_id, parent=None, on_ready=None: calls.append(
            (svc_, run_id, parent)
        ),
    )

    tab = AuditTab(brain_service=svc)
    try:
        btn = _single_button(tab, "Story Map öffnen…")
        assert btn.isEnabled() is True
        tab.show()
        app.processEvents()

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert calls == [(svc, 1, tab)]
    finally:
        _cleanup(app, tab)


# ── MemoryTab #86-#88 ─────────────────────────────────────────────────────────


def test_control_86_memory_type_combo_populates_and_sets_filter(
    tmp_path: Path,
) -> None:
    """#86 memory_tab.py:397 _type_combo: aus DB befuellt; Index-Wechsel setzt
    current_filter()['pattern_type'].

    Bewusst dokumentiert: die Combo hat KEINEN Change-Handler — Neuladen
    passiert erst ueber 'Anwenden' (#87, Apply-Design)."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, pattern_type="harmonic", confidence=0.5)
        _seed_pattern(conn, pattern_id=2, pattern_type="style", confidence=0.6)

    tab = MemoryTab(
        brain_service=BrainService(session_factory=Session),
        backup_service=_backup_service(tmp_path),
    )
    try:
        combos = tab._pattern_table.findChildren(QComboBox)
        assert len(combos) == 1
        combo = combos[0]
        assert combo is tab._pattern_table._type_combo
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True
        assert [combo.itemText(i) for i in range(combo.count())] == [
            "(any)", "harmonic", "style",
        ]

        combo.setCurrentIndex(_combo_index_for(combo, "harmonic"))
        app.processEvents()

        assert tab._pattern_table.current_filter()["pattern_type"] == "harmonic"
        # Apply-Design: ohne 'Anwenden' bleiben beide Zeilen sichtbar.
        assert tab._pattern_table.row_count() == 2
    finally:
        _cleanup(app, tab)


def test_control_87_memory_apply_button_reloads_pattern_table(
    tmp_path: Path,
) -> None:
    """#87 memory_tab.py:420 'Anwenden': Klick -> applyRequested ->
    _on_filter_apply -> invalidate + Reload mit Typ-Filter."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, pattern_type="harmonic", confidence=0.5)
        _seed_pattern(conn, pattern_id=2, pattern_type="style", confidence=0.6)

    tab = MemoryTab(
        brain_service=BrainService(session_factory=Session),
        backup_service=_backup_service(tmp_path),
    )
    try:
        assert tab._pattern_table.row_count() == 2
        combo = tab._pattern_table._type_combo
        combo.setCurrentIndex(_combo_index_for(combo, "harmonic"))

        btn = _single_button(tab, "Anwenden")
        assert btn.isEnabled() is True
        tab.show()
        app.processEvents()

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert tab._pattern_table.row_count() == 1
    finally:
        _cleanup(app, tab)


def test_control_88_memory_reset_button_decline_path_no_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#88 memory_tab.py:658 'Gelerntes zurücksetzen…': Klick erreicht
    _on_reset_clicked (QMessageBox.question), Decline -> kein Delete, kein
    Signal, kein Backup.

    Nur der synchrone Decline-Pfad: der Accept-Pfad laeuft ueber
    QThreadPool + Full-DB-Backup (B-641) und ist bereits real abgedeckt in
    tests/ui/test_memory_tab.py::test_memory_tab_reset_creates_backup_and_deletes
    (waitForDone-Muster). Echte Threads hier bewusst vermieden."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, confidence=0.5)

    question_calls: list[tuple] = []

    def _fake_question(*args, **kwargs):
        question_calls.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", _fake_question)

    tab = MemoryTab(
        brain_service=BrainService(session_factory=Session),
        backup_service=_backup_service(tmp_path),
    )
    try:
        received: list[int] = []
        tab.patternsReset.connect(received.append)

        btn = _single_button(tab, "Gelerntes zurücksetzen…")
        assert btn.isEnabled() is True
        tab.show()
        app.processEvents()

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(question_calls) == 1  # Handler erreicht
        with engine.begin() as conn:
            remaining = conn.execute(
                text("SELECT COUNT(*) FROM mem_learned_pattern")
            ).scalar()
        assert remaining == 1  # nichts geloescht
        assert received == []
        assert btn.isEnabled() is True  # nicht gesperrt (kein Reset gestartet)
    finally:
        _cleanup(app, tab)


# ── SteerTab #89, #94-#96 ─────────────────────────────────────────────────────


def _build_steer(tmp_path: Path, *, tracks: int, queue: SteerOverrideQueue):
    engine, Session = _build_struct_db(tmp_path)
    _add_audio_track_bpm_and_duration(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for i in range(1, tracks + 1):
            _seed_steer_track(
                conn,
                track_id=i,
                file_path=f"/mixes/track_{i:02d}.mp3",
                created_at=now - timedelta(minutes=tracks - i),
                bpm=124.0 + i,
                duration=180.0,
            )
    svc = BrainService(session_factory=Session)
    return SteerTab(brain_service=svc, override_queue=queue)


def test_control_89_steer_track_combo_emits_trackChanged_and_updates_snapshot(
    tmp_path: Path,
) -> None:
    """#89 steer_tab.py:144 (Inventar :164 alt) _TrackSelector._combo:
    Index-Wechsel -> trackChanged + Snapshot-Track-Id + Run-Button-Zustand."""
    app = _qapp()
    tab = _build_steer(tmp_path, tracks=2, queue=SteerOverrideQueue())
    try:
        combos = tab._track_selector.findChildren(QComboBox)
        assert len(combos) == 1
        combo = combos[0]
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True

        received: list[int] = []
        tab.trackChanged.connect(received.append)

        expected_id = combo.itemData(1)
        combo.setCurrentIndex(1)
        app.processEvents()

        assert received[-1] == expected_id
        assert tab.current_snapshot()["audio_track_id"] == expected_id
        assert tab._run_bar.is_run_enabled() is True
    finally:
        _cleanup(app, tab)


def test_control_94_boost_remove_button_drops_queue_entry(
    tmp_path: Path,
) -> None:
    """#94 steer_tab.py:255 (Inventar :423 alt) _boost_remove_btn: Klick ->
    boostRemoveRequested -> queue.remove(scene_id)."""
    app = _qapp()
    queue = SteerOverrideQueue()
    queue.add(5, "boost", source="structure")
    tab = _build_steer(tmp_path, tracks=1, queue=queue)
    try:
        remove_buttons = [
            b for b in tab._overrides.findChildren(QPushButton)
            if b.text() == "− Entfernen"
        ]
        assert len(remove_buttons) == 2  # Boost + Exclude Spalte
        btn = tab._overrides._boost_remove_btn
        assert btn in remove_buttons
        assert btn.isVisibleTo(tab) is True
        assert btn.isEnabled() is True

        assert tab._overrides.boost_count() == 1
        tab.show()
        app.processEvents()
        tab._overrides.select_first_boost()

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert {e.scene_id for e in queue.list()} == set()
        assert tab._overrides.boost_count() == 0
    finally:
        _cleanup(app, tab)


def test_control_95_exclude_remove_button_drops_queue_entry(
    tmp_path: Path,
) -> None:
    """#95 steer_tab.py:286 (Inventar :454 alt) _exclude_remove_btn."""
    app = _qapp()
    queue = SteerOverrideQueue()
    queue.add(21, "exclude", source="graph")
    tab = _build_steer(tmp_path, tracks=1, queue=queue)
    try:
        btn = tab._overrides._exclude_remove_btn
        assert btn.text() == "− Entfernen"
        assert btn.isVisibleTo(tab) is True
        assert btn.isEnabled() is True

        assert tab._overrides.exclude_count() == 1
        tab.show()
        app.processEvents()
        tab._overrides.select_first_exclude()

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert {e.scene_id for e in queue.list()} == set()
        assert tab._overrides.exclude_count() == 0
    finally:
        _cleanup(app, tab)


def test_control_96_run_button_emits_snapshot_and_toast(tmp_path: Path) -> None:
    """#96 steer_tab.py:370 (Inventar :586 alt) 'Mit diesen Einstellungen
    starten': Klick -> runRequested(snapshot) + Status-Toast."""
    app = _qapp()
    queue = SteerOverrideQueue()
    queue.add(7, "boost", source="structure")
    queue.add(8, "exclude", source="graph")
    tab = _build_steer(tmp_path, tracks=1, queue=queue)
    try:
        btn = _single_button(tab, "Mit diesen Einstellungen starten")
        assert btn.isEnabled() is True  # Track selektiert -> enabled

        received: list[dict] = []
        tab.runRequested.connect(received.append)
        tab.show()
        app.processEvents()

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(received) == 1
        snap = received[0]
        assert snap["audio_track_id"] == 1
        assert snap["boosts"] == [7]
        assert snap["excludes"] == [8]
        assert tab._run_bar.status_visible() is True
        assert tab._run_bar.status_text() == _RUN_BUTTON_TOAST
    finally:
        _cleanup(app, tab)


# ── StructureTab #99-#106 ─────────────────────────────────────────────────────


def _seed_graph_minimal(engine) -> None:
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in (90, 91, 92):
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)
        conn.execute(
            text(
                "INSERT INTO struct_compat_edge "
                "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
                "VALUES (90, 91, 0.7, 0)"
            )
        )


def _filter_bar_combos(tab: StructureTab) -> list[QComboBox]:
    combos = tab._filter_bar.findChildren(QComboBox)
    assert len(combos) == 4  # Ansicht / Rolle / Stimmung / Stil
    return combos


def test_control_99_view_mode_combo_swaps_stack(tmp_path: Path) -> None:
    """#99 structure_tab.py:281 (Inventar :294 alt) _mode_combo: Wechsel auf
    Graph -> Stack-Index 1 (echtes render_graph), zurueck -> 0."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_graph_minimal(engine)

    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=SteerOverrideQueue(),
    )
    try:
        _filter_bar_combos(tab)
        combo = tab._filter_bar._mode_combo
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True
        assert tab._stack.currentIndex() == 0

        combo.setCurrentIndex(_combo_index_for(combo, "Graph"))
        app.processEvents()
        assert tab.current_view_mode() == "Graph"
        assert tab._stack.currentIndex() == 1

        combo.setCurrentIndex(_combo_index_for(combo, "Grid"))
        app.processEvents()
        assert tab._stack.currentIndex() == 0
    finally:
        _cleanup(app, tab)


def test_control_100_role_combo_filters_grid_after_debounce(
    tmp_path: Path,
) -> None:
    """#100 structure_tab.py:294 (Inventar :307 alt) _role_combo:
    Index-Wechsel -> Debounce (150ms) -> filtersChanged -> refresh."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_five_scenes(engine)  # 3x hero (Bucket 1) + 2x filler (Bucket 2)

    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=SteerOverrideQueue(),
    )
    try:
        assert len(tab.current_cards()) == 5
        combo = tab._filter_bar._role_combo
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(_combo_index_for(combo, "hero"))
        assert tab._filter_bar._debounce.isActive() is True  # Handler verdrahtet
        QTest.qWait(400)  # Debounce feuern lassen

        cards = tab.current_cards()
        assert len(cards) == 3
        assert all(c["role"] == "hero" for c in cards)
    finally:
        _cleanup(app, tab)


def test_control_101_mood_combo_filters_grid_after_debounce(
    tmp_path: Path,
) -> None:
    """#101 structure_tab.py:309 (Inventar :322 alt) _mood_combo."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 200)
        _seed_scene(conn, 201)
        _seed_scene(conn, 202)
        _seed_tag(conn, 200, mood="euphoric", bucket_id=1)
        _seed_tag(conn, 201, mood="euphoric", bucket_id=1)
        _seed_tag(conn, 202, mood="brooding", bucket_id=1)

    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=SteerOverrideQueue(),
    )
    try:
        assert len(tab.current_cards()) == 3
        combo = tab._filter_bar._mood_combo
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(_combo_index_for(combo, "brooding"))
        assert tab._filter_bar._debounce.isActive() is True
        QTest.qWait(400)

        cards = tab.current_cards()
        assert len(cards) == 1
        assert cards[0]["scene_id"] == 202
    finally:
        _cleanup(app, tab)


def test_control_102_style_combo_filters_grid_after_debounce(
    tmp_path: Path,
) -> None:
    """#102 structure_tab.py:323 (Inventar :336 alt) _style_combo."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_five_scenes(engine)  # Bucket 1: 3 Szenen, Bucket 2: 2 Szenen

    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=SteerOverrideQueue(),
    )
    try:
        assert len(tab.current_cards()) == 5
        combo = tab._filter_bar._style_combo
        assert combo.isVisibleTo(tab) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(_combo_index_for(combo, 2))
        assert tab._filter_bar._debounce.isActive() is True
        QTest.qWait(400)

        cards = tab.current_cards()
        assert len(cards) == 2
        assert all(c["style_bucket_id"] == 2 for c in cards)
    finally:
        _cleanup(app, tab)


def test_control_103_inspector_boost_button_queues_override(
    tmp_path: Path,
) -> None:
    """#103 structure_tab.py:691 (Inventar :704 alt) '⤴ Boost im nächsten
    Lauf': Karten-Klick armiert, Button-Klick -> Queue-Entry
    (scene, boost, source='inspector')."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 77)
        _seed_tag(conn, 77, bucket_id=1)

    queue = SteerOverrideQueue()
    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=queue,
    )
    try:
        btn = _single_button(tab, "⤴ Boost im nächsten Lauf")
        assert btn.isEnabled() is False  # ohne Selektion gesperrt

        tab.show()
        app.processEvents()
        cards = tab.findChildren(_ClipCard)
        assert len(cards) == 1
        QTest.mouseClick(cards[0], Qt.MouseButton.LeftButton)
        app.processEvents()

        assert btn.isEnabled() is True
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        entries = queue.list()
        assert len(entries) == 1
        assert (entries[0].scene_id, entries[0].action, entries[0].source) == (
            77, "boost", "inspector",
        )
    finally:
        _cleanup(app, tab)


def test_control_104_inspector_exclude_button_queues_override(
    tmp_path: Path,
) -> None:
    """#104 structure_tab.py:701 (Inventar :714 alt) '⊗ Ausschließen im
    nächsten Lauf'."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 78)
        _seed_tag(conn, 78, bucket_id=1)

    queue = SteerOverrideQueue()
    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=queue,
    )
    try:
        btn = _single_button(tab, "⊗ Ausschließen im nächsten Lauf")
        assert btn.isEnabled() is False

        tab.show()
        app.processEvents()
        cards = tab.findChildren(_ClipCard)
        assert len(cards) == 1
        QTest.mouseClick(cards[0], Qt.MouseButton.LeftButton)
        app.processEvents()

        assert btn.isEnabled() is True
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        entries = queue.list()
        assert len(entries) == 1
        assert (entries[0].scene_id, entries[0].action, entries[0].source) == (
            78, "exclude", "inspector",
        )
    finally:
        _cleanup(app, tab)


def test_control_105_context_menu_boost_action_queues_override(
    tmp_path: Path,
) -> None:
    """#105 structure_tab.py:880 (Inventar :893 alt) QAction 'Boost im
    nächsten Lauf' in _build_override_menu: trigger() -> Queue-Entry mit
    source='structure'. (Blocking QMenu.exec bewusst umgangen — der
    Menu-Builder ist dafuer explizit ausgekoppelt.)"""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)

    queue = SteerOverrideQueue()
    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=queue,
    )
    try:
        menu = tab._build_override_menu(101, source="structure")
        actions = menu.actions()
        assert [a.text() for a in actions] == [
            "Boost im nächsten Lauf",
            "Exclude im nächsten Lauf",
        ]
        boost_action = actions[0]
        assert boost_action.isEnabled() is True
        assert boost_action.isVisible() is True

        boost_action.trigger()
        app.processEvents()

        entries = queue.list()
        assert len(entries) == 1
        assert (entries[0].scene_id, entries[0].action, entries[0].source) == (
            101, "boost", "structure",
        )
    finally:
        _cleanup(app, tab)


def test_control_106_context_menu_exclude_action_queues_override(
    tmp_path: Path,
) -> None:
    """#106 structure_tab.py:887 (Inventar :900 alt) QAction 'Exclude im
    nächsten Lauf' — hier ueber den Graph-Pfad (source='graph')."""
    app = _qapp()
    engine, Session = _build_struct_db(tmp_path)

    queue = SteerOverrideQueue()
    tab = StructureTab(
        brain_service=BrainService(session_factory=Session),
        override_queue=queue,
    )
    try:
        menu = tab._build_override_menu(102, source="graph")
        actions = menu.actions()
        assert len(actions) == 2
        exclude_action = actions[1]
        assert exclude_action.text() == "Exclude im nächsten Lauf"
        assert exclude_action.isEnabled() is True
        assert exclude_action.isVisible() is True

        exclude_action.trigger()
        app.processEvents()

        entries = queue.list()
        assert len(entries) == 1
        assert (entries[0].scene_id, entries[0].action, entries[0].source) == (
            102, "exclude", "graph",
        )
    finally:
        _cleanup(app, tab)


# ── Dokumentation: entfernte Inventar-Controls ────────────────────────────────


def test_controls_90_to_93_and_97_98_removed_in_brain_cleanup(
    tmp_path: Path,
) -> None:
    """#90-#93 (Profil-Picker + Pins, SteerTab) und #97/#98 (QActions in
    _ClipCard._build_context_menu) wurden in Commit 4bea226 (Brain-Bereinigung
    2026-08-27, User-Scope 'Nur Totes + Inaktives') entfernt. Dieser Test
    dokumentiert die Abwesenheit, damit das STAB-5-Inventar abgleichbar ist."""
    app = _qapp()
    tab = _build_steer(tmp_path, tracks=1, queue=SteerOverrideQueue())
    try:
        button_texts = {b.text() for b in tab.findChildren(QPushButton)}
        assert "Profil bearbeiten" not in button_texts        # ex-#91
        assert "+ Pin hinzufügen" not in button_texts         # ex-#92
        # ex-#90: einzige verbleibende Combo ist der Track-Selector.
        assert len(tab.findChildren(QComboBox)) == 1
        # ex-#97/#98: tote Menu-Doppel-Implementierung auf der Karte ist weg;
        # produktiv baut StructureTab._build_override_menu (#105/#106).
        assert not hasattr(_ClipCard, "_build_context_menu")
    finally:
        _cleanup(app, tab)

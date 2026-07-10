"""Tier-1 Wiring-Tests fuer SchnittController.

Plan: docs/superpowers/archive/2026-05-09-schnitt-workspace-redesign/
Hardening 2026-05-09 — Tier 1 (Wiring + State-Konflikt-Schutz).

Plan-Abweichung: nutzt `test_engine`-Fixture und monkeypatched `engine`
in `ui.workspaces.schnitt_workspace`, analog zu Phase-02-Tests.
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# B1 — Konstruktor erstellt PacingProfileBinder + initialer apply_profile
# ---------------------------------------------------------------------------

def test_controller_creates_binder_with_pacing_widgets():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController
    from services.ui_binder import PacingProfileBinder
    from services.pacing_profile import PacingProfile

    ws = SchnittWorkspace()
    ws._project_id = 1
    ctrl = SchnittController(ws)
    assert isinstance(ctrl.profile, PacingProfile)
    assert isinstance(ctrl.binder, PacingProfileBinder)
    tab = ws.editor_view.tab_pacing_anker
    # Initial-Sync: Widget-Werte spiegeln Profile-Defaults
    assert tab.cut_rate_combo.currentIndex() == ctrl.profile.cut_rate_index
    assert tab.reactivity_spin.value() == ctrl.profile.energy_reactivity


# ---------------------------------------------------------------------------
# B7 — Empty-State Preset-Klick verdrahten
# ---------------------------------------------------------------------------

def test_preset_selected_applies_profile_and_emits_request():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ws._project_id = 1
    ctrl = SchnittController(ws)

    captured = []
    ctrl.request_auto_edit_with_profile.connect(lambda p: captured.append(p))

    ws.empty_view.preset_selected.emit("Techno")

    assert len(captured) == 1
    profile = captured[0]
    # Techno-Preset: cut_rate_index=2, reactivity=70, breakdown=halve
    assert profile.cut_rate_index == 2
    assert profile.energy_reactivity == 70
    assert profile.breakdown == "halve"
    # Binder hat Profil uebernommen
    assert ctrl.profile.style_preset == "Techno"
    assert ctrl.profile.energy_reactivity == 70
    # Loading-State aktiv
    assert ws.current_state() == STATE_LOADING


def test_preset_selected_without_project_is_blocked():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    captured = []
    ctrl.request_auto_edit_with_profile.connect(lambda p: captured.append(p))

    ws.empty_view.preset_selected.emit("Techno")

    assert captured == []
    assert ws.current_state() == STATE_EMPTY


# ---------------------------------------------------------------------------
# B8 — Empty-State custom_clicked verdrahten
# ---------------------------------------------------------------------------

def test_custom_clicked_emits_open_settings():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    fired = []
    ctrl.request_open_settings.connect(lambda: fired.append(True))

    ws.empty_view.custom_clicked.emit()

    assert fired == [True]


# ---------------------------------------------------------------------------
# B6 — Cancel: bereits in Phase 09 implementiert. Verifizieren.
# ---------------------------------------------------------------------------

def test_cancel_invokes_worker_and_refreshes(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    cancelled = []

    class FakeWorker:
        def cancel(self):
            cancelled.append(True)

    ctrl.attach_worker(FakeWorker())
    ws.cancel_requested.emit()
    assert cancelled == [True]
    assert ctrl._current_worker is None


# ---------------------------------------------------------------------------
# D25 — set_active_project_protected ignoriert STATE_LOADING
# ---------------------------------------------------------------------------

def test_set_active_project_protected_skipped_during_loading(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING

    calls = []
    orig = ws.set_active_project
    def spy(pid):
        calls.append(pid)
        return orig(pid)
    monkeypatch.setattr(ws, "set_active_project", spy)

    ctrl.set_active_project_protected(99)
    assert calls == []  # Loading-Schutz greift
    assert ws.current_state() == STATE_LOADING


# ---------------------------------------------------------------------------
# B5 — Timeline-Selection erreicht Inspector-Panel
# ---------------------------------------------------------------------------

def test_timeline_selection_forwarded_to_inspector(monkeypatch):
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    received = []
    monkeypatch.setattr(
        ws.editor_view.inspector_panel,
        "update_from_selection",
        lambda data: received.append(data),
    )
    # Re-wire (monkeypatch ersetzt ATTR aber Signal-Verbindung bleibt
    # auf altem Bound-Method). Stattdessen direkt erneut connecten:
    ws.editor_view.tab_schnitt.timeline_view.selection_changed.connect(
        ws.editor_view.inspector_panel.update_from_selection
    )

    fake_payload = [{"entry_id": 7, "media_id": 1, "track_type": "video",
                     "pos_x": 0.0, "width": 100.0}]
    ws.editor_view.tab_schnitt.timeline_view.selection_changed.emit(fake_payload)

    assert any(item == fake_payload for item in received)


def test_inspector_property_change_refreshes_timeline_and_reemits(monkeypatch):
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ws._project_id = 1
    ctrl = SchnittController(ws)

    timeline = ws.editor_view.tab_schnitt.timeline_view
    # B-523-FIX: Voll-Teardown via load_from_db() darf bei Inspector-Edits NICHT
    # mehr laufen — er riss die gesamte Timeline-Ansicht ab und liess sie bei
    # async-Reload-Fehlern leer (A1/V1 verschwanden bis App-Neustart).
    full_reload = []
    monkeypatch.setattr(timeline, "load_from_db", lambda *a, **k: full_reload.append(True))
    geometry_refresh = []
    monkeypatch.setattr(
        timeline, "refresh_clip_geometry_from_db",
        lambda entry_id: geometry_refresh.append(entry_id),
    )

    emitted = []
    ctrl.clip_property_changed.connect(
        lambda entry_id, field, value: emitted.append((entry_id, field, value))
    )

    # Nicht-geometrisches Feld (Effekt, wirkt erst beim Export): kein
    # Timeline-Refresh, aber Re-Emit an die Host-Logik bleibt.
    ws.editor_view.inspector_panel.clip_property_changed.emit(7, "brightness", 0.5)
    assert full_reload == []
    assert geometry_refresh == []

    # Geometrie-Feld (Trim): nur In-Place-Geometrie-Update des betroffenen
    # Clips, KEIN Voll-Reload.
    ws.editor_view.inspector_panel.clip_property_changed.emit(7, "end_time", 5.0)
    assert full_reload == []
    assert geometry_refresh == [7]

    assert emitted == [(7, "brightness", 0.5), (7, "end_time", 5.0)]


def test_inspector_async_db_load_updates_fields(
    test_engine, db_session, project, video_clip, monkeypatch
):
    _qapp()
    import database
    import ui.clip_inspector as inspector_mod
    from database import TimelineEntry
    from ui.clip_inspector import ClipInspectorPanel

    monkeypatch.setattr(inspector_mod, "nullpool_session", database.nullpool_session)

    entry = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=12.25,
        end_time=22.75,
        brightness=0.15,
        contrast=1.25,
        crossfade_duration=0.5,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    panel = ClipInspectorPanel()
    try:
        panel.update_from_selection(
            [{"entry_id": entry.id, "media_id": video_clip.id, "track_type": "video"}]
        )

        deadline = time.time() + 3.0
        while time.time() < deadline and (
            panel._type_label.text() != "Typ: Video"
            or panel._media_label.text() != f"Media ID: {video_clip.id}"
            or panel._start_spin.value() != 12.25
        ):
            _qapp().processEvents()
            time.sleep(0.01)

        assert panel._type_label.text() == "Typ: Video"
        assert panel._media_label.text() == f"Media ID: {video_clip.id}"
        assert panel._start_spin.value() == 12.25
        assert panel._end_spin.value() == 22.75
        assert panel._duration_label.text() == "Dauer: 10.50s"
    finally:
        panel.deleteLater()


def test_inspector_debounced_change_keeps_original_entry_id(
    test_engine, db_session, project, video_clip, monkeypatch
):
    _qapp()
    import database
    import ui.clip_inspector as inspector_mod
    from database import TimelineEntry
    from ui.clip_inspector import ClipInspectorPanel

    monkeypatch.setattr(inspector_mod, "nullpool_session", database.nullpool_session)

    entry_a = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=0.0,
        end_time=10.0,
    )
    entry_b = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=20.0,
        end_time=30.0,
    )
    db_session.add_all([entry_a, entry_b])
    db_session.commit()
    db_session.refresh(entry_a)
    db_session.refresh(entry_b)

    panel = ClipInspectorPanel()
    writes = []
    panel.clip_property_changed.connect(
        lambda entry_id, field, value: writes.append((entry_id, field, value))
    )
    try:
        panel._current_entry_id = entry_a.id
        panel._on_field_changed("start_time", 4.25)
        panel._current_entry_id = entry_b.id
        panel._flush_pending_change()

        deadline = time.time() + 3.0
        while time.time() < deadline and not writes:
            _qapp().processEvents()
            time.sleep(0.01)

        with database.nullpool_session() as s:
            a = s.get(TimelineEntry, entry_a.id)
            b = s.get(TimelineEntry, entry_b.id)
            assert a.start_time == 4.25
            assert b.start_time == 20.0
        assert writes == [(entry_a.id, "start_time", 4.25)]
    finally:
        panel.deleteLater()


def test_inspector_ignores_stale_async_load_for_previous_entry():
    _qapp()
    from ui.clip_inspector import ClipInspectorPanel

    panel = ClipInspectorPanel()
    try:
        panel._current_entry_id = 2
        panel._apply_entry_data(
            {
                "entry_id": 2,
                "track": "video",
                "media_id": 22,
                "start_time": 20.0,
                "end_time": 30.0,
                "brightness": 0.2,
                "contrast": 1.2,
                "crossfade": 0.0,
            },
            1,
        )

        panel._apply_entry_data(
            {
                "entry_id": 1,
                "track": "video",
                "media_id": 11,
                "start_time": 1.0,
                "end_time": 9.0,
                "brightness": 0.1,
                "contrast": 1.1,
                "crossfade": 0.0,
            },
            1,
        )

        assert panel._media_label.text() == "Media ID: 22"
        assert panel._start_spin.value() == 20.0
        assert panel._end_spin.value() == 30.0
    finally:
        panel.deleteLater()


def test_timeline_anchor_add_remove_updates_anchor_map(
    test_engine, db_session, project, video_clip, monkeypatch
):
    _qapp()
    import database
    import ui.timeline as timeline_mod
    from database import TimelineEntry
    from ui.timeline import InteractiveTimeline, TimelineClipItem, PIXELS_PER_SECOND

    monkeypatch.setattr(timeline_mod, "nullpool_session", database.nullpool_session)

    entry = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=0.0,
        end_time=10.0,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    timeline = InteractiveTimeline()
    clip = TimelineClipItem(
        entry_id=entry.id,
        media_id=video_clip.id,
        track_type="video",
        title="Clip",
        x=0.0,
        y=0.0,
        width=100.0,
        height=40.0,
        anchors=[],
    )
    timeline._scene.addItem(clip)
    timeline.clip_items.append(clip)
    try:
        anchor_id = clip.add_anchor_at(2.0 * PIXELS_PER_SECOND)

        assert anchor_id is not None
        assert entry.id in timeline._anchor_map
        assert [a.time_offset for a in timeline._anchor_map[entry.id]] == [2.0]

        clip.remove_all_anchors()

        assert timeline._anchor_map.get(entry.id) == []
    finally:
        timeline.deleteLater()


def test_timeline_context_menu_offers_remove_for_invisible_anchors(monkeypatch):
    """B-384: Remove-Action muss auch erscheinen, wenn alle Anker ausserhalb
    der sichtbaren Clip-Breite liegen (kein Marker, nur ``_all_anchor_offsets``)."""
    _qapp()
    from PySide6.QtWidgets import QMenu
    from ui.timeline import InteractiveTimeline, TimelineClipItem

    monkeypatch.setattr(QMenu, "popup", lambda self, *a, **k: None)

    timeline = InteractiveTimeline()
    invisible = SimpleNamespace(id=1, time_offset=50.0)
    clip = TimelineClipItem(
        entry_id=1,
        media_id=11,
        track_type="video",
        title="Clip",
        x=0.0,
        y=0.0,
        width=100.0,
        height=40.0,
        anchors=[invisible],
    )
    timeline._scene.addItem(clip)
    timeline.clip_items.append(clip)
    try:
        assert clip._anchor_markers == []
        assert clip._all_anchor_offsets == [50.0]

        clip.show_context_menu_at(
            screen_pos=clip.scenePos().toPoint(),
            local_x=10.0,
        )
        labels = [a.text() for a in clip._context_menu.actions()]
        assert "Alle Anker entfernen" in labels
    finally:
        timeline.deleteLater()


def test_timeline_anchor_sync_clamps_db_start_time_to_zero(
    test_engine, db_session, project, audio_track, video_clip, monkeypatch
):
    _qapp()
    import database
    import ui.timeline as timeline_mod
    from database import TimelineEntry
    from ui.timeline import InteractiveTimeline, TimelineClipItem, PIXELS_PER_SECOND

    monkeypatch.setattr(timeline_mod, "nullpool_session", database.nullpool_session)

    audio_entry = TimelineEntry(
        project_id=project.id,
        track="audio",
        media_id=audio_track.id,
        start_time=0.0,
        end_time=10.0,
    )
    video_entry = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=10.0,
        end_time=20.0,
    )
    db_session.add_all([audio_entry, video_entry])
    db_session.commit()
    db_session.refresh(audio_entry)
    db_session.refresh(video_entry)

    timeline = InteractiveTimeline()
    audio_item = TimelineClipItem(
        entry_id=audio_entry.id,
        media_id=audio_track.id,
        track_type="audio",
        title="Audio",
        x=0.0,
        y=0.0,
        width=100.0,
        height=40.0,
        anchors=[],
    )
    video_item = TimelineClipItem(
        entry_id=video_entry.id,
        media_id=video_clip.id,
        track_type="video",
        title="Video",
        x=10.0 * PIXELS_PER_SECOND,
        y=50.0,
        width=100.0,
        height=40.0,
        anchors=[],
    )
    timeline._scene.addItem(audio_item)
    timeline._scene.addItem(video_item)
    timeline.clip_items.extend([audio_item, video_item])
    # M1 Timeline-Virtualisierung (D-066): sync_anchors arbeitet auf Records.
    # Manuell gebaute Items hier als materialisierte Records registrieren.
    from ui.timeline import ClipRecord
    for _it in (audio_item, video_item):
        _rec = ClipRecord(
            entry_id=_it.entry_id, media_id=_it.media_id,
            track_type=_it.track_type, title=_it.title,
            x=_it.pos().x(), y=_it._track_y,
            width=_it._clip_width, height=_it._clip_height,
            item=_it,
        )
        timeline.clip_records.append(_rec)
        timeline._records_by_entry[_it.entry_id] = _rec
    timeline._anchor_map = {
        audio_entry.id: [SimpleNamespace(time_offset=1.0)],
        video_entry.id: [SimpleNamespace(time_offset=5.0)],
    }
    try:
        assert timeline.sync_anchors() is True

        with database.nullpool_session() as s:
            refreshed = s.get(TimelineEntry, video_entry.id)
            assert refreshed.start_time == 0.0
        assert video_item.pos().x() == 0.0
    finally:
        timeline.deleteLater()


# ---------------------------------------------------------------------------
# B2 — btn_regenerate triggert Confirm + Signal
# ---------------------------------------------------------------------------

def test_regenerate_confirmed_emits_signal_and_loads():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
    from ui.controllers.schnitt_controller import SchnittController
    import ui.controllers.schnitt_controller as ctrl_mod

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    # Confirm-Dialog mocken (Yes)
    import ui.workspaces.schnitt.regenerate_dialog as rd_mod
    rd_mod.confirm_regenerate = lambda parent: True

    captured = []
    ctrl.request_regenerate.connect(lambda p: captured.append(p))

    ws.editor_view.tab_pacing_anker.btn_regenerate.click()

    assert len(captured) == 1
    assert captured[0] is ctrl.profile
    assert ws.current_state() == STATE_LOADING


def test_regenerate_cancelled_does_nothing():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    import ui.workspaces.schnitt.regenerate_dialog as rd_mod
    rd_mod.confirm_regenerate = lambda parent: False

    captured = []
    ctrl.request_regenerate.connect(lambda p: captured.append(p))

    ws.editor_view.tab_pacing_anker.btn_regenerate.click()

    assert captured == []
    assert ws.current_state() == STATE_EMPTY


def test_set_active_project_protected_runs_when_not_loading(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    from ui.controllers.schnitt_controller import SchnittController
    from database.models import Project

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    assert ws.current_state() == STATE_EMPTY

    with Session(test_engine) as s:
        p = Project(name="protected", path="/tmp/protected")
        s.add(p)
        s.commit()
        pid = p.id

    ctrl.set_active_project_protected(pid)
    # Kein Crash, project_id wurde uebernommen
    assert ws._project_id == pid


# ---------------------------------------------------------------------------
# T5.11 Coverage-Sweep (E11)
# ---------------------------------------------------------------------------


def test_attach_worker_without_progress_signal_no_crash():
    """attach_worker akzeptiert Objekte ohne progress/done/failed-Signal — keine Krasche."""
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    class BareWorker:
        pass

    bw = BareWorker()
    ctrl.attach_worker(bw)
    assert ctrl._current_worker is bw


def test_cancel_without_active_worker_no_crash():
    """Cancel-Signal ohne aktiven Worker → kein AttributeError."""
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    assert ctrl._current_worker is None
    # Direkt Cancel triggern — _on_cancel guard
    ws.cancel_requested.emit()
    assert ctrl._current_worker is None


def test_attach_worker_replaces_old_worker():
    """Zweiter attach_worker-Call ersetzt den alten Worker-Referenz."""
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    class W:
        pass

    a = W()
    b = W()
    ctrl.attach_worker(a)
    assert ctrl._current_worker is a
    ctrl.attach_worker(b)
    assert ctrl._current_worker is b


# ---------------------------------------------------------------------------
# B-523 — Inspector-Trim leert NICHT mehr die Timeline-Ansicht
# (Regression: frueher riss _on_clip_property_changed via load_from_db() die
#  ganze Szene ab und liess sie bei async-Reload-Fehlern leer bis Neustart).
# ---------------------------------------------------------------------------

def test_refresh_clip_geometry_keeps_items_and_updates_width(
    test_engine, db_session, project, video_clip, monkeypatch
):
    _qapp()
    import database
    import ui.timeline as timeline_mod
    from database import TimelineEntry
    from ui.timeline import InteractiveTimeline, PIXELS_PER_SECOND

    # ui.timeline wird von conftest NICHT automatisch auf die Test-DB gepatcht.
    monkeypatch.setattr(timeline_mod, "nullpool_session", database.nullpool_session)

    entry = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=0.0,
        end_time=10.0,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    tl = InteractiveTimeline()
    try:
        # Echtes Clip-Item synchron in die Szene bauen. Im echten Pfad setzt
        # _on_db_load_finished diese Maps vor dem Build — hier explizit setzen.
        tl._brain_v3_timeline_meta = {}
        tl._anchor_map = {}
        tl._build_entries([entry], {}, {video_clip.id: video_clip}, {})
        # M1 Timeline-Virtualisierung (D-066): Build erzeugt Records; fuer den
        # Headless-Test explizit materialisieren.
        tl.materialize_all()
        assert len(tl.clip_items) == 1
        item = tl._find_clip_item(entry.id)
        assert item is not None
        assert item._clip_width == pytest.approx(10.0 * PIXELS_PER_SECOND)

        # Trim auf 5s in der DB (so wie der Inspector es nach dem Debounce tut).
        with database.nullpool_session() as s:
            row = s.get(TimelineEntry, entry.id)
            row.end_time = 5.0
            s.commit()

        # B-523-FIX: In-Place-Update statt Voll-Teardown.
        tl.refresh_clip_geometry_from_db(entry.id)

        # KERN-REGRESSION: Item bleibt erhalten (Szene NICHT geleert) ...
        assert len(tl.clip_items) == 1
        assert tl._find_clip_item(entry.id) is item
        # ... und die Breite spiegelt den neuen Trim (5s).
        assert item._clip_width == pytest.approx(5.0 * PIXELS_PER_SECOND)
    finally:
        # Test-Isolation: ausstehende Timeline-Worker/Timer + Thumb-Threads
        # stoppen und Event-Loop drainen, damit kein Hintergrund-Job in einen
        # nachfolgenden (timing-sensitiven) Test wie test_b508 hineinlaeuft.
        import time as _t
        try:
            tl._cancel_pending_db_load()
        except Exception:
            pass
        tl.deleteLater()
        app = _qapp()
        for _ in range(10):
            app.processEvents(); _t.sleep(0.02)

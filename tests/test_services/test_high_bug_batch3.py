"""B-077 + B-088 + B-089 Batch-3 regression tests.

UI-Thread-DB-Issues. Source-Inspection-basiert, GPU+Qt-frei.
"""

from __future__ import annotations

import inspect


# ---------------------------------------------------------------------------
# B-077: Timeline get_first_anchor_time ohne sync DB-Read
# ---------------------------------------------------------------------------


def test_timeline_get_first_anchor_time_uses_local_state() -> None:
    """B-077: ``TimelineClipItem.get_first_anchor_time`` darf nicht mehr
    eine sync DB-Query im Main-Thread machen — Daten kommen jetzt aus
    der lokalen ``_anchor_markers``-Liste."""
    from ui.timeline import TimelineClipItem

    src = inspect.getsource(TimelineClipItem.get_first_anchor_time)
    assert "nullpool_session" not in src, (
        "B-077: get_first_anchor_time oeffnet immer noch eine DB-Session "
        "im Main-Thread — sync UI-Freeze ist zurueck."
    )
    assert "session.query" not in src
    assert "_anchor_markers" in src, (
        "B-077: get_first_anchor_time muss aus _anchor_markers ableiten."
    )


def test_anchor_marker_has_time_offset_attribute() -> None:
    """B-077: ``AnchorMarkerItem`` muss ``time_offset`` als Attribut
    speichern, damit ``get_first_anchor_time`` ihn lokal lesen kann.
    """
    from ui.timeline import AnchorMarkerItem

    src = inspect.getsource(AnchorMarkerItem.__init__)
    assert "self.time_offset" in src, (
        "B-077: AnchorMarkerItem.time_offset fehlt — local-derive faellt aus."
    )


# ---------------------------------------------------------------------------
# B-088: MediaWorkspace _dispatch_audio_analysis nutzt NullPool
# ---------------------------------------------------------------------------


def test_dispatch_audio_analysis_uses_nullpool_not_orm_get() -> None:
    """B-088: ``_dispatch_audio_analysis`` darf nicht mehr
    ``DBSession(engine).get(AudioTrack, ...)`` im Main-Thread aufrufen
    — das hydrierte das volle ORM-Objekt mit Lazy-Relations und konnte
    bei SQLite-Lock-Contention 1-5 s blocken.
    """
    from ui.workspaces.media_workspace import MediaWorkspace

    src = inspect.getsource(MediaWorkspace._dispatch_audio_analysis)
    # Negatives Pattern: alter ORM-Get-Aufruf
    assert "session.get(AudioTrack" not in src, (
        "B-088: ORM-Get-Aufruf im Main-Thread noch vorhanden."
    )
    # Positives Pattern: NullPool + Raw-SQL
    assert "nullpool_session" in src, (
        "B-088: nullpool_session ist die kanonische Wahl im Main-Thread."
    )


# ---------------------------------------------------------------------------
# B-089: AnalysisStatusPanel Generation-Counter gegen Stale-Data
# ---------------------------------------------------------------------------


def test_status_panel_set_media_increments_generation() -> None:
    """B-089: ``set_media`` muss ``_refresh_generation`` inkrementieren —
    sonst koennen Stale-Results den schon umgeschalteten Track ueberschreiben.
    """
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    src = inspect.getsource(AnalysisStatusPanel.set_media)
    assert "_refresh_generation" in src
    assert "+ 1" in src or "+1" in src or "+=" in src or "+= 1" in src or "+ 1" in src


def test_status_panel_apply_data_checks_generation() -> None:
    """B-089: ``_apply_status_data`` muss ``expected_gen`` gegen
    ``_refresh_generation`` pruefen — sonst landet Stale-Result in der
    UI nach schnellem Track-Switch.
    """
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    src = inspect.getsource(AnalysisStatusPanel._apply_status_data)
    assert "expected_gen" in src, (
        "B-089: _apply_status_data nimmt keine expected_gen entgegen."
    )
    # Stale-Drop-Pattern muss im Source erkennbar sein
    assert "current_gen" in src or "_refresh_generation" in src


def test_status_panel_refresh_passes_generation_to_apply() -> None:
    """B-089: ``refresh`` muss ``my_gen`` capturen und an
    ``_apply_status_data`` durchgeben (sonst bringt der Counter nichts).
    """
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    src = inspect.getsource(AnalysisStatusPanel.refresh)
    assert "my_gen" in src, (
        "B-089: refresh muss die aktuelle Generation einfangen + weitergeben."
    )
    assert "_refresh_generation" in src

"""B-208..B-214 — bug-hunter Batch-1-7 Regression-Audit (2026-04-27).

Tests fuer die 7 Fixes, die aus dem Audit hervorgegangen sind:
- B-208: services/lufs_service.py — partial-parse loudnorm-JSON faellt nicht
  als echte Messung durch.
- B-209: ui/controllers/panel_setup.py — invalidate_system_prompt_cache an
  project_changed verdrahtet.
- B-210: services/convert_service.py — User-Cancel hat Vorrang vor Timeout.
- B-211: ui/timeline.py — get_first_anchor_time deckt ALLE DB-Anker, nicht
  nur sichtbare.
- B-212: services/ingest_service.py — DB-Lock (OperationalError) wird als
  ValueError raised statt swallowed.
- B-213: workers/import_export.py — FolderImportWorker emittet
  Empty-Folder-Warnung wenn walk_root keine Medien findet.
- B-214: workers/import_export.py — ProxyCreationWorker.run() prueft
  should_stop VOR dem Semaphor-Acquire.
"""

from __future__ import annotations

import inspect
import textwrap


# ---------------------------------------------------------------------------
# B-208 — LUFS Fallback-Detection bei partial-parse
# ---------------------------------------------------------------------------

def test_b208_lufs_partial_parse_returns_fallback() -> None:
    """JSON-Block ohne input_i darf NICHT als echte Messung durchgehen."""
    from services.lufs_service import LUFSService

    # Nur 2 von 3 Pflicht-Keys vorhanden — input_i fehlt.
    partial = {"input_lra": "8.0", "input_tp": "-1.0"}
    result = LUFSService._extract_values(partial, "/tmp/test.wav")
    assert result.is_fallback is True
    assert "missing keys" in result.fallback_reason
    assert "input_i" in result.fallback_reason


def test_b208_lufs_full_parse_no_fallback() -> None:
    """Vollstaendiges JSON liefert echte Werte, is_fallback=False."""
    from services.lufs_service import LUFSService

    complete = {
        "input_i": "-12.5",
        "input_lra": "9.0",
        "input_tp": "-0.5",
    }
    result = LUFSService._extract_values(complete, "/tmp/test.wav")
    assert result.is_fallback is False
    assert result.integrated == -12.5
    assert result.loudness_range == 9.0
    assert result.true_peak == -0.5


def test_b208_lufs_completely_empty_dict_is_fallback() -> None:
    """Leeres dict (alle 3 Keys fehlen) → Fallback."""
    from services.lufs_service import LUFSService

    result = LUFSService._extract_values({}, "/tmp/test.wav")
    assert result.is_fallback is True


def test_b208_lufs_none_values_treated_as_missing() -> None:
    """B-208-restfall: Key vorhanden, Value None → muss als missing zaehlen,
    sonst greift _safe_float und liefert die Default-Werte still."""
    from services.lufs_service import LUFSService

    partial_with_nones = {
        "input_i": None,           # explizit null
        "input_lra": "8.0",
        "input_tp": "-1.0",
    }
    result = LUFSService._extract_values(partial_with_nones, "/tmp/test.wav")
    assert result.is_fallback is True, (
        "B-208 restfall: None-Value muss als missing-key behandelt werden."
    )
    assert "input_i" in result.fallback_reason


# ---------------------------------------------------------------------------
# B-209 — panel_setup verdrahtet invalidate_system_prompt_cache
# ---------------------------------------------------------------------------

def test_b209_panel_setup_wires_invalidate_on_project_changed() -> None:
    """Source-Inspect: invalidate_system_prompt_cache wird im setup_chat_dock
    Pfad an project_manager.project_changed angeschlossen."""
    from ui.controllers.panel_setup import PanelSetupController

    src = inspect.getsource(PanelSetupController)
    assert "invalidate_system_prompt_cache" in src, (
        "panel_setup.py ruft den Hook nicht auf — B-209-Verdrahtung fehlt."
    )
    assert "project_changed.connect" in src, (
        "panel_setup.py connectet project_changed nicht auf den Cache-Invalidate-Hook."
    )


# ---------------------------------------------------------------------------
# B-210 — convert_service: cancelled vor timed_out
# ---------------------------------------------------------------------------

def test_b210_convert_checks_cancelled_before_timed_out() -> None:
    """Im Source steht der cancelled-Check VOR dem timed_out-Check."""
    from services import convert_service

    src = inspect.getsource(convert_service)
    cancelled_idx = src.find("if cancelled.is_set():")
    timed_out_idx = src.find("if timed_out.is_set():\n        raise FFmpegTimeoutError")
    # Der Source enthaelt evtl. mehrere is_set-Stellen (Watchdog-Setup) — wir
    # vergleichen die Position der finalen Raise-Bloecke nach process.wait.
    final_cancel = src.rfind("Convert abgebrochen (User-Cancel)")
    final_timeout = src.rfind("FFmpegTimeoutError(int(timeout if timeout")
    assert cancelled_idx > 0
    assert timed_out_idx > 0
    assert final_cancel > 0
    assert final_timeout > 0
    assert final_cancel < final_timeout, (
        "B-210: User-Cancel-Raise muss VOR dem Timeout-Raise stehen."
    )


# ---------------------------------------------------------------------------
# B-211 — timeline get_first_anchor_time liest aus _all_anchor_offsets
# ---------------------------------------------------------------------------

def test_b211_get_first_anchor_time_uses_all_offsets() -> None:
    """Source-Inspect: get_first_anchor_time iteriert ueber
    _all_anchor_offsets, nicht ueber _anchor_markers."""
    from ui import timeline as timeline_mod

    # Source des Moduls (statt der Methode, weil Klassenname dynamisch).
    src = inspect.getsource(timeline_mod)
    # Funktionssignatur muss intakt sein:
    assert "def get_first_anchor_time(self) -> float | None:" in src
    # Das Body muss _all_anchor_offsets nutzen:
    assert "_all_anchor_offsets" in src, (
        "B-211: timeline.py erwaehnt _all_anchor_offsets nicht — Fix fehlt."
    )
    # Und die Methode darf NICHT mehr direkt ueber _anchor_markers iterieren
    # (das war der broken Pfad).
    body_start = src.find("def get_first_anchor_time(self)")
    body_end = src.find("def ", body_start + 10)
    body = src[body_start:body_end]
    assert "_all_anchor_offsets" in body
    assert "m.time_offset for m in self._anchor_markers" not in body


# ---------------------------------------------------------------------------
# B-212 — ingest_service raises ValueError on OperationalError
# ---------------------------------------------------------------------------

def test_b212_ensure_project_raises_on_db_lock() -> None:
    """Source-Inspect: _ensure_project_exists catched OperationalError und
    raised stattdessen ValueError mit klarer Message."""
    from services import ingest_service

    src = inspect.getsource(ingest_service._ensure_project_exists)
    assert "OperationalError" in src, (
        "B-212: _ensure_project_exists muss OperationalError speziell catchen."
    )
    assert "DB temporaer nicht verfuegbar" in src or "DB temporär nicht verfügbar" in src
    assert "raise ValueError" in src


# ---------------------------------------------------------------------------
# B-213 — FolderImportWorker emittet Empty-Folder-Warnung
# ---------------------------------------------------------------------------

def test_b213_folder_worker_warns_on_empty_walk() -> None:
    """Source-Inspect: FolderImportWorker.run() emittet eine Warning wenn
    nach dem walk weder Audio- noch Video-Files gefunden wurden."""
    from workers.import_export import FolderImportWorker

    src = inspect.getsource(FolderImportWorker.run)
    assert "Keine unterstuetzten Medien" in src, (
        "B-213: FolderImportWorker emittet keinen Empty-Folder-Hinweis."
    )
    # Der Hinweis muss INNERHALB des walk_root-Pfads kommen (im if-Block,
    # vor 'total = len(...)') — sonst feuert er bei normalen Imports.
    walk_block = src[src.find("if self.walk_root"):src.find("total = len(self.paths_audio)")]
    assert "Keine unterstuetzten Medien" in walk_block, (
        "B-213: Empty-Folder-Warning muss im walk_root-Block stehen."
    )


# ---------------------------------------------------------------------------
# B-214 — ProxyCreationWorker.run pruefe should_stop vor Semaphor-Acquire
# ---------------------------------------------------------------------------

def test_b214_proxy_worker_pre_cancel_check() -> None:
    """ProxyCreationWorker.run() ruft should_stop() VOR dem Semaphor-Acquire."""
    from workers.import_export import ProxyCreationWorker

    src = inspect.getsource(ProxyCreationWorker.run)
    src = textwrap.dedent(src)
    # Reihenfolge: should_stop() muss VOR dem `with _PROXY_CREATION_SEMAPHORE`
    # auftauchen.
    pre_check_idx = src.find("self.should_stop()")
    semaphore_idx = src.find("with _PROXY_CREATION_SEMAPHORE")
    assert pre_check_idx > 0, "B-214: kein should_stop()-Check in run()."
    assert semaphore_idx > 0, "Semaphor-Acquire fehlt — Source-Drift?"
    assert pre_check_idx < semaphore_idx, (
        "B-214: should_stop() muss VOR dem Semaphor-Acquire stehen."
    )


# ===========================================================================
# Behavior-Tests (statt Source-Inspect) — verifiziert tatsaechliches
# Runtime-Verhalten der Fixes, nicht nur dass der Code da steht.
# ===========================================================================


def test_b212_ensure_project_raises_value_error_on_operational_error(monkeypatch) -> None:
    """B-212 BEHAVIOR: simuliere OperationalError im Pre-Check → muss als
    ValueError mit klarer 'DB temporaer'-Message raisen."""
    from sqlalchemy.exc import OperationalError
    from services import ingest_service
    import pytest

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def query(self, *_a, **_kw):
            raise OperationalError("SELECT", {}, Exception("database is locked"))

    def _fake_session_ctx():
        return _FakeSession()

    # Monkeypatch nullpool_session in der Funktion-Lokalen-Import-Resolution.
    import database
    monkeypatch.setattr(database, "nullpool_session", _fake_session_ctx)

    with pytest.raises(ValueError) as exc_info:
        ingest_service._ensure_project_exists(project_id=42)

    msg = str(exc_info.value)
    assert "DB temporaer nicht verfuegbar" in msg or "DB temporär nicht verfügbar" in msg
    assert "42" in msg


def test_b213_folder_worker_emits_warning_on_empty_walk(tmp_path) -> None:
    """B-213 BEHAVIOR: FolderImportWorker.run() ueber leeren Ordner emittet
    'Keine unterstuetzten Medien'-Hinweis ueber file_imported-Signal."""
    from workers.import_export import FolderImportWorker

    empty_dir = tmp_path / "empty_folder"
    empty_dir.mkdir()

    worker = FolderImportWorker([], [], walk_root=str(empty_dir))
    captured: list[str] = []
    worker.file_imported.connect(captured.append)
    # Ohne Qt-Eventloop: direkt run() aufrufen — Signal-Emit landet
    # synchron in _connect (DirectConnection-Default ohne QThread).
    worker.run()

    assert any("Keine unterstuetzten Medien" in msg for msg in captured), (
        f"B-213: empty-folder Warnung fehlt. Captured: {captured}"
    )


def test_b214_proxy_worker_skips_run_when_cancelled_before_start() -> None:
    """B-214 BEHAVIOR: cancel() vor run() → run() darf _run_with_slot NICHT
    aufrufen (kein convert_service.convert()-Call, kein Semaphor-Acquire-Wait)."""
    from workers.import_export import ProxyCreationWorker, _PROXY_CREATION_SEMAPHORE
    import threading as _t

    worker = ProxyCreationWorker(clip_id=999, video_path="/dev/null/no-such")
    # Pre-cancel:
    worker.cancel()

    # Sentinel: ueberwache ob _run_with_slot() jemals aufgerufen wird.
    called = {"slot": False}
    original_slot = worker._run_with_slot

    def _spy_slot():
        called["slot"] = True
        return original_slot()

    worker._run_with_slot = _spy_slot

    # Sentinel: ueberwache, ob das Semaphor irgendwo waehrend run() einen
    # acquire macht (Semaphor wuerde bei Slot-Acquire blockieren wenn voll;
    # hier ist es nicht voll, daher pruefen wir einfach _value-Wechsel).
    initial_value = _PROXY_CREATION_SEMAPHORE._value

    # Run direkt ausfuehren (kein QThread).
    worker.run()

    assert called["slot"] is False, (
        "B-214: _run_with_slot wurde aufgerufen obwohl pre-cancel gesetzt."
    )
    # Semaphor wieder im Ausgangszustand (wir haben nicht geacquired):
    assert _PROXY_CREATION_SEMAPHORE._value == initial_value, (
        "B-214: Semaphor wurde acquired obwohl pre-cancel gesetzt."
    )


def test_b211_get_first_anchor_time_returns_invisible_anchor() -> None:
    """B-211 BEHAVIOR: konstruiere AnchoredClipItem mit einem Anker, dessen
    x-Pixel-Position ausserhalb _clip_width liegt (also unsichtbar).
    get_first_anchor_time muss diesen Anker zurueckgeben — nicht None.

    Braucht eine QApplication (QGraphicsItem-Subklasse). Wenn PySide6
    nicht verfuegbar oder keine QApplication erstellbar, skip statt fail.
    """
    import pytest
    try:
        from PySide6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv[:1])
    except Exception as exc:
        pytest.skip(f"PySide6 nicht verfuegbar: {exc}")
        return

    try:
        from ui.timeline import TimelineClipItem
    except ImportError as exc:
        pytest.skip(f"ui.timeline.TimelineClipItem nicht importierbar: {exc}")
        return

    from types import SimpleNamespace
    fake_anchor = SimpleNamespace(time_offset=10.0, id=1)

    sig = inspect.signature(TimelineClipItem.__init__)
    if "anchors" not in sig.parameters:
        pytest.skip("TimelineClipItem-Signatur hat sich geaendert.")
        return

    # Echte Signatur (ui/timeline.py):
    # __init__(entry_id, media_id, track_type, title, x, y, width, height,
    #          on_moved=None, on_trimmed=None, has_waveform=False, anchors=None)
    # _clip_width=100, PIXELS_PER_SECOND im Modul ist 50 → time_offset=10s
    # ergibt x=500 px, deutlich ausserhalb _clip_width=100. Marker wird
    # NICHT gezeichnet, time_offset muss aber in _all_anchor_offsets sein.
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="audio",
        title="test", x=0, y=0, width=100, height=50,
        anchors=[fake_anchor],
    )

    # _all_anchor_offsets muss ALLE DB-Anker enthalten (auch unsichtbare):
    assert 10.0 in clip._all_anchor_offsets, (
        f"B-211: invisible anchor wurde nicht in _all_anchor_offsets gespeichert. "
        f"Inhalt: {clip._all_anchor_offsets}"
    )
    # get_first_anchor_time liefert den Wert, NICHT None:
    result = clip.get_first_anchor_time()
    assert result == 10.0, (
        f"B-211: get_first_anchor_time muss 10.0 zurueckgeben, lieferte {result}"
    )


def test_b209_panel_setup_setup_chat_dock_calls_invalidate_on_signal() -> None:
    """B-209 BEHAVIOR (light): inspiziere die generierte connect-Closure auf
    der PanelSetupController-Methode. Wir koennen ohne PySide6/MainWindow
    nicht den vollen Flow laufen — aber wir koennen sicherstellen dass
    1) der wiring-Block existiert und
    2) der Lambda explizit invalidate_system_prompt_cache('media') ruft."""
    from ui.controllers import panel_setup as ps

    src = inspect.getsource(ps)
    # Wiring-Pfad ist im setup_chat_dock vorhanden:
    assert "project_changed.connect" in src
    # Der lambda muss konkret 'media' invalidieren (nicht 'all' — sonst
    # wirft das den ganzen Cache, was teuer ist):
    assert 'invalidate_system_prompt_cache("media")' in src, (
        "B-209: invalidate-Aufruf muss Kind 'media' verwenden, nicht 'all'."
    )

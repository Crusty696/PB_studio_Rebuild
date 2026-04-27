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

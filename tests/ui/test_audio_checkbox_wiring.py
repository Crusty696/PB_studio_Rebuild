"""B-293: Audio-Pool Checkbox + Alle-Button werden von jeder Audio-Analyse
respektiert. Symmetrisch zu Video-Helper."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    """AST-strict slot body extraction."""
    import ast
    src = (REPO / file_rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == slot_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None
            return seg
    raise AssertionError(f"Slot {slot_name} nicht gefunden in {file_rel}")


def test_b293_audio_selected_track_uses_get_checked_ids():
    """R-13: Audio-Helper muss get_checked_ids referenzieren BEVOR selectionModel."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_track")
    assert "get_checked_ids" in body, (
        "B-293: _get_selected_audio_track ignoriert Checkbox — "
        "Audio-Multi-Select tot."
    )
    pos_checked = body.find("get_checked_ids")
    pos_selmodel = body.find("selectionModel")
    if pos_selmodel > 0:
        assert pos_checked < pos_selmodel, (
            "B-293: get_checked_ids muss VOR selectionModel-Fallback stehen."
        )


def test_b293_audio_selected_tracks_plural_exists():
    """B-293: Plural-Variante fuer Batch-Funktionen."""
    src = (REPO / "ui/controllers/audio_analysis.py").read_text(encoding="utf-8")
    assert "def _get_selected_audio_tracks(" in src, (
        "B-293: _get_selected_audio_tracks (Plural) fehlt."
    )


def test_b293_audio_selected_tracks_plural_uses_checked_ids():
    body = _slot_body("ui/controllers/audio_analysis.py", "_get_selected_audio_tracks")
    assert "get_checked_ids" in body
    # returns iterable
    assert "list" in body or "return [" in body or "return list" in body


# ---------------------------------------------------------------------------
# R-23 I-1: Behavioral tests (MagicMock-based, verify actual return values).
# ---------------------------------------------------------------------------


def test_b293_plural_returns_all_checked_ids(qapp):
    """Behavioral: get_checked_ids -> [1,2,3] => plural returns [1,2,3]."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = [1, 2, 3]
    ctrl.window.audio_pool_table.model.return_value = model
    result = ctrl._get_selected_audio_tracks()
    assert result == [1, 2, 3]


def test_b293_plural_empty_returns_empty_list(qapp):
    """Behavioral: no checks + no selection => []."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = []
    selmodel = MagicMock()
    selmodel.selectedRows.return_value = []
    view = MagicMock()
    view.model.return_value = model
    view.selectionModel.return_value = selmodel
    ctrl.window.audio_pool_table = view
    result = ctrl._get_selected_audio_tracks()
    assert result == []


def test_b293_plural_falls_back_to_selectionmodel(qapp):
    """Behavioral: empty get_checked_ids => fallback to selectionModel rows."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = []
    row1 = MagicMock()
    row1.row.return_value = 0
    row2 = MagicMock()
    row2.row.return_value = 1
    selmodel = MagicMock()
    selmodel.selectedRows.return_value = [row1, row2]

    def idx_func(r, c):
        m = MagicMock()
        m.data.return_value = str(7 + r)  # row0 -> "7", row1 -> "8"
        return m

    model.index.side_effect = idx_func
    view = MagicMock()
    view.model.return_value = model
    view.selectionModel.return_value = selmodel
    ctrl.window.audio_pool_table = view
    result = ctrl._get_selected_audio_tracks()
    assert result == [7, 8]


def test_b293_single_returns_first_checked_id(qapp, monkeypatch):
    """Behavioral: get_checked_ids=[42] => single helper returns track tuple
    with id=42. DB-Session via monkeypatch on sqlalchemy.orm.Session."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    model = MagicMock()
    model.get_checked_ids.return_value = [42]
    ctrl.window.audio_pool_table.model.return_value = model

    # B-625: die Implementierung nutzt column-select (execute(select(...)).first())
    # statt session.get() — verhindert eager-load der Blob-Spalten. .first() liefert
    # ein Row-Objekt mit denselben Attributnamen wie die selektierten Spalten.
    fake_track = MagicMock()
    fake_track.id = 42
    fake_track.file_path = "/x.mp3"
    fake_track.title = "X"
    fake_track.bpm = 120.0

    fake_session = MagicMock()
    fake_session.execute.return_value.first.return_value = fake_track
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_session
    fake_ctx.__exit__.return_value = False

    # _get_selected_audio_track does `from sqlalchemy.orm import Session as DBSession`
    # patch the source module so the local import resolves to our fake.
    import sqlalchemy.orm as _orm_mod
    monkeypatch.setattr(_orm_mod, "Session", lambda eng: fake_ctx)

    result = ctrl._get_selected_audio_track()
    assert result is not None
    assert result[0] == 42
    assert result[1] == "/x.mp3"
    assert result[2] == "X"
    assert result[3] == 120.0


def test_b293_sequential_analyse_uses_plural_helper():
    """B-293: _analyze_all_sequential ruft _get_selected_audio_tracks (Plural-Helper)."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_analyze_all_sequential")
    assert "_get_selected_audio_tracks" in body, (
        "B-293: _analyze_all_sequential ignoriert Plural-Checkbox-Helper."
    )


# ---------------------------------------------------------------------------
# R-23 C-1/C-2 + I-3: TRUE multi-track sequential.
# ---------------------------------------------------------------------------


def test_b293_sequential_iterates_all_tracks_or_chains():
    """C-1 Fix: _analyze_all_sequential muss alle Tracks abarbeiten — entweder
    explizite Loop oder Batch-Queue + Process-Next-Helper."""
    body = _slot_body("ui/controllers/audio_analysis.py", "_analyze_all_sequential")
    has_loop = "for track_id in" in body or "for tid in" in body
    has_queue = "_batch_queue" in body or "_process_next_batch_track" in body
    assert has_loop or has_queue, (
        "C-1: _analyze_all_sequential muss alle Tracks abarbeiten, nicht nur ersten."
    )


def test_b293_no_multi_track_deferred_comment():
    """C-1/C-2 Fix: Der irrefuehrende 'Batch-Multi-Track deferred'-Hinweis
    darf nicht mehr im Code stehen."""
    src = (REPO / "ui/controllers/audio_analysis.py").read_text(encoding="utf-8")
    assert "Batch-Multi-Track deferred" not in src, (
        "C-1: Multi-Track-deferred-Kommentar muss entfernt sein (Logik faehrt jetzt alle Tracks)."
    )


def test_b293_process_next_batch_track_exists():
    """C-1 Fix: Per-Track-Helper muss existieren."""
    src = (REPO / "ui/controllers/audio_analysis.py").read_text(encoding="utf-8")
    assert "def _process_next_batch_track(" in src, (
        "C-1: _process_next_batch_track-Helper fehlt — Batch-Chain broken."
    )


def test_b293_run_audio_steps_for_track_exists():
    """C-1 Fix: Step-Chain pro Track muss extrahiert sein."""
    src = (REPO / "ui/controllers/audio_analysis.py").read_text(encoding="utf-8")
    assert "def _run_audio_steps_for_track(" in src, (
        "C-1: _run_audio_steps_for_track-Helper fehlt — Per-Track-Steps nicht extrahiert."
    )


def test_b458_complete_audio_chain_covers_all_audio_steps(qapp, monkeypatch):
    """B-458: Komplett-Analyse muss alle AUDIO_STEPS fahren, sonst bleibt UI bei 75%."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from services import analysis_status_service
    from services.analysis_status_service import AUDIO_STEPS
    from ui.controllers.audio_analysis import AudioAnalysisController

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    ctrl.window._media_ws.btn_analyze_all.setText = MagicMock()
    ctrl.window.progress_bar.setVisible = MagicMock()
    ctrl.window.progress_bar.setRange = MagicMock()
    ctrl.window.progress_bar.setValue = MagicMock()
    ctrl.window.console_text.append = MagicMock()
    ctrl._run_next_sequential_step = MagicMock()
    monkeypatch.setattr(analysis_status_service, "infer_from_db", lambda *_args: None)
    monkeypatch.setattr(analysis_status_service, "get_status", lambda *_args: {})

    ctrl._run_audio_steps_for_track(7, "C:/audio.mp3", "Track", 142.0)

    step_names = [name for name, _factory in ctrl._seq_steps]
    assert len(step_names) == len(AUDIO_STEPS), (
        f"B-458: Komplett-Analyse muss {len(AUDIO_STEPS)} Audio-Steps starten, "
        f"nicht {len(step_names)}: {step_names}"
    )
    assert "Mood/Genre" in step_names
    assert "Spektral" in step_names


def test_b461_complete_audio_chain_does_not_skip_done_steps(qapp, monkeypatch):
    """B-461: Komplett-Analyse muss alle Steps erneut starten, auch wenn sie done sind."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from services import analysis_status_service
    from services.analysis_status_service import AUDIO_STEPS
    from ui.controllers.audio_analysis import AudioAnalysisController

    done_steps = {
        "bpm_detection",
        "waveform_analysis",
        "key_detection",
        "structure_detection",
        "stem_separation",
    }

    def fake_get_status(*_args):
        status = {key: SimpleNamespace(status="done") for key in done_steps}
        status["lufs_analysis"] = SimpleNamespace(status="error")
        return status

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    ctrl.window._media_ws.btn_analyze_all.setText = MagicMock()
    ctrl.window.progress_bar.setVisible = MagicMock()
    ctrl.window.progress_bar.setRange = MagicMock()
    ctrl.window.progress_bar.setValue = MagicMock()
    ctrl.window.console_text.append = MagicMock()
    ctrl._run_next_sequential_step = MagicMock()
    monkeypatch.setattr(analysis_status_service, "infer_from_db", lambda *_args: None)
    monkeypatch.setattr(analysis_status_service, "get_status", fake_get_status)

    ctrl._run_audio_steps_for_track(7, "C:/audio.mp3", "Track", 142.0)

    step_names = [name for name, _factory in ctrl._seq_steps]
    assert len(step_names) == len(AUDIO_STEPS)


def test_b293_sequential_step_chain_calls_next_batch_track():
    """C-1 Fix: Nach letztem Step muss zum naechsten Batch-Track weitergeschaltet werden."""
    body = _slot_body(
        "ui/controllers/audio_analysis.py", "_run_next_sequential_step_inner"
    )
    assert "_process_next_batch_track" in body, (
        "C-1: _run_next_sequential_step_inner muss nach letztem Step "
        "_process_next_batch_track triggern (Track-Chain)."
    )


def test_b293_batch_queue_contains_all_checked_ids(qapp, monkeypatch):
    """I-3 Behavioral: 3 checked tracks => _batch_queue startet mit allen 3,
    _batch_total = 3. (Process-Next gemockt, kein echter DB-Hit.)"""
    import ui.controllers.audio_analysis as mod
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    # _SeqStepSignalHelper is a real QObject -> needs real parent or None.
    # Replace with a lightweight stub for behavioral testing.
    class _HelperStub:
        def __init__(self, *_a, **_kw):
            self.step_done = MagicMock()
            self.step_done.connect = MagicMock()
            self.step_done.disconnect = MagicMock()

    monkeypatch.setattr(mod, "_SeqStepSignalHelper", _HelperStub)

    # Mock settings store to return v2_default = False, so we hit the classical batch path
    mock_store = MagicMock()
    mock_store.get_nested.return_value = False
    monkeypatch.setattr("services.settings_store.get_settings_store", lambda: mock_store)

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    # Window visible -> guards pass
    ctrl.window.isVisible.return_value = True
    model = MagicMock()
    model.get_checked_ids.return_value = [10, 11, 12]
    ctrl.window.audio_pool_table.model.return_value = model

    # Block _process_next_batch_track so we can inspect state right after
    # _analyze_all_sequential setup.
    calls = []

    def fake_process_next():
        calls.append(1)

    ctrl._process_next_batch_track = fake_process_next  # type: ignore[method-assign]

    ctrl._analyze_all_sequential()

    assert ctrl._batch_total == 3, (
        f"C-1: Batch muss alle 3 gechecketen Tracks aufnehmen, got {ctrl._batch_total}."
    )
    assert list(ctrl._batch_queue) == [10, 11, 12], (
        f"C-1: Batch-Queue muss [10,11,12] sein, got {list(ctrl._batch_queue)}."
    )
    assert calls, "C-1: _process_next_batch_track muss am Ende von _analyze_all_sequential gerufen werden."


def test_audio_analysis_mood_and_spectral_actions(qapp, monkeypatch):
    """Verifies that _classify_mood and _analyze_spectral correctly instantiate and run workers."""
    from ui.controllers.audio_analysis import AudioAnalysisController
    from unittest.mock import MagicMock

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()
    ctrl.window.btn_mood_classify = MagicMock()
    ctrl.window.btn_spectral_analyze = MagicMock()
    ctrl.window.progress_bar = MagicMock()
    ctrl.window._console_append = MagicMock()
    ctrl.window.console_text.append = MagicMock()

    # Mock selection
    ctrl._get_selected_audio_track = MagicMock(return_value=(12, "/path/track.mp3", "Track Title", 120.0))

    # Mock worker dispatcher
    dispatched_worker = None
    def fake_start_worker_thread(w, **kwargs):
        nonlocal dispatched_worker
        dispatched_worker = w

    ctrl.window.worker_dispatcher._start_worker_thread = fake_start_worker_thread

    # Test Mood Classify
    ctrl._classify_mood()
    assert dispatched_worker is not None
    from workers.audio_analysis import AudioClassifyWorker
    assert isinstance(dispatched_worker, AudioClassifyWorker)
    assert dispatched_worker.audio_track_id == 12
    assert dispatched_worker.file_path == "/path/track.mp3"
    assert dispatched_worker.bpm == 120.0
    ctrl.window.btn_mood_classify.setEnabled.assert_called_with(False)
    ctrl.window.btn_mood_classify.setText.assert_called_with("Mood/Genre laeuft...")

    dispatched_worker = None
    # Test Spectral Analyse
    ctrl._analyze_spectral()
    assert dispatched_worker is not None
    from workers.audio_analysis import SpectralAnalysisWorker
    assert isinstance(dispatched_worker, SpectralAnalysisWorker)
    assert dispatched_worker.audio_track_id == 12
    assert dispatched_worker.file_path == "/path/track.mp3"
    ctrl.window.btn_spectral_analyze.setEnabled.assert_called_with(False)
    ctrl.window.btn_spectral_analyze.setText.assert_called_with("Spektral laeuft...")


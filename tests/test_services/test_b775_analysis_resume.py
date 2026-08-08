"""B-775: Batch-Analyse Resume — Clip-Filter + Step-Skips in run_full_pipeline.

Abgedeckt:
1. Kein-Auswahl-Fallback im Controller filtert vollstaendig analysierte
   Videos raus (get_completion_percent_map < 100.0).
2. run_full_pipeline: alle Steps 'done' + Artefakte vorhanden -> alles
   geskippt, keine schwere Funktion laeuft.
3. Status 'done' aber Keyframe-Dateien fehlen -> keyframe_extraction laeuft
   trotzdem (Skip nur bei real vorhandenem Artefakt).
4. force_full=True -> nichts geskippt.
5. scene_detection geskippt -> Folgeschritte bekommen aus der DB rehydrierte
   Szenen (Anzahl + Felder stimmen).

Alle schweren Schritte (SceneDetect, RAFT, FFmpeg, SigLIP, Ollama, LanceDB)
sind gemockt — kein GPU-Zugriff, keine echten Modelle, keine echte Projekt-DB.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services import video_analysis_service as vas
from services.video_analysis_service import SceneInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VIDEO_STEPS = [
    "scene_detection", "motion_scores", "keyframe_extraction",
    "siglip_embeddings", "ai_scene_caption", "scene_db_storage",
    "vector_db_storage",
]


def _fake_status(done_steps: list[str], vectors: int = 3) -> dict:
    """Baut ein get_status-Ergebnis aus SimpleNamespace-Eintraegen."""
    status = {}
    for step in done_steps:
        summary = {"vectors": vectors} if step == "vector_db_storage" else {}
        status[step] = SimpleNamespace(status="done", value_summary=summary)
    return status


@pytest.fixture
def status_stub(monkeypatch):
    """Stubbt alle analysis_status_service-Aufrufe (kein DB-Write, kein Read).

    ``get_status`` liefert das per ``set_done(...)`` konfigurierte Ergebnis.
    """
    state = {"status": {}}
    recorded: list[tuple[str, str]] = []

    ass = vas.analysis_status_service
    monkeypatch.setattr(ass, "get_status", lambda mt, mid: dict(state["status"]))
    monkeypatch.setattr(
        ass, "mark_started", lambda mt, mid, step: recorded.append((step, "started")))
    monkeypatch.setattr(
        ass, "mark_done", lambda mt, mid, step, summary=None: recorded.append((step, "done")))
    monkeypatch.setattr(
        ass, "mark_error", lambda mt, mid, step, msg: recorded.append((step, "error")))
    monkeypatch.setattr(
        ass, "mark_degraded",
        lambda mt, mid, step, reason, summary=None: recorded.append((step, "degraded")))
    monkeypatch.setattr(
        ass, "mark_cancelled", lambda mt, mid, step: recorded.append((step, "cancelled")))

    def set_done(steps: list[str], vectors: int = 3):
        state["status"] = _fake_status(steps, vectors=vectors)

    return SimpleNamespace(set_done=set_done, recorded=recorded)


@pytest.fixture
def heavy_calls(monkeypatch, tmp_path):
    """Ersetzt alle schweren Pipeline-Schritte durch Recorder-Stubs."""
    calls: list[str] = []
    fresh_scenes = [
        SceneInfo(index=0, start_time=0.0, end_time=2.0),
        SceneInfo(index=1, start_time=2.0, end_time=4.0),
    ]

    def _detect(path, threshold=27.0):
        calls.append("detect_scenes")
        return list(fresh_scenes)

    def _motion(path, sc, raft_model_device=None):
        calls.append("compute_motion_scores")
        return sc

    def _keyframes(path, sc, output_dir=None, progress_cb=None):
        calls.append("extract_keyframes")
        for s in sc:
            s.keyframe_path = str(tmp_path / f"kf_{s.index}.jpg")
        return sc

    def _embeddings(sc, progress_cb=None, siglip_model_processor=None):
        calls.append("generate_embeddings")
        return sc

    def _caption(sc, **kw):
        calls.append("analyze_scene_with_caption")
        return sc

    def _store_scenes(clip_id, sc, expected_db_url=None):
        calls.append("store_scenes_in_db")
        return True

    def _store_embeddings(path, sc, clip_id):
        calls.append("store_embeddings")
        return len(sc)

    def _enrichment(clip_id):
        calls.append("_run_structure_enrichment")

    monkeypatch.setattr(vas, "detect_scenes", _detect)
    monkeypatch.setattr(vas, "compute_motion_scores", _motion)
    monkeypatch.setattr(vas, "extract_keyframes", _keyframes)
    monkeypatch.setattr(vas, "generate_embeddings", _embeddings)
    monkeypatch.setattr(vas, "analyze_scene_with_caption", _caption)
    monkeypatch.setattr(vas, "store_scenes_in_db", _store_scenes)
    monkeypatch.setattr(vas, "store_embeddings", _store_embeddings)
    monkeypatch.setattr(vas, "_run_structure_enrichment", _enrichment)
    return calls


def _add_db_scenes(db_session, clip_id: int) -> None:
    """Legt 2 Szenen-Rows an, wie sie store_scenes_in_db hinterlaesst."""
    import database

    db_session.add(database.Scene(
        video_clip_id=clip_id, start_time=0.0, end_time=2.0, energy=0.4,
        label="Scene 0", ai_caption={"description": "a"}, ai_mood="calm",
        ai_tags=["t1"],
    ))
    db_session.add(database.Scene(
        video_clip_id=clip_id, start_time=2.0, end_time=4.0, energy=0.9,
        label="Scene 1", ai_caption={"description": "b"}, ai_mood="energetic",
        ai_tags=["t2"],
    ))
    db_session.commit()


def _make_video(tmp_path):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"not-a-real-video")
    return video_file


def _write_keyframes(monkeypatch, tmp_path, stem: str, count: int):
    """Legt Keyframe-Dateien im gefakten Keyframe-Dir an (B-775 Artefakt-Check)."""
    kf_dir = tmp_path / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vas, "_keyframe_dir", lambda: kf_dir)
    for i in range(count):
        (kf_dir / f"{stem}_scene{i:04d}.jpg").write_bytes(b"jpg")
    return kf_dir


# ---------------------------------------------------------------------------
# Test 1 — Controller-Fallback filtert fertige Videos
# ---------------------------------------------------------------------------

class _FakeConsole:
    def __init__(self):
        self.lines: list[str] = []

    def append(self, text):
        self.lines.append(str(text))


def test_fallback_filters_fully_analyzed_videos(monkeypatch):
    """3 Videos, 1 komplett done -> Batch enthaelt nur die 2 unfertigen."""
    from ui.controllers import video_analysis as va_mod

    # Fallback-Quellen stubben (lazy imports im Controller)
    import services.ingest_service as ingest_service
    monkeypatch.setattr(ingest_service, "get_all_video", lambda: [
        {"id": 1, "title": "A"}, {"id": 2, "title": "B"}, {"id": 3, "title": "C"},
    ])
    import services.analysis_status_service as ass
    monkeypatch.setattr(
        ass, "get_completion_percent_map",
        lambda mt, ids: {1: 100.0, 2: 40.0, 3: 0.0},
    )

    captured = {}

    class _FakeSignal:
        def connect(self, *a, **kw):
            pass

    class _FakeWorker:
        def __init__(self, batch=None, force_full=True, **kw):
            captured["batch"] = batch
            captured["force_full"] = force_full
            self.progress = _FakeSignal()
            self.finished = _FakeSignal()
            self.error = _FakeSignal()
            self.task_id = None

    monkeypatch.setattr(va_mod, "VideoAnalysisPipelineWorker", _FakeWorker)
    monkeypatch.setattr(
        va_mod, "_task_manager",
        SimpleNamespace(create_task=lambda *a, **kw: SimpleNamespace(task_id="t1")),
    )

    # Fake-Window: keine Checkboxen, keine Selektion -> Fallback-Pfad
    model = SimpleNamespace(get_checked_ids=lambda: [])
    view = SimpleNamespace(
        model=lambda: model,
        selectionModel=lambda: SimpleNamespace(selectedRows=lambda: []),
    )
    console = _FakeConsole()
    window = SimpleNamespace(
        video_pool_table=view,
        console_text=console,
        status_bar=SimpleNamespace(showMessage=lambda *a, **kw: None),
        btn_video_pipeline=SimpleNamespace(
            setEnabled=lambda *a: None, setText=lambda *a: None),
        progress_bar=SimpleNamespace(setVisible=lambda *a: None),
        worker_dispatcher=SimpleNamespace(_start_worker_thread=lambda w: None),
    )

    controller = object.__new__(va_mod.VideoAnalysisController)
    controller.window = window

    controller._start_video_pipeline()

    assert captured["batch"] == [(2, "B"), (3, "C")], captured
    assert captured["force_full"] is False
    assert any(
        "1 von 3 Videos bereits vollstaendig analysiert — starte 2 unfertige." in line
        for line in console.lines
    ), console.lines


def test_fallback_all_done_starts_nothing(monkeypatch):
    """Alle Videos fertig -> kein Worker-Start, klare Meldung."""
    from ui.controllers import video_analysis as va_mod

    import services.ingest_service as ingest_service
    monkeypatch.setattr(ingest_service, "get_all_video", lambda: [
        {"id": 1, "title": "A"}, {"id": 2, "title": "B"},
    ])
    import services.analysis_status_service as ass
    monkeypatch.setattr(
        ass, "get_completion_percent_map", lambda mt, ids: {1: 100.0, 2: 100.0})

    started = []
    monkeypatch.setattr(
        va_mod, "VideoAnalysisPipelineWorker",
        lambda **kw: started.append(kw))

    model = SimpleNamespace(get_checked_ids=lambda: [])
    view = SimpleNamespace(
        model=lambda: model,
        selectionModel=lambda: SimpleNamespace(selectedRows=lambda: []),
    )
    console = _FakeConsole()
    window = SimpleNamespace(
        video_pool_table=view,
        console_text=console,
        status_bar=SimpleNamespace(showMessage=lambda *a, **kw: None),
    )

    controller = object.__new__(va_mod.VideoAnalysisController)
    controller.window = window

    controller._start_video_pipeline()

    assert started == []
    assert any(
        "Alle 2 Videos bereits vollstaendig analysiert" in line
        for line in console.lines
    ), console.lines


# ---------------------------------------------------------------------------
# Test 2 — alles done + Artefakte vorhanden -> Voll-Skip
# ---------------------------------------------------------------------------

def test_pipeline_all_done_skips_everything(
    monkeypatch, tmp_path, test_engine, db_session, video_clip,
    status_stub, heavy_calls,
):
    video_file = _make_video(tmp_path)
    _add_db_scenes(db_session, video_clip.id)
    _write_keyframes(monkeypatch, tmp_path, video_file.stem, count=2)
    status_stub.set_done(VIDEO_STEPS, vectors=5)

    result = vas.run_full_pipeline(str(video_file), video_clip.id)

    assert heavy_calls == [], f"Schwere Schritte liefen trotz Voll-Skip: {heavy_calls}"
    assert status_stub.recorded == [], (
        f"Status-Writes trotz Voll-Skip: {status_stub.recorded}"
    )
    assert len(result.scenes) == 2
    assert result.total_duration == 4.0
    assert result.embeddings_stored == 5  # aus value_summary rehydriert
    assert result.captions_skipped is True


# ---------------------------------------------------------------------------
# Test 3 — Status done, aber Keyframe-Dateien fehlen -> Schritt laeuft doch
# ---------------------------------------------------------------------------

def test_pipeline_reruns_keyframes_when_files_missing(
    monkeypatch, tmp_path, test_engine, db_session, video_clip,
    status_stub, heavy_calls,
):
    video_file = _make_video(tmp_path)
    _add_db_scenes(db_session, video_clip.id)
    # Keyframe-Dir existiert, aber KEINE Dateien -> Status luegt.
    _write_keyframes(monkeypatch, tmp_path, video_file.stem, count=0)
    status_stub.set_done(VIDEO_STEPS)

    vas.run_full_pipeline(str(video_file), video_clip.id)

    assert "extract_keyframes" in heavy_calls, heavy_calls
    # Szenen kamen aus der DB, SigLIP/Vector bleiben geskippt (beide done).
    assert "detect_scenes" not in heavy_calls
    assert "generate_embeddings" not in heavy_calls
    assert "store_embeddings" not in heavy_calls


# ---------------------------------------------------------------------------
# Test 4 — force_full=True skippt nichts
# ---------------------------------------------------------------------------

def test_pipeline_force_full_runs_all_steps(
    monkeypatch, tmp_path, test_engine, db_session, video_clip,
    status_stub, heavy_calls,
):
    video_file = _make_video(tmp_path)
    _add_db_scenes(db_session, video_clip.id)
    _write_keyframes(monkeypatch, tmp_path, video_file.stem, count=2)
    status_stub.set_done(VIDEO_STEPS)

    result = vas.run_full_pipeline(str(video_file), video_clip.id, force_full=True)

    expected = [
        "detect_scenes", "compute_motion_scores", "extract_keyframes",
        "generate_embeddings", "analyze_scene_with_caption",
        "store_scenes_in_db", "store_embeddings", "_run_structure_enrichment",
    ]
    assert heavy_calls == expected, heavy_calls
    assert result.captions_skipped is False


# ---------------------------------------------------------------------------
# Test 5 — scene_detection geskippt -> Folgeschritt bekommt DB-Szenen
# ---------------------------------------------------------------------------

def test_pipeline_scene_skip_rehydrates_scenes_for_next_steps(
    monkeypatch, tmp_path, test_engine, db_session, video_clip,
    status_stub, heavy_calls,
):
    video_file = _make_video(tmp_path)
    _add_db_scenes(db_session, video_clip.id)
    _write_keyframes(monkeypatch, tmp_path, video_file.stem, count=2)
    # NUR scene_detection done -> alle Folgeschritte muessen laufen und die
    # rehydrierten Szenen sehen.
    status_stub.set_done(["scene_detection"])

    seen_by_motion: list[SceneInfo] = []

    def _motion_capture(path, sc, raft_model_device=None):
        heavy_calls.append("compute_motion_scores")
        seen_by_motion.extend(sc)
        return sc

    monkeypatch.setattr(vas, "compute_motion_scores", _motion_capture)

    result = vas.run_full_pipeline(str(video_file), video_clip.id)

    assert "detect_scenes" not in heavy_calls, heavy_calls
    assert "compute_motion_scores" in heavy_calls
    assert "store_scenes_in_db" in heavy_calls

    assert len(seen_by_motion) == 2
    s0, s1 = seen_by_motion
    assert (s0.index, s0.start_time, s0.end_time) == (0, 0.0, 2.0)
    assert (s1.index, s1.start_time, s1.end_time) == (1, 2.0, 4.0)
    assert s0.motion_score == pytest.approx(0.4)  # aus Scene.energy rehydriert
    assert s1.motion_score == pytest.approx(0.9)
    assert s0.ai_caption == {"description": "a"}
    assert s1.ai_mood == "energetic"

    assert len(result.scenes) == 2
    assert result.total_duration == 4.0

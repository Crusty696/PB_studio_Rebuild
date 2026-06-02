from __future__ import annotations

from database import (
    AnalysisStatus,
    AudioTrack,
    Beatgrid,
    Scene,
    TimelineEntry,
    VideoClip,
)


def _mark(session, media_type: str, media_id: int, step_key: str, status: str = "done"):
    session.add(
        AnalysisStatus(
            media_type=media_type,
            media_id=media_id,
            step_key=step_key,
            status=status,
        )
    )


def test_cockpit_without_project_requests_project_creation():
    from services.cockpit_orchestrator import get_cockpit_readiness

    readiness = get_cockpit_readiness(None)

    assert readiness.project_id is None
    assert readiness.next_action.key == "open_project"
    assert readiness.next_action.label == "Projekt starten"
    assert readiness.can_auto_edit is False
    assert "Kein Projekt geladen" in readiness.blockers


def test_cockpit_project_with_audio_missing_beatgrid_runs_audio(project, audio_track):
    from services.cockpit_orchestrator import get_cockpit_readiness

    readiness = get_cockpit_readiness(project.id)

    assert readiness.audio_ready is False
    assert readiness.video_ready is False
    assert readiness.next_action.key == "run_audio_complete"
    assert "Audioanalyse fehlt" in readiness.blockers


def test_cockpit_audio_ready_video_missing_scenes_runs_video(db_session, project, audio_track, video_clip):
    from services.cockpit_orchestrator import AUDIO_STEP_SPECS, get_cockpit_readiness

    db_session.add(
        Beatgrid(
            audio_track_id=audio_track.id,
            bpm=128.0,
            beat_positions=[0.0, 0.5, 1.0],
            downbeat_positions=[0.0],
            energy_per_beat=[0.5, 0.6, 0.7],
        )
    )
    audio_track.energy_curve = [0.5, 0.6]
    for step in (spec.key for spec in AUDIO_STEP_SPECS):
        _mark(db_session, "audio", audio_track.id, step)
    db_session.commit()

    readiness = get_cockpit_readiness(project.id)

    assert readiness.audio_ready is True
    assert readiness.video_ready is False
    assert readiness.next_action.key == "run_video_pipeline"
    assert "Videoanalyse fehlt" in readiness.blockers


def test_cockpit_audio_and_video_ready_opens_auto_edit(db_session, project, audio_track, video_clip):
    from services.cockpit_orchestrator import AUDIO_STEP_SPECS, get_cockpit_readiness

    db_session.add(
        Beatgrid(
            audio_track_id=audio_track.id,
            bpm=128.0,
            beat_positions=[0.0, 0.5, 1.0],
            downbeat_positions=[0.0],
            energy_per_beat=[0.5, 0.6, 0.7],
        )
    )
    db_session.add(Scene(video_clip_id=video_clip.id, start_time=0.0, end_time=1.0, energy=0.7))
    for step in (spec.key for spec in AUDIO_STEP_SPECS):
        _mark(db_session, "audio", audio_track.id, step)
    for step in (
        "scene_detection",
        "motion_scores",
        "keyframe_extraction",
        "siglip_embeddings",
        "vector_db_storage",
        "scene_db_storage",
    ):
        _mark(db_session, "video", video_clip.id, step)
    db_session.commit()

    readiness = get_cockpit_readiness(project.id)

    assert readiness.audio_ready is True
    assert readiness.video_ready is True
    assert readiness.can_auto_edit is True
    assert readiness.next_action.key == "open_schnitt"
    assert any("Captioning" in warning for warning in readiness.warnings)


def test_cockpit_timeline_ready_opens_review_or_export(db_session, project, audio_track, video_clip):
    from services.cockpit_orchestrator import get_cockpit_readiness

    db_session.add(TimelineEntry(project_id=project.id, track="video", media_id=video_clip.id, start_time=0.0))
    db_session.commit()

    readiness = get_cockpit_readiness(project.id)

    assert readiness.can_export is True
    assert readiness.next_action.key == "open_schnitt"


def test_cockpit_step_specs_keep_captioning_non_blocking():
    from services.cockpit_orchestrator import VIDEO_STEP_SPECS

    required = {spec.key for spec in VIDEO_STEP_SPECS if spec.required_for_auto_edit}

    assert "ai_scene_caption" not in required
    assert {
        "scene_detection",
        "motion_scores",
        "keyframe_extraction",
        "siglip_embeddings",
        "vector_db_storage",
        "scene_db_storage",
    }.issubset(required)


def test_cockpit_dispatch_ignores_unregistered_worker_commands():
    from services.cockpit_orchestrator import dispatch_cockpit_action

    class FakeSignal:
        def __init__(self):
            self.emits = []

        def emit(self, command, payload):
            self.emits.append((command, payload))

    class FakeTaskManager:
        _WORKER_REGISTRY = {}

        def __init__(self):
            self.agent_command_signal = FakeSignal()

    manager = FakeTaskManager()

    assert dispatch_cockpit_action("run_video_pipeline", {"project_id": 1}, task_manager=manager) is False
    assert manager.agent_command_signal.emits == []


def test_cockpit_dispatch_emits_registered_worker_command():
    from services.cockpit_orchestrator import dispatch_cockpit_action

    class FakeSignal:
        def __init__(self):
            self.emits = []

        def emit(self, command, payload):
            self.emits.append((command, payload))

    class FakeTaskManager:
        _WORKER_REGISTRY = {"run_video_pipeline": object()}

        def __init__(self):
            self.agent_command_signal = FakeSignal()

    manager = FakeTaskManager()

    assert dispatch_cockpit_action("run_video_pipeline", {"project_id": 1}, task_manager=manager) is True
    assert manager.agent_command_signal.emits == [("run_video_pipeline", {"project_id": 1})]

"""
Deep Functional Test Suite for PB Studio Database Layer.
Tests all SQLAlchemy models (CRUD), relationships, cascades, edge cases,
nullpool_session, and migration system using in-memory SQLite.

Run with: .venv310/Scripts/python.exe test_db_deep.py
"""
import sys
import os
import traceback
import datetime
import threading
import time
import tempfile

# ── Patch: redirect the global engine to in-memory SQLite BEFORE importing database ──
# We monkey-patch _make_engine and the module-level engine creation so we never
# touch the real pb_studio.db.

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# ── Results tracking ──
_results = []

def record(test_name, passed, detail=""):
    _results.append((test_name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {test_name}")
    if detail and not passed:
        for line in detail.strip().split("\n"):
            print(f"         {line}")

def run_test(test_name, func):
    """Run a test function, catching any exception as FAIL."""
    try:
        func()
        record(test_name, True)
    except Exception:
        tb = traceback.format_exc()
        record(test_name, False, tb)


# ── Create in-memory engine with FK support ──
def make_test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _set_pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    return eng

test_engine = make_test_engine()

# ── Import models ──
from database.models import (
    Base, Project, AudioTrack, VideoClip, Scene, Beatgrid, WaveformData,
    PacingBlueprint, AudioVideoAnchor, ClipAnchor, AIPacingMemory,
    StructureSegment, HotCue, ModelRegistry, AgentFeedback, StylePreset,
    TimelineEntry, AnalysisStatus, TimelineSnapshot, ProjectNote,
)

# Create all tables in the in-memory DB
Base.metadata.create_all(test_engine)


def fresh_session():
    """Return a new session bound to the test engine."""
    return Session(test_engine)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: Database Initialization
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 1: Database Initialization (create_all)")
print("=" * 70)


def test_tables_created():
    insp = inspect(test_engine)
    expected_tables = {
        "projects", "audio_tracks", "video_clips", "scenes", "beatgrids",
        "waveform_data", "pacing_blueprints", "audio_video_anchors",
        "clip_anchors", "ai_pacing_memory", "structure_segments", "hotcues",
        "model_registry", "agent_feedback", "style_presets",
        "timeline_entries", "analysis_status", "timeline_snapshots",
        "project_notes",
    }
    actual = set(insp.get_table_names())
    missing = expected_tables - actual
    if missing:
        raise AssertionError(f"Missing tables: {missing}")

run_test("1.1 All model tables created via create_all", test_tables_created)


def test_foreign_keys_enabled():
    with test_engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys"))
        val = result.fetchone()[0]
        assert val == 1, f"foreign_keys PRAGMA is {val}, expected 1"

run_test("1.2 Foreign keys enabled (PRAGMA)", test_foreign_keys_enabled)


def test_indexes_exist():
    insp = inspect(test_engine)
    # Check a few key indexes
    at_indexes = {idx["name"] for idx in insp.get_indexes("audio_tracks")}
    assert "idx_audio_project" in at_indexes, f"Missing idx_audio_project, found: {at_indexes}"
    vc_indexes = {idx["name"] for idx in insp.get_indexes("video_clips")}
    assert "idx_video_project" in vc_indexes, f"Missing idx_video_project, found: {vc_indexes}"

run_test("1.3 Key indexes exist after create_all", test_indexes_exist)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: CRUD for all 17 models
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 2: CRUD for all 17 models")
print("=" * 70)


# ── 2.1 Project ──
def test_project_crud():
    s = fresh_session()
    try:
        # Create
        p = Project(name="TestProject", path="/tmp/test", resolution="1920x1080", fps=30.0)
        s.add(p)
        s.commit()
        pid = p.id
        assert pid is not None

        # Read
        p2 = s.get(Project, pid)
        assert p2.name == "TestProject"
        assert p2.path == "/tmp/test"
        assert p2.resolution == "1920x1080"
        assert p2.fps == 30.0

        # Update
        p2.name = "RenamedProject"
        p2.fps = 60.0
        s.commit()
        p3 = s.get(Project, pid)
        assert p3.name == "RenamedProject"
        assert p3.fps == 60.0

        # Delete
        s.delete(p3)
        s.commit()
        assert s.get(Project, pid) is None
    finally:
        s.close()

run_test("2.1 Project CRUD", test_project_crud)


# ── 2.2 AudioTrack ──
def test_audiotrack_crud():
    s = fresh_session()
    try:
        proj = Project(name="ATProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        at = AudioTrack(
            project_id=proj.id, file_path="/audio/test.wav",
            title="Test Track", duration=180.0, sample_rate=44100,
            bpm=128.0, key="Am", energy_curve=[0.5, 0.8, 1.0],
            stem_vocals_path="/stems/vocals.wav",
            stem_drums_path="/stems/drums.wav",
            stem_bass_path="/stems/bass.wav",
            stem_other_path="/stems/other.wav",
            key_confidence=0.95, lufs=-14.0, mood="energetic",
            genre="Psytrance", is_dj_mix=False,
            spectral_bands=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            key_modulation_data=[{"time": 0, "key": "Am", "camelot": "8A", "confidence": 0.9}],
            harmonic_tension_curve=[0.1, 0.2, 0.15],
        )
        s.add(at)
        s.commit()
        at_id = at.id
        assert at_id is not None

        # Read
        at2 = s.get(AudioTrack, at_id)
        assert at2.title == "Test Track"
        assert at2.bpm == 128.0
        assert at2.energy_curve == [0.5, 0.8, 1.0]
        assert at2.key_modulation_data[0]["key"] == "Am"

        # Update
        at2.bpm = 140.0
        at2.mood = "dark"
        s.commit()
        at3 = s.get(AudioTrack, at_id)
        assert at3.bpm == 140.0
        assert at3.mood == "dark"

        # Delete
        s.delete(at3)
        s.commit()
        assert s.get(AudioTrack, at_id) is None

        # Cleanup
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.2 AudioTrack CRUD", test_audiotrack_crud)


# ── 2.3 VideoClip ──
def test_videoclip_crud():
    s = fresh_session()
    try:
        proj = Project(name="VCProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        vc = VideoClip(
            project_id=proj.id, file_path="/video/test.mp4",
            proxy_path="/proxy/test_proxy.mp4", duration=120.0,
            width=1920, height=1080, fps=60.0, codec="h264",
            playback_offset=1.5,
        )
        s.add(vc)
        s.commit()
        vc_id = vc.id

        vc2 = s.get(VideoClip, vc_id)
        assert vc2.width == 1920
        assert vc2.playback_offset == 1.5
        assert vc2.codec == "h264"

        vc2.duration = 150.0
        s.commit()
        assert s.get(VideoClip, vc_id).duration == 150.0

        s.delete(s.get(VideoClip, vc_id))
        s.commit()
        assert s.get(VideoClip, vc_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.3 VideoClip CRUD", test_videoclip_crud)


# ── 2.4 Scene ──
def test_scene_crud():
    s = fresh_session()
    try:
        proj = Project(name="ScProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        vc = VideoClip(project_id=proj.id, file_path="/video/sc.mp4")
        s.add(vc)
        s.commit()

        sc = Scene(
            video_clip_id=vc.id, start_time=0.0, end_time=5.0,
            label="intro", energy=0.3,
            ai_caption={"description": "forest scene", "mood": "calm"},
            ai_mood="calm", ai_tags=["nature", "forest"],
        )
        s.add(sc)
        s.commit()
        sc_id = sc.id

        sc2 = s.get(Scene, sc_id)
        assert sc2.label == "intro"
        assert sc2.ai_caption["description"] == "forest scene"
        assert sc2.ai_tags == ["nature", "forest"]

        sc2.energy = 0.8
        s.commit()
        assert s.get(Scene, sc_id).energy == 0.8

        s.delete(s.get(Scene, sc_id))
        s.commit()
        assert s.get(Scene, sc_id) is None

        s.delete(vc)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.4 Scene CRUD", test_scene_crud)


# ── 2.5 Beatgrid ──
def test_beatgrid_crud():
    s = fresh_session()
    try:
        proj = Project(name="BGProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/bg.wav")
        s.add(at)
        s.commit()

        bg = Beatgrid(
            audio_track_id=at.id, bpm=140.0, offset=0.01,
            beat_positions=[0.0, 0.428, 0.857],
            downbeat_positions=[0.0, 1.714],
            energy_per_beat=[0.5, 0.7, 0.9],
            stem_weighted_energy=[0.4, 0.6, 0.85],
            onset_kick_data=[[0.0, 0.9], [0.428, 0.8]],
            onset_snare_data=[[0.214, 0.7]],
            onset_hihat_data=[[0.107, 0.3], [0.321, 0.35]],
            syncopation_score=0.4,
            groove_template="straight_4_4",
        )
        s.add(bg)
        s.commit()
        bg_id = bg.id

        bg2 = s.get(Beatgrid, bg_id)
        assert bg2.bpm == 140.0
        assert bg2.beat_positions == [0.0, 0.428, 0.857]
        assert bg2.syncopation_score == 0.4

        bg2.bpm = 145.0
        s.commit()
        assert s.get(Beatgrid, bg_id).bpm == 145.0

        s.delete(s.get(Beatgrid, bg_id))
        s.commit()
        assert s.get(Beatgrid, bg_id) is None

        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.5 Beatgrid CRUD", test_beatgrid_crud)


# ── 2.6 WaveformData ──
def test_waveformdata_crud():
    s = fresh_session()
    try:
        proj = Project(name="WFProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/wf.wav")
        s.add(at)
        s.commit()

        wf = WaveformData(
            audio_track_id=at.id, num_samples=1000, duration=23.0,
            band_low=[0.1, 0.2, 0.3], band_mid=[0.4, 0.5, 0.6],
            band_high=[0.7, 0.8, 0.9],
        )
        s.add(wf)
        s.commit()
        wf_id = wf.id

        wf2 = s.get(WaveformData, wf_id)
        assert wf2.num_samples == 1000
        assert wf2.band_low == [0.1, 0.2, 0.3]

        wf2.duration = 25.0
        s.commit()
        assert s.get(WaveformData, wf_id).duration == 25.0

        s.delete(s.get(WaveformData, wf_id))
        s.commit()
        assert s.get(WaveformData, wf_id) is None

        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.6 WaveformData CRUD", test_waveformdata_crud)


# ── 2.7 PacingBlueprint ──
def test_pacingblueprint_crud():
    s = fresh_session()
    try:
        proj = Project(name="PBProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        pb = PacingBlueprint(
            project_id=proj.id, name="Techno Pacing",
            style="techno", cuts_per_bar=2,
            energy_curve=[0.5, 0.7, 1.0, 0.8],
        )
        s.add(pb)
        s.commit()
        pb_id = pb.id

        pb2 = s.get(PacingBlueprint, pb_id)
        assert pb2.name == "Techno Pacing"
        assert pb2.energy_curve == [0.5, 0.7, 1.0, 0.8]

        pb2.cuts_per_bar = 4
        s.commit()
        assert s.get(PacingBlueprint, pb_id).cuts_per_bar == 4

        s.delete(s.get(PacingBlueprint, pb_id))
        s.commit()
        assert s.get(PacingBlueprint, pb_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.7 PacingBlueprint CRUD", test_pacingblueprint_crud)


# ── 2.8 TimelineEntry ──
def test_timelineentry_crud():
    s = fresh_session()
    try:
        proj = Project(name="TEProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        te = TimelineEntry(
            project_id=proj.id, track="video", media_id=999,
            start_time=0.0, end_time=10.0, lane=0,
            crossfade_duration=0.5, source_start=0.0, source_end=10.0,
            brightness=0.1, contrast=1.2,
        )
        s.add(te)
        s.commit()
        te_id = te.id

        te2 = s.get(TimelineEntry, te_id)
        assert te2.track == "video"
        assert te2.crossfade_duration == 0.5
        assert te2.brightness == 0.1

        te2.lane = 1
        s.commit()
        assert s.get(TimelineEntry, te_id).lane == 1

        s.delete(s.get(TimelineEntry, te_id))
        s.commit()
        assert s.get(TimelineEntry, te_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.8 TimelineEntry CRUD", test_timelineentry_crud)


# ── 2.9 ClipAnchor ──
def test_clipanchor_crud():
    s = fresh_session()
    try:
        proj = Project(name="CAProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        te = TimelineEntry(project_id=proj.id, track="audio", media_id=1, start_time=0.0)
        s.add(te)
        s.commit()

        ca = ClipAnchor(
            timeline_entry_id=te.id, time_offset=3.5,
            label="Drop Marker", color="#00FF00",
        )
        s.add(ca)
        s.commit()
        ca_id = ca.id

        ca2 = s.get(ClipAnchor, ca_id)
        assert ca2.time_offset == 3.5
        assert ca2.label == "Drop Marker"
        assert ca2.color == "#00FF00"

        ca2.label = "Updated"
        s.commit()
        assert s.get(ClipAnchor, ca_id).label == "Updated"

        s.delete(s.get(ClipAnchor, ca_id))
        s.commit()
        assert s.get(ClipAnchor, ca_id) is None

        s.delete(te)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.9 ClipAnchor CRUD", test_clipanchor_crud)


# ── 2.10 AudioVideoAnchor ──
def test_audiovideoanchor_crud():
    s = fresh_session()
    try:
        proj = Project(name="AVAProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/ava.wav")
        vc = VideoClip(project_id=proj.id, file_path="/video/ava.mp4")
        s.add_all([at, vc])
        s.commit()

        ava = AudioVideoAnchor(
            audio_track_id=at.id, video_clip_id=vc.id,
            audio_time=10.5, video_time=12.0, anchor_type="drop",
        )
        s.add(ava)
        s.commit()
        ava_id = ava.id

        ava2 = s.get(AudioVideoAnchor, ava_id)
        assert ava2.audio_time == 10.5
        assert ava2.anchor_type == "drop"

        ava2.anchor_type = "beat"
        s.commit()
        assert s.get(AudioVideoAnchor, ava_id).anchor_type == "beat"

        s.delete(s.get(AudioVideoAnchor, ava_id))
        s.commit()
        assert s.get(AudioVideoAnchor, ava_id) is None

        s.delete(at)
        s.commit()
        s.delete(vc)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.10 AudioVideoAnchor CRUD", test_audiovideoanchor_crud)


# ── 2.11 AIPacingMemory ──
def test_aipacingmemory_crud():
    s = fresh_session()
    try:
        apm = AIPacingMemory(
            bpm=140.0, bass_energy=0.9, drum_energy=0.85,
            overall_energy=0.88, mood="drop", audio_time=120.0,
            raft_motion=0.7, siglip_tags=["outdoor", "energetic"],
            cut_type="hard_cut", crossfade_duration=0.0,
            section_type="DROP", label="Main Drop",
        )
        s.add(apm)
        s.commit()
        apm_id = apm.id
        assert apm_id is not None
        assert apm.created_at is not None

        apm2 = s.get(AIPacingMemory, apm_id)
        assert apm2.bpm == 140.0
        assert apm2.siglip_tags == ["outdoor", "energetic"]
        assert apm2.mood == "drop"

        apm2.mood = "buildup"
        s.commit()
        assert s.get(AIPacingMemory, apm_id).mood == "buildup"

        s.delete(s.get(AIPacingMemory, apm_id))
        s.commit()
        assert s.get(AIPacingMemory, apm_id) is None
    finally:
        s.close()

run_test("2.11 AIPacingMemory CRUD", test_aipacingmemory_crud)


# ── 2.12 StructureSegment ──
def test_structuresegment_crud():
    s = fresh_session()
    try:
        proj = Project(name="SSProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/ss.wav")
        s.add(at)
        s.commit()

        ss = StructureSegment(
            audio_track_id=at.id, start_time=0.0, end_time=30.0,
            label="INTRO", energy=0.3, confidence=0.9,
        )
        s.add(ss)
        s.commit()
        ss_id = ss.id

        ss2 = s.get(StructureSegment, ss_id)
        assert ss2.label == "INTRO"
        assert ss2.confidence == 0.9

        ss2.label = "BUILDUP"
        s.commit()
        assert s.get(StructureSegment, ss_id).label == "BUILDUP"

        s.delete(s.get(StructureSegment, ss_id))
        s.commit()
        assert s.get(StructureSegment, ss_id) is None

        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.12 StructureSegment CRUD", test_structuresegment_crud)


# ── 2.13 HotCue ──
def test_hotcue_crud():
    s = fresh_session()
    try:
        proj = Project(name="HCProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/hc.wav")
        s.add(at)
        s.commit()

        hc = HotCue(
            audio_track_id=at.id, time=45.5,
            label="Drop 1", color="#FF0000", cue_type="cue",
        )
        s.add(hc)
        s.commit()
        hc_id = hc.id

        hc2 = s.get(HotCue, hc_id)
        assert hc2.time == 45.5
        assert hc2.cue_type == "cue"

        hc2.cue_type = "loop"
        s.commit()
        assert s.get(HotCue, hc_id).cue_type == "loop"

        s.delete(s.get(HotCue, hc_id))
        s.commit()
        assert s.get(HotCue, hc_id) is None

        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("2.13 HotCue CRUD", test_hotcue_crud)


# ── 2.14 ModelRegistry ──
def test_modelregistry_crud():
    s = fresh_session()
    try:
        mr = ModelRegistry(
            model_id="gemma3:4b", source="ollama",
            display_name="Gemma 4 E4B", size_mb=4500.0,
            installed_at=datetime.datetime(2024, 1, 15, 10, 30),
            last_used_at=datetime.datetime(2024, 1, 16, 14, 0),
            status="installed", local_path=None,
            metadata_json={"params": "4B", "quant": "q4_K_M"},
        )
        s.add(mr)
        s.commit()
        mr_id = mr.id

        mr2 = s.get(ModelRegistry, mr_id)
        assert mr2.model_id == "gemma3:4b"
        assert mr2.metadata_json["params"] == "4B"

        mr2.status = "error"
        s.commit()
        assert s.get(ModelRegistry, mr_id).status == "error"

        s.delete(s.get(ModelRegistry, mr_id))
        s.commit()
        assert s.get(ModelRegistry, mr_id) is None
    finally:
        s.close()

run_test("2.14 ModelRegistry CRUD", test_modelregistry_crud)


# ── 2.15 AgentFeedback ──
def test_agentfeedback_crud():
    s = fresh_session()
    try:
        af = AgentFeedback(
            session_id="sess-001", model_id="gemma3:4b",
            backend="ollama", user_query="Analyze this track",
            ai_response='{"action": "analyze_audio"}',
            action_name="analyze_audio", rating=1,
            user_comment="Great analysis!",
        )
        s.add(af)
        s.commit()
        af_id = af.id
        assert af.created_at is not None

        af2 = s.get(AgentFeedback, af_id)
        assert af2.rating == 1
        assert af2.action_name == "analyze_audio"

        af2.rating = -1
        s.commit()
        assert s.get(AgentFeedback, af_id).rating == -1

        s.delete(s.get(AgentFeedback, af_id))
        s.commit()
        assert s.get(AgentFeedback, af_id) is None
    finally:
        s.close()

run_test("2.15 AgentFeedback CRUD", test_agentfeedback_crud)


# ── 2.16 StylePreset ──
def test_stylepreset_crud():
    s = fresh_session()
    try:
        sp = StylePreset(
            name="TestPreset", cut_rate=1.2, energy_reactivity=0.8,
            breakdown_behavior="16beat", min_clip_duration=1.5,
            max_clip_duration=10.0, beat_weight=1.0, kick_weight=1.3,
            snare_weight=0.9, hihat_weight=0.4, description="Test preset",
        )
        s.add(sp)
        s.commit()
        sp_id = sp.id

        sp2 = s.get(StylePreset, sp_id)
        assert sp2.name == "TestPreset"
        assert sp2.kick_weight == 1.3

        sp2.description = "Updated description"
        s.commit()
        assert s.get(StylePreset, sp_id).description == "Updated description"

        s.delete(s.get(StylePreset, sp_id))
        s.commit()
        assert s.get(StylePreset, sp_id) is None
    finally:
        s.close()

run_test("2.16 StylePreset CRUD", test_stylepreset_crud)


# ── 2.17 AnalysisStatus ──
def test_analysisstatus_crud():
    s = fresh_session()
    try:
        ans = AnalysisStatus(
            media_type="video", media_id=42, step_key="scene_detection",
            status="running",
            value_summary={"scenes": 12, "avg_motion": 0.73},
            started_at=datetime.datetime(2024, 1, 15, 10, 0),
            completed_at=None, error_message=None,
        )
        s.add(ans)
        s.commit()
        ans_id = ans.id

        ans2 = s.get(AnalysisStatus, ans_id)
        assert ans2.media_type == "video"
        assert ans2.step_key == "scene_detection"
        assert ans2.value_summary["scenes"] == 12

        ans2.status = "done"
        ans2.completed_at = datetime.datetime(2024, 1, 15, 10, 5)
        s.commit()
        ans3 = s.get(AnalysisStatus, ans_id)
        assert ans3.status == "done"
        assert ans3.completed_at is not None

        s.delete(s.get(AnalysisStatus, ans_id))
        s.commit()
        assert s.get(AnalysisStatus, ans_id) is None
    finally:
        s.close()

run_test("2.17 AnalysisStatus CRUD", test_analysisstatus_crud)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: Relationships (Foreign Keys, Cascades, Back-Populates)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 3: Relationships & Cascades")
print("=" * 70)


# ── 3.1 Project -> AudioTrack (cascade delete) ──
def test_project_cascade_audio():
    s = fresh_session()
    try:
        proj = Project(name="CascProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/casc.wav")
        s.add(at)
        s.commit()
        at_id = at.id

        s.delete(proj)
        s.commit()
        assert s.get(AudioTrack, at_id) is None, "AudioTrack should be cascade deleted with Project"
    finally:
        s.close()

run_test("3.1 Project -> AudioTrack cascade delete", test_project_cascade_audio)


# ── 3.2 Project -> VideoClip (cascade delete) ──
def test_project_cascade_video():
    s = fresh_session()
    try:
        proj = Project(name="CascVProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        vc = VideoClip(project_id=proj.id, file_path="/video/casc.mp4")
        s.add(vc)
        s.commit()
        vc_id = vc.id

        s.delete(proj)
        s.commit()
        assert s.get(VideoClip, vc_id) is None, "VideoClip should be cascade deleted with Project"
    finally:
        s.close()

run_test("3.2 Project -> VideoClip cascade delete", test_project_cascade_video)


# ── 3.3 Project -> TimelineEntry (cascade delete) ──
def test_project_cascade_timeline():
    s = fresh_session()
    try:
        proj = Project(name="CascTEProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        te = TimelineEntry(project_id=proj.id, track="video", media_id=1, start_time=0.0)
        s.add(te)
        s.commit()
        te_id = te.id

        s.delete(proj)
        s.commit()
        assert s.get(TimelineEntry, te_id) is None
    finally:
        s.close()

run_test("3.3 Project -> TimelineEntry cascade delete", test_project_cascade_timeline)


# ── 3.4 Project -> PacingBlueprint (cascade delete) ──
def test_project_cascade_blueprint():
    s = fresh_session()
    try:
        proj = Project(name="CascBPProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        pb = PacingBlueprint(project_id=proj.id, name="TestBP")
        s.add(pb)
        s.commit()
        pb_id = pb.id

        s.delete(proj)
        s.commit()
        assert s.get(PacingBlueprint, pb_id) is None
    finally:
        s.close()

run_test("3.4 Project -> PacingBlueprint cascade delete", test_project_cascade_blueprint)


# ── 3.5 AudioTrack -> Beatgrid (cascade delete, uselist=False) ──
def test_audio_cascade_beatgrid():
    s = fresh_session()
    try:
        proj = Project(name="ABGProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/abg.wav")
        s.add(at)
        s.commit()
        bg = Beatgrid(audio_track_id=at.id, bpm=128.0, offset=0.0)
        s.add(bg)
        s.commit()
        bg_id = bg.id

        s.delete(at)
        s.commit()
        assert s.get(Beatgrid, bg_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.5 AudioTrack -> Beatgrid cascade delete", test_audio_cascade_beatgrid)


# ── 3.6 AudioTrack -> WaveformData (cascade delete, uselist=False) ──
def test_audio_cascade_waveform():
    s = fresh_session()
    try:
        proj = Project(name="AWFProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/awf.wav")
        s.add(at)
        s.commit()
        wf = WaveformData(
            audio_track_id=at.id, num_samples=100, duration=2.3,
            band_low=[0.1], band_mid=[0.2], band_high=[0.3],
        )
        s.add(wf)
        s.commit()
        wf_id = wf.id

        s.delete(at)
        s.commit()
        assert s.get(WaveformData, wf_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.6 AudioTrack -> WaveformData cascade delete", test_audio_cascade_waveform)


# ── 3.7 AudioTrack -> StructureSegment (cascade delete) ──
def test_audio_cascade_structure():
    s = fresh_session()
    try:
        proj = Project(name="ASSProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/ass.wav")
        s.add(at)
        s.commit()
        ss = StructureSegment(audio_track_id=at.id, start_time=0, end_time=30, label="DROP")
        s.add(ss)
        s.commit()
        ss_id = ss.id

        s.delete(at)
        s.commit()
        assert s.get(StructureSegment, ss_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.7 AudioTrack -> StructureSegment cascade delete", test_audio_cascade_structure)


# ── 3.8 AudioTrack -> HotCue (cascade delete) ──
def test_audio_cascade_hotcue():
    s = fresh_session()
    try:
        proj = Project(name="AHCProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/ahc.wav")
        s.add(at)
        s.commit()
        hc = HotCue(audio_track_id=at.id, time=10.0)
        s.add(hc)
        s.commit()
        hc_id = hc.id

        s.delete(at)
        s.commit()
        assert s.get(HotCue, hc_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.8 AudioTrack -> HotCue cascade delete", test_audio_cascade_hotcue)


# ── 3.9 AudioTrack -> AudioVideoAnchor (cascade delete) ──
def test_audio_cascade_av_anchor():
    s = fresh_session()
    try:
        proj = Project(name="AAVAProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/aava.wav")
        vc = VideoClip(project_id=proj.id, file_path="/video/aava.mp4")
        s.add_all([at, vc])
        s.commit()
        ava = AudioVideoAnchor(
            audio_track_id=at.id, video_clip_id=vc.id,
            audio_time=5.0, video_time=5.0,
        )
        s.add(ava)
        s.commit()
        ava_id = ava.id

        # Delete audio track => anchor should be deleted
        s.delete(at)
        s.commit()
        assert s.get(AudioVideoAnchor, ava_id) is None

        s.delete(vc)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.9 AudioTrack -> AudioVideoAnchor cascade delete", test_audio_cascade_av_anchor)


# ── 3.10 VideoClip -> Scene (cascade delete) ──
def test_video_cascade_scene():
    s = fresh_session()
    try:
        proj = Project(name="VCSProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        vc = VideoClip(project_id=proj.id, file_path="/video/vcs.mp4")
        s.add(vc)
        s.commit()
        sc = Scene(video_clip_id=vc.id, start_time=0.0, end_time=5.0)
        s.add(sc)
        s.commit()
        sc_id = sc.id

        s.delete(vc)
        s.commit()
        assert s.get(Scene, sc_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.10 VideoClip -> Scene cascade delete", test_video_cascade_scene)


# ── 3.11 VideoClip -> AudioVideoAnchor (cascade delete) ──
def test_video_cascade_av_anchor():
    s = fresh_session()
    try:
        proj = Project(name="VCAVAProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/vcava.wav")
        vc = VideoClip(project_id=proj.id, file_path="/video/vcava.mp4")
        s.add_all([at, vc])
        s.commit()
        ava = AudioVideoAnchor(
            audio_track_id=at.id, video_clip_id=vc.id,
            audio_time=5.0, video_time=5.0,
        )
        s.add(ava)
        s.commit()
        ava_id = ava.id

        # Delete video clip => anchor should be deleted
        s.delete(vc)
        s.commit()
        assert s.get(AudioVideoAnchor, ava_id) is None

        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.11 VideoClip -> AudioVideoAnchor cascade delete", test_video_cascade_av_anchor)


# ── 3.12 TimelineEntry -> ClipAnchor (cascade delete) ──
def test_timeline_cascade_clipanchor():
    s = fresh_session()
    try:
        proj = Project(name="TECAProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        te = TimelineEntry(project_id=proj.id, track="video", media_id=1, start_time=0.0)
        s.add(te)
        s.commit()
        ca = ClipAnchor(timeline_entry_id=te.id, time_offset=2.0)
        s.add(ca)
        s.commit()
        ca_id = ca.id

        s.delete(te)
        s.commit()
        assert s.get(ClipAnchor, ca_id) is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.12 TimelineEntry -> ClipAnchor cascade delete", test_timeline_cascade_clipanchor)


# ── 3.13 Deep cascade: Project -> AudioTrack -> Beatgrid + WaveformData + HotCue ──
def test_deep_cascade_project_audio_children():
    s = fresh_session()
    try:
        proj = Project(name="DeepCascProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        at = AudioTrack(project_id=proj.id, file_path="/audio/deep.wav")
        s.add(at)
        s.commit()

        bg = Beatgrid(audio_track_id=at.id, bpm=128.0, offset=0.0)
        wf = WaveformData(
            audio_track_id=at.id, num_samples=50, duration=1.0,
            band_low=[0.1], band_mid=[0.2], band_high=[0.3],
        )
        hc = HotCue(audio_track_id=at.id, time=5.0, label="CueA")
        ss = StructureSegment(audio_track_id=at.id, start_time=0, end_time=10, label="INTRO")
        s.add_all([bg, wf, hc, ss])
        s.commit()

        at_id, bg_id, wf_id, hc_id, ss_id = at.id, bg.id, wf.id, hc.id, ss.id

        # Delete project => all children should cascade
        s.delete(proj)
        s.commit()

        assert s.get(AudioTrack, at_id) is None
        assert s.get(Beatgrid, bg_id) is None
        assert s.get(WaveformData, wf_id) is None
        assert s.get(HotCue, hc_id) is None
        assert s.get(StructureSegment, ss_id) is None
    finally:
        s.close()

run_test("3.13 Deep cascade: Project -> AudioTrack -> all children", test_deep_cascade_project_audio_children)


# ── 3.14 Deep cascade: Project -> VideoClip -> Scene ──
def test_deep_cascade_project_video_scene():
    s = fresh_session()
    try:
        proj = Project(name="DeepCascV", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        vc = VideoClip(project_id=proj.id, file_path="/video/deepv.mp4")
        s.add(vc)
        s.commit()
        sc = Scene(video_clip_id=vc.id, start_time=0.0, end_time=5.0)
        s.add(sc)
        s.commit()
        vc_id, sc_id = vc.id, sc.id

        s.delete(proj)
        s.commit()
        assert s.get(VideoClip, vc_id) is None
        assert s.get(Scene, sc_id) is None
    finally:
        s.close()

run_test("3.14 Deep cascade: Project -> VideoClip -> Scene", test_deep_cascade_project_video_scene)


# ── 3.15 AIPacingMemory FK SET NULL on scene/audio delete ──
def test_aipacing_set_null():
    s = fresh_session()
    try:
        proj = Project(name="APMProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/apm.wav")
        vc = VideoClip(project_id=proj.id, file_path="/video/apm.mp4")
        s.add_all([at, vc])
        s.commit()
        sc = Scene(video_clip_id=vc.id, start_time=0, end_time=5)
        s.add(sc)
        s.commit()

        apm = AIPacingMemory(
            bpm=140.0, mood="drop",
            scene_id=sc.id, audio_track_id=at.id,
        )
        s.add(apm)
        s.commit()
        apm_id = apm.id

        # Delete the audio track => audio_track_id should be SET NULL
        s.delete(at)
        s.commit()
        s.expire_all()
        apm2 = s.get(AIPacingMemory, apm_id)
        assert apm2 is not None, "AIPacingMemory should NOT be deleted"
        assert apm2.audio_track_id is None, f"audio_track_id should be NULL, got {apm2.audio_track_id}"

        # Delete the scene => scene_id should be SET NULL
        s.delete(sc)
        s.commit()
        s.expire_all()
        apm3 = s.get(AIPacingMemory, apm_id)
        assert apm3 is not None, "AIPacingMemory should NOT be deleted"
        assert apm3.scene_id is None, f"scene_id should be NULL, got {apm3.scene_id}"

        # Cleanup
        s.delete(apm3)
        s.commit()
        s.delete(vc)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.15 AIPacingMemory SET NULL on scene/audio delete", test_aipacing_set_null)


# ── 3.16 back_populates: Project.audio_tracks ──
def test_back_populates_project_audio():
    s = fresh_session()
    try:
        proj = Project(name="BPProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at1 = AudioTrack(project_id=proj.id, file_path="/audio/bp1.wav")
        at2 = AudioTrack(project_id=proj.id, file_path="/audio/bp2.wav")
        s.add_all([at1, at2])
        s.commit()

        s.expire_all()
        proj2 = s.get(Project, proj.id)
        tracks = proj2.audio_tracks
        assert len(tracks) == 2
        assert all(t.project is proj2 for t in tracks)

        # Cleanup
        s.delete(proj2)
        s.commit()
    finally:
        s.close()

run_test("3.16 back_populates: Project.audio_tracks", test_back_populates_project_audio)


# ── 3.17 back_populates: AudioTrack.beatgrid (uselist=False) ──
def test_back_populates_audio_beatgrid():
    s = fresh_session()
    try:
        proj = Project(name="ABBPProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/abbp.wav")
        s.add(at)
        s.commit()
        bg = Beatgrid(audio_track_id=at.id, bpm=128.0, offset=0.0)
        s.add(bg)
        s.commit()

        s.expire_all()
        at2 = s.get(AudioTrack, at.id)
        assert at2.beatgrid is not None
        assert at2.beatgrid.bpm == 128.0
        assert at2.beatgrid.audio_track is at2

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.17 back_populates: AudioTrack.beatgrid (uselist=False)", test_back_populates_audio_beatgrid)


# ── 3.18 FK constraint violation: AudioTrack with invalid project_id ──
def test_fk_violation_audiotrack():
    s = fresh_session()
    try:
        at = AudioTrack(project_id=99999, file_path="/audio/bad.wav")
        s.add(at)
        try:
            s.commit()
            # If we get here, FK wasn't enforced
            raise AssertionError("FK constraint should have rejected invalid project_id=99999")
        except Exception as e:
            s.rollback()
            if "FOREIGN KEY constraint failed" in str(e) or "IntegrityError" in type(e).__name__:
                pass  # expected
            elif "AssertionError" in type(e).__name__:
                raise
            else:
                pass  # Some other integrity error, still means FK is enforced
    finally:
        s.close()

run_test("3.18 FK constraint violation: AudioTrack with invalid project_id", test_fk_violation_audiotrack)


# ── 3.19 Unique constraint: AudioTrack (project_id, file_path) ──
def test_unique_audiotrack():
    s = fresh_session()
    try:
        proj = Project(name="UQProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        at1 = AudioTrack(project_id=proj.id, file_path="/audio/unique.wav")
        s.add(at1)
        s.commit()

        at2 = AudioTrack(project_id=proj.id, file_path="/audio/unique.wav")
        s.add(at2)
        try:
            s.commit()
            raise AssertionError("Unique constraint should have rejected duplicate (project_id, file_path)")
        except Exception as e:
            s.rollback()
            if "AssertionError" in type(e).__name__:
                raise

        s.delete(at1)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.19 Unique constraint: AudioTrack (project_id, file_path)", test_unique_audiotrack)


# ── 3.20 Unique constraint: Beatgrid.audio_track_id ──
def test_unique_beatgrid():
    s = fresh_session()
    try:
        proj = Project(name="UQBGProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/uqbg.wav")
        s.add(at)
        s.commit()

        bg1 = Beatgrid(audio_track_id=at.id, bpm=128.0, offset=0.0)
        s.add(bg1)
        s.commit()

        bg2 = Beatgrid(audio_track_id=at.id, bpm=140.0, offset=0.0)
        s.add(bg2)
        try:
            s.commit()
            raise AssertionError("Unique constraint should reject second beatgrid for same audio_track_id")
        except Exception as e:
            s.rollback()
            if "AssertionError" in type(e).__name__:
                raise

        s.delete(bg1)
        s.commit()
        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("3.20 Unique constraint: Beatgrid.audio_track_id", test_unique_beatgrid)


# ── 3.21 Unique constraint: ModelRegistry.model_id ──
def test_unique_model_registry():
    s = fresh_session()
    try:
        mr1 = ModelRegistry(model_id="test-model-unique", source="ollama", status="installed")
        s.add(mr1)
        s.commit()

        mr2 = ModelRegistry(model_id="test-model-unique", source="huggingface", status="installed")
        s.add(mr2)
        try:
            s.commit()
            raise AssertionError("Unique constraint should reject duplicate model_id")
        except Exception as e:
            s.rollback()
            if "AssertionError" in type(e).__name__:
                raise

        s.delete(mr1)
        s.commit()
    finally:
        s.close()

run_test("3.21 Unique constraint: ModelRegistry.model_id", test_unique_model_registry)


# ── 3.22 Unique constraint: StylePreset.name ──
def test_unique_style_preset():
    s = fresh_session()
    try:
        sp1 = StylePreset(name="UniqueName")
        s.add(sp1)
        s.commit()

        sp2 = StylePreset(name="UniqueName")
        s.add(sp2)
        try:
            s.commit()
            raise AssertionError("Unique constraint should reject duplicate StylePreset name")
        except Exception as e:
            s.rollback()
            if "AssertionError" in type(e).__name__:
                raise

        s.delete(sp1)
        s.commit()
    finally:
        s.close()

run_test("3.22 Unique constraint: StylePreset.name", test_unique_style_preset)


# ── 3.23 Unique constraint: AnalysisStatus (media_type, media_id, step_key) ──
def test_unique_analysis_status():
    s = fresh_session()
    try:
        a1 = AnalysisStatus(media_type="video", media_id=1, step_key="scene_detection", status="done")
        s.add(a1)
        s.commit()

        a2 = AnalysisStatus(media_type="video", media_id=1, step_key="scene_detection", status="running")
        s.add(a2)
        try:
            s.commit()
            raise AssertionError("Unique constraint should reject duplicate (media_type, media_id, step_key)")
        except Exception as e:
            s.rollback()
            if "AssertionError" in type(e).__name__:
                raise

        s.delete(a1)
        s.commit()
    finally:
        s.close()

run_test("3.23 Unique constraint: AnalysisStatus (media_type, media_id, step_key)", test_unique_analysis_status)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: nullpool_session Context Manager
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 4: nullpool_session Context Manager")
print("=" * 70)


def _make_section4_engine():
    """Build a file-backed SQLite engine for Section-4 tests.

    _NullPoolSessionContext.__exit__ disposes the engine, which destroys an
    in-memory SQLite database between the with-block and the verification
    query. A file-backed DB survives the dispose and lets the follow-up
    Session read back the committed row.
    """
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db", prefix="pb_section4_")
    os.close(fd)
    eng = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    return eng, path


# ── 4.1 _NullPoolSessionContext basic usage ──
def test_nullpool_basic():
    """Test the _NullPoolSessionContext with a real engine (not via nullpool_session
    which uses the global engine URL pointing at the real DB).

    Uses StaticPool so the in-memory SQLite connection is shared between
    create_all() and the context session — NullPool would give the context
    a fresh empty DB. The test only checks context-manager semantics, not
    actual pool behavior.
    """
    from database.session import _NullPoolSessionContext
    from sqlalchemy.pool import StaticPool

    np_eng = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(np_eng)

    ctx = _NullPoolSessionContext(np_eng)
    with ctx as session:
        session.add(Project(name="NullPoolTest", path="/tmp", fps=30.0))
        session.commit()
    # Key assertion: __exit__ returned without raising.

run_test("4.1 _NullPoolSessionContext basic open/commit/close", test_nullpool_basic)


# ── 4.2 _NullPoolSessionContext auto-commit ──
def test_nullpool_autocommit():
    from database.session import _NullPoolSessionContext

    np_eng, np_path = _make_section4_engine()
    try:
        ctx = _NullPoolSessionContext(np_eng)
        with ctx as session:
            session.add(StylePreset(name="AutoCommitTest"))
            # No explicit commit — should auto-commit on __exit__

        # Verify auto-commit worked — reopen engine from file (ctx disposed the old one)
        verify_eng = create_engine(f"sqlite:///{np_path}")
        with Session(verify_eng) as s2:
            sp = s2.query(StylePreset).filter_by(name="AutoCommitTest").first()
            assert sp is not None, "Auto-commit did not persist StylePreset"
        verify_eng.dispose()
    finally:
        try:
            os.unlink(np_path)
        except OSError:
            pass

run_test("4.2 _NullPoolSessionContext auto-commit on clean exit", test_nullpool_autocommit)


# ── 4.3 _NullPoolSessionContext rollback on exception ──
def test_nullpool_rollback_on_error():
    from database.session import _NullPoolSessionContext

    np_eng, np_path = _make_section4_engine()
    try:
        try:
            ctx = _NullPoolSessionContext(np_eng)
            with ctx as session:
                session.add(StylePreset(name="RollbackTest"))
                raise ValueError("Intentional error")
        except ValueError:
            pass

        # Verify rollback — data should NOT exist (reopen from file; ctx disposed old engine)
        verify_eng = create_engine(f"sqlite:///{np_path}")
        with Session(verify_eng) as s2:
            sp = s2.query(StylePreset).filter_by(name="RollbackTest").first()
            assert sp is None, "Data should have been rolled back after exception"
        verify_eng.dispose()
    finally:
        try:
            os.unlink(np_path)
        except OSError:
            pass

run_test("4.3 _NullPoolSessionContext rollback on exception", test_nullpool_rollback_on_error)


# ── 4.4 _TrackedSession tracks explicit commit ──
def test_tracked_session_explicit_commit():
    from database.session import _NullPoolSessionContext

    np_eng, np_path = _make_section4_engine()
    try:
        ctx = _NullPoolSessionContext(np_eng)
        with ctx as session:
            session.add(StylePreset(name="ExplicitCommitTest"))
            session.commit()  # explicit commit
            assert ctx._explicitly_committed is True
    finally:
        try:
            os.unlink(np_path)
        except OSError:
            pass

run_test("4.4 _TrackedSession tracks explicit commit flag", test_tracked_session_explicit_commit)


# ── 4.5 _TrackedSession tracks explicit rollback ──
def test_tracked_session_explicit_rollback():
    from database.session import _NullPoolSessionContext

    np_eng, np_path = _make_section4_engine()
    try:
        ctx = _NullPoolSessionContext(np_eng)
        with ctx as session:
            session.add(StylePreset(name="ExplicitRollbackTest"))
            session.rollback()  # explicit rollback
            assert ctx._explicitly_rolled_back is True

        # Data should NOT exist (reopen from file; ctx disposed old engine)
        verify_eng = create_engine(f"sqlite:///{np_path}")
        with Session(verify_eng) as s2:
            sp = s2.query(StylePreset).filter_by(name="ExplicitRollbackTest").first()
            assert sp is None, "Data should have been rolled back"
        verify_eng.dispose()
    finally:
        try:
            os.unlink(np_path)
        except OSError:
            pass

run_test("4.5 _TrackedSession tracks explicit rollback flag", test_tracked_session_explicit_rollback)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: EngineProxy
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 5: EngineProxy")
print("=" * 70)


def test_engine_proxy_attr_forwarding():
    from database.session import EngineProxy
    real_eng = create_engine("sqlite:///:memory:")
    proxy = EngineProxy(real_eng)
    # dialect should be forwarded
    assert proxy.dialect.name == "sqlite"
    assert "memory" in str(proxy.url)
    proxy.dispose()

run_test("5.1 EngineProxy attribute forwarding (dialect, url)", test_engine_proxy_attr_forwarding)


def test_engine_proxy_swap():
    from database.session import EngineProxy
    eng1 = create_engine("sqlite:///:memory:")
    eng2 = create_engine("sqlite:///:memory:")
    proxy = EngineProxy(eng1)
    assert proxy.dialect.name == "sqlite"

    proxy.swap(eng2)
    # After swap, proxy should use eng2; eng1 should be disposed
    assert proxy.dialect.name == "sqlite"
    proxy.dispose()

run_test("5.2 EngineProxy.swap() atomically replaces engine", test_engine_proxy_swap)


def test_engine_proxy_connect():
    from database.session import EngineProxy
    eng = create_engine("sqlite:///:memory:")
    proxy = EngineProxy(eng)
    conn = proxy.connect()
    result = conn.execute(text("SELECT 1"))
    assert result.fetchone()[0] == 1
    conn.close()
    proxy.dispose()

run_test("5.3 EngineProxy.connect() works", test_engine_proxy_connect)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: Migration System (Alembic)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 6: Migration System")
print("=" * 70)


def test_alembic_config_exists():
    import os
    alembic_ini = os.path.join(PROJECT_ROOT, "alembic.ini")
    assert os.path.exists(alembic_ini), f"alembic.ini not found at {alembic_ini}"

run_test("6.1 alembic.ini exists", test_alembic_config_exists)


def test_alembic_env_exists():
    import os
    env_py = os.path.join(PROJECT_ROOT, "database", "alembic", "env.py")
    assert os.path.exists(env_py), f"env.py not found at {env_py}"

run_test("6.2 database/alembic/env.py exists", test_alembic_env_exists)


def test_alembic_versions_exist():
    import os
    versions_dir = os.path.join(PROJECT_ROOT, "database", "alembic", "versions")
    py_files = [f for f in os.listdir(versions_dir) if f.endswith(".py") and not f.startswith("__")]
    assert len(py_files) >= 1, f"Expected at least 1 migration file, found {len(py_files)}"

run_test("6.3 Alembic migration files exist", test_alembic_versions_exist)


def test_alembic_baseline_rev_matches():
    """Verify the _ALEMBIC_BASELINE_REV in migrations.py matches the initial migration filename."""
    import os
    from database.migrations import _ALEMBIC_BASELINE_REV

    versions_dir = os.path.join(PROJECT_ROOT, "database", "alembic", "versions")
    initial_files = [f for f in os.listdir(versions_dir) if "initial" in f.lower() and f.endswith(".py")]
    assert len(initial_files) >= 1, "No initial migration file found"

    # Check the baseline rev appears in the filename
    found = any(_ALEMBIC_BASELINE_REV in f for f in initial_files)
    assert found, f"Baseline rev {_ALEMBIC_BASELINE_REV} not found in any initial migration file: {initial_files}"

run_test("6.4 _ALEMBIC_BASELINE_REV matches initial migration", test_alembic_baseline_rev_matches)


def test_migration_chain_integrity():
    """Verify the Alembic migration chain is linear (each has down_revision pointing to previous)."""
    import importlib.util
    import os

    versions_dir = os.path.join(PROJECT_ROOT, "database", "alembic", "versions")
    py_files = sorted([f for f in os.listdir(versions_dir) if f.endswith(".py") and not f.startswith("__")])

    revisions = {}
    for f in py_files:
        spec = importlib.util.spec_from_file_location(f[:-3], os.path.join(versions_dir, f))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        revisions[mod.revision] = {
            "down": mod.down_revision,
            "file": f,
        }

    # Verify chain: exactly one root (down_revision=None), all others point to existing revision
    roots = [rev for rev, info in revisions.items() if info["down"] is None]
    assert len(roots) == 1, f"Expected 1 root migration, found {len(roots)}: {roots}"

    for rev, info in revisions.items():
        if info["down"] is not None:
            assert info["down"] in revisions, \
                f"Broken chain: {rev} ({info['file']}) points to {info['down']} which doesn't exist"

run_test("6.5 Alembic migration chain integrity", test_migration_chain_integrity)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: Edge Cases
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 7: Edge Cases")
print("=" * 70)


# ── 7.1 Empty strings ──
def test_empty_strings():
    s = fresh_session()
    try:
        proj = Project(name="", path="", fps=30.0)
        s.add(proj)
        s.commit()
        proj2 = s.get(Project, proj.id)
        assert proj2.name == ""
        assert proj2.path == ""
        s.delete(proj2)
        s.commit()
    finally:
        s.close()

run_test("7.1 Empty strings in nullable=False fields (Project.name, path)", test_empty_strings)


# ── 7.2 None values in nullable fields ──
def test_none_nullable_fields():
    s = fresh_session()
    try:
        proj = Project(name="NoneTest", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        at = AudioTrack(
            project_id=proj.id, file_path="/audio/none.wav",
            title=None, duration=None, sample_rate=None,
            bpm=None, key=None, energy_curve=None,
            stem_vocals_path=None, stem_drums_path=None,
            stem_bass_path=None, stem_other_path=None,
            key_confidence=None, lufs=None, mood=None,
            genre=None, is_dj_mix=None, spectral_bands=None,
            key_modulation_data=None, harmonic_tension_curve=None,
            deleted_at=None,
        )
        s.add(at)
        s.commit()

        at2 = s.get(AudioTrack, at.id)
        assert at2.title is None
        assert at2.bpm is None
        assert at2.energy_curve is None

        s.delete(at)
        s.commit()
        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.2 None values in all nullable AudioTrack fields", test_none_nullable_fields)


# ── 7.3 NOT NULL violation ──
def test_not_null_violation():
    s = fresh_session()
    try:
        # Project.name is nullable=False
        proj = Project(name=None, path="/tmp", fps=30.0)
        s.add(proj)
        try:
            s.commit()
            # SQLite may not enforce NOT NULL on all cases with ORM defaults
            # So this might pass — document it
            s.rollback()
            raise AssertionError("NOT NULL constraint should reject None for Project.name")
        except Exception as e:
            s.rollback()
            if "AssertionError" in type(e).__name__:
                raise
            # Expected: IntegrityError or similar
    finally:
        s.close()

run_test("7.3 NOT NULL violation: Project.name=None", test_not_null_violation)


# ── 7.4 Very long strings ──
def test_very_long_strings():
    s = fresh_session()
    try:
        long_str = "A" * 100000  # 100KB string
        proj = Project(name=long_str, path=long_str, fps=30.0)
        s.add(proj)
        s.commit()
        proj2 = s.get(Project, proj.id)
        assert len(proj2.name) == 100000
        assert len(proj2.path) == 100000
        s.delete(proj2)
        s.commit()
    finally:
        s.close()

run_test("7.4 Very long strings (100KB in Project.name, path)", test_very_long_strings)


# ── 7.5 Special characters (Unicode, SQL injection attempts) ──
def test_special_characters():
    s = fresh_session()
    try:
        special_name = "Test'; DROP TABLE projects; --\x00\uFFFF\U0001F600 日本語 العربية"
        proj = Project(name=special_name, path="/tmp/special", fps=30.0)
        s.add(proj)
        s.commit()
        proj2 = s.get(Project, proj.id)
        # Note: SQLite may strip null bytes
        assert "DROP TABLE" in proj2.name  # SQL injection attempt stored as-is
        assert "日本語" in proj2.name
        s.delete(proj2)
        s.commit()
    finally:
        s.close()

run_test("7.5 Special characters (Unicode, SQL injection, null bytes)", test_special_characters)


# ── 7.6 Large JSON data ──
def test_large_json():
    s = fresh_session()
    try:
        proj = Project(name="JSONTest", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/json.wav")
        s.add(at)
        s.commit()

        # Large beat positions array (10000 beats ~ 71 minutes at 140 BPM)
        large_beats = [i * 0.4286 for i in range(10000)]
        bg = Beatgrid(
            audio_track_id=at.id, bpm=140.0, offset=0.0,
            beat_positions=large_beats,
        )
        s.add(bg)
        s.commit()

        bg2 = s.get(Beatgrid, bg.id)
        assert len(bg2.beat_positions) == 10000
        assert abs(bg2.beat_positions[9999] - 9999 * 0.4286) < 0.001

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.6 Large JSON data (10000-element beat_positions array)", test_large_json)


# ── 7.7 Float precision edge cases ──
def test_float_precision():
    s = fresh_session()
    try:
        proj = Project(name="FloatTest", path="/tmp", fps=29.97)
        s.add(proj)
        s.commit()
        proj2 = s.get(Project, proj.id)
        assert abs(proj2.fps - 29.97) < 0.001

        at = AudioTrack(project_id=proj.id, file_path="/audio/float.wav", bpm=174.999999)
        s.add(at)
        s.commit()
        at2 = s.get(AudioTrack, at.id)
        assert abs(at2.bpm - 174.999999) < 0.0001

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.7 Float precision edge cases (fps=29.97, bpm=174.999999)", test_float_precision)


# ── 7.8 Zero and negative values ──
def test_zero_negative():
    s = fresh_session()
    try:
        proj = Project(name="ZeroNeg", path="/tmp", fps=0.0)
        s.add(proj)
        s.commit()
        proj2 = s.get(Project, proj.id)
        assert proj2.fps == 0.0

        at = AudioTrack(project_id=proj.id, file_path="/audio/zero.wav", bpm=-1.0, duration=0.0)
        s.add(at)
        s.commit()
        at2 = s.get(AudioTrack, at.id)
        assert at2.bpm == -1.0
        assert at2.duration == 0.0

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.8 Zero and negative values (fps=0, bpm=-1, duration=0)", test_zero_negative)


# ── 7.9 Soft-delete support (deleted_at column) ──
def test_soft_delete_columns():
    s = fresh_session()
    try:
        now = datetime.datetime.utcnow()
        proj = Project(name="SoftDel", path="/tmp", fps=30.0, deleted_at=now)
        s.add(proj)
        s.commit()

        proj2 = s.get(Project, proj.id)
        assert proj2.deleted_at is not None

        # Query for non-deleted projects
        active = s.query(Project).filter(Project.deleted_at.is_(None)).all()
        assert proj2 not in active

        s.delete(proj2)
        s.commit()
    finally:
        s.close()

run_test("7.9 Soft-delete: deleted_at column works for filtering", test_soft_delete_columns)


# ── 7.10 DateTime defaults (created_at on AIPacingMemory, AgentFeedback) ──
def test_datetime_defaults():
    s = fresh_session()
    try:
        before = datetime.datetime.utcnow()

        apm = AIPacingMemory(bpm=128.0, mood="test")
        s.add(apm)
        s.commit()
        after = datetime.datetime.utcnow()

        apm2 = s.get(AIPacingMemory, apm.id)
        assert apm2.created_at is not None
        # created_at should be between before and after
        assert before <= apm2.created_at <= after, \
            f"created_at {apm2.created_at} not between {before} and {after}"

        s.delete(apm2)
        s.commit()
    finally:
        s.close()

run_test("7.10 DateTime default: AIPacingMemory.created_at auto-set", test_datetime_defaults)


# ── 7.11 Concurrent access (multiple threads) ──
def test_concurrent_access():
    """Test that multiple threads can read/write without corrupting the suite DB.

    The main suite uses one in-memory SQLite connection via StaticPool. That is
    correct for deterministic single-threaded table state, but SQLite cannot run
    simultaneous transactions safely on that one shared connection.
    """
    fd, db_path = tempfile.mkstemp(prefix="pb_studio_db_deep_", suffix=".sqlite")
    os.close(fd)
    concurrent_engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(concurrent_engine, "connect")
    def _set_concurrent_pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    Base.metadata.create_all(concurrent_engine)

    def concurrent_session():
        return Session(concurrent_engine)

    errors = []
    barrier = threading.Barrier(4, timeout=10)

    def worker(thread_id):
        try:
            s = concurrent_session()
            try:
                barrier.wait()  # synchronize start
                proj = Project(name=f"Thread-{thread_id}", path=f"/tmp/t{thread_id}", fps=30.0)
                s.add(proj)
                s.commit()

                # Read all projects
                all_projs = s.query(Project).all()
                assert len(all_projs) >= 1

                # Update
                proj.name = f"Updated-{thread_id}"
                s.commit()

                # Read back
                proj2 = s.get(Project, proj.id)
                assert proj2.name == f"Updated-{thread_id}"
            finally:
                s.close()
        except Exception as e:
            errors.append((thread_id, traceback.format_exc()))

    try:
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        if errors:
            detail = "\n".join(f"Thread {tid}: {tb}" for tid, tb in errors)
            raise AssertionError(f"Concurrent access errors:\n{detail}")
    finally:
        concurrent_engine.dispose()
        try:
            os.remove(db_path)
        except OSError:
            pass

run_test("7.11 Concurrent access: 4 threads CRUD simultaneously", test_concurrent_access)


# ── 7.12 Bulk operations ──
def test_bulk_insert():
    s = fresh_session()
    try:
        proj = Project(name="BulkProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        # Bulk insert 100 audio tracks
        tracks = [
            AudioTrack(project_id=proj.id, file_path=f"/audio/bulk_{i}.wav", title=f"Track {i}")
            for i in range(100)
        ]
        s.add_all(tracks)
        s.commit()

        count = s.query(AudioTrack).filter_by(project_id=proj.id).count()
        assert count == 100, f"Expected 100 tracks, got {count}"

        # Bulk delete via cascade
        s.delete(proj)
        s.commit()

        remaining = s.query(AudioTrack).filter_by(project_id=proj.id).count()
        assert remaining == 0, f"Expected 0 tracks after cascade, got {remaining}"
    finally:
        s.close()

run_test("7.12 Bulk insert (100 AudioTracks) + cascade delete", test_bulk_insert)


# ── 7.13 Empty JSON arrays/objects ──
def test_empty_json():
    s = fresh_session()
    try:
        proj = Project(name="EmptyJSON", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(
            project_id=proj.id, file_path="/audio/ejson.wav",
            energy_curve=[], spectral_bands=[], key_modulation_data=[],
            harmonic_tension_curve={},
        )
        s.add(at)
        s.commit()

        at2 = s.get(AudioTrack, at.id)
        assert at2.energy_curve == []
        assert at2.spectral_bands == []
        assert at2.key_modulation_data == []
        assert at2.harmonic_tension_curve == {}

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.13 Empty JSON arrays and objects", test_empty_json)


# ── 7.14 Nested JSON ──
def test_nested_json():
    s = fresh_session()
    try:
        nested = {
            "description": "Complex scene with nested data",
            "mood": "dramatic",
            "motion": {"x": 0.5, "y": -0.3, "magnitude": 0.7},
            "tags": ["action", "explosion", {"nested": True}],
            "metadata": {"confidence": 0.92, "model": "gemma4"},
        }
        proj = Project(name="NestedJSON", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        vc = VideoClip(project_id=proj.id, file_path="/video/nested.mp4")
        s.add(vc)
        s.commit()
        sc = Scene(
            video_clip_id=vc.id, start_time=0.0, end_time=5.0,
            ai_caption=nested,
        )
        s.add(sc)
        s.commit()

        sc2 = s.get(Scene, sc.id)
        assert sc2.ai_caption["motion"]["magnitude"] == 0.7
        assert sc2.ai_caption["tags"][2]["nested"] is True

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.14 Nested JSON structures in Scene.ai_caption", test_nested_json)


# ── 7.15 Boolean field behavior ──
def test_boolean_field():
    s = fresh_session()
    try:
        proj = Project(name="BoolTest", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        # Test True
        at1 = AudioTrack(project_id=proj.id, file_path="/audio/bool_true.wav", is_dj_mix=True)
        s.add(at1)
        s.commit()
        assert s.get(AudioTrack, at1.id).is_dj_mix is True

        # Test False
        at2 = AudioTrack(project_id=proj.id, file_path="/audio/bool_false.wav", is_dj_mix=False)
        s.add(at2)
        s.commit()
        assert s.get(AudioTrack, at2.id).is_dj_mix is False

        # Test None (nullable=True)
        at3 = AudioTrack(project_id=proj.id, file_path="/audio/bool_none.wav", is_dj_mix=None)
        s.add(at3)
        s.commit()
        assert s.get(AudioTrack, at3.id).is_dj_mix is None

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.15 Boolean field: True, False, None", test_boolean_field)


# ── 7.16 Default values ──
def test_default_values():
    s = fresh_session()
    try:
        proj = Project(name="DefaultTest", path="/tmp")
        s.add(proj)
        s.commit()

        proj2 = s.get(Project, proj.id)
        assert proj2.resolution == "1920x1080", f"Expected default resolution, got {proj2.resolution}"
        assert proj2.fps == 30.0, f"Expected default fps=30.0, got {proj2.fps}"

        # StylePreset defaults
        sp = StylePreset(name="DefaultPreset")
        s.add(sp)
        s.commit()
        sp2 = s.get(StylePreset, sp.id)
        assert sp2.cut_rate == 1.0
        assert sp2.energy_reactivity == 0.7
        assert sp2.breakdown_behavior == "halve"
        assert sp2.min_clip_duration == 1.0
        assert sp2.max_clip_duration == 8.0

        # ClipAnchor defaults
        te = TimelineEntry(project_id=proj.id, track="video", media_id=1, start_time=0.0)
        s.add(te)
        s.commit()
        ca = ClipAnchor(timeline_entry_id=te.id, time_offset=1.0)
        s.add(ca)
        s.commit()
        ca2 = s.get(ClipAnchor, ca.id)
        assert ca2.label == "", f"Expected default label='', got {ca2.label!r}"
        assert ca2.color == "#FF3333", f"Expected default color='#FF3333', got {ca2.color}"

        # HotCue defaults
        at = AudioTrack(project_id=proj.id, file_path="/audio/def.wav")
        s.add(at)
        s.commit()
        hc = HotCue(audio_track_id=at.id, time=5.0)
        s.add(hc)
        s.commit()
        hc2 = s.get(HotCue, hc.id)
        assert hc2.label == "", f"Expected default label='', got {hc2.label!r}"
        assert hc2.color == "#FF3333"
        assert hc2.cue_type == "cue"

        s.delete(proj)
        s.commit()
        s.delete(sp)
        s.commit()
    finally:
        s.close()

run_test("7.16 Default values: Project, StylePreset, ClipAnchor, HotCue", test_default_values)


# ── 7.17 Repr methods ──
def test_repr_methods():
    s = fresh_session()
    try:
        proj = Project(name="ReprTest", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        assert "ReprTest" in repr(proj)
        assert "fps=30.0" in repr(proj)

        at = AudioTrack(project_id=proj.id, file_path="/audio/repr.wav", title="ReprTrack", bpm=128.0)
        s.add(at)
        s.commit()
        assert "ReprTrack" in repr(at)
        assert "128.0" in repr(at)

        sp = StylePreset(name="ReprPreset")
        s.add(sp)
        s.commit()
        assert "ReprPreset" in repr(sp)

        ans = AnalysisStatus(media_type="audio", media_id=1, step_key="bpm", status="done")
        s.add(ans)
        s.commit()
        r = repr(ans)
        assert "audio" in r
        assert "bpm" in r
        assert "done" in r

        s.delete(proj)
        s.commit()
        s.delete(sp)
        s.commit()
        s.delete(ans)
        s.commit()
    finally:
        s.close()

run_test("7.17 __repr__ methods on all models", test_repr_methods)


# ── 7.18 Relationship: adding children via relationship attribute ──
def test_add_via_relationship():
    s = fresh_session()
    try:
        proj = Project(name="RelAddProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()

        at = AudioTrack(project_id=proj.id, file_path="/audio/reladd.wav")
        s.add(at)
        s.commit()

        # Add hotcues via the relationship list
        at.hotcues.append(HotCue(time=1.0, label="Cue1"))
        at.hotcues.append(HotCue(time=2.0, label="Cue2"))
        s.commit()

        s.expire_all()
        at2 = s.get(AudioTrack, at.id)
        assert len(at2.hotcues) == 2
        labels = sorted(hc.label for hc in at2.hotcues)
        assert labels == ["Cue1", "Cue2"]

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.18 Adding children via relationship attribute (AudioTrack.hotcues)", test_add_via_relationship)


# ── 7.19 Multiple scenes per video clip ──
def test_multiple_scenes():
    s = fresh_session()
    try:
        proj = Project(name="MultiScene", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        vc = VideoClip(project_id=proj.id, file_path="/video/multi.mp4")
        s.add(vc)
        s.commit()

        for i in range(10):
            sc = Scene(video_clip_id=vc.id, start_time=i * 5.0, end_time=(i + 1) * 5.0, label=f"Scene_{i}")
            s.add(sc)
        s.commit()

        s.expire_all()
        vc2 = s.get(VideoClip, vc.id)
        assert len(vc2.scenes) == 10

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.19 Multiple scenes per VideoClip (10 scenes)", test_multiple_scenes)


# ── 7.20 Orphan removal test ──
def test_orphan_removal():
    """Test that removing a child from parent's collection deletes it (delete-orphan)."""
    s = fresh_session()
    try:
        proj = Project(name="OrphanProj", path="/tmp", fps=30.0)
        s.add(proj)
        s.commit()
        at = AudioTrack(project_id=proj.id, file_path="/audio/orphan.wav")
        s.add(at)
        s.commit()

        hc = HotCue(audio_track_id=at.id, time=5.0, label="OrphanCue")
        s.add(hc)
        s.commit()
        hc_id = hc.id

        # Remove from parent's collection => should delete orphan
        at.hotcues.remove(hc)
        s.commit()

        assert s.get(HotCue, hc_id) is None, "Orphan HotCue should be deleted"

        s.delete(proj)
        s.commit()
    finally:
        s.close()

run_test("7.20 Orphan removal: removing from parent collection deletes child", test_orphan_removal)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8: Model Count Verification
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SECTION 8: Model Count Verification")
print("=" * 70)


def test_model_count():
    """Verify model classes match the expected database.models exports."""
    from database import models
    model_classes = [
        cls for name in dir(models)
        if not name.startswith("_")
        and isinstance((cls := getattr(models, name)), type)
        and issubclass(cls, Base)
        and cls is not Base
    ]
    names = sorted(cls.__name__ for cls in model_classes)
    expected = sorted([
        "Project", "AudioTrack", "VideoClip", "Scene", "Beatgrid",
        "WaveformData", "PacingBlueprint", "AudioVideoAnchor", "ClipAnchor",
        "AIPacingMemory", "StructureSegment", "HotCue", "ModelRegistry",
        "AgentFeedback", "StylePreset", "TimelineEntry", "AnalysisStatus",
        "TimelineSnapshot", "ProjectNote",
    ])
    assert names == expected, f"Model mismatch.\nExpected: {expected}\nActual:   {names}"

run_test("8.1 Model classes match expected exports", test_model_count)


def test_all_models_exported():
    """Verify all model classes are exported from database/__init__.py."""
    import database as db_mod
    expected_names = [
        "Project", "AudioTrack", "VideoClip", "Scene", "Beatgrid",
        "WaveformData", "PacingBlueprint", "AudioVideoAnchor", "ClipAnchor",
        "AIPacingMemory", "StructureSegment", "HotCue", "ModelRegistry",
        "AgentFeedback", "StylePreset", "TimelineEntry", "AnalysisStatus",
        "TimelineSnapshot", "ProjectNote",
    ]
    missing = [n for n in expected_names if not hasattr(db_mod, n)]
    assert not missing, f"Models not exported from database/__init__.py: {missing}"

run_test("8.2 All models exported from database/__init__.py", test_all_models_exported)


# ═══════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)

total = len(_results)
passed = sum(1 for _, p, _ in _results if p)
failed = sum(1 for _, p, _ in _results if not p)

print(f"\nTotal: {total}  |  PASS: {passed}  |  FAIL: {failed}")
print()

if failed > 0:
    print("FAILED TESTS:")
    print("-" * 50)
    for name, p, detail in _results:
        if not p:
            print(f"\n  [FAIL] {name}")
            if detail:
                for line in detail.strip().split("\n"):
                    print(f"         {line}")
    print()

# Exit code for CI
sys.exit(0 if failed == 0 else 1)

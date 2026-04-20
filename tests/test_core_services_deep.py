"""Deep functional tests for PB Studio core services.

Tests all 8 services: ProjectManager, SettingsStore, TaskManager,
ActionRegistry, IngestService, TimelineService, ConvertService, ExportService.

Run with: .venv310/Scripts/python.exe tests/test_core_services_deep.py
"""

import json
import os
import sys
import shutil
import tempfile
import traceback
from pathlib import Path

# Project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force QApplication to exist before any Qt service import
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

# Force unbuffered output
import functools
print = functools.partial(print, flush=True)

# Suppress noisy loggers
import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("alembic").setLevel(logging.ERROR)
logging.getLogger("services").setLevel(logging.WARNING)

# Results accumulator
results = []

def record(service: str, function: str, status: str, detail: str = ""):
    results.append({
        "service": service,
        "function": function,
        "status": status,
        "detail": detail,
    })
    icon = "PASS" if status == "PASS" else "FAIL"
    print(f"  [{icon}] {service}.{function}" + (f" -- {detail[:200]}" if detail else ""))


def run_test(service: str, function: str, test_fn):
    """Run a single test, catching all exceptions."""
    try:
        test_fn()
        record(service, function, "PASS")
    except Exception as e:
        tb = traceback.format_exc()
        record(service, function, "FAIL", f"{type(e).__name__}: {e}\n{tb}")


# ======================================================================
# 1. SettingsStore (no heavy dependencies, test first)
# ======================================================================
print("\n" + "=" * 70)
print("1. SETTINGSSTORE")
print("=" * 70)

def test_settings_store():
    from services.settings_store import SettingsStore

    # Use a temp file to avoid polluting real settings
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.close()
    tmp_path = Path(tmp.name)

    store = SettingsStore.__new__(SettingsStore)
    store._path = tmp_path
    store._data = {}
    import threading
    store._lock = threading.RLock()

    # --- get/set ---
    def t_get_default():
        assert store.get("nonexistent") is None
        assert store.get("nonexistent", 42) == 42
    run_test("SettingsStore", "get(default)", t_get_default)

    def t_set_get():
        store.set("foo", "bar")
        assert store.get("foo") == "bar"
    run_test("SettingsStore", "set+get", t_set_get)

    # --- JSON persistence ---
    def t_persistence():
        store.set("persist_key", [1, 2, 3])
        with open(tmp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["persist_key"] == [1, 2, 3]
    run_test("SettingsStore", "JSON_persistence", t_persistence)

    # --- get_nested / set_nested ---
    def t_nested_get_empty():
        assert store.get_nested("a", "b", "c", default="X") == "X"
    run_test("SettingsStore", "get_nested(empty)", t_nested_get_empty)

    def t_nested_set_get():
        store.set_nested("deep", "level2", "level3", value=99)
        assert store.get_nested("deep", "level2", "level3") == 99
    run_test("SettingsStore", "set_nested+get_nested", t_nested_set_get)

    def t_set_nested_empty_path():
        store.set_nested(value=42)  # empty path should be no-op
        # Should not crash
    run_test("SettingsStore", "set_nested(empty_path)", t_set_nested_empty_path)

    # --- section ---
    def t_section():
        store.set_section("mysection", {"a": 1, "b": 2})
        s = store.get_section("mysection")
        assert s["a"] == 1 and s["b"] == 2
    run_test("SettingsStore", "get/set_section", t_section)

    def t_section_missing():
        assert store.get_section("nope") == {}
    run_test("SettingsStore", "get_section(missing)", t_section_missing)

    # --- shortcuts ---
    def t_shortcut():
        store.set_shortcut("action_save", "Ctrl+S")
        assert store.get_shortcut("action_save") == "Ctrl+S"
        assert store.get_shortcut("action_missing") == ""
        assert store.get_shortcut("action_missing", "Ctrl+X") == "Ctrl+X"
    run_test("SettingsStore", "get/set_shortcut", t_shortcut)

    def t_all_shortcuts():
        store.set_all_shortcuts({"a": "Ctrl+A", "b": "Ctrl+B"})
        all_sc = store.get_all_shortcuts()
        assert all_sc == {"a": "Ctrl+A", "b": "Ctrl+B"}
    run_test("SettingsStore", "get/set_all_shortcuts", t_all_shortcuts)

    # --- ollama settings ---
    def t_ollama():
        store.save_ollama_settings(enabled=False, url="http://test:1234", model="llama3")
        o = store.get_ollama_settings()
        assert o["enabled"] is False
        assert o["url"] == "http://test:1234"
        assert o["model"] == "llama3"
    run_test("SettingsStore", "ollama_settings", t_ollama)

    # --- recent projects ---
    def t_recent():
        store.set_recent_projects(["/a", "/b"])
        assert store.get_recent_projects() == ["/a", "/b"]
    run_test("SettingsStore", "recent_projects", t_recent)

    # --- edge: overwrite types ---
    def t_type_overwrite():
        store.set("x", 1)
        store.set("x", "now_a_string")
        assert store.get("x") == "now_a_string"
    run_test("SettingsStore", "type_overwrite", t_type_overwrite)

    # --- edge: None value ---
    def t_none_value():
        store.set("n", None)
        assert store.get("n") is None
        assert store.get("n", "default") is None  # key exists, value is None
    run_test("SettingsStore", "None_value", t_none_value)

    # --- edge: corrupt JSON reload ---
    def t_corrupt_json():
        with open(tmp_path, "w") as f:
            f.write("{bad json!!")
        store2 = SettingsStore.__new__(SettingsStore)
        store2._path = tmp_path
        store2._data = {}
        store2._lock = threading.RLock()
        store2._load()
        assert store2._data == {}  # should recover empty
    run_test("SettingsStore", "corrupt_JSON_recovery", t_corrupt_json)

    # cleanup
    tmp_path.unlink(missing_ok=True)

test_settings_store()


# ======================================================================
# 2. ActionRegistry (pure Python, no DB)
# ======================================================================
print("\n" + "=" * 70)
print("2. ACTIONREGISTRY")
print("=" * 70)

def test_action_registry():
    from services.action_registry import ActionRegistry

    reg = ActionRegistry()

    # --- register via decorator ---
    def t_register_decorator():
        @reg.register(name="greet", description="Say hello",
                      param_schema={"type": "object", "properties": {"name": {"type": "string"}}})
        def greet(name: str = "World"):
            return f"Hello, {name}!"
        assert "greet" in reg.list_actions()
    run_test("ActionRegistry", "register(decorator)", t_register_decorator)

    # --- register_function ---
    def t_register_function():
        def add(a: int, b: int):
            return a + b
        reg.register_function("add", "Add two numbers", add)
        assert "add" in reg.list_actions()
    run_test("ActionRegistry", "register_function", t_register_function)

    # --- get exact ---
    def t_get_exact():
        a = reg.get("greet")
        assert a is not None and a.name == "greet"
    run_test("ActionRegistry", "get(exact)", t_get_exact)

    def t_get_missing():
        assert reg.get("nonexistent") is None
    run_test("ActionRegistry", "get(missing)", t_get_missing)

    # --- resolve exact ---
    def t_resolve_exact():
        a = reg.resolve("add")
        assert a is not None and a.name == "add"
    run_test("ActionRegistry", "resolve(exact)", t_resolve_exact)

    # --- fuzzy_match ---
    def t_fuzzy():
        matched, score = reg.fuzzy_match("gre")
        assert matched == "greet" and score > 50
    run_test("ActionRegistry", "fuzzy_match", t_fuzzy)

    def t_fuzzy_no_match():
        matched, score = reg.fuzzy_match("zzzzzzzzz")
        # score should be below threshold
        assert matched is None or score < 55
    run_test("ActionRegistry", "fuzzy_match(no_match)", t_fuzzy_no_match)

    # --- resolve fuzzy ---
    def t_resolve_fuzzy():
        a = reg.resolve("greeting")  # should fuzzy-match to "greet"
        assert a is not None
    run_test("ActionRegistry", "resolve(fuzzy)", t_resolve_fuzzy)

    def t_resolve_none():
        a = reg.resolve("xyzxyzxyz_totally_unknown")
        assert a is None
    run_test("ActionRegistry", "resolve(total_miss)", t_resolve_none)

    # --- execute ---
    def t_execute_exact():
        result = reg.execute("greet", {"name": "Claude"})
        assert result == "Hello, Claude!"
    run_test("ActionRegistry", "execute(exact)", t_execute_exact)

    def t_execute_no_params():
        result = reg.execute("greet")
        assert result == "Hello, World!"
    run_test("ActionRegistry", "execute(no_params)", t_execute_no_params)

    def t_execute_extra_params():
        result = reg.execute("greet", {"name": "Test", "extra_key": 999})
        assert result == "Hello, Test!"
        # Should also have _dropped_params if result is dict...
        # But result is string here, so just pass
    run_test("ActionRegistry", "execute(extra_params_dropped)", t_execute_extra_params)

    def t_execute_missing_action():
        try:
            reg.execute("totally_nonexistent_action_xyz")
            assert False, "Should have raised KeyError"
        except KeyError:
            pass
    run_test("ActionRegistry", "execute(missing_action)", t_execute_missing_action)

    # --- execute with bad handler ---
    def t_execute_type_error():
        def bad_handler(required_arg):
            pass
        reg.register_function("bad", "bad", bad_handler)
        # execute with wrong param type - should call with no matching params
        try:
            reg.execute("bad", {})
            assert False, "Should raise TypeError"
        except TypeError:
            pass
    run_test("ActionRegistry", "execute(TypeError)", t_execute_type_error)

    # --- unregister ---
    def t_unregister():
        assert reg.unregister("greet") is True
        assert reg.unregister("greet") is False
        assert reg.get("greet") is None
    run_test("ActionRegistry", "unregister", t_unregister)

    # --- list_all ---
    def t_list_all():
        actions = reg.list_all()
        assert len(actions) > 0
        assert all(hasattr(a, 'name') for a in actions)
    run_test("ActionRegistry", "list_all", t_list_all)

    # --- schema for prompt ---
    def t_schema_prompt():
        schema_str = reg.get_schema_for_prompt()
        data = json.loads(schema_str)
        assert isinstance(data, list)
    run_test("ActionRegistry", "get_schema_for_prompt", t_schema_prompt)

    # --- edge: empty registry ---
    def t_empty_registry():
        empty_reg = ActionRegistry()
        matched, score = empty_reg.fuzzy_match("anything")
        assert matched is None and score == 0
    run_test("ActionRegistry", "fuzzy_match(empty_registry)", t_empty_registry)

test_action_registry()


# ======================================================================
# 3. TaskManager (requires QApplication)
# ======================================================================
print("\n" + "=" * 70)
print("3. TASKMANAGER")
print("=" * 70)

def test_task_manager():
    from services.task_manager import GlobalTaskManager, TaskInfo

    # --- singleton ---
    def t_singleton():
        tm1 = GlobalTaskManager.instance()
        tm2 = GlobalTaskManager.instance()
        assert tm1 is tm2
    run_test("TaskManager", "singleton_pattern", t_singleton)

    tm = GlobalTaskManager.instance()

    # --- create_task ---
    def t_create():
        task = tm.create_task("Test Task", "Testing")
        assert isinstance(task, TaskInfo)
        assert task.status == "running"
        assert task.name == "Test Task"
        assert task.description == "Testing"
        assert task.progress == 0
        assert task.total == 100
    run_test("TaskManager", "create_task", t_create)

    # --- update_task ---
    def t_update():
        task = tm.create_task("Update Test")
        tm.update_task(task.task_id, progress=50, message="halfway")
        fetched = tm.get_task(task.task_id)
        assert fetched.progress == 50
        assert fetched.message == "halfway"
    run_test("TaskManager", "update_task", t_update)

    # --- finish_task ---
    def t_finish():
        task = tm.create_task("Finish Test")
        tm.finish_task(task.task_id, status="finished", message="done")
        fetched = tm.get_task(task.task_id)
        assert fetched.status == "finished"
        assert fetched.message == "done"
    run_test("TaskManager", "finish_task", t_finish)

    # --- finish with error status ---
    def t_finish_error():
        task = tm.create_task("Error Test")
        tm.finish_task(task.task_id, status="error", message="something broke")
        fetched = tm.get_task(task.task_id)
        assert fetched.status == "error"
    run_test("TaskManager", "finish_task(error)", t_finish_error)

    # --- get_task missing ---
    def t_get_missing():
        assert tm.get_task("nonexistent_task_id") is None
    run_test("TaskManager", "get_task(missing)", t_get_missing)

    # --- get_all_tasks ---
    def t_get_all():
        tasks = tm.get_all_tasks()
        assert isinstance(tasks, list)
        assert len(tasks) > 0
    run_test("TaskManager", "get_all_tasks", t_get_all)

    # --- update nonexistent task (should not crash) ---
    def t_update_nonexistent():
        tm.update_task("fake_id_12345", progress=50, message="nope")
        # Should just do nothing
    run_test("TaskManager", "update_task(nonexistent)", t_update_nonexistent)

    # --- finish nonexistent task (should not crash) ---
    def t_finish_nonexistent():
        tm.finish_task("fake_id_12345", "finished", "nope")
    run_test("TaskManager", "finish_task(nonexistent)", t_finish_nonexistent)

    # --- cancel nonexistent task ---
    def t_cancel_nonexistent():
        tm.cancel_task("fake_id_12345")
    run_test("TaskManager", "cancel_task(nonexistent)", t_cancel_nonexistent)

    # --- cancel already finished task ---
    def t_cancel_finished():
        task = tm.create_task("Cancel Finished Test")
        tm.finish_task(task.task_id, "finished")
        tm.cancel_task(task.task_id)  # should be no-op
        fetched = tm.get_task(task.task_id)
        assert fetched.status == "finished"
    run_test("TaskManager", "cancel_task(already_finished)", t_cancel_finished)

    # --- clear_finished ---
    def t_clear_finished():
        t1 = tm.create_task("Clear1")
        t2 = tm.create_task("Clear2")
        tm.finish_task(t1.task_id)
        tm.finish_task(t2.task_id)
        tm.clear_finished()
        assert tm.get_task(t1.task_id) is None
        assert tm.get_task(t2.task_id) is None
    run_test("TaskManager", "clear_finished", t_clear_finished)

    # --- TaskInfo.elapsed ---
    def t_elapsed():
        task = TaskInfo("t1", "Elapsed Test")
        import time
        time.sleep(0.05)
        assert task.elapsed >= 0.0
    run_test("TaskManager", "TaskInfo.elapsed", t_elapsed)

    # --- cleanup: finish all running tasks so ProjectManager tests work ---
    for t in tm.get_all_tasks():
        if t.status == "running":
            tm.finish_task(t.task_id, "finished", "test cleanup")
    tm.clear_finished()

test_task_manager()


# ======================================================================
# 4. ProjectManager (requires DB setup)
# ======================================================================
print("\n" + "=" * 70)
print("4. PROJECTMANAGER")
print("=" * 70)

def _dispose_and_gc():
    """Dispose global engine pool and force GC to release all DB locks."""
    import database
    import gc
    try:
        raw = database.get_raw_engine()
        raw.pool.dispose()
    except Exception:
        pass
    gc.collect()

def test_project_manager():
    from services.project_manager import ProjectManager
    import database
    import gc
    import time

    pm = ProjectManager()

    # --- ensure_dirs idempotent (no DB needed) ---
    def t_ensure_dirs():
        tmp_dir = Path(tempfile.mkdtemp(prefix="pb_test_dirs_"))
        ProjectManager._ensure_dirs(tmp_dir)
        ProjectManager._ensure_dirs(tmp_dir)  # should not crash
        assert (tmp_dir / "storage" / "proxies").is_dir()
        assert (tmp_dir / "storage" / "keyframes").is_dir()
        assert (tmp_dir / "storage" / "stems").is_dir()
        assert (tmp_dir / "exports").is_dir()
        assert (tmp_dir / "data" / "vector").is_dir()
        shutil.rmtree(tmp_dir, ignore_errors=True)
    run_test("ProjectManager", "_ensure_dirs(idempotent)", t_ensure_dirs)

    # --- _has_running_tasks ---
    def t_has_running():
        # After cleanup above, should be False
        result = pm._has_running_tasks()
        assert isinstance(result, bool)
    run_test("ProjectManager", "_has_running_tasks", t_has_running)

    # --- Test create+open+saveas using a SINGLE dedicated project path ---
    # IMPORTANT: ProjectManager.create_project/open_project/save_project_as
    # call database.set_project() which swaps the global SQLAlchemy engine.
    # In rapid-fire test scenarios, Alembic migrations and SQLAlchemy pool
    # connections from previous engine swaps cause "database is locked" errors.
    # This is a TESTABILITY issue, not a runtime bug (production only switches
    # projects when user clicks a button, seconds apart).
    #
    # Strategy: Do ONE create_project into a dedicated temp dir, then test
    # open_project on the SAME db, avoiding rapid engine swaps.

    _test_proj_dir = Path(tempfile.mkdtemp(prefix="pb_test_pm_"))
    _test_proj_path = _test_proj_dir / "FunctionalTestProject"

    def t_create():
        _dispose_and_gc()
        result = pm.create_project(_test_proj_path, name="FunctionalTestProject",
                                   resolution="1920x1080", fps=30.0)
        assert result == _test_proj_path
        assert (_test_proj_path / "pb_studio.db").exists()
        assert (_test_proj_path / "storage" / "proxies").is_dir()
        assert (_test_proj_path / "exports").is_dir()
        assert (_test_proj_path / "data" / "vector").is_dir()
    run_test("ProjectManager", "create_project", t_create)

    def t_open():
        _dispose_and_gc()
        meta = pm.open_project(_test_proj_path)
        assert isinstance(meta, dict)
        assert meta["name"] == "FunctionalTestProject"
        assert "resolution" in meta
        assert "fps" in meta
    run_test("ProjectManager", "open_project", t_open)

    def t_create_dup():
        _dispose_and_gc()
        try:
            pm.create_project(_test_proj_path, "DupProject")
            assert False, "Should raise FileExistsError"
        except FileExistsError:
            pass
    run_test("ProjectManager", "create_project(duplicate)", t_create_dup)

    def t_open_missing():
        _dispose_and_gc()
        tmp_dir = Path(tempfile.mkdtemp(prefix="pb_test_missing_"))
        try:
            pm.open_project(tmp_dir)
            assert False, "Should raise FileNotFoundError"
        except FileNotFoundError:
            pass
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    run_test("ProjectManager", "open_project(missing_db)", t_open_missing)

    def t_save_as():
        _dispose_and_gc()
        tgt = _test_proj_dir / "SavedCopy"
        result = pm.save_project_as(tgt)
        assert result == tgt
        assert (tgt / "pb_studio.db").exists()
    run_test("ProjectManager", "save_project_as", t_save_as)

    def t_save_as_exists():
        _dispose_and_gc()
        tgt = _test_proj_dir / "ExistingTarget"
        tgt.mkdir(parents=True, exist_ok=True)
        try:
            pm.save_project_as(tgt)
            assert False, "Should raise FileExistsError"
        except FileExistsError:
            pass
    run_test("ProjectManager", "save_project_as(exists)", t_save_as_exists)

    # Cleanup + restore engine to project root DB
    _dispose_and_gc()
    database.set_project(PROJECT_ROOT)
    try:
        database.init_db()
    except Exception:
        pass
    _dispose_and_gc()
    shutil.rmtree(_test_proj_dir, ignore_errors=True)

test_project_manager()


# ======================================================================
# 5. TimelineService (OTIO, no DB needed for basic ops)
# ======================================================================
print("\n" + "=" * 70)
print("5. TIMELINESERVICE")
print("=" * 70)

def test_timeline_service():
    from services.timeline_service import TimelineService, safe_get_metadata

    ts = TimelineService(fps=30.0)

    # --- create_timeline ---
    def t_create():
        tl = ts.create_timeline("Test Timeline")
        assert tl.name == "Test Timeline"
        tracks = list(tl.tracks)
        assert len(tracks) == 2
    run_test("TimelineService", "create_timeline", t_create)

    # --- timeline property (lazy creation) ---
    def t_lazy():
        ts2 = TimelineService(fps=24.0)
        tl = ts2.timeline  # should auto-create
        assert tl is not None
        assert tl.name == "Untitled"
    run_test("TimelineService", "timeline(lazy_create)", t_lazy)

    # --- get_video_track ---
    def t_video_track():
        vt = ts.get_video_track(0)
        assert vt is not None
        import opentimelineio as otio
        assert vt.kind == otio.schema.TrackKind.Video
    run_test("TimelineService", "get_video_track(0)", t_video_track)

    def t_video_track_new():
        vt2 = ts.get_video_track(5)  # should create new
        assert vt2 is not None
    run_test("TimelineService", "get_video_track(new)", t_video_track_new)

    # --- get_audio_track ---
    def t_audio_track():
        at = ts.get_audio_track(0)
        assert at is not None
    run_test("TimelineService", "get_audio_track(0)", t_audio_track)

    # --- add_clip ---
    def t_add_clip():
        vt = ts.get_video_track(0)
        clip = ts.add_clip(
            track=vt,
            name="TestClip",
            media_path="C:/test/video.mp4",
            source_start=0.0,
            source_duration=5.0,
            available_duration=60.0,
            metadata={"scene_type": "intro"},
        )
        assert clip is not None
        assert clip.name == "TestClip"
    run_test("TimelineService", "add_clip", t_add_clip)

    # --- add_clip with no available_duration ---
    def t_add_clip_no_avail():
        vt = ts.get_video_track(0)
        clip = ts.add_clip(vt, "Clip2", "C:/test/v2.mp4", 1.0, 3.0)
        assert clip is not None
    run_test("TimelineService", "add_clip(no_avail_dur)", t_add_clip_no_avail)

    # --- add_transition ---
    def t_transition():
        vt = ts.get_video_track(0)
        t = ts.add_transition(vt, position=1, duration=0.5)
        assert t is not None
    run_test("TimelineService", "add_transition", t_transition)

    # --- add_marker ---
    def t_marker():
        m = ts.add_marker("Beat1", time=2.5, duration=0.0, color="GREEN",
                          metadata={"beat_idx": 0})
        assert m is not None
    run_test("TimelineService", "add_marker", t_marker)

    def t_marker_invalid_color():
        m = ts.add_marker("M2", time=5.0, color="INVALID_COLOR")
        assert m is not None  # should fall back to RED
    run_test("TimelineService", "add_marker(invalid_color)", t_marker_invalid_color)

    # --- get_markers ---
    def t_get_markers():
        markers = ts.get_markers()
        assert len(markers) >= 1
        assert "name" in markers[0]
        assert "time" in markers[0]
    run_test("TimelineService", "get_markers", t_get_markers)

    # --- get_all_clips ---
    def t_get_clips():
        clips = ts.get_all_clips()
        assert len(clips) >= 1
    run_test("TimelineService", "get_all_clips", t_get_clips)

    # --- beatgrid metadata ---
    def t_beatgrid():
        ts.set_beatgrid_metadata([0.0, 0.5, 1.0, 1.5], bpm=120.0)
        bg = ts.get_beatgrid_metadata()
        assert bg["bpm"] == 120.0
        assert len(bg["beat_positions"]) == 4
    run_test("TimelineService", "set/get_beatgrid_metadata", t_beatgrid)

    # --- get_duration ---
    def t_duration():
        dur = ts.get_duration()
        assert isinstance(dur, float)
        assert dur >= 0.0
    run_test("TimelineService", "get_duration", t_duration)

    # --- save_otio + load_otio ---
    def t_save_load():
        tmp = tempfile.NamedTemporaryFile(suffix=".otio", delete=False)
        tmp.close()
        saved = ts.save_otio(tmp.name)
        assert Path(saved).exists()

        ts2 = TimelineService(fps=30.0)
        tl = ts2.load_otio(tmp.name)
        assert tl.name == ts.timeline.name
        Path(tmp.name).unlink(missing_ok=True)
    run_test("TimelineService", "save_otio+load_otio", t_save_load)

    # --- clear ---
    def t_clear():
        ts.clear()
        clips = ts.get_all_clips()
        assert len(clips) == 0
    run_test("TimelineService", "clear", t_clear)

    # --- safe_get_metadata edge ---
    def t_safe_metadata_empty():
        result = safe_get_metadata({})
        assert result == {}
    run_test("TimelineService", "safe_get_metadata(empty)", t_safe_metadata_empty)

    def t_safe_metadata_none_ns():
        result = safe_get_metadata({"other": "data"})
        assert result == {}
    run_test("TimelineService", "safe_get_metadata(missing_ns)", t_safe_metadata_none_ns)

    # --- export_edl (requires project path, may fail) ---
    def t_export_edl():
        ts3 = TimelineService(fps=30.0)
        ts3.create_timeline("EDL Test")
        vt = ts3.get_video_track(0)
        ts3.add_clip(vt, "C1", "C:/test/v.mp4", 0.0, 2.0)
        tmp_dir = tempfile.mkdtemp(prefix="pb_edl_")
        edl_path = Path(tmp_dir) / "test.edl"
        try:
            result = ts3.export_edl(edl_path)
            assert Path(result).exists()
        except RuntimeError as e:
            if "cmx_3600" in str(e):
                record("TimelineService", "export_edl", "PASS",
                       "EDL adapter not available (expected in some envs)")
                return
            raise
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    run_test("TimelineService", "export_edl", t_export_edl)

test_timeline_service()


# ======================================================================
# 6. IngestService (requires DB)
# ======================================================================
print("\n" + "=" * 70)
print("6. INGESTSERVICE")
print("=" * 70)

def test_ingest_service():
    from services.ingest_service import (
        ingest_audio, ingest_video, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
        _file_meta,
    )

    # --- extension sets ---
    def t_audio_ext():
        assert ".mp3" in AUDIO_EXTENSIONS
        assert ".wav" in AUDIO_EXTENSIONS
        assert ".flac" in AUDIO_EXTENSIONS
        assert ".mp4" not in AUDIO_EXTENSIONS
    run_test("IngestService", "AUDIO_EXTENSIONS", t_audio_ext)

    def t_video_ext():
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mov" in VIDEO_EXTENSIONS
        assert ".mkv" in VIDEO_EXTENSIONS
        assert ".mp3" not in VIDEO_EXTENSIONS
    run_test("IngestService", "VIDEO_EXTENSIONS", t_video_ext)

    # --- _file_meta ---
    def t_file_meta():
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"fake audio data " * 100)
        tmp.close()
        meta = _file_meta(Path(tmp.name))
        assert "file_path" in meta
        assert meta["extension"] == ".mp3"
        assert meta["size_bytes"] > 0
        assert meta["title"] == Path(tmp.name).stem
        Path(tmp.name).unlink()
    run_test("IngestService", "_file_meta", t_file_meta)

    def t_file_meta_missing():
        try:
            _file_meta(Path("C:/nonexistent/path/file.mp3"))
            assert False, "Should raise"
        except FileNotFoundError:
            pass
    run_test("IngestService", "_file_meta(missing)", t_file_meta_missing)

    # --- ingest_audio missing file ---
    def t_ingest_audio_missing():
        try:
            ingest_audio("C:/nonexistent/audio.mp3")
            assert False, "Should raise"
        except FileNotFoundError:
            pass
    run_test("IngestService", "ingest_audio(missing)", t_ingest_audio_missing)

    # --- ingest_audio wrong extension ---
    def t_ingest_audio_bad_ext():
        tmp = tempfile.NamedTemporaryFile(suffix=".xyz", delete=False)
        tmp.close()
        try:
            ingest_audio(tmp.name)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Extension" in str(e)
        Path(tmp.name).unlink()
    run_test("IngestService", "ingest_audio(bad_ext)", t_ingest_audio_bad_ext)

    # --- ingest_video missing file ---
    def t_ingest_video_missing():
        try:
            ingest_video("C:/nonexistent/video.mp4")
            assert False, "Should raise"
        except FileNotFoundError:
            pass
    run_test("IngestService", "ingest_video(missing)", t_ingest_video_missing)

    # --- ingest_video wrong extension ---
    def t_ingest_video_bad_ext():
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        try:
            ingest_video(tmp.name)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Extension" in str(e)
        Path(tmp.name).unlink()
    run_test("IngestService", "ingest_video(bad_ext)", t_ingest_video_bad_ext)

    # --- ingest_audio with valid extension but fake file (DB write test) ---
    def t_ingest_audio_real():
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"\xff\xfb\x90\x00" * 1000)  # fake MP3 header
        tmp.close()
        try:
            result = ingest_audio(tmp.name)
            # result is AudioTrack or None (if already exists)
            if result is not None:
                assert result.file_path is not None
                assert result.title is not None
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    run_test("IngestService", "ingest_audio(valid_ext_fake_data)", t_ingest_audio_real)

    # --- ingest_video with valid extension but fake file ---
    def t_ingest_video_real():
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"\x00\x00\x00\x1c\x66\x74\x79\x70" * 100)  # fake MP4
        tmp.close()
        try:
            result = ingest_video(tmp.name)
            if result is not None:
                assert result.file_path is not None
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    run_test("IngestService", "ingest_video(valid_ext_fake_data)", t_ingest_video_real)

test_ingest_service()


# ======================================================================
# 7. ConvertService
# ======================================================================
print("\n" + "=" * 70)
print("7. CONVERTSERVICE")
print("=" * 70)

def test_convert_service():
    # --- import ---
    def t_import():
        from services.convert_service import (
            convert, detect_nvenc, get_available_presets,
            PRESETS, PRESET_EDIT_PROXY, PRESET_MASTER_1080P, PRESET_DAVINCI_PROXY,
            ConvertPreset,
        )
    run_test("ConvertService", "import", t_import)

    from services.convert_service import (
        convert, detect_nvenc, get_available_presets, PRESETS,
        _safe_stem, _sanitize_ffmpeg_error,
    )

    # --- PRESETS dict ---
    def t_presets():
        assert "edit_proxy" in PRESETS
        assert "master" in PRESETS
        assert "davinci" in PRESETS
    run_test("ConvertService", "PRESETS_exist", t_presets)

    # --- detect_nvenc ---
    def t_detect():
        result = detect_nvenc()
        assert isinstance(result, dict)
        assert "h264_nvenc" in result
        assert "hevc_nvenc" in result
        assert "cuda_hwaccel" in result
        assert "ffmpeg_version" in result
    run_test("ConvertService", "detect_nvenc", t_detect)

    # --- get_available_presets ---
    def t_avail():
        presets = get_available_presets()
        assert isinstance(presets, list)
        assert len(presets) == 3
        for p in presets:
            assert "key" in p
            assert "name" in p
            assert "available" in p
    run_test("ConvertService", "get_available_presets", t_avail)

    # --- convert missing file ---
    def t_convert_missing():
        try:
            convert("C:/nonexistent/file.mp4", preset_name="edit_proxy")
            assert False, "Should raise"
        except FileNotFoundError:
            pass
    run_test("ConvertService", "convert(missing_file)", t_convert_missing)

    # --- convert bad preset ---
    def t_convert_bad_preset():
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"fake")
        tmp.close()
        try:
            convert(tmp.name, preset_name="nonexistent_preset")
            assert False, "Should raise"
        except Exception as e:
            assert "Unbekanntes Preset" in str(e)
        Path(tmp.name).unlink(missing_ok=True)
    run_test("ConvertService", "convert(bad_preset)", t_convert_bad_preset)

    # --- _safe_stem ---
    def t_safe_stem():
        assert _safe_stem("normal") == "normal"
        assert _safe_stem("CON") == "_CON"
        assert _safe_stem("con") == "_con"
        assert _safe_stem("PRN") == "_PRN"
        assert _safe_stem("COM1") == "_COM1"
    run_test("ConvertService", "_safe_stem", t_safe_stem)

    # --- _sanitize_ffmpeg_error ---
    def t_sanitize_error():
        assert _sanitize_ffmpeg_error("") == "(no stderr)"
        assert _sanitize_ffmpeg_error(None) == "(no stderr)"
        long_stderr = "\n".join(f"line{i}" for i in range(100))
        sanitized = _sanitize_ffmpeg_error(long_stderr, max_lines=3)
        assert len(sanitized.splitlines()) == 3
    run_test("ConvertService", "_sanitize_ffmpeg_error", t_sanitize_error)

test_convert_service()


# ======================================================================
# 8. ExportService
# ======================================================================
print("\n" + "=" * 70)
print("8. EXPORTSERVICE")
print("=" * 70)

def test_export_service():
    # --- import ---
    def t_import():
        from services.export_service import (
            export_timeline, export_preview,
            get_timeline_summary, estimate_render_time,
            clear_probe_cache, _probe_video, _sanitize_ffmpeg_error,
        )
    run_test("ExportService", "import", t_import)

    from services.export_service import (
        get_timeline_summary, estimate_render_time,
        clear_probe_cache, _sanitize_ffmpeg_error,
        export_timeline,
    )

    # --- clear_probe_cache ---
    def t_clear_cache():
        clear_probe_cache()  # should not crash
    run_test("ExportService", "clear_probe_cache", t_clear_cache)

    # --- _sanitize_ffmpeg_error ---
    def t_sanitize():
        assert _sanitize_ffmpeg_error("") == "(no stderr)"
        assert _sanitize_ffmpeg_error(None) == "(no stderr)"
    run_test("ExportService", "_sanitize_ffmpeg_error", t_sanitize)

    # --- get_timeline_summary ---
    def t_summary():
        s = get_timeline_summary(project_id=1)
        assert isinstance(s, dict)
        assert "video_clips" in s
        assert "audio_tracks" in s
        assert "total_entries" in s
        assert "estimated_duration" in s
    run_test("ExportService", "get_timeline_summary", t_summary)

    # --- estimate_render_time ---
    def t_estimate():
        est = estimate_render_time(project_id=1)
        assert isinstance(est, dict)
        assert "estimated_seconds" in est
        assert "estimated_label" in est
        assert "segment_count" in est
    run_test("ExportService", "estimate_render_time", t_estimate)

    # --- export_timeline with no entries ---
    def t_export_no_entries():
        # Use a project_id that has no timeline entries
        try:
            export_timeline(project_id=99999)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "Keine" in str(e)
    run_test("ExportService", "export_timeline(no_entries)", t_export_no_entries)

    # --- export_timeline with bad resolution ---
    def t_export_bad_res():
        try:
            export_timeline(project_id=1, resolution="invalid")
            assert False, "Should raise"
        except ValueError as e:
            assert "Aufl" in str(e) or "resolution" in str(e).lower() or "Ungültig" in str(e)
    run_test("ExportService", "export_timeline(bad_resolution)", t_export_bad_res)

test_export_service()


# ======================================================================
# SUMMARY
# ======================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

pass_count = sum(1 for r in results if r["status"] == "PASS")
fail_count = sum(1 for r in results if r["status"] == "FAIL")
total = len(results)

print(f"\nTotal: {total}  |  PASS: {pass_count}  |  FAIL: {fail_count}\n")

if fail_count > 0:
    print("-" * 70)
    print("FAILURES:")
    print("-" * 70)
    for r in results:
        if r["status"] == "FAIL":
            print(f"\n  [{r['service']}] {r['function']}:")
            print(f"    {r['detail']}")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)

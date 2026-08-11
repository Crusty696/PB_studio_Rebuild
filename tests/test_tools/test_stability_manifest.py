from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


def _create_db(path: Path, *, value: str = "value") -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, status TEXT NOT NULL)")
    connection.execute("INSERT INTO sample (status) VALUES (?)", (value,))
    connection.commit()
    return connection


def _init_git_repo(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "stability@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Stability Test"],
        cwd=repo,
        check=True,
    )
    tracked = repo / "tracked.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=repo, check=True)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
    ).strip()


def _cli_evidence(tmp_path: Path, run_id: str) -> tuple[Path, dict[str, str]]:
    localappdata = tmp_path / "localappdata"
    output = localappdata / "PBStudioStability" / run_id
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(localappdata)
    return output, env


def test_discover_protected_databases_without_importing_product_modules(tmp_path):
    from tools.stability_manifest import discover_protected_databases

    repo = tmp_path / "repo"
    appdata = tmp_path / "appdata"
    recent = tmp_path / "recent"
    settings = appdata / "PBStudio" / "settings.json"
    expected = {
        repo / "pb_studio.db",
        repo / "outputs" / "project-a" / "pb_studio.db",
        repo / "data" / "vector" / "embeddings.db",
        repo / "brain_v3" / "state.db",
        recent / "pb_studio.db",
        recent / "data" / "vector" / "embeddings.db",
        recent / "brain_v3" / "embeddings.db",
        appdata / "PB_Studio" / "brain_v3" / "weights.db",
    }
    for path in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    ignored = repo / ".worktrees" / "other" / "pb_studio.db"
    ignored.parent.mkdir(parents=True)
    ignored.touch()
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"recentProjects": [{"path": str(recent)}]}),
        encoding="utf-8",
    )

    found = discover_protected_databases(
        repo_root=repo,
        appdata=appdata,
        settings_path=settings,
    )

    assert set(found) == {path.resolve() for path in expected}
    assert ignored.resolve() not in found


def test_capture_raw_bundle_preserves_wal_and_analyzes_only_copy(tmp_path):
    from tools.stability_manifest import capture_database

    source = tmp_path / "project" / "pb_studio.db"
    source_connection = _create_db(source, value="committed-in-wal")
    try:
        source_wal = Path(f"{source}-wal")
        assert source_wal.stat().st_size > 0
        source_before = {
            suffix: Path(f"{source}{suffix}").read_bytes()
            for suffix in ("", "-wal", "-shm")
            if Path(f"{source}{suffix}").exists()
        }

        result = capture_database(
            source,
            backup_root=tmp_path / "external" / "backups",
        )

        assert result["stable"] is True
        assert result["analysis"]["quick_check"] == "ok"
        assert result["analysis"]["table_counts"]["sample"] == 1
        assert result["analysis"]["logical_content_sha256"]
        assert Path(result["backup"]["database"]).is_file()
        assert Path(result["backup"]["consolidated_database"]).is_file()
        for suffix, content in source_before.items():
            assert Path(f"{source}{suffix}").read_bytes() == content
    finally:
        source_connection.close()


def test_b749_archived_wal_and_shm_survive_consolidation(tmp_path):
    """B-749: listed -wal/-shm artifacts must still exist and match the source.

    Before the fix, consolidation opened the archived copy directly; SQLite
    recovered its WAL and deleted the archived -wal/-shm on close, so the
    manifest listed sidecar artifacts that were gone from disk.
    """
    from tools.stability_manifest import capture_database

    source = tmp_path / "project" / "pb_studio.db"
    source_connection = _create_db(source, value="committed-in-wal")
    try:
        source_bytes = {
            suffix: Path(f"{source}{suffix}").read_bytes()
            for suffix in ("", "-wal", "-shm")
            if Path(f"{source}{suffix}").is_file()
        }
        assert len(source_bytes["-wal"]) > 0

        result = capture_database(
            source,
            backup_root=tmp_path / "external" / "backups",
        )

        backup = result["backup"]
        assert Path(backup["consolidated_database"]).is_file()
        for key, suffix in (("database", ""), ("wal", "-wal"), ("shm", "-shm")):
            listed = backup[key]
            assert listed is not None, f"{key} was not archived at all"
            archived = Path(listed)
            assert archived.is_file(), f"manifest lists {key} but file is missing"
            assert archived.read_bytes() == source_bytes[suffix], (
                f"archived {key} bytes drifted from the source"
            )
        assert not (Path(backup["database"]).parent / "consolidation_work").exists()
        assert result["analysis"]["table_counts"]["sample"] == 1
    finally:
        source_connection.close()


def test_write_baseline_manifest_uses_required_json_contract(tmp_path):
    from tools.stability_manifest import write_baseline_manifest

    repo = tmp_path / "repo"
    appdata = tmp_path / "appdata"
    source = repo / "pb_studio.db"
    connection = _create_db(source)
    output = tmp_path / "PBStudioStability" / "run-1"
    try:
        manifest_path = write_baseline_manifest(
            run_id="run-1",
            baseline_commit="abc123",
            repo_root=repo,
            appdata=appdata,
            output_root=output,
            command="stability_manifest.py capture",
            process_status={"verdict": "quiescent", "processes": []},
        )
    finally:
        connection.close()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert {
        "run_id",
        "baseline_commit",
        "phase",
        "command",
        "started_at",
        "ended_at",
        "exit_code",
        "verdict",
        "process_status",
        "db_before",
        "db_after",
        "artifacts",
        "logs",
        "limits",
    } <= manifest.keys()
    assert manifest["phase"] == "STAB-1"
    assert manifest["verdict"] == "pass"
    assert manifest["db_before"] == manifest["db_after"]
    assert len(manifest["db_before"]) == 1


def test_run_evidenced_command_records_command_logs_and_unchanged_db(tmp_path):
    from tools.stability_manifest import run_evidenced_command

    source = tmp_path / "project" / "pb_studio.db"
    connection = _create_db(source)
    connection.close()
    output = tmp_path / "evidence"

    manifest_path = run_evidenced_command(
        run_id="run-command-pass",
        baseline_commit="f" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('command-ok')"],
        cwd=tmp_path,
        databases=[source],
        output_root=output,
        process_status={"verdict": "test", "processes": []},
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "pass"
    assert manifest["exit_code"] == 0
    assert "command-ok" in (output / "stdout.log").read_text(encoding="utf-8")
    assert manifest["db_before"] == manifest["db_after"]
    assert manifest["logs"] == [
        str((output / "stdout.log").resolve()),
        str((output / "stderr.log").resolve()),
    ]


def test_run_evidenced_command_fails_if_temp_database_changes(tmp_path):
    from tools.stability_manifest import run_evidenced_command

    source = tmp_path / "project" / "pb_studio.db"
    connection = _create_db(source)
    connection.close()
    mutation = (
        "import sqlite3; "
        f"c=sqlite3.connect({str(source)!r}); "
        "c.execute(\"INSERT INTO sample(status) VALUES ('changed')\"); "
        "c.commit(); c.close()"
    )

    manifest_path = run_evidenced_command(
        run_id="run-command-mutation",
        baseline_commit="e" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", mutation],
        cwd=tmp_path,
        databases=[source],
        output_root=tmp_path / "evidence",
        process_status={"verdict": "test", "processes": []},
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["exit_code"] == 0
    assert manifest["verdict"] == "fail"
    assert manifest["db_before"] != manifest["db_after"]
    assert "Protected database bytes changed" in manifest["limits"]


def test_stability_run_cli_executes_gate_and_writes_manifest(tmp_path):
    repo = tmp_path / "repo"
    appdata = tmp_path / "appdata"
    _init_git_repo(repo)
    source = repo / "pb_studio.db"
    connection = _create_db(source)
    connection.close()
    subprocess.run(["git", "add", "pb_studio.db"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "tracked database"],
        cwd=repo,
        check=True,
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
    ).strip()
    output, env = _cli_evidence(tmp_path, "cli-run")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "cli-run",
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(appdata),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            "print('cli-ok')",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "pass"
    assert manifest["source_status"]["actual_commit"] == head
    assert manifest["source_status"]["dirty_paths"] == []
    assert "cli-ok" in (output / "stdout.log").read_text(encoding="utf-8")


def test_run_evidenced_command_fails_when_protected_database_is_created(
    tmp_path,
    monkeypatch,
):
    from tools.stability_manifest import run_evidenced_command

    source = tmp_path / "repo" / "pb_studio.db"
    source.parent.mkdir()
    monkeypatch.chdir(tmp_path)
    mutation = (
        "import sqlite3; "
        f"c=sqlite3.connect({str(source)!r}); "
        "c.execute('CREATE TABLE created (id INTEGER PRIMARY KEY)'); "
        "c.commit(); c.close()"
    )

    manifest_path = run_evidenced_command(
        run_id="run-command-create",
        baseline_commit="c" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", mutation],
        cwd=tmp_path,
        databases=[source],
        output_root=tmp_path / "evidence",
        process_status={
            "capture_exit_code": 0,
            "verdict": "test",
            "processes": [],
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "Protected database bytes changed" in manifest["limits"]
    assert not (tmp_path / "None").exists()
    assert not (tmp_path / "consolidated.db").exists()


def test_run_evidenced_command_fails_when_protected_database_is_deleted(
    tmp_path,
    monkeypatch,
):
    from tools.stability_manifest import run_evidenced_command

    source = tmp_path / "project" / "pb_studio.db"
    monkeypatch.chdir(tmp_path)
    connection = _create_db(source)
    connection.close()
    deletion = f"from pathlib import Path; Path({str(source)!r}).unlink()"

    manifest_path = run_evidenced_command(
        run_id="run-command-delete",
        baseline_commit="b" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", deletion],
        cwd=tmp_path,
        databases=[source],
        output_root=tmp_path / "evidence",
        process_status={
            "capture_exit_code": 0,
            "verdict": "test",
            "processes": [],
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "Protected database bytes changed" in manifest["limits"]
    assert not (tmp_path / "None").exists()
    assert not (tmp_path / "consolidated.db").exists()


def test_run_evidenced_command_blocks_failed_process_snapshot(tmp_path):
    from tools.stability_manifest import run_evidenced_command

    manifest_path = run_evidenced_command(
        run_id="run-process-snapshot-fail",
        baseline_commit="a" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('command-ok')"],
        cwd=tmp_path,
        databases=[],
        output_root=tmp_path / "evidence",
        process_status={
            "capture_exit_code": 1,
            "verdict": "failed",
            "processes": [],
            "limits": ["process probe failed"],
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "process probe failed" in manifest["limits"]


def test_validate_git_source_rejects_wrong_commit_and_dirty_tree(tmp_path):
    from tools.stability_manifest import validate_git_source

    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    tracked = repo / "tracked.py"

    assert validate_git_source(repo, head)["verdict"] == "pass"
    assert validate_git_source(repo, "0" * 40)["verdict"] == "blocked"
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    dirty = validate_git_source(repo, head)
    assert dirty["verdict"] == "blocked"
    assert "tracked.py" in dirty["dirty_paths"]


def test_cli_blocks_before_command_on_head_mismatch(tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    marker = tmp_path / "command-ran"
    output, env = _cli_evidence(tmp_path, "wrong-head")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "wrong-head",
            "--baseline-commit",
            "0" * 40,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(tmp_path / "appdata"),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not marker.exists()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "blocked"
    assert "Baseline commit does not match current HEAD" in manifest["limits"]


def test_cli_fails_when_new_outputs_database_appears(tmp_path):
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    source = repo / "outputs" / "new-project" / "pb_studio.db"
    output, env = _cli_evidence(tmp_path, "new-output-db")
    mutation = (
        "import pathlib, sqlite3; "
        f"p=pathlib.Path({str(source)!r}); p.parent.mkdir(parents=True); "
        "c=sqlite3.connect(p); c.execute('CREATE TABLE created(id INTEGER)'); "
        "c.commit(); c.close()"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "new-output-db",
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(tmp_path / "appdata"),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            mutation,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "Protected database set changed" in manifest["limits"]


def test_runner_preserves_manifest_on_after_capture_exception(tmp_path, monkeypatch):
    import tools.stability_manifest as stability_manifest

    source = tmp_path / "project" / "pb_studio.db"
    connection = _create_db(source)
    connection.close()
    real_capture = stability_manifest.capture_database
    calls = 0

    def fail_second_capture(database, *, backup_root):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("capture exploded")
        return real_capture(database, backup_root=backup_root)

    monkeypatch.setattr(
        stability_manifest,
        "capture_database",
        fail_second_capture,
    )
    output = tmp_path / "evidence"
    manifest_path = stability_manifest.run_evidenced_command(
        run_id="after-capture-error",
        baseline_commit="9" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('command-ok')"],
        cwd=tmp_path,
        databases=[source],
        output_root=output,
        process_status={"capture_exit_code": 0, "processes": [], "limits": []},
        process_snapshotter=lambda: {
            "capture_exit_code": 0,
            "processes": [],
            "limits": [],
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "command-ok" in (output / "stdout.log").read_text(encoding="utf-8")
    assert any("after capture" in limit for limit in manifest["limits"])


def test_runner_fails_when_command_has_surviving_descendant(
    tmp_path,
    monkeypatch,
):
    import tools.stability_manifest as stability_manifest

    original_popen = subprocess.Popen
    command_pid: list[int] = []

    def recording_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        command_pid.append(process.pid)
        return process

    monkeypatch.setattr(stability_manifest.subprocess, "Popen", recording_popen)

    def descendant_snapshot():
        return {
            "capture_exit_code": 0,
            "processes": [
                {
                    "ProcessId": 987654,
                    "ParentProcessId": command_pid[0],
                    "Name": "python.exe",
                    "CommandLine": "synthetic surviving child",
                }
            ],
            "limits": [],
        }

    manifest_path = stability_manifest.run_evidenced_command(
        run_id="surviving-child",
        baseline_commit="8" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('parent-done')"],
        cwd=tmp_path,
        databases=[],
        output_root=tmp_path / "evidence",
        process_status={"capture_exit_code": 0, "processes": [], "limits": []},
        process_snapshotter=descendant_snapshot,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "Command left relevant descendant processes running" in manifest["limits"]
    assert manifest["process_status"]["surviving_descendants"][0]["ProcessId"] == 987654


def test_cli_blocks_before_command_on_dirty_tracked_source(tmp_path):
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    (repo / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    marker = tmp_path / "command-ran"
    output, env = _cli_evidence(tmp_path, "dirty-source")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "dirty-source",
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(tmp_path / "appdata"),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not marker.exists()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "blocked"
    assert "Git worktree is not clean" in manifest["limits"]
    assert "tracked.py" in manifest["source_status"]["dirty_paths"]


def test_runner_blocks_and_writes_manifest_on_before_capture_exception(
    tmp_path,
    monkeypatch,
):
    import tools.stability_manifest as stability_manifest

    source = tmp_path / "project" / "pb_studio.db"
    connection = _create_db(source)
    connection.close()
    marker = tmp_path / "command-ran"
    output = tmp_path / "evidence"

    def fail_capture(database, *, backup_root):
        assert (output / "manifest.json").is_file()
        raise OSError("capture exploded")

    monkeypatch.setattr(stability_manifest, "capture_database", fail_capture)
    manifest_path = stability_manifest.run_evidenced_command(
        run_id="before-capture-error",
        baseline_commit="7" * 40,
        phase="STAB-1",
        command=[
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        cwd=tmp_path,
        databases=[source],
        output_root=output,
        process_status={"capture_exit_code": 0, "processes": [], "limits": []},
        process_snapshotter=lambda: {
            "capture_exit_code": 0,
            "processes": [],
            "limits": [],
        },
    )

    assert not marker.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert any("before capture" in limit for limit in manifest["limits"])


def test_runner_preserves_manifest_when_post_process_snapshot_raises(tmp_path):
    import tools.stability_manifest as stability_manifest

    def explode_snapshot():
        raise OSError("CIM exploded")

    output = tmp_path / "evidence"
    manifest_path = stability_manifest.run_evidenced_command(
        run_id="post-process-error",
        baseline_commit="5" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('command-ok')"],
        cwd=tmp_path,
        databases=[],
        output_root=output,
        process_status={"capture_exit_code": 0, "processes": [], "limits": []},
        process_snapshotter=explode_snapshot,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "command-ok" in (output / "stdout.log").read_text(encoding="utf-8")
    assert any("post process snapshot" in limit for limit in manifest["limits"])


def test_snapshot_preserves_ollama_in_all_process_inventory(monkeypatch):
    import tools.stability_manifest as stability_manifest

    payload = json.dumps(
        {
            "ProbePid": 99,
            "ProbeCreationDate": "probe-now",
            "Processes": [
                {
                    "ProcessId": 42,
                    "ParentProcessId": 1,
                    "Name": "ollama.exe",
                    "CreationDate": "now",
                }
            ],
        }
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(stability_manifest.subprocess, "run", fake_run)
    result = stability_manifest.snapshot_relevant_processes()

    assert result["capture_exit_code"] == 0
    assert result["inventory_scope"] == "all"
    assert result["processes"][0]["Name"] == "ollama.exe"


def test_runner_fails_on_real_detached_python_child(tmp_path):
    import tools.stability_manifest as stability_manifest

    stop = tmp_path / "stop"
    ready = tmp_path / "ready"
    exited = tmp_path / "exited"
    child_script = tmp_path / "detached_child.py"
    child_script.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import sys\n"
        "import time\n"
        "stop, ready, exited = map(Path, sys.argv[1:4])\n"
        "ready.write_text(str(os.getpid()), encoding='utf-8')\n"
        "deadline = time.time() + 30\n"
        "while not stop.exists() and time.time() < deadline:\n"
        "    time.sleep(0.05)\n"
        "exited.touch()\n",
        encoding="utf-8",
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"ready={str(ready)!r}; "
        "p=subprocess.Popen("
        f"[sys.executable,{str(child_script)!r},{str(stop)!r},ready,{str(exited)!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        "stderr=subprocess.DEVNULL,close_fds=True,"
        "creationflags=subprocess.DETACHED_PROCESS|"
        "subprocess.CREATE_NEW_PROCESS_GROUP); "
        "deadline=time.time()+10; "
        "exec(\"while not __import__('pathlib').Path(ready).exists() "
        "and time.time()<deadline:\\n time.sleep(0.05)\"); "
        "print(p.pid)"
    )
    try:
        manifest_path = stability_manifest.run_evidenced_command(
            run_id="real-detached-child",
            baseline_commit="6" * 40,
            phase="STAB-1",
            command=[sys.executable, "-c", parent_code],
            cwd=tmp_path,
            databases=[],
            output_root=tmp_path / "evidence",
            process_status={
                "capture_exit_code": 0,
                "processes": [],
                "limits": [],
            },
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["verdict"] == "fail"
        assert (
            "Command left relevant descendant processes running"
            in manifest["limits"]
        )
        child_pid = int(ready.read_text(encoding="utf-8"))
        assert any(
            process["ProcessId"] == child_pid
            for process in manifest["process_status"]["surviving_descendants"]
        )
    finally:
        stop.touch()
        deadline = time.time() + 10
        while not exited.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert exited.exists(), "detached test child did not exit cooperatively"


def test_cli_fails_if_command_dirties_tracked_source(tmp_path):
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    output, env = _cli_evidence(tmp_path, "post-command-dirty")
    mutation = (
        "from pathlib import Path; "
        f"Path({str(repo / 'tracked.py')!r}).write_text('VALUE = 3\\n')"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "post-command-dirty",
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(tmp_path / "appdata"),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            mutation,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert manifest["source_status_after"]["verdict"] == "blocked"
    assert "tracked.py" in manifest["source_status_after"]["dirty_paths"]


def test_runner_fails_when_quick_check_is_not_ok(tmp_path, monkeypatch):
    import tools.stability_manifest as stability_manifest

    source = (tmp_path / "project" / "pb_studio.db").resolve()
    absent = stability_manifest._absent_snapshot(source)

    def corrupt_capture(database, *, backup_root):
        return {
            "source": str(source),
            "stable": True,
            "source_before": absent,
            "source_after": absent,
            "backup": {},
            "analysis": {
                "quick_check": "database disk image is malformed",
                "logical_content_sha256": "same",
            },
        }

    monkeypatch.setattr(stability_manifest, "capture_database", corrupt_capture)
    manifest_path = stability_manifest.run_evidenced_command(
        run_id="corrupt-unchanged",
        baseline_commit="4" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('command-ok')"],
        cwd=tmp_path,
        databases=[source],
        output_root=tmp_path / "evidence",
        process_status={"capture_exit_code": 0, "processes": [], "limits": []},
        process_snapshotter=lambda: {
            "capture_exit_code": 0,
            "processes": [],
            "limits": [],
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "Protected database quick_check failed" in manifest["limits"]


def test_runner_fails_on_new_process_with_vanished_intermediate(tmp_path):
    import tools.stability_manifest as stability_manifest

    process_before = {
        "capture_exit_code": 0,
        "inventory_scope": "all",
        "processes": [
            {
                "ProcessId": 100,
                "ParentProcessId": 1,
                "Name": "existing.exe",
                "CreationDate": "before",
            }
        ],
        "limits": [],
    }

    def post_snapshot():
        return {
            "capture_exit_code": 0,
            "inventory_scope": "all",
            "processes": [
                *process_before["processes"],
                {
                    "ProcessId": 300,
                    "ParentProcessId": 200,
                    "Name": "cmd.exe",
                    "CreationDate": "after",
                },
            ],
            "limits": [],
        }

    manifest_path = stability_manifest.run_evidenced_command(
        run_id="vanished-intermediate",
        baseline_commit="3" * 40,
        phase="STAB-1",
        command=[sys.executable, "-c", "print('parent-done')"],
        cwd=tmp_path,
        databases=[],
        output_root=tmp_path / "evidence",
        process_status=process_before,
        process_snapshotter=post_snapshot,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verdict"] == "fail"
    assert "New processes survived the gate command" in manifest["limits"]
    assert manifest["process_status"]["new_processes"][0]["ProcessId"] == 300


def test_new_process_diff_excludes_only_known_probe_tree():
    from tools.stability_manifest import _new_processes

    before = {
        "inventory_scope": "all",
        "probe_pid": 200,
        "probe_creation_date": "probe",
        "processes": [
            {
                "ProcessId": 100,
                "ParentProcessId": 1,
                "Name": "existing.exe",
                "CreationDate": "before",
            }
        ],
    }
    after = {
        "inventory_scope": "all",
        "probe_pid": 400,
        "probe_creation_date": "after-probe",
        "processes": [
            *before["processes"],
            {
                "ProcessId": 200,
                "ParentProcessId": 10,
                "Name": "powershell.exe",
                "CreationDate": "probe",
            },
            {
                "ProcessId": 300,
                "ParentProcessId": 200,
                "Name": "conhost.exe",
                "CreationDate": "probe-child",
            },
            {
                "ProcessId": 500,
                "ParentProcessId": 999,
                "Name": "cmd.exe",
                "CreationDate": "unrelated",
            },
        ],
    }

    assert [process["ProcessId"] for process in _new_processes(before, after)] == [
        500
    ]


def test_new_process_diff_ignores_tree_owned_by_preexisting_process():
    from tools.stability_manifest import _new_processes

    existing = {
        "ProcessId": 100,
        "ParentProcessId": 1,
        "Name": "test-host.exe",
        "CreationDate": "before",
    }
    before = {
        "inventory_scope": "all",
        "processes": [existing],
    }
    after = {
        "inventory_scope": "all",
        "processes": [
            existing,
            {
                "ProcessId": 200,
                "ParentProcessId": 100,
                "Name": "powershell.exe",
                "CreationDate": "ambient",
            },
            {
                "ProcessId": 300,
                "ParentProcessId": 200,
                "Name": "conhost.exe",
                "CreationDate": "ambient-child",
            },
        ],
    }

    assert _new_processes(before, after, command_pid=999) == []


def test_new_process_diff_does_not_hide_reused_probe_pid():
    from tools.stability_manifest import _new_processes

    before = {
        "inventory_scope": "all",
        "probe_pid": 200,
        "probe_creation_date": "old-probe",
        "processes": [],
    }
    reused = {
        "ProcessId": 200,
        "ParentProcessId": 999,
        "Name": "cmd.exe",
        "CreationDate": "new-command-process",
    }
    after = {
        "inventory_scope": "all",
        "probe_pid": 400,
        "probe_creation_date": "new-probe",
        "processes": [reused],
    }

    assert _new_processes(before, after, command_pid=999) == [reused]


def test_new_process_diff_fails_closed_if_before_parent_vanished():
    from tools.stability_manifest import _new_processes

    before = {
        "inventory_scope": "all",
        "processes": [
            {
                "ProcessId": 200,
                "ParentProcessId": 1,
                "Name": "old.exe",
                "CreationDate": "old-parent",
            }
        ],
    }
    child = {
        "ProcessId": 300,
        "ParentProcessId": 200,
        "Name": "cmd.exe",
        "CreationDate": "survivor",
    }
    after = {
        "inventory_scope": "all",
        "processes": [child],
    }

    assert _new_processes(before, after, command_pid=999) == [child]


def test_snapshot_query_has_no_executable_allowlist(monkeypatch):
    import tools.stability_manifest as stability_manifest

    seen_script: list[str] = []

    def fake_run(command, **kwargs):
        seen_script.append(command[-1])
        payload = json.dumps(
            {
                "ProbePid": 99,
                "ProbeCreationDate": "probe-now",
                "Processes": [],
            }
        )
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(stability_manifest.subprocess, "run", fake_run)
    stability_manifest.snapshot_relevant_processes()

    assert ".Name -match" not in seen_script[0]
    assert "python|pythonw" not in seen_script[0]


def test_cli_writes_blocked_manifest_if_initial_discovery_raises(tmp_path):
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    appdata = tmp_path / "appdata"
    settings = appdata / "PBStudio" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{invalid", encoding="utf-8")
    output, env = _cli_evidence(tmp_path, "discovery-error")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "discovery-error",
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(appdata),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            "print('must-not-run')",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "blocked"
    assert any("database discovery" in limit for limit in manifest["limits"])


def test_cli_rejects_repo_internal_evidence_root(tmp_path):
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    run_id = "invalid-evidence-root"
    localappdata = tmp_path / "localappdata"
    expected_output = localappdata / "PBStudioStability" / run_id
    rejected_output = repo / "evidence"
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(localappdata)

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            run_id,
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(tmp_path / "appdata"),
            "--output-root",
            str(rejected_output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            "print('must-not-run')",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not rejected_output.exists()
    manifest = json.loads(
        (expected_output / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["verdict"] == "blocked"
    assert "Evidence root must be external PBStudioStability run directory" in (
        manifest["limits"]
    )


def test_cli_rejects_localappdata_inside_repo_without_writing(tmp_path):
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    run_id = "repo-localappdata"
    output = repo / "PBStudioStability" / run_id
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(repo)

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            run_id,
            "--baseline-commit",
            head,
            "--phase",
            "STAB-1",
            "--repo-root",
            str(repo),
            "--appdata",
            str(tmp_path / "appdata"),
            "--output-root",
            str(output),
            "--confirmed-no-pb-db-writer",
            "--",
            sys.executable,
            "-c",
            "print('must-not-run')",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "LOCALAPPDATA resolves inside repository" in result.stderr
    assert not output.exists()

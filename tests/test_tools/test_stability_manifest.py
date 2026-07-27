from __future__ import annotations

import json
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
    output = tmp_path / "evidence"

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
    output = tmp_path / "evidence"

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
    output = tmp_path / "evidence"
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
    output = tmp_path / "evidence"

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


def test_snapshot_query_includes_ollama(monkeypatch):
    import tools.stability_manifest as stability_manifest

    seen_script: list[str] = []

    def fake_run(command, **kwargs):
        seen_script.append(command[-1])
        return subprocess.CompletedProcess(command, 0, "[]", "")

    monkeypatch.setattr(stability_manifest.subprocess, "run", fake_run)
    result = stability_manifest.snapshot_relevant_processes()

    assert result["capture_exit_code"] == 0
    assert "ollama" in seen_script[0]


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

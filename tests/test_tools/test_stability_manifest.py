from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def _create_db(path: Path, *, value: str = "value") -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, status TEXT NOT NULL)")
    connection.execute("INSERT INTO sample (status) VALUES (?)", (value,))
    connection.commit()
    return connection


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
    source = repo / "pb_studio.db"
    connection = _create_db(source)
    connection.close()
    output = tmp_path / "evidence"

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools" / "stability_run.py"),
            "--run-id",
            "cli-run",
            "--baseline-commit",
            "d" * 40,
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
    assert "cli-ok" in (output / "stdout.log").read_text(encoding="utf-8")

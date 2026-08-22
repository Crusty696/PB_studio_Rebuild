"""Tests fuer tools/agent_session.py — die Multi-Agent-Session-Registry.

Geprueft werden die drei Zusagen des Systems (VERHINDERN / ERKENNEN / NACHWEISEN)
und die Faelle, die es idiotensicher machen sollen. Jeder Test bildet einen
realen Vorfall oder eine reale Falle ab:

- Registry im git-common-dir  -> sonst haette jeder Worktree seine eigene und
  das System wuerde NICHTS koordinieren (verifiziert: --git-dir zeigt im
  Linked-Worktree auf .git/worktrees/<name>/).
- Konflikt-Erkennung          -> der Antigravity-Vorfall (fremde Dateien
  mitcommittet, weil niemand wusste dass ein anderer arbeitet).
- Stale-Cleanup               -> ein abgestuerzter Agent darf nicht ewig blockieren.
- Atomares Schreiben/Lock     -> parallele Agenten duerfen sich nicht ueberschreiben.
- Korrupte Datei              -> darf agent_start nie crashen.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import agent_session as ag  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    """Registry in einen tmp-Ordner umlenken — nie die echte anfassen."""
    monkeypatch.setattr(ag, "_git_common_dir", lambda: tmp_path)
    ag.registry_path().write_text('{"sessions": []}', encoding="utf-8")
    ag.initialization_marker_path().write_bytes(ag.INITIALIZATION_MARKER_BYTES)
    yield


# ── Ort der Registry (die Worktree-Falle) ────────────────────────────────────

def test_registry_uses_git_common_dir_not_git_dir(monkeypatch):
    """Die Registry MUSS im gemeinsamen .git liegen.

    Wuerde sie ueber --git-dir/--git-path aufgeloest, laege sie in einem
    Linked-Worktree unter .git/worktrees/<name>/ — jeder Agent haette seine
    eigene und die Koordination waere wirkungslos. Genau diese Falle hat
    tools/session_learning.py (--git-path).

    Funktional geprueft (nicht per Text-Suche im Quelltext: die Begriffe kommen
    dort auch in der Doku vor, die vor genau dieser Falle warnt).
    """
    calls: list[list[str]] = []

    class _R:
        stdout = "/repo/.git"

    def _fake_run(cmd, **kw):
        calls.append(list(cmd))
        return _R()

    monkeypatch.undo()  # _git_common_dir hier NICHT gepatcht haben wollen
    monkeypatch.setattr(ag.subprocess, "run", _fake_run)
    ag._git_common_dir()

    assert calls, "es muss ueberhaupt git gefragt werden"
    assert "--git-common-dir" in calls[0]
    assert "--git-dir" not in calls[0]
    assert "--git-path" not in calls[0]


# ── VERHINDERN: Konflikte ────────────────────────────────────────────────────

def test_claim_blocks_overlapping_paths():
    """Der Antigravity-Fall: zweiter Agent will dieselbe Datei."""
    s1, c1 = ag.claim("agent-a", "B-643", ["ui/timeline.py"])
    assert s1 and not c1

    s2, c2 = ag.claim("agent-b", "andere Arbeit", ["ui/timeline.py"])
    assert not s2, "zweite Session darf NICHT registriert werden"
    assert c2 and c2[0]["agent"] == "agent-a"
    assert "ui/timeline.py" in c2[0]["_hits"]


def test_claim_allows_disjoint_paths():
    """Zwei Agenten an verschiedenen Dateien duerfen parallel laufen."""
    s1, _ = ag.claim("agent-a", "t1", ["ui/timeline.py"])
    s2, c2 = ag.claim("agent-b", "t2", ["services/export_service.py"])
    assert s1 and s2 and not c2
    assert len(ag.status()) == 2


def test_claim_captures_transitive_parent_lineage():
    director, _ = ag.claim("director", "coordinate", [])
    reviewer, _ = ag.claim(
        "reviewer", "pass-a", [], parent_session_id=director["id"]
    )
    child, _ = ag.claim(
        "child", "challenge", [], parent_session_id=reviewer["id"]
    )

    assert reviewer["parent_session_id"] == director["id"]
    assert reviewer["ancestor_session_ids"] == [director["id"]]
    assert child["ancestor_session_ids"] == [director["id"], reviewer["id"]]


def test_claim_rejects_missing_parent_and_marks_force():
    session, conflicts = ag.claim(
        "orphan", "audit", [], parent_session_id="not-live"
    )
    assert not session
    assert conflicts and conflicts[0]["_reason"] == "parent-session-not-live"

    forced, _ = ag.claim("forced", "audit", [], force=True)
    assert forced["forced"] is True
    child, _ = ag.claim("child", "audit", [], parent_session_id=forced["id"])
    assert child["forced_lineage"] is True


def test_glob_claims_conflict():
    """Globs muessen in BEIDE Richtungen greifen."""
    ag.claim("agent-a", "tests", ["tests/**"])
    _, c = ag.claim("agent-b", "ein test", ["tests/ui/test_x.py"])
    assert c, "Glob des Ersten muss die konkrete Datei des Zweiten treffen"

    ag.release(ag.status()[0]["id"])
    ag.claim("agent-c", "konkret", ["ui/timeline.py"])
    _, c2 = ag.claim("agent-d", "glob", ["ui/*.py"])
    assert c2, "Glob des Zweiten muss die konkrete Datei des Ersten treffen"


def test_overlapping_glob_claims_conflict_on_shared_file_language():
    ag.claim("agent-a", "python ui", ["ui/*.py"])
    _, conflicts = ag.claim("agent-b", "timeline files", ["ui/timeline.*"])

    assert conflicts, "ueberlappende Glob-Sprachen muessen kollidieren"


def test_recursive_and_nested_glob_claims_conflict():
    ag.claim("agent-a", "all tests", ["tests/**/test_*.py"])
    _, conflicts = ag.claim("agent-b", "ui tests", ["tests/ui/*.py"])

    assert conflicts, "rekursiver und eingeschraenkter Glob muessen kollidieren"


def test_disjoint_character_class_globs_remain_parallel():
    ag.claim("agent-a", "lower shard", ["tests/test_[0-4]*.py"])
    second, conflicts = ag.claim("agent-b", "upper shard", ["tests/test_[5-9]*.py"])

    assert second and not conflicts, "disjunkte Zeichenklassen duerfen parallel laufen"
    assert ag._claims_overlap(["ui/[ab].py"], ["ui/[bc].py"])


def test_glob_intersection_respects_fixed_wildcard_length():
    ag.claim("agent-a", "one char", ["ui/a?.py"])
    second, conflicts = ag.claim("agent-b", "two chars", ["ui/a??.py"])

    assert second and not conflicts, "unterschiedliche feste Laengen sind disjunkt"


def test_unclosed_character_class_claim_fails_closed():
    ag.claim("agent-a", "malformed class", ["ui/[abc.py"])
    second, conflicts = ag.claim("agent-b", "matching file", ["ui/a.py"])

    assert not second and conflicts, "unvollstaendige Klasse muss fail-closed blockieren"


def test_empty_claim_never_conflicts():
    """Ein Agent ohne exklusiven Anspruch (z.B. reiner Lese-/Test-Lauf) darf
    immer starten — sonst koennte nie jemand neben einem Fixer testen."""
    ag.claim("fixer", "B-643", ["ui/timeline.py"])
    s, c = ag.claim("tester", "nur lesen", [])
    assert s and not c


def test_force_registers_despite_conflict():
    ag.claim("agent-a", "t", ["ui/timeline.py"])
    s, c = ag.claim("agent-b", "t", ["ui/timeline.py"], force=True)
    assert s, "force muss registrieren"
    assert c, "der Konflikt muss trotzdem gemeldet werden"


# ── ERKENNEN: Heartbeat / Stale ──────────────────────────────────────────────

def test_stale_session_is_pruned_and_unblocks():
    """Ein abgestuerzter Agent darf Dateien nicht dauerhaft blockieren."""
    ag.claim("crashed", "t", ["ui/timeline.py"])

    raw = json.loads(ag.registry_path().read_text(encoding="utf-8"))
    old = datetime.now(timezone.utc) - timedelta(seconds=ag.STALE_SEC + 60)
    raw["sessions"][0]["heartbeat"] = old.isoformat(timespec="seconds")
    raw["sessions"][0]["pid"] = 0          # keine PID-Aussage
    raw["sessions"][0]["host"] = "anderer-host"   # PID-Check ueberspringen
    ag.registry_path().write_text(json.dumps(raw), encoding="utf-8")

    assert ag.status() == [], "veraltete Session muss verschwinden"
    s, c = ag.claim("neuer", "t", ["ui/timeline.py"])
    assert s and not c, "nach dem Pruning muss der Pfad frei sein"


def test_dead_pid_is_pruned_on_same_host():
    """Prozess weg -> Session weg, auch wenn der Heartbeat noch frisch ist."""
    import platform
    ag.claim("crashed", "t", ["ui/timeline.py"])
    raw = json.loads(ag.registry_path().read_text(encoding="utf-8"))
    raw["sessions"][0]["pid"] = 999_999_999      # existiert sicher nicht
    raw["sessions"][0]["host"] = platform.node()  # eigener Host -> PID zaehlt
    ag.registry_path().write_text(json.dumps(raw), encoding="utf-8")
    assert ag.status() == []


def test_heartbeat_keeps_session_alive():
    s, _ = ag.claim("agent-a", "t", ["ui/timeline.py"])
    before = ag.status()[0]["heartbeat"]
    time.sleep(1.1)
    assert ag.heartbeat(s["id"]) is True
    assert ag.status()[0]["heartbeat"] != before


def test_heartbeat_unknown_id_is_false():
    assert ag.heartbeat("gibtsnicht") is False


# ── NACHWEISEN / Aufräumen ───────────────────────────────────────────────────

def test_release_frees_the_paths():
    s, _ = ag.claim("agent-a", "t", ["ui/timeline.py"])
    assert ag.release(s["id"]) is True
    assert ag.status() == []
    s2, c2 = ag.claim("agent-b", "t", ["ui/timeline.py"])
    assert s2 and not c2


def test_release_is_idempotent():
    s, _ = ag.claim("agent-a", "t", ["x.py"])
    ag.release(s["id"])
    ag.release(s["id"])   # darf nicht werfen
    assert ag.status() == []


def test_check_reports_conflict_without_registering():
    ag.claim("agent-a", "t", ["ui/timeline.py"])
    hits = ag.check(["ui/timeline.py"])
    assert hits and hits[0]["agent"] == "agent-a"
    assert len(ag.status()) == 1, "check darf nichts registrieren"


def test_check_ignores_own_session():
    s, _ = ag.claim("agent-a", "t", ["ui/timeline.py"])
    assert ag.check(["ui/timeline.py"], ignore_id=s["id"]) == []


# ── Idiotensicherheit ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [b"{kaputt: [", b"\xff\xfe"])
def test_corrupt_registry_fails_closed_without_overwrite(raw):
    ag.registry_path().write_bytes(raw)

    with pytest.raises(ag.RegistryReadError):
        ag.claim("agent-a", "t", ["x.py"])

    assert ag.registry_path().read_bytes() == raw


@pytest.mark.parametrize(
    "read_error",
    [PermissionError("transient registry read failure"), FileNotFoundError("vanished")],
)
def test_transient_registry_read_error_preserves_and_recovers_claim(
    monkeypatch, read_error
):
    ag.claim("owner", "active", ["ui/timeline.py"])
    registry = ag.registry_path()
    raw = registry.read_bytes()
    real_read_text = Path.read_text
    failed = False

    def flaky_read_text(path, *args, **kwargs):
        nonlocal failed
        if path == registry and not failed:
            failed = True
            raise read_error
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)
    with pytest.raises(ag.RegistryReadError):
        ag.status()
    assert registry.read_bytes() == raw

    second, conflicts = ag.claim("other", "conflict", ["ui/timeline.py"])
    assert not second and conflicts and conflicts[0]["agent"] == "owner"


def test_operational_missing_marker_and_registry_fails_closed():
    ag.initialization_marker_path().unlink()
    ag.registry_path().unlink()

    with pytest.raises(ag.RegistryReadError):
        ag.status()

    assert not ag.registry_path().exists()
    assert not ag.initialization_marker_path().exists()


def test_initialized_missing_registry_fails_closed():
    ag.claim("owner", "active", ["ui/timeline.py"])
    marker = ag.initialization_marker_path()
    assert marker.read_bytes() == ag.INITIALIZATION_MARKER_BYTES
    ag.registry_path().unlink()

    with pytest.raises(ag.RegistryReadError):
        ag.status()


def test_registry_stat_error_fails_closed(monkeypatch):
    ag.claim("owner", "active", ["ui/timeline.py"])
    registry = ag.registry_path()
    raw = registry.read_bytes()
    real_stat = Path.stat

    def failing_stat(path, *args, **kwargs):
        if path == registry:
            raise PermissionError("registry stat denied")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing_stat)
    with pytest.raises(ag.RegistryReadError):
        ag.status()
    assert registry.read_bytes() == raw


def test_markerless_legacy_registry_blocks_without_mutation():
    ag.claim("owner", "active", ["ui/timeline.py"])
    marker = ag.initialization_marker_path()
    marker.unlink()
    raw = ag.registry_path().read_bytes()

    with pytest.raises(ag.RegistryReadError):
        ag.status()

    assert ag.registry_path().read_bytes() == raw
    assert not marker.exists()


def test_markerless_legacy_registry_stat_false_missing_fails_closed(monkeypatch):
    ag.claim("owner", "active", ["ui/timeline.py"])
    registry = ag.registry_path()
    raw = registry.read_bytes()
    marker = ag.initialization_marker_path()
    marker.unlink()
    real_stat = Path.stat

    def false_missing_stat(path, *args, **kwargs):
        if path == registry:
            raise FileNotFoundError("legacy registry falsely missing")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", false_missing_stat)
    with pytest.raises(ag.RegistryReadError):
        ag.claim("other", "conflict", ["ui/timeline.py"])

    assert registry.read_bytes() == raw
    assert not marker.exists()


def test_invalid_initialization_marker_fails_closed():
    ag.claim("owner", "active", ["ui/timeline.py"])
    marker = ag.initialization_marker_path()
    marker.write_bytes(b"unknown-version\n")
    raw = ag.registry_path().read_bytes()

    with pytest.raises(ag.RegistryReadError):
        ag.status()

    assert ag.registry_path().read_bytes() == raw


def test_initialization_marker_read_error_fails_closed(monkeypatch):
    ag.claim("owner", "active", ["ui/timeline.py"])
    marker = ag.initialization_marker_path()
    registry = ag.registry_path()
    raw = registry.read_bytes()
    real_read_bytes = Path.read_bytes

    def failing_read_bytes(path, *args, **kwargs):
        if path == marker:
            raise PermissionError("registry marker read denied")
        return real_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", failing_read_bytes)
    with pytest.raises(ag.RegistryReadError):
        ag.status()

    assert registry.read_bytes() == raw


def test_bootstrap_initialize_empty_success():
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    registry.unlink()
    marker.unlink()

    ag.bootstrap_initialize_empty()

    assert json.loads(registry.read_text(encoding="utf-8")) == {"sessions": []}
    assert marker.read_bytes() == ag.INITIALIZATION_MARKER_BYTES
    assert ag.status() == []


def test_bootstrap_initialize_fstat_error_is_retryable_without_traceback(
    monkeypatch, capsys
):
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    registry.unlink()
    marker.unlink()
    real_open = os.open
    real_fstat = os.fstat
    registry_temp_fd = None

    def tracking_open(path, flags, *args, **kwargs):
        nonlocal registry_temp_fd
        fd = real_open(path, flags, *args, **kwargs)
        name = Path(path).name
        if name.startswith(".pb-agent-sessions.json.") and name.endswith(".tmp"):
            registry_temp_fd = fd
        return fd

    def failing_fstat(fd):
        if fd == registry_temp_fd:
            raise OSError("registry temp fstat denied")
        return real_fstat(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "fstat", failing_fstat)
    assert ag.main(["bootstrap", "--initialize-empty"]) == ag.EXIT_ERROR
    captured = capsys.readouterr()
    assert "registry temp fstat denied" in captured.err
    assert "Traceback" not in captured.err
    assert not registry.exists()
    assert not marker.exists()

    monkeypatch.setattr(os, "open", real_open)
    monkeypatch.setattr(os, "fstat", real_fstat)
    assert ag.main(["bootstrap", "--initialize-empty"]) == ag.EXIT_OK


def test_bootstrap_initialize_partial_write_is_retryable(monkeypatch):
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    registry.unlink()
    marker.unlink()
    real_write = os.write
    registry_fd = None
    calls = 0

    def partial_then_fail(fd, data):
        nonlocal registry_fd, calls
        if registry_fd is None and data != ag.EMPTY_REGISTRY_BYTES:
            return real_write(fd, data)
        if registry_fd is None:
            registry_fd = fd
        if fd != registry_fd:
            return real_write(fd, data)
        calls += 1
        if calls == 1:
            return real_write(fd, data[:1])
        raise PermissionError("empty registry write denied")

    monkeypatch.setattr(os, "write", partial_then_fail)
    with pytest.raises(ag.RegistryReadError, match="empty registry write denied"):
        ag.bootstrap_initialize_empty()
    assert not registry.exists()
    assert not marker.exists()

    monkeypatch.setattr(os, "write", real_write)
    ag.bootstrap_initialize_empty()
    assert ag.status() == []


def test_bootstrap_initialize_link_error_is_retryable(monkeypatch):
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    registry.unlink()
    marker.unlink()
    real_link = os.link
    failed = False

    def failing_registry_link(source, destination, *args, **kwargs):
        nonlocal failed
        if Path(destination) == registry and not failed:
            failed = True
            raise PermissionError("empty registry publish denied")
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", failing_registry_link)
    with pytest.raises(ag.RegistryReadError, match="empty registry publish denied"):
        ag.bootstrap_initialize_empty()
    assert not registry.exists()
    assert not marker.exists()

    ag.bootstrap_initialize_empty()
    assert ag.status() == []


@pytest.mark.parametrize("existing", ["registry", "marker"])
def test_bootstrap_initialize_empty_refuses_existing_state(existing):
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    if existing == "registry":
        marker.unlink()
        original = registry.read_bytes()
    else:
        registry.unlink()
        original = marker.read_bytes()

    with pytest.raises(ag.RegistryReadError):
        ag.bootstrap_initialize_empty()

    path = registry if existing == "registry" else marker
    assert path.read_bytes() == original


def test_bootstrap_migrate_preserves_registry_bytes_and_claims():
    ag.claim("owner", "active", ["ui/timeline.py"])
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    raw = registry.read_bytes()
    marker.unlink()

    ag.bootstrap_migrate_existing()

    assert registry.read_bytes() == raw
    assert marker.read_bytes() == ag.INITIALIZATION_MARKER_BYTES
    assert ag.status()[0]["agent"] == "owner"


@pytest.mark.parametrize(
    "open_error", [FileNotFoundError("vanished"), PermissionError("denied")]
)
def test_bootstrap_migrate_open_error_leaves_no_marker(monkeypatch, open_error):
    marker = ag.initialization_marker_path()
    marker.unlink()
    real_open = os.open

    def failing_open(path, flags, *args, **kwargs):
        if Path(path) == ag.registry_path():
            raise open_error
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", failing_open)
    with pytest.raises(ag.RegistryReadError):
        ag.bootstrap_migrate_existing()

    assert not marker.exists()


def test_bootstrap_migrate_identity_drift_leaves_no_marker(monkeypatch):
    marker = ag.initialization_marker_path()
    marker.unlink()
    real_stat = os.stat

    def drifting_stat(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if Path(path) == ag.registry_path():
            values = list(result)
            values[1] += 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "stat", drifting_stat)
    with pytest.raises(ag.RegistryReadError, match="Identitaet"):
        ag.bootstrap_migrate_existing()

    assert not marker.exists()


def test_partial_marker_write_never_publishes_final_marker(monkeypatch):
    ag.claim("owner", "active", ["ui/timeline.py"])
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    raw = registry.read_bytes()
    marker.unlink()
    real_write = os.write
    calls = 0
    marker_fd = None

    def partial_then_fail(fd, data):
        nonlocal calls, marker_fd
        if marker_fd is None and data != ag.INITIALIZATION_MARKER_BYTES:
            return real_write(fd, data)
        if marker_fd is None:
            marker_fd = fd
        if fd != marker_fd:
            return real_write(fd, data)
        calls += 1
        if calls == 1:
            return real_write(fd, data[:1])
        raise PermissionError("marker write denied")

    monkeypatch.setattr(os, "write", partial_then_fail)
    with pytest.raises(ag.RegistryReadError, match="marker write denied"):
        ag.bootstrap_migrate_existing()

    assert registry.read_bytes() == raw
    assert not marker.exists()
    monkeypatch.setattr(os, "write", real_write)
    ag.bootstrap_migrate_existing()
    assert ag.status()[0]["agent"] == "owner"


def test_marker_close_error_does_not_mask_primary_write_error(monkeypatch):
    ag.claim("owner", "active", ["ui/timeline.py"])
    marker = ag.initialization_marker_path()
    marker.unlink()
    real_write = os.write
    real_close = os.close
    marker_fd = None

    def failing_write(fd, data):
        nonlocal marker_fd
        if data != ag.INITIALIZATION_MARKER_BYTES:
            return real_write(fd, data)
        marker_fd = fd
        raise PermissionError("marker write denied")

    def failing_close(fd):
        real_close(fd)
        if fd == marker_fd:
            raise OSError("marker close failed")

    monkeypatch.setattr(os, "write", failing_write)
    monkeypatch.setattr(os, "close", failing_close)

    with pytest.raises(ag.RegistryReadError, match="marker write denied"):
        ag.bootstrap_migrate_existing()

    assert not marker.exists()


def test_cli_bootstrap_requires_exactly_one_mode():
    with pytest.raises(SystemExit) as missing:
        ag.main(["bootstrap"])
    assert missing.value.code == 2

    with pytest.raises(SystemExit) as both:
        ag.main(["bootstrap", "--migrate-existing", "--initialize-empty"])
    assert both.value.code == 2


def test_cli_bootstrap_modes_are_wired(capsys):
    registry = ag.registry_path()
    marker = ag.initialization_marker_path()
    registry.unlink()
    marker.unlink()

    assert ag.main(["bootstrap", "--initialize-empty"]) == ag.EXIT_OK
    assert marker.read_bytes() == ag.INITIALIZATION_MARKER_BYTES

    marker.unlink()
    raw = registry.read_bytes()
    assert ag.main(["bootstrap", "--migrate-existing"]) == ag.EXIT_OK
    assert registry.read_bytes() == raw
    assert marker.read_bytes() == ag.INITIALIZATION_MARKER_BYTES
    assert "Bootstrap" in capsys.readouterr().out


def test_cli_missing_marker_reports_explicit_recovery(capsys):
    ag.initialization_marker_path().unlink()

    assert ag.main(["status"]) == ag.EXIT_ERROR
    captured = capsys.readouterr()
    assert "--migrate-existing" in captured.err
    assert "--initialize-empty" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "mutation", ["top-level-list", "sessions-dict", "empty-row", "claims-string"]
)
def test_invalid_session_schema_fails_closed_without_overwrite(mutation):
    ag.claim("owner", "active", ["ui/timeline.py"])
    registry = ag.registry_path()
    data = json.loads(registry.read_text(encoding="utf-8"))
    if mutation == "top-level-list":
        data = []
    elif mutation == "sessions-dict":
        data["sessions"] = {}
    elif mutation == "empty-row":
        data["sessions"] = [{}]
    else:
        data["sessions"][0]["claims"] = "ui/timeline.py"
    registry.write_text(json.dumps(data), encoding="utf-8")
    raw = registry.read_bytes()

    with pytest.raises(ag.RegistryReadError):
        ag.status()

    assert registry.read_bytes() == raw


@pytest.mark.parametrize("mutation", ["duplicate", "invalid-format"])
def test_invalid_or_duplicate_session_ids_fail_closed(mutation):
    ag.claim("owner", "active", ["ui/timeline.py"])
    ag.claim("other", "active", ["services/export.py"])
    registry = ag.registry_path()
    data = json.loads(registry.read_text(encoding="utf-8"))
    if mutation == "duplicate":
        data["sessions"][1]["id"] = data["sessions"][0]["id"]
    else:
        data["sessions"][0]["id"] = "not-a-writer-id"
    registry.write_text(json.dumps(data), encoding="utf-8")
    raw = registry.read_bytes()

    with pytest.raises(ag.RegistryReadError):
        ag.release(data["sessions"][0]["id"])

    assert registry.read_bytes() == raw


def test_negative_pid_writer_roundtrips_as_unspecified():
    session, conflicts = ag.claim("owner", "active", ["x.py"], pid=-1)

    assert session and not conflicts and session["pid"] == 0
    assert ag.status()[0]["pid"] == 0


@pytest.mark.parametrize("raw", [b"{kaputt: [", b"\xff\xfe"])
def test_cli_registry_error_returns_one_without_traceback(capsys, raw):
    ag.registry_path().write_bytes(raw)

    assert ag.main(["status"]) == ag.EXIT_ERROR
    captured = capsys.readouterr()
    assert "Registry" in captured.err
    assert "Traceback" not in captured.err


def test_wrappers_block_all_registry_errors_before_success_messages():
    start = (REPO_ROOT / "tools" / "agent_start.ps1").read_text(encoding="utf-8")
    handoff = (REPO_ROOT / "tools" / "agent_handoff.ps1").read_text(encoding="utf-8")

    assert "$agentGuardExit = $LASTEXITCODE" in start
    assert "if ($agentGuardExit -ne 0)" in start
    assert "$sessionReleaseExit = $LASTEXITCODE" in handoff
    assert "if ($sessionReleaseExit -ne 0)" in handoff
    assert "$sessionStatusExit = $LASTEXITCODE" in handoff
    assert "if ($sessionStatusExit -ne 0)" in handoff
    assert handoff.index("if ($sessionReleaseExit -ne 0)") < handoff.index("Session freigegeben")
    assert handoff.index("if ($sessionStatusExit -ne 0)") < handoff.index("OK: clean handoff state")


def test_stale_lock_is_broken():
    """Verwaistes Lock eines abgestuerzten Prozesses -> kein Deadlock."""
    lock = ag._lock_path()
    lock.write_text("999999")
    old = time.time() - (ag.LOCK_STALE_SEC + 10)
    import os as _os
    _os.utime(lock, (old, old))
    s, _ = ag.claim("agent-a", "t", ["x.py"])   # darf nicht haengen
    assert s


def test_lock_exit_never_removes_foreign_owner_payload():
    """Lockverlust darf niemals fremde Bytes am gemeinsamen Pfad loeschen."""
    guard = ag._Lock()
    guard.__enter__()
    lock = ag._lock_path()
    ag._write_lock_payload(guard._fd, b"foreign-owner")
    guard.__exit__(None, None, None)
    assert ag._read_lock_payload(lock) == b"foreign-owner"


def test_write_is_atomic_no_tmp_left():
    ag.claim("agent-a", "t", ["x.py"])
    assert not list(ag.registry_path().parent.glob("*.tmp")), "tmp-Datei blieb liegen"


# ── CLI / Exit-Codes (die Skripte haengen daran) ─────────────────────────────

def test_cli_exit_codes():
    assert ag.main(["status"]) == ag.EXIT_OK
    assert ag.main(["claim", "--agent", "a", "--files", "ui/timeline.py"]) == ag.EXIT_OK
    # zweiter Claim auf dieselbe Datei -> Exit 2, damit PowerShell blocken kann
    assert ag.main(["claim", "--agent", "b", "--files", "ui/timeline.py"]) == ag.EXIT_CONFLICT
    assert ag.main(["check", "--files", "ui/timeline.py"]) == ag.EXIT_CONFLICT
    assert ag.main(["check", "--files", "voellig/anderes.py"]) == ag.EXIT_OK


def test_cli_claim_prints_only_the_id():
    """agent_start.ps1 liest die ID aus stdout — da darf nichts anderes stehen."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ag.main(["claim", "--agent", "a", "--task", "t", "--files", "x.py"])
    assert rc == ag.EXIT_OK
    out = buf.getvalue().strip()
    assert len(out) == 32 and all(ch in "0123456789abcdef" for ch in out), out

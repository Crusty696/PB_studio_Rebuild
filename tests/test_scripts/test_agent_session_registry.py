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


def test_glob_claims_conflict():
    """Globs muessen in BEIDE Richtungen greifen."""
    ag.claim("agent-a", "tests", ["tests/**"])
    _, c = ag.claim("agent-b", "ein test", ["tests/ui/test_x.py"])
    assert c, "Glob des Ersten muss die konkrete Datei des Zweiten treffen"

    ag.release(ag.status()[0]["id"])
    ag.claim("agent-c", "konkret", ["ui/timeline.py"])
    _, c2 = ag.claim("agent-d", "glob", ["ui/*.py"])
    assert c2, "Glob des Zweiten muss die konkrete Datei des Ersten treffen"


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

def test_corrupt_registry_does_not_crash():
    """Eine kaputte Datei darf agent_start NIE blockieren."""
    ag.registry_path().write_text("{kaputt: [", encoding="utf-8")
    assert ag.status() == []
    s, _ = ag.claim("agent-a", "t", ["x.py"])
    assert s


def test_stale_lock_is_broken():
    """Verwaistes Lock eines abgestuerzten Prozesses -> kein Deadlock."""
    lock = ag._lock_path()
    lock.write_text("999999")
    old = time.time() - (ag.LOCK_STALE_SEC + 10)
    import os as _os
    _os.utime(lock, (old, old))
    s, _ = ag.claim("agent-a", "t", ["x.py"])   # darf nicht haengen
    assert s


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

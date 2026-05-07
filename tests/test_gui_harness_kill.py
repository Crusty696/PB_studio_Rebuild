from __future__ import annotations

import json
from types import SimpleNamespace

import tests.gui_harness as harness


def test_cmd_kill_uses_minimum_grace_before_force(monkeypatch, tmp_path, capsys):
    pid_file = tmp_path / ".app_pid"
    pid_file.write_text("1234", encoding="utf-8")
    monkeypatch.setattr(harness, "PID_FILE", pid_file)
    monkeypatch.setattr(harness.sys, "platform", "win32")

    clock = {"now": 0.0}
    monkeypatch.setattr(harness.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(harness.time, "sleep", lambda sec: clock.__setitem__("now", clock["now"] + sec))

    def fake_run(cmd, **kwargs):
        if cmd[0] == "tasklist":
            # Process exits only after 12s; requested grace=10 would force-kill
            # without the harness minimum.
            stdout = '"python.exe","1234"\n' if clock["now"] < 12.0 else ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(harness.subprocess, "run", fake_run)

    rc = harness.cmd_kill(SimpleNamespace(pid=None, force=False, grace_sec=10.0))

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["method"] == "graceful"
    assert out["requested_grace_sec"] == 10.0
    assert out["grace_sec"] == 15.0

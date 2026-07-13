from __future__ import annotations

import json
from pathlib import Path


def test_session_requires_lesson_before_handoff(tmp_path):
    from tools.session_learning import record_lesson, start_session, verify_session

    state = tmp_path / "session.json"
    lessons = tmp_path / "lessons"
    started = start_session(state_path=state, repo_root=tmp_path, head="abc123")

    assert verify_session(state_path=state, lessons_path=lessons)["ok"] is False

    record_lesson(
        state_path=state,
        lessons_path=lessons,
        problem="Worktree used different FFmpeg",
        cause="Ignored bin directory missing in linked worktree",
        rule="Resolve from Git common root and verify SHA256",
        applies_to="External tool binaries in source/worktree/frozen runs",
    )

    result = verify_session(state_path=state, lessons_path=lessons)
    assert result == {"ok": True, "session_id": started["session_id"], "count": 1}
    assert len(list(lessons.glob("*.json"))) == 1


def test_start_preserves_and_returns_recent_cross_session_lessons(tmp_path):
    from tools.session_learning import record_lesson, recent_lessons, start_session

    lessons = tmp_path / "lessons"
    first_state = tmp_path / "first.json"
    start_session(state_path=first_state, repo_root=tmp_path, head="one")
    record_lesson(
        state_path=first_state,
        lessons_path=lessons,
        problem="Version drift",
        cause="PATH fallback",
        rule="Pin version and hash",
        applies_to="All subprocess tools",
    )
    second_state = tmp_path / "second.json"
    start_session(state_path=second_state, repo_root=tmp_path, head="two")

    recent = recent_lessons(lessons_path=lessons, limit=5)
    assert len(recent) == 1
    assert recent[0]["rule"] == "Pin version and hash"
    assert json.loads(second_state.read_text(encoding="utf-8"))["head"] == "two"


def test_agent_hooks_load_and_enforce_session_learning():
    root = Path(__file__).parents[2]
    start = (root / "tools" / "agent_start.ps1").read_text(encoding="utf-8")
    handoff = (root / "tools" / "agent_handoff.ps1").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert 'session_learning.py" start' in start
    assert 'session_learning.py" verify' in handoff
    assert "BLOCKED: session learning entry missing" in handoff
    assert "tools/session_learning.py record" in agents
    assert "nach jedem abgeschlossenen task" in agents.casefold()

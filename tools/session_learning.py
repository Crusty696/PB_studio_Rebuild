from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LESSONS = REPO_ROOT / "docs" / "superpowers" / "agent_lessons"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_state_path() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "pb-agent-session.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def start_session(*, state_path: Path, repo_root: Path, head: str) -> dict:
    state = {
        "session_id": uuid.uuid4().hex,
        "started_at": _utc_now(),
        "repo_root": str(Path(repo_root).resolve()),
        "head": head,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def recent_lessons(*, lessons_path: Path, limit: int = 8) -> list[dict]:
    if not lessons_path.is_dir():
        return []
    lessons = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in lessons_path.glob("*.json")
    ]
    lessons.sort(key=lambda item: (item.get("recorded_at", ""), item.get("lesson_id", "")))
    return lessons[-limit:]


def record_lesson(
    *,
    state_path: Path,
    lessons_path: Path,
    problem: str,
    cause: str,
    rule: str,
    applies_to: str,
) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = {
        "lesson_id": uuid.uuid4().hex,
        "recorded_at": _utc_now(),
        "session_id": state["session_id"],
        "head_at_start": state["head"],
        "problem": problem.strip(),
        "cause": cause.strip(),
        "rule": rule.strip(),
        "applies_to": applies_to.strip(),
    }
    if not all(entry[key] for key in ("problem", "cause", "rule", "applies_to")):
        raise ValueError("lesson fields must not be empty")
    lessons_path.mkdir(parents=True, exist_ok=True)
    lesson_file = lessons_path / f"{entry['recorded_at'][:10]}-{entry['lesson_id']}.json"
    lesson_file.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entry


def verify_session(*, state_path: Path, lessons_path: Path) -> dict:
    if not state_path.is_file():
        return {"ok": False, "error": "session state missing"}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    count = sum(
        1
        for lesson in recent_lessons(lessons_path=lessons_path, limit=100000)
        if lesson.get("session_id") == state["session_id"]
    )
    return {"ok": count > 0, "session_id": state["session_id"], "count": count}


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent agent session lessons")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start")
    record = sub.add_parser("record")
    record.add_argument("--problem", required=True)
    record.add_argument("--cause", required=True)
    record.add_argument("--rule", required=True)
    record.add_argument("--applies-to", required=True)
    sub.add_parser("verify")
    args = parser.parse_args()
    state_path = _default_state_path()

    if args.command == "start":
        state = start_session(state_path=state_path, repo_root=REPO_ROOT, head=_head())
        print(json.dumps({"session": state, "recent_lessons": recent_lessons(lessons_path=DEFAULT_LESSONS)}, indent=2, ensure_ascii=False))
        return 0
    if args.command == "record":
        entry = record_lesson(
            state_path=state_path,
            lessons_path=DEFAULT_LESSONS,
            problem=args.problem,
            cause=args.cause,
            rule=args.rule,
            applies_to=args.applies_to,
        )
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return 0
    result = verify_session(state_path=state_path, lessons_path=DEFAULT_LESSONS)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

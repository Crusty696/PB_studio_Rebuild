"""Short log watcher for OTK-021 long-run prep.

Default mode tails configured files from their current end position for a short
duration and reports matching error patterns. It is meant to be started before a
long run, not to run the long verification itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tests" / "qa_artifacts" / "otk021_live_log_watch_config.json"
RESULT = ROOT / "tests" / "qa_artifacts" / "otk021_live_log_watch_result.json"


def _write_result(result_path: Path, result: dict[str, object]) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _load_config(config_path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(config.get("logs"), list) or not isinstance(config.get("patterns"), list):
        return None, "config must contain list keys: logs, patterns"
    return config, None


def _compile_pattern(raw: str) -> re.Pattern[str]:
    if raw.lower() in {"error", "failed", "ffmpeg"}:
        return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(raw)}(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(re.escape(raw), re.IGNORECASE)


def _decode_log_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if data[:512].count(b"\x00") > max(1, len(data[:512]) // 4):
        return data.decode("utf-16le", errors="replace")
    return data.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-s", type=float, default=5.0)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--result", type=Path, default=RESULT)
    args = parser.parse_args()

    config, config_error = _load_config(args.config)
    if config_error:
        result = {
            "ok": False,
            "duration_s": args.duration_s,
            "hits": [],
            "logs": [],
            "missing_logs": [],
            "observed_logs": [],
            "events": [],
            "errors": [config_error],
        }
        _write_result(args.result, result)
        return 1

    logs = [Path(str(p)) for p in config["logs"]]  # type: ignore[index]
    pattern_pairs = [(str(p), _compile_pattern(str(p))) for p in config["patterns"]]  # type: ignore[index]
    offsets = {str(path): path.stat().st_size if path.exists() else 0 for path in logs}
    hits: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    existing_logs: set[str] = {str(path) for path in logs if path.exists()}
    read_logs: set[str] = set()
    deadline = time.monotonic() + args.duration_s

    while time.monotonic() < deadline:
        for path in logs:
            if not path.exists():
                continue
            key = str(path)
            existing_logs.add(key)
            size = path.stat().st_size
            if size < offsets.get(key, 0):
                events.append({"path": key, "event": "truncated_or_rotated", "old_offset": offsets[key], "new_size": size})
                offsets[key] = 0
            with path.open("rb") as fh:
                fh.seek(offsets.get(key, 0))
                data = fh.read()
                offsets[key] = fh.tell()
            if not data:
                continue
            read_logs.add(key)
            chunk = _decode_log_bytes(data)
            for line in chunk.splitlines():
                for raw, pattern in pattern_pairs:
                    if pattern.search(line):
                        hits.append({"path": key, "pattern": raw, "line": line[:1000]})
        time.sleep(0.5)

    missing_logs = [str(path) for path in logs if not path.exists()]
    result = {
        "ok": len(hits) == 0 and len(existing_logs) > 0,
        "duration_s": args.duration_s,
        "hits": hits,
        "logs": [str(path) for path in logs],
        "missing_logs": missing_logs,
        "existing_logs": sorted(existing_logs),
        "read_logs": sorted(read_logs),
        "events": events,
        "errors": [] if existing_logs else ["no configured log existed during watch"],
    }
    _write_result(args.result, result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

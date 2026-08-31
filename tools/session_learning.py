from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
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


# Themen-Schluessel: Muster im Lehrtext -> Muster in Dateipfaden.
# Aus der Auswertung des Bestandes am 2026-08-31 (289 Lehren): die haeufigsten
# Wiederholungen sind Verifikation (81), Pfade/Projektwechsel (102),
# Threads/Qt (61), Timeline/Pacing (53), Feature-Flags (46).
THEMEN: dict[str, tuple[str, str]] = {
    "verifikation": (
        r"verifizier|beleg|gemessen|nachweis|behaupt|live-?test|smoke",
        r"",
    ),
    "feature_flag": (
        r"flag|feature-?gate|settings\.json|settings_store|env-?var|default=",
        r"bridge\.py|settings|config",
    ),
    "threads": (
        r"thread|qthread|signal|slot|main-?thread|freeze|deadlock",
        r"workers?/|ui/|_worker|task_manager",
    ),
    "pfade": (
        r"pfad|path|projektwechsel|relativ|absolut|app_root|projektkopie",
        r"session\.py|_router|storage|export",
    ),
    "pacing": (
        r"pacing|segment|cut-?beat|timeline|schnitt|beat|onset",
        r"pacing|timeline|edit",
    ),
    "tests": (
        r"fixture|monkeypatch|test-?isolation|singleton|reale db|echte db",
        r"tests?/|conftest",
    ),
    "gpu": (
        r"gpu|vram|cuda|nvenc|siglip|demucs",
        r"model_manager|video_analysis|convert|ffmpeg",
    ),
    "datenbank": (
        r"sqlalchemy|session|commit|expire_on_commit|migration|alembic",
        r"database|models\.py|migrations",
    ),
}


def relevante_lessons(
    *,
    lessons_path: Path,
    stichworte: list[str] | None = None,
    dateien: list[str] | None = None,
    limit: int = 6,
) -> list[dict]:
    """Lehren, die zum aktuellen Arbeitsgegenstand passen.

    ``start`` gibt die acht juengsten Lehren aus. Bei 289 Eintraegen trifft das
    das eigene Thema nur zufaellig — die Lehre zum Pruefen von Feature-Flags lag
    am 2026-08-31 im Bestand und wurde am selben Tag trotzdem verletzt.

    Hier wird stattdessen nach Thema gesucht: entweder ueber freie Stichworte
    oder ueber die gerade geaenderten Dateien.
    """
    if not lessons_path.is_dir():
        return []

    heu = " ".join(stichworte or []).lower()
    pfade = " ".join(dateien or []).lower().replace("\\", "/")

    aktive: list[str] = []
    for thema, (text_muster, pfad_muster) in THEMEN.items():
        if heu and re.search(text_muster, heu):
            aktive.append(text_muster)
        elif pfade and pfad_muster and re.search(pfad_muster, pfade):
            aktive.append(text_muster)

    if not aktive and heu:
        # Kein Thema erkannt: die Stichworte selbst als Muster nutzen.
        aktive = [re.escape(w) for w in heu.split() if len(w) > 3]
    if not aktive:
        return []

    treffer: list[tuple[int, str, dict]] = []
    for pfad in lessons_path.glob("*.json"):
        lesson = json.loads(pfad.read_text(encoding="utf-8"))
        text = " ".join(str(lesson.get(k, "")) for k in
                        ("problem", "cause", "rule", "applies_to")).lower()
        punkte = sum(len(re.findall(muster, text)) for muster in aktive)
        if punkte:
            treffer.append((punkte, lesson.get("recorded_at", ""), lesson))

    treffer.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [lesson for _, _, lesson in treffer[:limit]]


def geaenderte_dateien() -> list[str]:
    """Dateien im aktuellen Arbeitsstand (uncommitted + letzter Commit)."""
    namen: set[str] = set()
    for befehl in (["git", "diff", "--name-only", "HEAD"],
                   ["git", "diff", "--name-only", "--cached"]):
        ergebnis = subprocess.run(befehl, cwd=REPO_ROOT,
                                  capture_output=True, text=True)
        namen.update(z.strip() for z in ergebnis.stdout.splitlines() if z.strip())
    return sorted(namen)


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
    rel = sub.add_parser(
        "relevant", help="Lehren zum aktuellen Thema statt der juengsten acht")
    rel.add_argument("--for", dest="stichworte", nargs="*", default=None,
                     help="freie Stichworte, z.B. flag pacing")
    rel.add_argument("--changed", action="store_true",
                     help="Thema aus den gerade geaenderten Dateien ableiten")
    rel.add_argument("--limit", type=int, default=6)
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
    if args.command == "relevant":
        dateien = geaenderte_dateien() if args.changed else None
        gefunden = relevante_lessons(
            lessons_path=DEFAULT_LESSONS,
            stichworte=args.stichworte,
            dateien=dateien,
            limit=args.limit,
        )
        if not gefunden:
            print("Keine passende Lehre im Bestand.")
            return 0
        if dateien:
            print(f"Thema aus {len(dateien)} geaenderten Datei(en) abgeleitet.")
        for lesson in gefunden:
            print("")
            print("[%s] %s" % (lesson.get("recorded_at", "?")[:10],
                               lesson.get("applies_to", "?")))
            print(f"  Problem: {lesson.get('problem', '')}")
            print(f"  REGEL  : {lesson.get('rule', '')}")
        return 0

    result = verify_session(state_path=state_path, lessons_path=DEFAULT_LESSONS)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Multi-Agent-Session-Registry — Konflikte verhindern, erkennen, nachweisen.

WARUM ES DAS GIBT (reale Vorfaelle 2026-07-15, siehe Vault log.md 12:35/13:00):
  1. Ein zweiter Agent ("Antigravity Agent") committete 23 Dateien, an denen ein
     anderer Agent gerade arbeitete — niemand merkte, dass beide liefen.
  2. Ein Test-Subagent loeschte eine Doku-Datei, um agent_handoff.ps1 gruen zu
     bekommen — obwohl er die Regel kannte und zweimal zitiert hatte.
  3. Am Obsidian-Vault arbeiteten parallel weitere Agenten (gemini).

WARUM DER BISHERIGE SCHUTZ NICHT REICHTE:
  agent_start.ps1/agent_handoff.ps1 koordinieren ueber den WORKTREE-ZUSTAND
  ("dirty?"). Das erkennt unfertige Arbeit, NICHT einen aktiven Agenten. Committet
  Agent A (wie oben geschehen), ist der Worktree sauber -> Agent B startet
  ahnungslos, obwohl A weiterarbeitet. Genau so ist es passiert.

WAS DIESES MODUL TUT:
  - ERKENNEN:   aktive Praesenz per Heartbeat (+ best-effort PID-Liveness)
  - NACHWEISEN: jede Session beansprucht explizit Pfade (claims)
  - VERHINDERN: ueberlappende Claims werden abgelehnt (Exit-Code != 0)
  Die eigentliche STRUKTURELLE Trennung macht der Worktree-Zwang in
  agent_start.ps1; dieses Modul liefert ihm die Entscheidungsgrundlage.

WO DIE REGISTRY LIEGT — der kritische Punkt:
  ``git rev-parse --git-common-dir``, NICHT ``--git-dir``/``--git-path``.
  In einem Worktree zeigt --git-dir auf .git/worktrees/<name>/ — eine Registry
  dort waere PRO WORKTREE getrennt und wuerde exakt nichts koordinieren.
  --git-common-dir zeigt in ALLEN Worktrees auf dasselbe .git/. Verifiziert:
    Haupt-Worktree: git-dir=.git            common=.git
    Linked-Worktree: git-dir=.git/worktrees/x  common=.git
  Die Datei liegt bewusst in .git/ -> nicht versioniert, kein Merge-Konflikt,
  wird von `git clean` nicht angefasst.

  Dateiname PLURAL (pb-agent-sessions.json), um die bestehende
  pb-agent-session.json (Singular, gehoert tools/session_learning.py) NICHT
  anzufassen.

IDIOTENSICHERHEIT — was hier bewusst abgesichert ist:
  - Atomares Schreiben (tmp + os.replace) -> nie eine halbe Datei.
  - Exklusiv-Lock per O_CREAT|O_EXCL (atomar auf NTFS und POSIX) mit Timeout;
    ein verwaistes Lock aelter als LOCK_STALE_SEC wird gebrochen -> kein Deadlock.
  - Korrupte/leere Registry -> wird verworfen statt zu crashen.
  - Tote Sessions (Heartbeat alt ODER, falls eine echte Agent-PID mitgegeben
    wurde, Prozess weg) werden bei JEDER Operation automatisch entfernt -> ein
    abgestuerzter Agent blockiert nichts dauerhaft.
  - Die PID ist OPTIONAL und meint die des AGENTEN. Sie darf NICHT die dieses
    CLI-Prozesses sein: der stirbt sofort nach dem Kommando, und die eigene
    Session wuerde beim naechsten Aufruf als "Prozess weg" geloescht. Genau
    dieser Fehler trat im ersten Worktree-Test auf (beide Sessions weg,
    Konflikt unerkannt). Ohne --pid ist der Heartbeat der alleinige Nachweis.
  - Alle Operationen sind idempotent.

CLI (fuer PowerShell-Skripte und Menschen):
    python tools/agent_session.py claim   --agent claude --task "B-643" --files ui/timeline.py
    python tools/agent_session.py heartbeat --id <session-id>
    python tools/agent_session.py release --id <session-id>
    python tools/agent_session.py status
    python tools/agent_session.py check   --files ui/timeline.py
Exit-Codes: 0 = ok/frei, 1 = Fehler, 2 = KONFLIKT (fremde aktive Session).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Eine Session gilt als tot, wenn ihr Heartbeat aelter ist als das hier.
# 15 Min: lang genug fuer einen langen Build/Testlauf ohne Heartbeat,
# kurz genug, dass ein abgestuerzter Agent nicht ewig blockiert.
STALE_SEC: int = 15 * 60

# Ein Lock, das aelter ist, gilt als verwaist (Prozess waehrend des Schreibens
# gestorben) und darf gebrochen werden. Schreibvorgaenge dauern Millisekunden.
LOCK_STALE_SEC: int = 30

LOCK_TIMEOUT_SEC: float = 10.0
LOCK_POLL_SEC: float = 0.05

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFLICT = 2


# ── Pfade ────────────────────────────────────────────────────────────────────

def _git_common_dir() -> Path:
    """Gemeinsames .git ALLER Worktrees.

    NICHT --git-dir/--git-path verwenden: die zeigen in einem Linked-Worktree
    auf .git/worktrees/<name>/ und wuerden die Registry pro Worktree isolieren.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    p = Path(out)
    if not p.is_absolute():
        # Im Haupt-Worktree liefert git ".git" relativ zum CWD.
        p = (Path.cwd() / p).resolve()
    return p


def registry_path() -> Path:
    return _git_common_dir() / "pb-agent-sessions.json"


def _lock_path() -> Path:
    return _git_common_dir() / "pb-agent-sessions.lock"


# ── Lock ─────────────────────────────────────────────────────────────────────

class _Lock:
    """Exklusiv-Lock ueber O_CREAT|O_EXCL — atomar auf NTFS und POSIX.

    Kein Deadlock moeglich: verwaiste Locks (aelter als LOCK_STALE_SEC) werden
    gebrochen, und nach LOCK_TIMEOUT_SEC wird aufgegeben.
    """

    def __init__(self) -> None:
        self._path = _lock_path()
        self._fd: int | None = None

    def __enter__(self) -> "_Lock":
        deadline = time.time() + LOCK_TIMEOUT_SEC
        while True:
            try:
                self._fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                # Verwaistes Lock eines abgestuerzten Prozesses brechen.
                try:
                    age = time.time() - self._path.stat().st_mtime
                    if age > LOCK_STALE_SEC:
                        self._path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError(
                        f"agent_session: Lock nicht erhalten ({self._path}). "
                        f"Laeuft ein anderer Vorgang? Notfalls Datei loeschen."
                    )
                time.sleep(LOCK_POLL_SEC)

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._path.unlink(missing_ok=True)


# ── Registry-IO ──────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _read_raw() -> dict:
    p = registry_path()
    if not p.exists():
        return {"sessions": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Korrupt (z.B. abgebrochener Schreibvorgang aus einer Alt-Version) ->
        # verwerfen statt crashen. Schlimmster Fall: aktive Sessions vergessen,
        # das ist reparabel; ein Crash im agent_start waere es nicht.
        return {"sessions": []}
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        return {"sessions": []}
    return data


def _write_raw(data: dict) -> None:
    """Atomar schreiben: erst tmp, dann os.replace (atomar auf NTFS + POSIX)."""
    p = registry_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


# ── Liveness ─────────────────────────────────────────────────────────────────

def _pid_alive(pid: int) -> bool | None:
    """True/False wenn ermittelbar, sonst None (dann zaehlt nur der Heartbeat).

    Best effort und bewusst konservativ: Im Zweifel None -> die Session bleibt
    stehen, bis ihr Heartbeat veraltet. Lieber einmal zu lange blockieren als
    einen aktiven Agenten faelschlich fuer tot erklaeren und seine Dateien
    freizugeben.

    pid <= 0 bedeutet ausdruecklich "keine PID-Aussage moeglich" -> None.
    """
    if not pid or pid <= 0:
        return None
    try:
        if platform.system() == "Windows":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True   # existiert, gehoert nur jemand anderem
    except (OSError, ProcessLookupError):
        return False
    except Exception:  # noqa: BLE001 — Liveness darf nie die Registry killen
        return None


def _is_dead(session: dict, now: float) -> bool:
    if now - _parse_ts(session.get("heartbeat", "")) > STALE_SEC:
        return True
    # Nur der eigene Host kann PIDs sinnvoll pruefen.
    if session.get("host") == platform.node():
        if _pid_alive(session.get("pid", 0)) is False:
            return True
    return False


def _prune(data: dict) -> tuple[dict, list[dict]]:
    now = time.time()
    alive, dead = [], []
    for s in data.get("sessions", []):
        (dead if _is_dead(s, now) else alive).append(s)
    return {"sessions": alive}, dead


# ── Claims ───────────────────────────────────────────────────────────────────

def _norm(path: str) -> str:
    return str(path).replace("\\", "/").strip().lstrip("./")


def _claims_overlap(a: list[str], b: list[str]) -> list[str]:
    """Ueberlappende Claims. Unterstuetzt Globs auf beiden Seiten.

    Ein leerer Claim ("ich beanspruche nichts Konkretes") kollidiert NICHT —
    sonst koennte ein reiner Lese-/Test-Agent nie neben einem Fixer laufen.
    """
    hits: list[str] = []
    for x in a:
        nx = _norm(x)
        for y in b:
            ny = _norm(y)
            if nx == ny or fnmatch.fnmatch(nx, ny) or fnmatch.fnmatch(ny, nx):
                hits.append(nx)
                break
    return hits


# ── Operationen ──────────────────────────────────────────────────────────────

def status() -> list[dict]:
    with _Lock():
        data, dead = _prune(_read_raw())
        if dead:
            _write_raw(data)
    return data["sessions"]


def check(files: list[str], ignore_id: str | None = None) -> list[dict]:
    """Fremde aktive Sessions, deren Claims mit *files* kollidieren."""
    conflicts = []
    for s in status():
        if ignore_id and s.get("id") == ignore_id:
            continue
        hits = _claims_overlap(files, s.get("claims", []))
        if hits:
            conflicts.append({**s, "_hits": hits})
    return conflicts


def claim(agent: str, task: str, files: list[str], branch: str | None = None,
          worktree: str | None = None, force: bool = False,
          pid: int = 0) -> tuple[dict, list[dict]]:
    """Session registrieren. Gibt (session, conflicts) zurueck.

    Bei Konflikt wird NICHT registriert (ausser force=True) — der Aufrufer
    entscheidet. force ist fuer den dokumentierten Ausnahmefall (User sagt
    ausdruecklich "trotzdem"), nicht fuer den Alltag.

    pid: PID des AGENTEN (nicht dieses Prozesses!). 0 = keine Angabe -> es
    zaehlt allein der Heartbeat.

    WARUM NICHT os.getpid(): Dieses Modul laeuft als kurzlebiger CLI-Prozess.
    Seine PID ist tot, sobald claim() zurueckkehrt — beim naechsten Aufruf
    wuerde die eigene Session sofort als "Prozess weg" weggeraeumt. Genau das
    passierte im ersten Worktree-Test: beide Sessions verschwanden und der
    Konflikt blieb unerkannt. Wer eine echte, langlebige PID hat (z.B. ein
    Wrapper-Skript), kann sie via --pid mitgeben; sonst ist der Heartbeat der
    alleinige Lebendigkeits-Nachweis.
    """
    with _Lock():
        data, _ = _prune(_read_raw())
        conflicts = []
        for s in data["sessions"]:
            hits = _claims_overlap(files, s.get("claims", []))
            if hits:
                conflicts.append({**s, "_hits": hits})
        if conflicts and not force:
            return {}, conflicts

        session = {
            "id": uuid.uuid4().hex,
            "agent": agent,
            "task": task,
            "pid": int(pid or 0),
            "host": platform.node(),
            "branch": branch or _git("rev-parse", "--abbrev-ref", "HEAD"),
            "worktree": worktree or _git("rev-parse", "--show-toplevel"),
            "started_at": _utc_now(),
            "heartbeat": _utc_now(),
            "claims": [_norm(f) for f in files],
        }
        data["sessions"].append(session)
        _write_raw(data)
        return session, conflicts


def heartbeat(session_id: str) -> bool:
    with _Lock():
        data, _ = _prune(_read_raw())
        for s in data["sessions"]:
            if s.get("id") == session_id:
                s["heartbeat"] = _utc_now()
                _write_raw(data)
                return True
        return False


def release(session_id: str) -> bool:
    with _Lock():
        data, _ = _prune(_read_raw())
        before = len(data["sessions"])
        data["sessions"] = [s for s in data["sessions"] if s.get("id") != session_id]
        _write_raw(data)
        return len(data["sessions"]) < before


def guard(worktree: str | None = None) -> tuple[list[dict], list[dict]]:
    """Start-Waechter fuer agent_start.ps1. Gibt (blocker, andere) zurueck.

    BLOCKER = fremde aktive Session im SELBEN Worktree. Das ist der
    Antigravity-Fall: zwei Agenten im selben Verzeichnis auf demselben Branch —
    einer committet die Dateien des anderen mit. Dagegen hilft keine Absprache,
    nur Trennung. -> Exit 2, der Start wird abgebrochen.

    ANDERE = aktive Sessions in anderen Worktrees. Das ist der GEWOLLTE Zustand
    (parallele Arbeit, sauber getrennt) -> kein Block, nur Anzeige, damit man
    weiss wer sonst noch laeuft.
    """
    wt = _norm(worktree or _git("rev-parse", "--show-toplevel"))
    blocker, andere = [], []
    for s in status():
        (blocker if _norm(s.get("worktree", "")) == wt else andere).append(s)
    return blocker, andere


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


# ── CLI ──────────────────────────────────────────────────────────────────────

def _fmt(s: dict) -> str:
    age = int(time.time() - _parse_ts(s.get("heartbeat", "")))
    return (f"  [{s.get('agent')}] {s.get('task') or '(ohne Task)'}\n"
            f"      id={s.get('id')}  pid={s.get('pid')}  host={s.get('host')}\n"
            f"      branch={s.get('branch')}  worktree={s.get('worktree')}\n"
            f"      heartbeat vor {age}s  claims={s.get('claims')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Multi-Agent-Session-Registry")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("claim", help="Session anmelden (prueft Konflikte)")
    c.add_argument("--agent", required=True)
    c.add_argument("--task", default="")
    c.add_argument("--files", nargs="*", default=[],
                   help="beanspruchte Pfade/Globs; leer = kein exklusiver Anspruch")
    c.add_argument("--branch")
    c.add_argument("--worktree")
    c.add_argument("--force", action="store_true",
                   help="trotz Konflikt registrieren (nur mit ausdruecklichem User-OK)")
    c.add_argument("--pid", type=int, default=0,
                   help="PID des AGENTEN (nicht dieses CLI-Prozesses!). "
                        "0 = keine Angabe, dann zaehlt allein der Heartbeat.")

    h = sub.add_parser("heartbeat", help="Lebenszeichen senden")
    h.add_argument("--id", required=True)

    r = sub.add_parser("release", help="Session abmelden")
    r.add_argument("--id", required=True)

    sub.add_parser("status", help="aktive Sessions anzeigen")

    g = sub.add_parser("guard", help="Start-Waechter: blockt fremde Session im selben Worktree")
    g.add_argument("--worktree")

    ck = sub.add_parser("check", help="pruefen ob Pfade frei sind")
    ck.add_argument("--files", nargs="+", required=True)
    ck.add_argument("--ignore-id")

    a = ap.parse_args(argv)

    try:
        if a.cmd == "status":
            sessions = status()
            if not sessions:
                print("Keine aktiven Agent-Sessions.")
                return EXIT_OK
            print(f"{len(sessions)} aktive Agent-Session(s):")
            for s in sessions:
                print(_fmt(s))
            return EXIT_OK

        if a.cmd == "guard":
            blocker, andere = guard(a.worktree)
            if andere:
                print(f"INFO: {len(andere)} Agent-Session(s) in ANDEREN Worktrees "
                      f"(gewollt, kein Block):")
                for s_ in andere:
                    print(_fmt(s_))
                print()
            if blocker:
                print("BLOCKED: in DIESEM Worktree arbeitet bereits ein Agent.")
                for s_ in blocker:
                    print(_fmt(s_))
                print()
                print("Zwei Agenten im selben Worktree = der Vorfall vom 2026-07-15")
                print("(fremde Dateien mitcommittet). Loesung: eigenen Worktree + Branch:")
                print("  git worktree add ../pb-<task> -b agent/<task>")
                print("Oder warten, bis die Session endet (release/Heartbeat-Ablauf).")
                return EXIT_CONFLICT
            print("OK: kein anderer Agent in diesem Worktree.")
            return EXIT_OK

        if a.cmd == "check":
            conflicts = check(a.files, ignore_id=a.ignore_id)
            if not conflicts:
                print("FREI: keine fremde Session beansprucht diese Pfade.")
                return EXIT_OK
            print("KONFLIKT: Pfade sind von einer aktiven Session beansprucht:")
            for s in conflicts:
                print(_fmt(s))
                print(f"      -> Ueberlappung: {s['_hits']}")
            return EXIT_CONFLICT

        if a.cmd == "claim":
            session, conflicts = claim(a.agent, a.task, a.files, a.branch,
                                       a.worktree, a.force, a.pid)
            if conflicts and not a.force:
                print("KONFLIKT: nicht registriert. Aktive fremde Session(s):")
                for s in conflicts:
                    print(_fmt(s))
                    print(f"      -> Ueberlappung: {s['_hits']}")
                print("\nOptionen: eigenen Worktree+Branch nutzen, warten, oder")
                print("(nur mit ausdruecklichem User-OK) --force.")
                return EXIT_CONFLICT
            if conflicts:
                print("WARNUNG: trotz Konflikt registriert (--force).")
            print(session["id"])
            return EXIT_OK

        if a.cmd == "heartbeat":
            return EXIT_OK if heartbeat(a.id) else EXIT_ERROR

        if a.cmd == "release":
            release(a.id)   # idempotent: schon weg ist auch ok
            return EXIT_OK

    except TimeoutError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return EXIT_ERROR
    except subprocess.CalledProcessError:
        print("FEHLER: kein Git-Repository?", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

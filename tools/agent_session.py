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
  - Exklusiv-Lock per OS-Byte-Lock (NTFS/POSIX) mit Timeout; der Lockpfad bleibt
    persistent und wird nie per Pfadoperation ersetzt oder fremd geloescht.
  - Operative Nutzung verlangt gueltigen Marker + Registry; fehlender Zustand
    blockiert fail-closed. Empty-Init/Legacy-Migration nur explizit per bootstrap.
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


class RegistryReadError(RuntimeError):
    """Bestehende Registry ist nicht sicher lesbar oder strukturell ungueltig."""


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


INITIALIZATION_MARKER_BYTES = b"pb-agent-sessions-v1\n"
EMPTY_REGISTRY_BYTES = b'{\n  "sessions": []\n}\n'


def initialization_marker_path() -> Path:
    return _git_common_dir() / "pb-agent-sessions.initialized"


def _lock_path() -> Path:
    return _git_common_dir() / "pb-agent-sessions.lock"


# ── Lock ─────────────────────────────────────────────────────────────────────

_LOCK_SENTINEL = b"\0"


def _prepare_lock_file(fd: int) -> None:
    if os.fstat(fd).st_size == 0:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, _LOCK_SENTINEL)
        os.fsync(fd)


def _try_lock_fd(fd: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_fd(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _path_matches_fd(path: Path, fd: int) -> bool:
    try:
        opened = os.fstat(fd)
        current = path.stat()
        return (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
    except OSError:
        return False


def _write_lock_payload(fd: int, payload: bytes) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, _LOCK_SENTINEL + payload)
    os.ftruncate(fd, 1 + len(payload))
    os.fsync(fd)


def _read_lock_payload(path: Path) -> bytes | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw.startswith(_LOCK_SENTINEL):
        return None
    return raw[1:]


def _read_lock_payload_fd(fd: int) -> bytes | None:
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, os.fstat(fd).st_size)
    finally:
        os.lseek(fd, position, os.SEEK_SET)
    if not raw.startswith(_LOCK_SENTINEL):
        return None
    return raw[1:]

class _Lock:
    """Exklusiver OS-Byte-Lock auf persistentem gemeinsamen Lockpfad.

    Der Kernel gibt den Byte-Lock bei Prozessende frei. Deshalb muss kein
    verwaister Pfad geloescht oder ersetzt werden; fremde Bytes bleiben bei
    Ownershipverlust unangetastet.
    """

    def __init__(self) -> None:
        self._path = _lock_path()
        self._fd: int | None = None
        self._token = uuid.uuid4().hex

    def _payload(self) -> bytes:
        return json.dumps(
            {"token": self._token, "pid": os.getpid()},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8") + b"\n"

    def _owner(self) -> bool:
        if self._fd is None or not _path_matches_fd(self._path, self._fd):
            return False
        try:
            value = json.loads((_read_lock_payload_fd(self._fd) or b"").decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return False
        return value == {"token": self._token, "pid": os.getpid()}

    def __enter__(self) -> "_Lock":
        deadline = time.monotonic() + LOCK_TIMEOUT_SEC
        while True:
            fd: int | None = None
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR)
                _prepare_lock_file(fd)
                if _try_lock_fd(fd) and _path_matches_fd(self._path, fd):
                    self._fd = fd
                    _write_lock_payload(fd, self._payload())
                    return self
            finally:
                if fd is not None and fd != self._fd:
                    _unlock_fd(fd)
                    os.close(fd)
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"agent_session: Lock nicht erhalten ({self._path}). "
                    "Laeuft ein anderer Vorgang?"
                )
            time.sleep(LOCK_POLL_SEC)

    def __exit__(self, *exc) -> None:
        fd = self._fd
        if fd is None:
            return
        cleanup_error: OSError | None = None
        try:
            try:
                owner = self._owner()
            except OSError as error:
                cleanup_error = error
                owner = False
            if owner:
                try:
                    _write_lock_payload(fd, b"")
                except OSError as error:
                    cleanup_error = cleanup_error or error
        finally:
            self._fd = None
            try:
                try:
                    _unlock_fd(fd)
                except OSError as error:
                    cleanup_error = cleanup_error or error
            finally:
                try:
                    os.close(fd)
                except OSError as error:
                    cleanup_error = cleanup_error or error
        if exc[0] is None and cleanup_error is not None:
            raise cleanup_error

    def _owner_with_fd(self, fd: int) -> bool:
        try:
            value = json.loads((_read_lock_payload_fd(fd) or b"").decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return False
        return value == {"token": self._token, "pid": os.getpid()}


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
    if not _read_initialization_marker():
        raise RegistryReadError(
            "Registry nicht initialisiert; explizit `bootstrap --migrate-existing` "
            "oder `bootstrap --initialize-empty` ausfuehren"
        )
    try:
        p.stat()
    except FileNotFoundError as exc:
        raise RegistryReadError(
            "Registry fehlt trotz vorhandenem Initialisierungsmarker"
        ) from exc
    except OSError as exc:
        raise RegistryReadError(f"Registry-Status nicht lesbar: {exc}") from exc
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RegistryReadError(
            "Registry verschwand nach erfolgreicher Statuspruefung"
        ) from exc
    except UnicodeError as exc:
        raise RegistryReadError(f"Registry ist nicht gueltiges UTF-8: {exc}") from exc
    except OSError as exc:
        raise RegistryReadError(f"Registry nicht lesbar: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryReadError(f"Registry enthaelt ungueltiges JSON: {exc}") from exc
    _validate_registry(data)
    return data


def _read_initialization_marker() -> bool:
    return _read_initialization_marker_at(_git_common_dir())


def _read_initialization_marker_at(common_dir: Path) -> bool:
    marker = common_dir / "pb-agent-sessions.initialized"
    try:
        raw = marker.read_bytes()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RegistryReadError(f"Registry-Marker nicht lesbar: {exc}") from exc
    if raw != INITIALIZATION_MARKER_BYTES:
        raise RegistryReadError("Registry-Marker hat unbekannte Version oder Bytes")
    return True


def _create_initialization_marker() -> None:
    marker = initialization_marker_path()
    if _read_initialization_marker():
        raise RegistryReadError("Registry-Marker ist bereits vorhanden")
    tmp = marker.with_name(f".{marker.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(str(tmp), flags)
    except FileExistsError:
        raise RegistryReadError("Einzigartige Registry-Marker-Tempdatei existiert")
    except OSError as exc:
        raise RegistryReadError(f"Registry-Marker nicht erstellbar: {exc}") from exc
    try:
        try:
            _write_all(fd, INITIALIZATION_MARKER_BYTES, "Registry-Marker")
            try:
                os.fsync(fd)
            except OSError as exc:
                raise RegistryReadError(
                    f"Registry-Marker nicht synchronisierbar: {exc}"
                ) from exc
        finally:
            _close_fd_preserving_primary(fd, "Registry-Marker")
        try:
            os.link(str(tmp), str(marker))
        except FileExistsError as exc:
            raise RegistryReadError(
                "Registry-Marker erschien waehrend atomarer Publikation"
            ) from exc
        except OSError as exc:
            raise RegistryReadError(
                f"Registry-Marker nicht atomar publizierbar: {exc}"
            ) from exc
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _write_all(fd: int, data: bytes, label: str) -> None:
    offset = 0
    while offset < len(data):
        try:
            written = os.write(fd, data[offset:])
        except OSError as exc:
            raise RegistryReadError(f"{label} nicht schreibbar: {exc}") from exc
        if written <= 0:
            raise RegistryReadError(f"{label} wurde nur teilweise geschrieben")
        offset += written


def _close_fd_preserving_primary(fd: int, label: str) -> None:
    primary_error_active = sys.exc_info()[0] is not None
    try:
        os.close(fd)
    except OSError as exc:
        if not primary_error_active:
            raise RegistryReadError(f"{label} nicht schliessbar: {exc}") from exc


def _read_all(fd: int, label: str) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(fd, 64 * 1024)
        except OSError as exc:
            raise RegistryReadError(f"{label} nicht lesbar: {exc}") from exc
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _stat_identity(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def _remove_owned_file(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        current = path.stat()
        if (current.st_dev, current.st_ino) == identity:
            path.unlink()
    except OSError:
        pass


def bootstrap_migrate_existing() -> None:
    with _Lock():
        if _read_initialization_marker():
            raise RegistryReadError("Registry ist bereits initialisiert")
        p = registry_path()
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            fd = os.open(str(p), flags)
        except FileNotFoundError as exc:
            raise RegistryReadError("Bestehende Registry fehlt; Migration blockiert") from exc
        except OSError as exc:
            raise RegistryReadError(f"Bestehende Registry nicht oeffenbar: {exc}") from exc
        try:
            try:
                before = os.fstat(fd)
                raw = _read_all(fd, "Bestehende Registry")
                after = os.fstat(fd)
            except OSError as exc:
                raise RegistryReadError(
                    f"Bestehende Registry nicht attestierbar: {exc}"
                ) from exc
            if _stat_identity(before) != _stat_identity(after):
                raise RegistryReadError("Registry-Identitaet aenderte sich beim Lesen")
            try:
                data = json.loads(raw.decode("utf-8"))
            except UnicodeError as exc:
                raise RegistryReadError(
                    f"Bestehende Registry ist nicht gueltiges UTF-8: {exc}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise RegistryReadError(
                    f"Bestehende Registry enthaelt ungueltiges JSON: {exc}"
                ) from exc
            _validate_registry(data)
        finally:
            _close_fd_preserving_primary(fd, "Bestehende Registry")
        try:
            path_stat = os.stat(str(p))
        except OSError as exc:
            raise RegistryReadError(
                f"Registry-Pfad vor Migration nicht attestierbar: {exc}"
            ) from exc
        if _stat_identity(path_stat) != _stat_identity(after):
            raise RegistryReadError("Registry-Identitaet driftete vor Markerpublikation")
        _create_initialization_marker()


def bootstrap_initialize_empty() -> None:
    with _Lock():
        if _read_initialization_marker():
            raise RegistryReadError("Registry ist bereits initialisiert")
        p = registry_path()
        tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex}.tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        identity: tuple[int, int] | None = None
        try:
            fd = os.open(str(tmp), flags)
        except FileExistsError as exc:
            raise RegistryReadError(
                "Einzigartige Empty-Registry-Tempdatei existiert"
            ) from exc
        except OSError as exc:
            raise RegistryReadError(
                f"Empty-Registry-Tempdatei nicht erstellbar: {exc}"
            ) from exc
        try:
            try:
                try:
                    owned = os.fstat(fd)
                except OSError as exc:
                    raise RegistryReadError(
                        f"Empty-Registry-Tempdatei nicht attestierbar: {exc}"
                    ) from exc
                identity = (owned.st_dev, owned.st_ino)
                _write_all(fd, EMPTY_REGISTRY_BYTES, "Leere Registry")
                try:
                    os.fsync(fd)
                except OSError as exc:
                    raise RegistryReadError(
                        f"Leere Registry nicht synchronisierbar: {exc}"
                    ) from exc
            finally:
                _close_fd_preserving_primary(fd, "Leere Registry")
            try:
                os.link(str(tmp), str(p))
            except FileExistsError as exc:
                raise RegistryReadError(
                    "Registry existiert bereits; `bootstrap --migrate-existing` verwenden"
                ) from exc
            except OSError as exc:
                raise RegistryReadError(
                    f"Leere Registry nicht atomar publizierbar: {exc}"
                ) from exc
        finally:
            _remove_owned_file(tmp, identity)
        _create_initialization_marker()


def _validate_registry(data: object) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        raise RegistryReadError("Registry-Top-Level oder sessions-Liste ungueltig")
    seen_ids: set[str] = set()
    for index, row in enumerate(data["sessions"]):
        if not isinstance(row, dict):
            raise RegistryReadError(f"Registry-Session {index} ist kein Objekt")
        required_strings = (
            "id", "agent", "task", "host", "branch", "worktree",
            "started_at", "heartbeat",
        )
        if not all(isinstance(row.get(field), str) for field in required_strings):
            raise RegistryReadError(f"Registry-Session {index}: Stringfelder ungueltig")
        session_id = row["id"]
        if len(session_id) != 32 or any(c not in "0123456789abcdef" for c in session_id):
            raise RegistryReadError(f"Registry-Session {index}: id-Format ungueltig")
        if session_id in seen_ids:
            raise RegistryReadError(f"Registry-Session {index}: id doppelt")
        seen_ids.add(session_id)
        for field in ("started_at", "heartbeat"):
            try:
                parsed = datetime.fromisoformat(row[field])
            except ValueError as exc:
                raise RegistryReadError(
                    f"Registry-Session {index}: {field} ungueltig"
                ) from exc
            if parsed.tzinfo is None:
                raise RegistryReadError(
                    f"Registry-Session {index}: {field} ohne Zeitzone"
                )
        pid = row.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 0:
            raise RegistryReadError(f"Registry-Session {index}: pid ungueltig")
        claims = row.get("claims")
        if not isinstance(claims, list) or not all(isinstance(x, str) for x in claims):
            raise RegistryReadError(f"Registry-Session {index}: claims ungueltig")
        parent = row.get("parent_session_id")
        if parent is not None and not isinstance(parent, str):
            raise RegistryReadError(
                f"Registry-Session {index}: parent_session_id ungueltig"
            )
        ancestors = row.get("ancestor_session_ids")
        if not isinstance(ancestors, list) or not all(
            isinstance(x, str) for x in ancestors
        ):
            raise RegistryReadError(
                f"Registry-Session {index}: ancestor_session_ids ungueltig"
            )
        if not isinstance(row.get("forced"), bool) or not isinstance(
            row.get("forced_lineage"), bool
        ):
            raise RegistryReadError(f"Registry-Session {index}: Boolflags ungueltig")


def _write_raw(data: dict) -> None:
    """Atomar schreiben: erst tmp, dann os.replace (atomar auf NTFS + POSIX)."""
    if not _read_initialization_marker():
        raise RegistryReadError("Registry-Marker fehlt; operative Mutation blockiert")
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


_MAX_CODEPOINT = 0x10FFFF
_ANY_CHAR = ((0, _MAX_CODEPOINT),)
_STAR = None


def _merge_ranges(ranges: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    merged: list[list[int]] = []
    for low, high in sorted(ranges):
        if merged and low <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return tuple((low, high) for low, high in merged)


def _class_ranges(content: str) -> tuple[tuple[int, int], ...] | None:
    negate = content.startswith("!")
    if negate:
        content = content[1:]
    if not content:
        return None
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(content):
        if index + 2 < len(content) and content[index + 1] == "-":
            low, high = ord(content[index]), ord(content[index + 2])
            if low > high:
                return None
            ranges.append((low, high))
            index += 3
        else:
            value = ord(content[index])
            ranges.append((value, value))
            index += 1
    merged = _merge_ranges(ranges)
    if not negate:
        return merged
    complement: list[tuple[int, int]] = []
    cursor = 0
    for low, high in merged:
        if cursor < low:
            complement.append((cursor, low - 1))
        cursor = high + 1
    if cursor <= _MAX_CODEPOINT:
        complement.append((cursor, _MAX_CODEPOINT))
    return tuple(complement)


def _parse_glob(
    pattern: str,
) -> tuple[list[tuple[tuple[int, int], ...] | None], bool] | None:
    tokens: list[tuple[tuple[int, int], ...] | None] = []
    has_glob = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            has_glob = True
            if not tokens or tokens[-1] is not _STAR:
                tokens.append(_STAR)
        elif char == "?":
            has_glob = True
            tokens.append(_ANY_CHAR)
        elif char == "[":
            search_from = index + 1
            if search_from < len(pattern) and pattern[search_from] == "!":
                search_from += 1
            if search_from < len(pattern) and pattern[search_from] == "]":
                search_from += 1
            closing = pattern.find("]", search_from)
            if closing < 0:
                return None
            else:
                ranges = _class_ranges(pattern[index + 1:closing])
                if ranges is None:
                    return None
                has_glob = True
                tokens.append(ranges)
                index = closing
        else:
            tokens.append(((ord(char), ord(char)),))
        index += 1
    return tokens, has_glob


def _ranges_intersect(
    a: tuple[tuple[int, int], ...], b: tuple[tuple[int, int], ...]
) -> bool:
    left = right = 0
    while left < len(a) and right < len(b):
        low_a, high_a = a[left]
        low_b, high_b = b[right]
        if max(low_a, low_b) <= min(high_a, high_b):
            return True
        if high_a < high_b:
            left += 1
        else:
            right += 1
    return False


def _glob_languages_overlap(
    a: list[tuple[tuple[int, int], ...] | None],
    b: list[tuple[tuple[int, int], ...] | None],
) -> bool:
    pending = [(0, 0)]
    seen: set[tuple[int, int]] = set()
    while pending:
        left, right = pending.pop()
        if (left, right) in seen:
            continue
        seen.add((left, right))
        if left == len(a) and right == len(b):
            return True
        if left < len(a) and a[left] is _STAR:
            pending.append((left + 1, right))
        if right < len(b) and b[right] is _STAR:
            pending.append((left, right + 1))
        if left == len(a) or right == len(b):
            continue
        ranges_a = _ANY_CHAR if a[left] is _STAR else a[left]
        ranges_b = _ANY_CHAR if b[right] is _STAR else b[right]
        if _ranges_intersect(ranges_a, ranges_b):
            next_left = left if a[left] is _STAR else left + 1
            next_right = right if b[right] is _STAR else right + 1
            pending.append((next_left, next_right))
    return False


def _glob_patterns_may_overlap(a: str, b: str) -> bool:
    """Exact supported-glob intersection; malformed classes fail closed."""
    parsed_a = _parse_glob(os.path.normcase(a))
    parsed_b = _parse_glob(os.path.normcase(b))
    if parsed_a is None or parsed_b is None:
        return True
    tokens_a, has_glob_a = parsed_a
    tokens_b, has_glob_b = parsed_b
    if not has_glob_a or not has_glob_b:
        return False
    return _glob_languages_overlap(tokens_a, tokens_b)


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
            if (
                nx == ny
                or fnmatch.fnmatch(nx, ny)
                or fnmatch.fnmatch(ny, nx)
                or _glob_patterns_may_overlap(nx, ny)
            ):
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
          pid: int = 0, parent_session_id: str | None = None) -> tuple[dict, list[dict]]:
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
        parent = None
        if parent_session_id:
            parent = next(
                (row for row in data["sessions"] if row.get("id") == parent_session_id),
                None,
            )
            if parent is None:
                return {}, [{
                    "id": parent_session_id,
                    "agent": "(fehlender Parent)",
                    "task": "",
                    "pid": 0,
                    "host": "",
                    "branch": "",
                    "worktree": "",
                    "heartbeat": "",
                    "claims": [],
                    "_hits": [],
                    "_reason": "parent-session-not-live",
                }]
        conflicts = []
        for s in data["sessions"]:
            hits = _claims_overlap(files, s.get("claims", []))
            if hits:
                conflicts.append({**s, "_hits": hits})
        if conflicts and not force:
            return {}, conflicts

        normalized_pid = int(pid or 0)
        if normalized_pid < 0:
            normalized_pid = 0
        session = {
            "id": uuid.uuid4().hex,
            "agent": agent,
            "task": task,
            "pid": normalized_pid,
            "host": platform.node(),
            "branch": branch or _git("rev-parse", "--abbrev-ref", "HEAD"),
            "worktree": worktree or _git("rev-parse", "--show-toplevel"),
            "started_at": _utc_now(),
            "heartbeat": _utc_now(),
            "claims": [_norm(f) for f in files],
            "parent_session_id": parent_session_id,
            "ancestor_session_ids": (
                [*parent.get("ancestor_session_ids", []), parent["id"]]
                if parent is not None else []
            ),
            "forced": bool(force),
            "forced_lineage": bool(force) or bool(
                parent is not None
                and (parent.get("forced") or parent.get("forced_lineage"))
            ),
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
    c.add_argument(
        "--parent-session-id",
        help="aktive Parent-Session; Registry versiegelt transitive Lineage",
    )

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

    bootstrap = sub.add_parser(
        "bootstrap", help="Registry explizit erstmalig initialisieren oder migrieren"
    )
    bootstrap_mode = bootstrap.add_mutually_exclusive_group(required=True)
    bootstrap_mode.add_argument("--migrate-existing", action="store_true")
    bootstrap_mode.add_argument("--initialize-empty", action="store_true")

    a = ap.parse_args(argv)

    try:
        if a.cmd == "bootstrap":
            if a.migrate_existing:
                bootstrap_migrate_existing()
                print("Bootstrap abgeschlossen: bestehende Registry migriert.")
            else:
                bootstrap_initialize_empty()
                print("Bootstrap abgeschlossen: leere Registry initialisiert.")
            return EXIT_OK

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
            session, conflicts = claim(
                a.agent, a.task, a.files, a.branch, a.worktree, a.force, a.pid,
                a.parent_session_id,
            )
            if conflicts and conflicts[0].get("_reason") == "parent-session-not-live":
                print("KONFLIKT: Parent-Session ist nicht aktiv; nicht registriert.")
                return EXIT_CONFLICT
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

    except RegistryReadError as e:
        print(f"FEHLER: Registry nicht sicher lesbar: {e}", file=sys.stderr)
        return EXIT_ERROR
    except TimeoutError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return EXIT_ERROR
    except subprocess.CalledProcessError:
        print("FEHLER: kein Git-Repository?", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

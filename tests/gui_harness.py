"""
gui_harness.py — Primitives fuer den pb-gui-tester Agent.

Dieses Modul wird NICHT direkt als pytest gesammelt. Es ist eine CLI, die ein
Subagent via `Bash` aufruft. Jede Aktion druckt strukturierte JSON-Zeilen auf
stdout, damit der Agent das Ergebnis parsen kann.

Kommandos:
    start           App via .venv310/python main.py starten, PID + Log-Pfad ausgeben
    wait-window     Warten bis ein Fenster mit Titel-Fragment erscheint
    screenshot      PNG unter tests/qa_artifacts/<label>_<ts>.png speichern
    click           Mausklick an (x, y) — absolute Bildschirm-Koordinaten
    type            Text tippen (Fenster muss fokussiert sein)
    key             Einzelne Taste/Kombination (z.B. "enter", "ctrl+s")
    log-tail        Letzte N Zeilen aus logs/pb_studio.log (default 50)
    log-since       Alle Log-Zeilen seit gegebenem Byte-Offset + neuer Offset
    find-crash      Sucht im Log nach "CRASH" / "UNHANDLED EXCEPTION" / Tracebacks
    kill            App-Prozess via PID beenden (auch Child-Prozesse)
    list-windows    Alle sichtbaren Fenstertitel dumpen (Debug)
    focus           Fenster mit Titelfragment in den Vordergrund ziehen

Alle Befehle geben JSON auf stdout zurueck. Fehler werden als
{"ok": false, "error": "..."} reportet, Erfolg als {"ok": true, ...}.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv310" / "Scripts" / "python.exe"
MAIN_PY = PROJECT_ROOT / "main.py"
LOG_FILE = PROJECT_ROOT / "logs" / "pb_studio.log"
ARTIFACT_DIR = PROJECT_ROOT / "tests" / "qa_artifacts"
PID_FILE = ARTIFACT_DIR / ".app_pid"

ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _ok(**kw) -> None:
    _emit({"ok": True, **kw})


def _fail(error: str, **kw) -> None:
    _emit({"ok": False, "error": error, **kw})


def cmd_start(args) -> int:
    if not VENV_PYTHON.exists():
        _fail(f"venv python not found: {VENV_PYTHON}")
        return 2
    if not MAIN_PY.exists():
        _fail(f"main.py not found: {MAIN_PY}")
        return 2

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(MAIN_PY)],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    _ok(pid=proc.pid, log_file=str(LOG_FILE))
    return 0


def cmd_kill(args) -> int:
    pid = args.pid or (int(PID_FILE.read_text()) if PID_FILE.exists() else None)
    if not pid:
        _fail("no pid provided and no .app_pid file")
        return 2
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, check=False,
            )
        else:
            os.kill(pid, signal.SIGTERM)
        if PID_FILE.exists():
            PID_FILE.unlink()
        _ok(pid=pid, killed=True)
        return 0
    except Exception as exc:
        _fail(f"kill failed: {exc}")
        return 3


_EXCLUDE_TITLE_SUBSTRINGS = (
    "Datei-Explorer",
    "File Explorer",
    "Eingabeaufforderung",
    "Command Prompt",
    "Visual Studio Code",
    " - VSCode",
)


def _is_real_app_window(w, title_fragment: str) -> bool:
    t = w.title or ""
    if title_fragment not in t:
        return False
    if not t.strip():
        return False
    # Offscreen (z.B. minimiert nach -32000 oder vorhandene Tool-Windows)
    if w.left < -10000 or w.top < -10000:
        return False
    # Mindestgroesse: ein echtes App-Fenster ist > 400x300
    if w.width < 400 or w.height < 300:
        return False
    # Bekannte Fehlquellen mit "PB_studio" im Titel
    if any(excl in t for excl in _EXCLUDE_TITLE_SUBSTRINGS):
        return False
    return True


def cmd_wait_window(args) -> int:
    import pygetwindow as gw
    start = time.time()
    last_candidates: list[dict] = []
    while time.time() - start < args.timeout:
        last_candidates = []
        for w in gw.getAllWindows():
            if not w.title:
                continue
            if args.title in w.title:
                last_candidates.append({
                    "title": w.title, "left": w.left, "top": w.top,
                    "width": w.width, "height": w.height,
                })
            if _is_real_app_window(w, args.title):
                _ok(
                    title=w.title,
                    left=w.left, top=w.top,
                    width=w.width, height=w.height,
                    elapsed=round(time.time() - start, 2),
                )
                return 0
        time.sleep(0.5)
    _fail(
        f"window with fragment {args.title!r} not found in {args.timeout}s",
        candidates_seen=last_candidates,
    )
    return 4


def cmd_list_windows(args) -> int:
    import pygetwindow as gw
    titles = []
    for w in gw.getAllWindows():
        if w.title and w.title.strip():
            titles.append({
                "title": w.title,
                "left": w.left, "top": w.top,
                "width": w.width, "height": w.height,
            })
    _ok(windows=titles)
    return 0


def cmd_focus(args) -> int:
    import pygetwindow as gw
    for w in gw.getAllWindows():
        if args.title in w.title:
            try:
                if w.isMinimized:
                    w.restore()
                w.activate()
                _ok(title=w.title)
                return 0
            except Exception as exc:
                _fail(f"focus failed: {exc}")
                return 5
    _fail(f"no window matching {args.title!r}")
    return 4


def _focus_app_window(title_fragment: str) -> dict | None:
    """Findet das PB_studio Fenster, bringt es in den Vordergrund und gibt die Geometrie zurueck.
    None wenn kein passendes Fenster existiert."""
    import pygetwindow as gw
    for w in gw.getAllWindows():
        if not w.title or title_fragment not in w.title:
            continue
        if not _is_real_app_window(w, title_fragment):
            continue
        try:
            if w.isMinimized:
                w.restore()
            w.activate()
        except Exception:
            # Windows verweigert manchmal das Aktivieren — notfalls per minimize/restore
            try:
                w.minimize()
                time.sleep(0.2)
                w.restore()
            except Exception:
                pass
        time.sleep(0.3)  # Compositor Zeit geben zu zeichnen
        return {"title": w.title, "left": w.left, "top": w.top, "width": w.width, "height": w.height}
    return None


def cmd_screenshot(args) -> int:
    import pyautogui
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = ARTIFACT_DIR / f"{args.label}_{ts}.png"
    focused = None
    if not args.no_focus:
        focused = _focus_app_window(args.window_title)
        if focused is None and args.require_app:
            _fail(f"app window {args.window_title!r} not found — refusing to screenshot other content")
            return 6
    try:
        img = pyautogui.screenshot()
        crop_mode = None
        if args.window_only and focused is not None:
            left = max(0, focused["left"])
            top = max(0, focused["top"])
            right = focused["left"] + focused["width"]
            bottom = focused["top"] + focused["height"]
            img = img.crop((left, top, right, bottom))
            crop_mode = "window"
        elif args.region:
            parts = [int(p) for p in args.region.split(",")]
            img = img.crop((parts[0], parts[1], parts[0] + parts[2], parts[1] + parts[3]))
            crop_mode = "region"
        img.save(str(path))
        _ok(path=str(path), size=list(img.size), focused=focused, crop=crop_mode)
        return 0
    except Exception as exc:
        _fail(f"screenshot failed: {exc}")
        return 6


def cmd_click(args) -> int:
    import pyautogui
    try:
        pyautogui.click(args.x, args.y, clicks=args.clicks, button=args.button)
        _ok(x=args.x, y=args.y, button=args.button, clicks=args.clicks)
        return 0
    except Exception as exc:
        _fail(f"click failed: {exc}")
        return 7


def _pwa_app(window_title: str):
    """Connect pywinauto to the running PB_studio window (UIA backend).

    Problem 1: `title_re=".*PB_studio.*"` matcht auch VSCode-Fenster mit
      'PB_studio_Rebuild' im Titel.
    Problem 2: Minimierte Fenster liegen bei (-16000,-16000) oder (-32000,-32000)
      und sind per pyautogui/UIA nicht sinnvoll ansprechbar.

    Wir finden das App-Fenster ueber den Titel (exakter Match), restoren es
    falls minimiert, und verbinden per HWND.
    """
    import pygetwindow as gw
    from pywinauto import Application

    target = None
    for w in gw.getAllWindows():
        t = w.title or ""
        if window_title not in t:
            continue
        if not t.strip():
            continue
        if any(excl in t for excl in _EXCLUDE_TITLE_SUBSTRINGS):
            continue
        # Match: echtes App-Fenster oder minimierte Variante davon
        target = w
        break

    if target is None:
        raise RuntimeError(f"no app window with fragment {window_title!r} found")

    # Restore falls minimiert/offscreen
    try:
        if target.isMinimized or target.left < -10000:
            target.restore()
            time.sleep(0.3)
        target.activate()
        time.sleep(0.2)
    except Exception:
        pass

    app = Application(backend="uia").connect(handle=target._hWnd, timeout=10)
    return app.window(handle=target._hWnd)


def _walk_children(element, max_depth: int = 6, _depth: int = 0):
    """Yield (element, depth) for the full UIA tree, bounded."""
    yield element, _depth
    if _depth >= max_depth:
        return
    try:
        children = element.children()
    except Exception:
        return
    for child in children:
        yield from _walk_children(child, max_depth, _depth + 1)


def _element_info(el) -> dict:
    try:
        rect = el.rectangle()
        return {
            "name": el.window_text() or "",
            "auto_id": getattr(el.element_info, "automation_id", "") or "",
            "class_name": el.class_name() or "",
            "control_type": el.element_info.control_type or "",
            "left": rect.left, "top": rect.top,
            "right": rect.right, "bottom": rect.bottom,
            "width": rect.width(), "height": rect.height(),
            "center_x": (rect.left + rect.right) // 2,
            "center_y": (rect.top + rect.bottom) // 2,
            "visible": bool(el.is_visible()) if hasattr(el, "is_visible") else True,
            "enabled": bool(el.is_enabled()) if hasattr(el, "is_enabled") else True,
        }
    except Exception as exc:
        return {"name": "?", "error": str(exc)}


def cmd_list_elements(args) -> int:
    try:
        top = _pwa_app(args.window_title)
        out = []
        for el, depth in _walk_children(top, max_depth=args.depth):
            info = _element_info(el)
            info["depth"] = depth
            if args.only_interactive:
                ct = info.get("control_type", "")
                if ct not in ("Button", "MenuItem", "TabItem", "Edit", "ComboBox", "ListItem", "CheckBox", "RadioButton"):
                    continue
            out.append(info)
            if len(out) >= args.limit:
                break
        _ok(count=len(out), elements=out)
        return 0
    except Exception as exc:
        _fail(f"list-elements failed: {exc}")
        return 9


def cmd_find_element(args) -> int:
    """Finde ein Element anhand name_re / auto_id / control_type. Gib Geometrie fuer klick zurueck."""
    import re
    try:
        top = _pwa_app(args.window_title)
        name_pat = re.compile(args.name_re, re.IGNORECASE) if args.name_re else None
        matches = []
        for el, _ in _walk_children(top, max_depth=args.depth):
            info = _element_info(el)
            if name_pat and not name_pat.search(info.get("name", "")):
                continue
            if args.auto_id and info.get("auto_id", "") != args.auto_id:
                continue
            if args.control_type and info.get("control_type", "") != args.control_type:
                continue
            if args.only_visible and not info.get("visible", False):
                continue
            matches.append(info)
            if len(matches) >= args.limit:
                break
        _ok(count=len(matches), matches=matches)
        return 0 if matches else 10
    except Exception as exc:
        _fail(f"find-element failed: {exc}")
        return 9


def cmd_click_element(args) -> int:
    """Klickt das erste passende Element per pywinauto invoke (wenn invokable) oder Mittelpunkt-Klick."""
    import re
    try:
        top = _pwa_app(args.window_title)
        name_pat = re.compile(args.name_re, re.IGNORECASE) if args.name_re else None
        target = None
        target_info = None
        for el, _ in _walk_children(top, max_depth=args.depth):
            info = _element_info(el)
            if name_pat and not name_pat.search(info.get("name", "")):
                continue
            if args.auto_id and info.get("auto_id", "") != args.auto_id:
                continue
            if args.control_type and info.get("control_type", "") != args.control_type:
                continue
            if args.only_visible and not info.get("visible", False):
                continue
            target = el
            target_info = info
            break
        if target is None:
            _fail("no element matched")
            return 10
        method = "invoke"
        try:
            target.invoke()
        except Exception:
            method = "center-click"
            import pyautogui
            pyautogui.click(target_info["center_x"], target_info["center_y"])
        _ok(method=method, element=target_info)
        return 0
    except Exception as exc:
        _fail(f"click-element failed: {exc}")
        return 9


def cmd_type(args) -> int:
    import pyautogui
    try:
        pyautogui.typewrite(args.text, interval=0.02)
        _ok(text_len=len(args.text))
        return 0
    except Exception as exc:
        _fail(f"type failed: {exc}")
        return 7


def cmd_key(args) -> int:
    import pyautogui
    try:
        if "+" in args.key:
            keys = args.key.split("+")
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(args.key)
        _ok(key=args.key)
        return 0
    except Exception as exc:
        _fail(f"key failed: {exc}")
        return 7


def cmd_log_tail(args) -> int:
    if not LOG_FILE.exists():
        _fail(f"log file missing: {LOG_FILE}")
        return 8
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-args.n:] if args.n > 0 else lines
    _ok(count=len(tail), lines=tail, total_lines=len(lines), size_bytes=LOG_FILE.stat().st_size)
    return 0


def cmd_log_since(args) -> int:
    if not LOG_FILE.exists():
        _fail(f"log file missing: {LOG_FILE}")
        return 8
    size = LOG_FILE.stat().st_size
    offset = max(0, min(args.offset, size))
    with LOG_FILE.open("rb") as fh:
        fh.seek(offset)
        data = fh.read().decode("utf-8", errors="replace")
    new_lines = data.splitlines() if data else []
    _ok(new_offset=size, count=len(new_lines), lines=new_lines)
    return 0


CRASH_MARKERS = (
    "UNHANDLED EXCEPTION",
    "CRASH —",
    "CRITICAL",
    "Traceback (most recent call last):",
)


def cmd_find_crash(args) -> int:
    if not LOG_FILE.exists():
        _fail(f"log file missing: {LOG_FILE}")
        return 8
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = []
    for i, line in enumerate(lines):
        if any(m in line for m in CRASH_MARKERS):
            ctx_start = max(0, i - 2)
            ctx_end = min(len(lines), i + 20)
            hits.append({
                "line_no": i + 1,
                "match": line[:400],
                "context": lines[ctx_start:ctx_end],
            })
    _ok(crash_count=len(hits), hits=hits[-args.max:] if args.max else hits)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="gui_harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("start").set_defaults(func=cmd_start)

    kp = sub.add_parser("kill"); kp.add_argument("--pid", type=int, default=None); kp.set_defaults(func=cmd_kill)

    ww = sub.add_parser("wait-window")
    ww.add_argument("--title", default="PB_studio")
    ww.add_argument("--timeout", type=float, default=60.0)
    ww.set_defaults(func=cmd_wait_window)

    sub.add_parser("list-windows").set_defaults(func=cmd_list_windows)

    fc = sub.add_parser("focus"); fc.add_argument("--title", required=True); fc.set_defaults(func=cmd_focus)

    ss = sub.add_parser("screenshot")
    ss.add_argument("--label", required=True)
    ss.add_argument("--region", default=None, help="x,y,w,h (absolute screen coords)")
    ss.add_argument("--window-only", action="store_true", help="Nur App-Fenster-Rechteck, nicht den ganzen Screen")
    ss.add_argument("--window-title", default="PB_studio", help="Fenster-Titelfragment fuer Focus/Crop")
    ss.add_argument("--no-focus", action="store_true", help="Fenster NICHT in den Vordergrund ziehen")
    ss.add_argument("--require-app", action="store_true", default=True, help="Abbruch wenn App-Fenster nicht gefunden")
    ss.set_defaults(func=cmd_screenshot)

    cl = sub.add_parser("click")
    cl.add_argument("--x", type=int, required=True)
    cl.add_argument("--y", type=int, required=True)
    cl.add_argument("--button", default="left", choices=["left", "right", "middle"])
    cl.add_argument("--clicks", type=int, default=1)
    cl.set_defaults(func=cmd_click)

    tp = sub.add_parser("type"); tp.add_argument("--text", required=True); tp.set_defaults(func=cmd_type)

    kk = sub.add_parser("key"); kk.add_argument("--key", required=True); kk.set_defaults(func=cmd_key)

    lt = sub.add_parser("log-tail"); lt.add_argument("--n", type=int, default=50); lt.set_defaults(func=cmd_log_tail)

    ls = sub.add_parser("log-since"); ls.add_argument("--offset", type=int, default=0); ls.set_defaults(func=cmd_log_since)

    fc2 = sub.add_parser("find-crash"); fc2.add_argument("--max", type=int, default=5); fc2.set_defaults(func=cmd_find_crash)

    le = sub.add_parser("list-elements", help="UIA-Baum dumpen fuer Explor.")
    le.add_argument("--window-title", default="PB_studio")
    le.add_argument("--depth", type=int, default=6)
    le.add_argument("--limit", type=int, default=150)
    le.add_argument("--only-interactive", action="store_true", help="Nur Button/Edit/TabItem/ComboBox etc.")
    le.set_defaults(func=cmd_list_elements)

    fe = sub.add_parser("find-element", help="Elemente per name/auto_id/control_type finden (liefert Geometrie)")
    fe.add_argument("--window-title", default="PB_studio")
    fe.add_argument("--name-re", default=None, help="Regex auf window_text()")
    fe.add_argument("--auto-id", default=None)
    fe.add_argument("--control-type", default=None, help="z.B. Button, Edit, TabItem")
    fe.add_argument("--only-visible", action="store_true")
    fe.add_argument("--depth", type=int, default=8)
    fe.add_argument("--limit", type=int, default=10)
    fe.set_defaults(func=cmd_find_element)

    ce = sub.add_parser("click-element", help="Klickt erstes Match per pywinauto invoke / Center-Klick Fallback")
    ce.add_argument("--window-title", default="PB_studio")
    ce.add_argument("--name-re", default=None)
    ce.add_argument("--auto-id", default=None)
    ce.add_argument("--control-type", default=None)
    ce.add_argument("--only-visible", action="store_true", default=True)
    ce.add_argument("--depth", type=int, default=8)
    ce.set_defaults(func=cmd_click_element)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

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
# Allow override via PB_PYTHON env-var (e.g. conda env) when .venv310 is absent
VENV_PYTHON = Path(os.environ["PB_PYTHON"]) if "PB_PYTHON" in os.environ else PROJECT_ROOT / ".venv310" / "Scripts" / "python.exe"
MAIN_PY = PROJECT_ROOT / "main.py"
LOG_FILE = PROJECT_ROOT / "logs" / "pb_studio.log"
ARTIFACT_DIR = PROJECT_ROOT / "tests" / "qa_artifacts"
PID_FILE = ARTIFACT_DIR / ".app_pid"

ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _rerun_with_pb_python_if_available() -> int | None:
    """Rerun this harness command in PB_PYTHON when the shell Python lacks GUI deps."""
    try:
        current = Path(sys.executable).resolve()
        target = VENV_PYTHON.resolve()
    except OSError:
        return None
    if current == target or not target.exists():
        return None
    completed = subprocess.run(
        [str(target), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    return completed.returncode


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _ok(**kw) -> None:
    _emit({"ok": True, **kw})


def _fail(error: str, **kw) -> None:
    _emit({"ok": False, "error": error, **kw})


APP_STDOUT = ARTIFACT_DIR / ".app_stdout.log"
APP_STDERR = ARTIFACT_DIR / ".app_stderr.log"


def _pid_is_alive(pid: int) -> bool:
    """Check if a PID is still running. Windows: tasklist; Unix: os.kill(pid, 0)."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, check=False,
            )
            return str(pid) in (out.stdout or "")
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_start(args) -> int:
    if not VENV_PYTHON.exists():
        _fail(f"venv python not found: {VENV_PYTHON}")
        return 2
    if not MAIN_PY.exists():
        _fail(f"main.py not found: {MAIN_PY}")
        return 2

    # Duplikats-Schutz: existierender lebender Prozess aus vorigem start?
    if PID_FILE.exists():
        try:
            existing = int(PID_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            existing = 0
        if existing and _pid_is_alive(existing):
            if getattr(args, "force", False):
                # Erst alten Prozess killen, dann neu starten
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(existing)],
                                   capture_output=True, check=False)
                else:
                    os.kill(existing, signal.SIGTERM)
                time.sleep(0.5)
            else:
                _fail(
                    f"app still running as PID {existing}. Use `kill` first or pass --force.",
                    existing_pid=existing,
                )
                return 11
        # Stale PID-File — einfach ueberschreiben

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Optionaler Freeze-Profiler aktivieren ueber Harness:
    if getattr(args, "freeze_probe", False):
        env["PB_STUDIO_FREEZE_PROBE"] = "1"

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    # Important-Fix: stdout/stderr in Dateien statt DEVNULL, damit Crashes *vor*
    # dem setup_logging() (Import-Errors, syntaxfehler, fehlende venv-Pakete)
    # einen sichtbaren Traceback im Artefakt-Ordner hinterlassen.
    stdout_fh = APP_STDOUT.open("ab")
    stderr_fh = APP_STDERR.open("ab")
    try:
        proc = subprocess.Popen(
            [str(VENV_PYTHON), str(MAIN_PY)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=stdout_fh,
            stderr=stderr_fh,
            creationflags=creationflags,
        )
    finally:
        # File-Handles im Parent schliessen — Child hat eigene Duplicates
        stdout_fh.close()
        stderr_fh.close()
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    _ok(pid=proc.pid, log_file=str(LOG_FILE),
        stdout_file=str(APP_STDOUT), stderr_file=str(APP_STDERR))
    return 0


def cmd_kill(args) -> int:
    """Beende die App — standardmaessig GRACEFUL (WM_CLOSE + Warten).

    Hart-Kill via /F nur mit --force oder wenn graceful nach --grace-sec
    Sekunden nicht geklappt hat. Grund: taskkill /F waehrend CUDA-Workload
    kann den NVIDIA-Treiber in einen stuck state bringen (`CUDA unknown
    error` bei Re-Init). Die App selbst hat einen funktionierenden
    closeEvent, der Worker sauber abbaut — also nutzen.
    """
    pid = args.pid or (int(PID_FILE.read_text()) if PID_FILE.exists() else None)
    if not pid:
        _fail("no pid provided and no .app_pid file")
        return 2

    method_used = None
    requested_grace_sec = float(args.grace_sec)
    effective_grace_sec = max(requested_grace_sec, 15.0) if not args.force else requested_grace_sec
    try:
        if not args.force:
            # 1) Graceful: WM_CLOSE an alle PB_studio-Fenster + taskkill ohne /F
            if sys.platform == "win32":
                _post_wm_close_for_pid(pid)
                try:
                    import pygetwindow as gw
                    for w in gw.getAllWindows():
                        if "PB_studio" in (w.title or "") and _is_real_app_window(w, "PB_studio"):
                            try:
                                w.close()  # WM_CLOSE
                            except Exception:
                                pass
                except Exception:
                    pass
                # Als Backup taskkill ohne /F (auch das sendet WM_CLOSE)
                subprocess.run(
                    ["taskkill", "/PID", str(pid)],
                    capture_output=True, check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)

            # Auf saubere Beendigung warten
            deadline = time.monotonic() + effective_grace_sec
            while time.monotonic() < deadline:
                if sys.platform == "win32":
                    out = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                        capture_output=True, text=True, check=False,
                    )
                    alive = str(pid) in (out.stdout or "")
                else:
                    try:
                        os.kill(pid, 0)
                        alive = True
                    except OSError:
                        alive = False
                if not alive:
                    method_used = "graceful"
                    break
                time.sleep(0.5)

        # 2) Force-Fallback (oder direkt bei --force)
        if method_used is None:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, check=False,
                )
            else:
                os.kill(pid, signal.SIGKILL)
            method_used = "force"

        if PID_FILE.exists():
            PID_FILE.unlink()
        _ok(
            pid=pid,
            killed=True,
            method=method_used,
            grace_sec=effective_grace_sec,
            requested_grace_sec=requested_grace_sec,
        )
        return 0
    except Exception as exc:
        _fail(f"kill failed: {exc}")
        return 3


def _post_wm_close_for_pid(pid: int) -> int:
    """Send WM_CLOSE directly to visible top-level windows of ``pid``."""
    if sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    count = 0

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        nonlocal count
        if not user32.IsWindowVisible(hwnd):
            return True
        found_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))
        if int(found_pid.value) != int(pid):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if "PB_studio" not in title:
            return True
        if user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
            count += 1
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return count


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
    try:
        import pygetwindow as gw
    except ModuleNotFoundError:
        rerun_code = _rerun_with_pb_python_if_available()
        if rerun_code is not None:
            return rerun_code
        raise
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
    try:
        import pygetwindow as gw
    except ModuleNotFoundError:
        rerun_code = _rerun_with_pb_python_if_available()
        if rerun_code is not None:
            return rerun_code
        raise
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
    try:
        import pygetwindow as gw
    except ModuleNotFoundError:
        rerun_code = _rerun_with_pb_python_if_available()
        if rerun_code is not None:
            return rerun_code
        raise
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
    mods = [m.strip() for m in (args.modifiers or "").split(",") if m.strip()]
    try:
        for m in mods:
            pyautogui.keyDown(m)
        try:
            pyautogui.click(args.x, args.y, clicks=args.clicks, button=args.button)
        finally:
            for m in reversed(mods):
                pyautogui.keyUp(m)
        _ok(x=args.x, y=args.y, button=args.button, clicks=args.clicks, modifiers=mods)
        return 0
    except Exception as exc:
        _fail(f"click failed: {exc}")
        return 7


def cmd_drag(args) -> int:
    """Drag von (from_x, from_y) nach (to_x, to_y).

    Realer Mausgesten-Drag (mouseDown, kontinuierliche Bewegung, mouseUp).
    Wichtig fuer: Clip-Drag in Timeline, Slider-Drag, Drag&Drop von Files.
    """
    import pyautogui
    try:
        pyautogui.moveTo(args.from_x, args.from_y, duration=0.05)
        pyautogui.mouseDown(button=args.button)
        # Bewegung in mehreren Schritten — manche Apps reagieren empfindlich auf
        # zu schnellen Maus-Sprung
        steps = max(5, args.steps)
        dx = (args.to_x - args.from_x) / steps
        dy = (args.to_y - args.from_y) / steps
        for i in range(1, steps + 1):
            pyautogui.moveTo(args.from_x + dx * i, args.from_y + dy * i,
                             duration=args.duration / steps)
        pyautogui.mouseUp(button=args.button)
        _ok(from_=[args.from_x, args.from_y], to=[args.to_x, args.to_y],
            button=args.button, steps=steps, duration=args.duration)
        return 0
    except Exception as exc:
        _fail(f"drag failed: {exc}")
        return 7


def cmd_mouse_down(args) -> int:
    import pyautogui
    try:
        pyautogui.moveTo(args.x, args.y)
        pyautogui.mouseDown(button=args.button)
        _ok(x=args.x, y=args.y, button=args.button)
        return 0
    except Exception as exc:
        _fail(f"mouse-down failed: {exc}")
        return 7


def cmd_mouse_up(args) -> int:
    import pyautogui
    try:
        pyautogui.mouseUp(button=args.button)
        _ok(button=args.button)
        return 0
    except Exception as exc:
        _fail(f"mouse-up failed: {exc}")
        return 7


def cmd_scroll(args) -> int:
    """Mausrad-Scroll an gegebener Position. delta>0 = nach oben, <0 = nach unten."""
    import pyautogui
    try:
        if args.x is not None and args.y is not None:
            pyautogui.moveTo(args.x, args.y)
        pyautogui.scroll(args.delta)
        _ok(delta=args.delta, x=args.x, y=args.y)
        return 0
    except Exception as exc:
        _fail(f"scroll failed: {exc}")
        return 7


def cmd_set_value(args) -> int:
    """Setzt einen QSpinBox / QSlider / QLineEdit per UIA SetValue.

    Funktioniert fuer Qt-Widgets die das ValuePattern implementieren.
    Fuer SpinBox: triggert die normale valueChanged-Signal-Kette wie ein
    User-Input — also ideal fuer Inspector-Tests.
    """
    try:
        top = _pwa_app(args.window_title)
        first = next(_iter_matching_elements(top, args, max_count=1), None)
        if first is None:
            _fail("no element matched")
            return 10
        target, target_info = first
        # Versuche ValuePattern → set_value(); fallback: triple-click + type
        try:
            target.set_value(str(args.value))
            _ok(method="set_value", value=args.value, element=target_info)
            return 0
        except Exception:
            pass
        # Fallback: focus, select-all, type
        import pyautogui
        cx, cy = target_info["center_x"], target_info["center_y"]
        pyautogui.tripleClick(cx, cy)
        pyautogui.typewrite(str(args.value), interval=0.02)
        pyautogui.press("tab")
        _ok(method="type-fallback", value=args.value, element=target_info)
        return 0
    except Exception as exc:
        _fail(f"set-value failed: {exc}")
        return 9


def cmd_select_combo(args) -> int:
    """Waehlt eine ComboBox-Option per Text-Label.

    Versucht UIA select_pattern; fallback: Combo oeffnen + Pfeiltasten + Enter.
    """
    try:
        top = _pwa_app(args.window_title)
        import re
        name_pat = re.compile(args.name_re, re.IGNORECASE) if args.name_re else None
        combo = None
        combo_info = None
        for el, _ in _walk_children(top, max_depth=args.depth):
            info = _element_info(el)
            if info.get("control_type") != "ComboBox":
                continue
            if name_pat and not name_pat.search(info.get("name", "")):
                continue
            combo = el
            combo_info = info
            break
        if combo is None:
            _fail("no combo matched")
            return 10
        # Versuche select via Selection/Value
        try:
            combo.select(args.option)
            _ok(method="select", option=args.option, combo=combo_info)
            return 0
        except Exception:
            pass
        # Fallback: anklicken, dann ggf. tippen
        import pyautogui
        pyautogui.click(combo_info["center_x"], combo_info["center_y"])
        time.sleep(0.3)
        if args.option:
            pyautogui.typewrite(args.option[:30], interval=0.02)
            time.sleep(0.2)
        pyautogui.press("enter")
        _ok(method="click-type-enter", option=args.option, combo=combo_info)
        return 0
    except Exception as exc:
        _fail(f"select-combo failed: {exc}")
        return 9


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


def _iter_matching_elements(top, args, max_count: int = 9999):
    """P9-E: Gemeinsame Match-Schleife fuer find/click/set-value/select-combo.

    Liefert (element, info) Paare die alle Filter erfuellen.
    Vorher 3x dupliziert in cmd_find/click/set_value.
    """
    import re
    name_pat = re.compile(args.name_re, re.IGNORECASE) if getattr(args, "name_re", None) else None
    auto_id = getattr(args, "auto_id", None) or None
    ctrl_type = getattr(args, "control_type", None) or None
    only_vis = bool(getattr(args, "only_visible", False))
    yielded = 0
    for el, _depth in _walk_children(top, max_depth=getattr(args, "depth", 8)):
        info = _element_info(el)
        if name_pat and not name_pat.search(info.get("name", "")):
            continue
        if auto_id and info.get("auto_id", "") != auto_id:
            continue
        if ctrl_type and info.get("control_type", "") != ctrl_type:
            continue
        if only_vis and not info.get("visible", False):
            continue
        yield el, info
        yielded += 1
        if yielded >= max_count:
            return


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
    """Finde Elemente anhand name_re / auto_id / control_type."""
    try:
        top = _pwa_app(args.window_title)
        matches = [info for _el, info in _iter_matching_elements(top, args, max_count=args.limit)]
        _ok(count=len(matches), matches=matches)
        return 0 if matches else 10
    except Exception as exc:
        _fail(f"find-element failed: {exc}")
        return 9


def cmd_click_element(args) -> int:
    """Klickt das erste passende Element per pywinauto invoke / Center-Klick Fallback."""
    try:
        top = _pwa_app(args.window_title)
        first = next(_iter_matching_elements(top, args, max_count=1), None)
        if first is None:
            _fail("no element matched")
            return 10
        target, target_info = first
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
    """Tippt args.text per pyautogui.typewrite.

    P9-E LIMITATION: typewrite akzeptiert nur ASCII. Umlaute / Sonderzeichen
    (ä, ö, ü, é) erzeugen je nach Locale unerwartete oder gar keine Eingabe.
    Fuer Pfade mit Sonderzeichen besser pyperclip + Ctrl+V Variante (TODO).
    """
    import pyautogui
    try:
        pyautogui.typewrite(args.text, interval=0.02)
        _ok(text_len=len(args.text))
        return 0
    except Exception as exc:
        _fail(f"type failed: {exc}")
        return 7


def cmd_key(args) -> int:
    """Druckt eine Taste oder Hotkey-Kombi.

    Beispiele: --key enter, --key ctrl+s, --key alt+f4
    P9-E LIMITATION: literales "+" als einzelne Taste ist nicht moeglich
    (interner Split-Trigger). Workaround: pyautogui.press('+') direkt nutzen
    in einem custom-Skript, oder Combo wie shift+= verwenden.
    """
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

    sp_start = sub.add_parser("start")
    sp_start.add_argument("--force", action="store_true",
                          help="Laufende App vorher killen statt Fehler zu werfen")
    sp_start.add_argument("--freeze-probe", action="store_true",
                          help="Aktiviert faulthandler → dumped Stack bei >3s Hangs in logs/freeze_stacks.log")
    sp_start.set_defaults(func=cmd_start)

    kp = sub.add_parser("kill")
    kp.add_argument("--pid", type=int, default=None)
    kp.add_argument("--force", action="store_true",
                    help="Sofort /F /T (taskkill hart). Sonst graceful + Fallback.")
    kp.add_argument("--grace-sec", type=float, default=15.0,
                    help="Wartezeit fuer graceful exit bevor /F greift (default: 15). "
                         "closeEvent hat eigene 10s Task-Wait-Deadline — 15 gibt Puffer.")
    kp.set_defaults(func=cmd_kill)

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
    cl.add_argument("--modifiers", default="",
                    help="Komma-separierte Modifier: shift,ctrl,alt (fuer Multi-Select etc.)")
    cl.set_defaults(func=cmd_click)

    dr = sub.add_parser("drag", help="Drag von (from_x,from_y) nach (to_x,to_y)")
    dr.add_argument("--from-x", type=int, required=True, dest="from_x")
    dr.add_argument("--from-y", type=int, required=True, dest="from_y")
    dr.add_argument("--to-x", type=int, required=True, dest="to_x")
    dr.add_argument("--to-y", type=int, required=True, dest="to_y")
    dr.add_argument("--button", default="left", choices=["left", "right", "middle"])
    dr.add_argument("--steps", type=int, default=20, help="Anzahl Zwischenschritte (>=5)")
    dr.add_argument("--duration", type=float, default=0.4, help="Gesamt-Drag-Dauer in s")
    dr.set_defaults(func=cmd_drag)

    md = sub.add_parser("mouse-down")
    md.add_argument("--x", type=int, required=True)
    md.add_argument("--y", type=int, required=True)
    md.add_argument("--button", default="left", choices=["left", "right", "middle"])
    md.set_defaults(func=cmd_mouse_down)

    mu = sub.add_parser("mouse-up")
    mu.add_argument("--button", default="left", choices=["left", "right", "middle"])
    mu.set_defaults(func=cmd_mouse_up)

    sc = sub.add_parser("scroll", help="Mausrad-Scroll. delta>0 nach oben, <0 nach unten")
    sc.add_argument("--delta", type=int, required=True)
    sc.add_argument("--x", type=int, default=None)
    sc.add_argument("--y", type=int, default=None)
    sc.set_defaults(func=cmd_scroll)

    sv = sub.add_parser("set-value", help="QSpinBox/QSlider/QLineEdit-Wert setzen via UIA")
    sv.add_argument("--window-title", default="PB_studio")
    sv.add_argument("--name-re", default=None)
    sv.add_argument("--auto-id", default=None)
    sv.add_argument("--control-type", default=None)
    sv.add_argument("--depth", type=int, default=10)
    sv.add_argument("--value", required=True)
    sv.set_defaults(func=cmd_set_value)

    cb = sub.add_parser("select-combo", help="ComboBox-Option per Label auswaehlen")
    cb.add_argument("--window-title", default="PB_studio")
    cb.add_argument("--name-re", default=None)
    cb.add_argument("--depth", type=int, default=10)
    cb.add_argument("--option", required=True)
    cb.set_defaults(func=cmd_select_combo)

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

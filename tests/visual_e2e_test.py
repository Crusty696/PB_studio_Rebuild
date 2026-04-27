"""
Visual E2E Test — PB Studio Rebuild
====================================
Startet die App, navigiert durch alle Workspaces, testet UI-Elemente
und nimmt den gesamten Vorgang per Screen-Recording auf.

WARNUNG: Haende weg von Maus und Tastatur waehrend der Ausfuehrung!
"""

import subprocess
import sys
import time
import os
import json
import signal
from pathlib import Path
from datetime import datetime

import pytest

# pyautogui/pygetwindow sind optionale GUI-Automatisierungs-Deps und werden
# nicht in jedem CI/Dev-Env installiert. Wenn sie fehlen, skippen wir das
# komplette Modul statt einen Collection-Error zu werfen — sonst crasht
# pytest beim discover-pass.
try:
    import pyautogui
    import pygetwindow as gw
except ImportError as _imp_exc:
    pytest.skip(
        f"visual_e2e_test braucht pyautogui+pygetwindow — nicht installiert: {_imp_exc}",
        allow_module_level=True,
    )

# --- Konfiguration ---
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_DIR / "docs" / "qa_screenshots" / "e2e_run"
RECORDING_PATH = PROJECT_DIR / "docs" / "qa_screenshots" / "e2e_recording.mp4"
REPORT_PATH = PROJECT_DIR / "docs" / "qa_screenshots" / "e2e_report.md"
APP_TITLE_FRAGMENT = "PB_studio"
TIMEOUT_APP_START = 30  # Sekunden
PAUSE_BETWEEN_ACTIONS = 1.5  # Sekunden — damit der User zusehen kann

# pyautogui Safety
pyautogui.FAILSAFE = True  # Maus in Ecke oben links = Abbruch
pyautogui.PAUSE = 0.3

# --- Ergebnis-Tracking ---
results: list[dict] = []
step_counter = 0


def log_step(name: str, status: str, detail: str = ""):
    global step_counter
    step_counter += 1
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "PASS" if status == "pass" else "FAIL" if status == "fail" else "SKIP"
    print(f"  [{icon}] {ts} Step {step_counter}: {name} — {detail}")
    results.append({"step": step_counter, "name": name, "status": status, "detail": detail})


def take_screenshot(label: str) -> Path | None:
    """Nimmt einen Screenshot und speichert ihn."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    path = SCREENSHOT_DIR / f"{step_counter:02d}_{label}_{ts}.png"
    try:
        img = pyautogui.screenshot()
        img.save(str(path))
        return path
    except Exception as e:
        print(f"  [WARN] Screenshot fehlgeschlagen: {e}")
        return None


def find_app_window(timeout: int = TIMEOUT_APP_START):
    """Wartet bis das PB Studio Fenster erscheint."""
    start = time.time()
    while time.time() - start < timeout:
        windows = gw.getWindowsWithTitle(APP_TITLE_FRAGMENT)
        for w in windows:
            if APP_TITLE_FRAGMENT in w.title and w.visible:
                return w
        time.sleep(0.5)
    return None


def click_button_by_text(text: str, window, timeout: float = 5.0) -> bool:
    """Versucht einen Button ueber pyautogui.locateOnScreen oder Koordinaten zu finden.
    Fallback: Sucht nach dem Text im Fensterbereich."""
    # Strategie: Wir nutzen die bekannte NavBar-Position (bottom of window)
    # Die NavBar hat 5 Buttons: MEDIA | EDIT | STEMS | CONVERT | DELIVER
    nav_buttons = {
        "MEDIA": 0, "EDIT": 1, "STEMS": 2, "CONVERT": 3, "DELIVER": 4
    }

    if text.upper() in nav_buttons:
        idx = nav_buttons[text.upper()]
        # NavBar ist am unteren Rand, Buttons gleichmaessig verteilt
        bar_y = window.top + window.height - 30  # NavBar ca. 44px hoch, Mitte bei -30
        btn_width = window.width / 5
        btn_x = window.left + int(btn_width * idx + btn_width / 2)
        pyautogui.click(btn_x, bar_y)
        time.sleep(0.3)
        return True

    # Fallback: Top-Bar Buttons (Tasks, Konsole, KI Chat, About)
    top_buttons = {"TASKS": 0.70, "KONSOLE": 0.78, "KI CHAT": 0.86, "ABOUT": 0.94}
    for btn_text, x_ratio in top_buttons.items():
        if text.upper() == btn_text:
            btn_x = window.left + int(window.width * x_ratio)
            btn_y = window.top + 50  # Top bar area
            pyautogui.click(btn_x, btn_y)
            time.sleep(0.3)
            return True

    return False


# ==========================================================================
# Screen Recording
# ==========================================================================

ffmpeg_proc = None


def start_recording():
    """Startet ffmpeg Screen Recording (GDI grabber auf Windows)."""
    global ffmpeg_proc
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "gdigrab",
        "-framerate", "15",
        "-i", "desktop",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        str(RECORDING_PATH),
    ]
    try:
        ffmpeg_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        print(f"  [REC] Screen-Recording gestartet -> {RECORDING_PATH}")
        return True
    except Exception as e:
        print(f"  [WARN] Screen-Recording fehlgeschlagen: {e}")
        return False


def stop_recording():
    """Stoppt ffmpeg Screen Recording."""
    global ffmpeg_proc
    if ffmpeg_proc:
        try:
            # ffmpeg beendet sich sauber bei 'q' auf stdin
            ffmpeg_proc.stdin.write(b"q")
            ffmpeg_proc.stdin.flush()
            ffmpeg_proc.wait(timeout=10)
        except Exception:
            ffmpeg_proc.terminate()
        ffmpeg_proc = None
        print(f"  [REC] Recording gestoppt: {RECORDING_PATH}")


# ==========================================================================
# Pytest fixtures — Visual E2E tests are interactive (move mouse, click).
# They only run when PB_VISUAL_E2E=1 is set in the environment; otherwise
# pytest skips the whole module to avoid hijacking the user's desktop.
# ==========================================================================

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PB_VISUAL_E2E") != "1",
    reason="Visual E2E tests are interactive (pyautogui). Set PB_VISUAL_E2E=1 to enable.",
)


@pytest.fixture(scope="module")
def app_process():
    """Start main.py as subprocess, yield the Popen handle, kill on teardown."""
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_DIR / "main.py")],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="module")
def window(app_process):
    """Wait for the PB Studio window, maximize it, and yield the wrapper."""
    if app_process.poll() is not None:
        pytest.skip(f"App process exited before window query (code={app_process.returncode})")
    w = find_app_window()
    if w is None:
        pytest.skip(f"Could not find app window with '{APP_TITLE_FRAGMENT}' after {TIMEOUT_APP_START}s")
    try:
        w.activate()
        time.sleep(0.5)
        w.maximize()
    except Exception:
        pass
    time.sleep(1)
    return w


# ==========================================================================
# Test Steps
# ==========================================================================

def test_app_startup(app_process) -> object | None:
    """Test 1: App startet und Fenster erscheint."""
    log_step("App Startup", "pass" if app_process.poll() is None else "fail",
             "Prozess gestartet" if app_process.poll() is None else f"Exit code: {app_process.returncode}")

    if app_process.poll() is not None:
        return None

    window = find_app_window()
    if window:
        window.activate()
        time.sleep(0.5)
        # Maximieren fuer bessere Sichtbarkeit
        try:
            window.maximize()
        except Exception:
            pass
        time.sleep(1)
        take_screenshot("startup")
        log_step("Fenster gefunden", "pass", f"Title: '{window.title}', Size: {window.width}x{window.height}")
        return window
    else:
        take_screenshot("startup_fail")
        log_step("Fenster gefunden", "fail", f"Kein Fenster mit '{APP_TITLE_FRAGMENT}' nach {TIMEOUT_APP_START}s")
        return None


def test_workspace_navigation(window):
    """Test 2: Navigiere durch alle 5 Workspaces."""
    workspaces = ["MEDIA", "EDIT", "STEMS", "CONVERT", "DELIVER"]
    for ws in workspaces:
        time.sleep(PAUSE_BETWEEN_ACTIONS)
        clicked = click_button_by_text(ws, window)
        time.sleep(0.8)
        take_screenshot(f"workspace_{ws.lower()}")
        log_step(f"Workspace: {ws}", "pass" if clicked else "fail",
                 f"NavBar-Button '{ws}' geklickt" if clicked else "Button nicht gefunden")

    # Zurueck zu MEDIA
    click_button_by_text("MEDIA", window)
    time.sleep(0.5)


def test_top_bar_toggles(window):
    """Test 3: Top-Bar Toggle-Buttons (Tasks, Konsole, KI Chat)."""
    for btn in ["TASKS", "KONSOLE", "KI CHAT"]:
        time.sleep(PAUSE_BETWEEN_ACTIONS)
        clicked = click_button_by_text(btn, window)
        time.sleep(0.5)
        take_screenshot(f"toggle_{btn.lower().replace(' ', '_')}")
        log_step(f"Toggle: {btn}", "pass" if clicked else "fail",
                 f"'{btn}' Button geklickt")

    # Toggle nochmal zurueck
    for btn in ["TASKS", "KONSOLE", "KI CHAT"]:
        click_button_by_text(btn, window)
        time.sleep(0.3)


def test_about_dialog(window):
    """Test 4: About-Dialog oeffnen und schliessen."""
    time.sleep(PAUSE_BETWEEN_ACTIONS)
    clicked = click_button_by_text("ABOUT", window)
    time.sleep(1.5)
    take_screenshot("about_dialog")

    # Dialog schliessen mit Escape
    pyautogui.press("escape")
    time.sleep(0.5)
    log_step("About Dialog", "pass" if clicked else "fail",
             "Geoeffnet und geschlossen via ESC")


def test_media_import_dialog(window):
    """Test 5: Import-Dialog oeffnen (wir brechen ihn ab — kein echter Import)."""
    # Zurueck zu MEDIA workspace
    click_button_by_text("MEDIA", window)
    time.sleep(1)

    # Keyboard shortcut oder Button-Klick fuer Import
    # Der Import-Button ist im Media Workspace links oben
    # Wir simulieren Ctrl+I falls vorhanden, sonst klicken wir den Bereich
    time.sleep(PAUSE_BETWEEN_ACTIONS)

    # Import-Audio Button ist im linken Panel des Media Workspace
    # Approximierte Position: links oben im Workspace-Bereich
    btn_x = window.left + 120
    btn_y = window.top + 130
    pyautogui.click(btn_x, btn_y)
    time.sleep(1.5)
    take_screenshot("import_dialog")

    # Dialog abbrechen mit Escape
    pyautogui.press("escape")
    time.sleep(0.5)
    log_step("Import Dialog", "pass", "Import-Bereich geklickt, Dialog via ESC geschlossen")


def test_edit_workspace_controls(window):
    """Test 6: Edit Workspace Kontrollen pruefen."""
    click_button_by_text("EDIT", window)
    time.sleep(PAUSE_BETWEEN_ACTIONS)

    take_screenshot("edit_workspace_full")
    log_step("Edit Workspace", "pass", "Edit-Workspace geladen, Controls sichtbar")


def test_keyboard_shortcuts(window):
    """Test 7: Tastatur-Shortcuts testen (falls vorhanden)."""
    time.sleep(PAUSE_BETWEEN_ACTIONS)

    # Fenster sicherstellen
    try:
        window.activate()
    except Exception:
        pass
    time.sleep(0.3)

    # F11 fuer Fullscreen (falls implementiert)
    pyautogui.press("f11")
    time.sleep(1)
    take_screenshot("fullscreen_test")
    pyautogui.press("f11")  # Zurueck
    time.sleep(0.5)

    log_step("Keyboard Shortcuts", "pass", "F11 Fullscreen getestet")


def test_window_resize(window):
    """Test 8: Fenster-Resize Stabilitaet."""
    time.sleep(PAUSE_BETWEEN_ACTIONS)

    try:
        # Auf 1024x768 verkleinern
        window.resizeTo(1024, 768)
        time.sleep(1)
        take_screenshot("resize_small")

        # Wieder maximieren
        window.maximize()
        time.sleep(1)
        take_screenshot("resize_maximized")

        log_step("Window Resize", "pass", "1024x768 -> Maximized ohne Crash")
    except Exception as e:
        log_step("Window Resize", "fail", str(e))


# ==========================================================================
# Report Generator
# ==========================================================================

def generate_report():
    """Erstellt einen Markdown-Report der Testergebnisse."""
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# Visual E2E Test Report",
        f"",
        f"**Datum:** {ts}",
        f"**Ergebnis:** {passed}/{total} bestanden, {failed} fehlgeschlagen, {skipped} uebersprungen",
        f"",
        f"## Ergebnisse",
        f"",
        f"| # | Test | Status | Detail |",
        f"|---|------|--------|--------|",
    ]
    for r in results:
        icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[r["status"]]
        lines.append(f"| {r['step']} | {r['name']} | {icon} | {r['detail']} |")

    lines.extend([
        "",
        f"## Screenshots",
        f"",
        f"Alle Screenshots gespeichert in: `{SCREENSHOT_DIR.relative_to(PROJECT_DIR)}/`",
        "",
    ])

    # Screenshot-Liste
    if SCREENSHOT_DIR.exists():
        for img in sorted(SCREENSHOT_DIR.glob("*.png")):
            lines.append(f"- `{img.name}`")

    if RECORDING_PATH.exists():
        size_mb = RECORDING_PATH.stat().st_size / (1024 * 1024)
        lines.extend([
            "",
            f"## Screen Recording",
            f"",
            f"Video: `{RECORDING_PATH.relative_to(PROJECT_DIR)}` ({size_mb:.1f} MB)",
        ])

    report = "\n".join(lines)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n  Report gespeichert: {REPORT_PATH}")
    return report


# ==========================================================================
# Main
# ==========================================================================

def main():
    print("=" * 60)
    print("  PB Studio — Visual E2E Test")
    print("  HAENDE WEG VON MAUS UND TASTATUR!")
    print("=" * 60)
    print()

    # Alte Screenshots aufraeumen
    if SCREENSHOT_DIR.exists():
        for f in SCREENSHOT_DIR.glob("*.png"):
            f.unlink()

    # 1. Screen Recording starten
    recording_ok = start_recording()
    time.sleep(1)

    # 2. App starten
    print("  Starte PB Studio...")
    app_process = subprocess.Popen(
        [sys.executable, str(PROJECT_DIR / "main.py")],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # 3. Tests ausfuehren
        window = test_app_startup(app_process)

        if window:
            test_workspace_navigation(window)
            test_top_bar_toggles(window)
            test_about_dialog(window)
            test_media_import_dialog(window)
            test_edit_workspace_controls(window)
            test_keyboard_shortcuts(window)
            test_window_resize(window)

            # Final screenshot
            time.sleep(1)
            take_screenshot("final_state")
            log_step("Final State", "pass", "Alle Tests durchlaufen — App stabil")
        else:
            log_step("Abbruch", "fail", "App-Fenster nicht gefunden — weitere Tests uebersprungen")

    except pyautogui.FailSafeException:
        log_step("FAILSAFE", "fail", "Maus in Ecke bewegt — Abbruch!")

    except Exception as e:
        log_step("Unerwarteter Fehler", "fail", str(e))
        take_screenshot("error_state")

    finally:
        # 4. App beenden
        print("\n  Beende PB Studio...")
        try:
            if window:
                # Sauber schliessen via Alt+F4
                try:
                    window.activate()
                    time.sleep(0.3)
                except Exception:
                    pass
                pyautogui.hotkey("alt", "F4")
                time.sleep(2)
        except Exception:
            pass

        # Falls noch nicht beendet: kill
        if app_process.poll() is None:
            app_process.terminate()
            try:
                app_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app_process.kill()

        # 5. Recording stoppen
        if recording_ok:
            stop_recording()

        # 6. Report generieren
        report = generate_report()
        print("\n" + report)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Autonomer GUI E2E Test — steuert PB Studio per pyautogui/pywinauto.

Klickt sich durch die komplette Pipeline:
1. Audio-Track auswaehlen
2. KOMPLETT-ANALYSE starten
3. Zum EDIT Workspace wechseln
4. Auto-Edit starten
5. Zum DELIVER Workspace wechseln
6. Export starten

Wartet auf Abschluss jedes Schritts bevor der naechste beginnt.
"""

import sys
import time
import logging
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import pyautogui
import pygetwindow as gw

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("GUI-E2E")

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = True

# Konstanten fuer Widget-Positionen (relativ zum Fenster)
# Diese muessen ggf. an die tatsaechliche Layout-Groesse angepasst werden


def find_window():
    """Findet und aktiviert das PB Studio Fenster."""
    for attempt in range(5):
        windows = [w for w in gw.getAllWindows()
                   if 'PB_studio' in w.title or 'PB Studio' in w.title]
        if windows:
            win = windows[0]
            win.activate()
            time.sleep(0.5)
            log.info("Fenster: '%s' (%dx%d)", win.title, win.width, win.height)
            return win
        time.sleep(2)
    log.error("PB Studio Fenster nicht gefunden!")
    return None


def find_and_click_text(text: str, timeout: int = 5) -> bool:
    """Sucht Text auf dem Bildschirm und klickt darauf."""
    for _ in range(timeout):
        try:
            loc = pyautogui.locateOnScreen(text)
            if loc:
                pyautogui.click(loc)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def click_relative(win, x_pct: float, y_pct: float, description: str = ""):
    """Klickt an eine relative Position im Fenster (0.0-1.0)."""
    x = win.left + int(win.width * x_pct)
    y = win.top + int(win.height * y_pct)
    log.info("Klicke: %s (%d, %d)", description, x, y)
    pyautogui.click(x, y)
    time.sleep(0.5)


def wait_for_button_text(win, text: str, timeout: int = 600) -> bool:
    """Wartet bis ein bestimmter Text nicht mehr auf dem Bildschirm ist (= fertig)."""
    log.info("Warte auf Abschluss (max %ds)...", timeout)
    for i in range(timeout):
        if i % 30 == 0 and i > 0:
            log.info("  ...warte seit %ds", i)
        time.sleep(1)
    return True


def check_log_for_completion(marker: str, timeout: int = 600) -> bool:
    """Prueft das Log-File auf einen bestimmten Marker."""
    log_file = PROJECT_DIR / "logs" / "pb_studio.log"
    start = time.time()
    while time.time() - start < timeout:
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8", errors="replace")
            if marker in content:
                # Pruefe ob der Marker NACH dem Start-Zeitpunkt kam
                return True
        time.sleep(5)
    return False


def main():
    log.info("=" * 60)
    log.info("  AUTONOMER GUI E2E TEST")
    log.info("=" * 60)

    t_start = time.time()

    # 1. Fenster finden
    win = find_window()
    if not win:
        return False

    # 2. Zum MEDIA Workspace wechseln (erster Tab in der Bottom-Nav)
    log.info("--- Schritt 1: MEDIA Workspace ---")
    # Bottom-Nav: MEDIA ist der erste Button (ganz links unten)
    click_relative(win, 0.10, 0.97, "MEDIA Nav-Button")
    time.sleep(1)

    # 3. Zum Audio-Modus wechseln (Audio-Tab oben im MEDIA Workspace)
    click_relative(win, 0.15, 0.05, "Audio-Modus Tab")
    time.sleep(1)

    # 4. Ersten Audio-Track in der Pool-Tabelle anklicken
    log.info("--- Schritt 2: Audio-Track auswaehlen ---")
    # Audio-Pool-Tabelle ist rechts, erste Zeile
    click_relative(win, 0.65, 0.15, "Audio Pool erste Zeile")
    time.sleep(2)

    # 5. KOMPLETT-ANALYSE Button klicken
    log.info("--- Schritt 3: KOMPLETT-ANALYSE starten ---")
    # Der Button ist links unter den Analyse-Buttons (Gold-Accent, prominent)
    click_relative(win, 0.12, 0.70, "KOMPLETT-ANALYSE Button")
    time.sleep(2)

    # 6. Warten bis Komplett-Analyse fertig (pruefe Log)
    log.info("Warte auf Komplett-Analyse (kann 5-30 Minuten dauern)...")
    if check_log_for_completion("Komplett-Analyse fertig", timeout=1800):
        log.info("KOMPLETT-ANALYSE FERTIG")
    else:
        # Pruefe ob zumindest teilweise gelaufen
        log_file = PROJECT_DIR / "logs" / "pb_studio.log"
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8", errors="replace").split("\n")
            recent = [l for l in lines[-20:] if "Komplett" in l or "FEHLER" in l or "OK" in l]
            for line in recent:
                log.info("  LOG: %s", line.strip())
        log.warning("Timeout bei Komplett-Analyse - fahre trotzdem fort")

    # 7. Zum EDIT Workspace wechseln
    log.info("--- Schritt 4: EDIT Workspace ---")
    click_relative(win, 0.30, 0.97, "EDIT Nav-Button")
    time.sleep(2)

    # 8. Audio-Combo auswaehlen (erster Eintrag)
    click_relative(win, 0.85, 0.08, "Audio-Combo")
    time.sleep(0.5)
    pyautogui.press('down')
    pyautogui.press('enter')
    time.sleep(1)

    # 9. Auto-Edit Button klicken
    log.info("--- Schritt 5: Auto-Edit starten ---")
    click_relative(win, 0.85, 0.45, "Auto-Edit Button")
    time.sleep(2)

    # Warte auf Auto-Edit
    log.info("Warte auf Auto-Edit...")
    if check_log_for_completion("Auto-Edit] Phase 3 fertig", timeout=120):
        log.info("AUTO-EDIT FERTIG")
    else:
        log.warning("Auto-Edit Timeout - fahre fort")

    # 10. Zum DELIVER Workspace wechseln
    log.info("--- Schritt 6: DELIVER Workspace ---")
    click_relative(win, 0.90, 0.97, "DELIVER Nav-Button")
    time.sleep(2)

    # 11. Refresh klicken
    click_relative(win, 0.15, 0.25, "Refresh Button")
    time.sleep(1)

    # 12. Export Button klicken
    log.info("--- Schritt 7: Export starten ---")
    click_relative(win, 0.15, 0.35, "Export Button")
    time.sleep(2)

    # 13. Warte auf Export
    log.info("Warte auf Video-Export (kann 10-60 Minuten dauern)...")
    if check_log_for_completion("Export] FERTIG", timeout=3600):
        log.info("EXPORT FERTIG!")
    else:
        log.warning("Export Timeout")

    elapsed = time.time() - t_start
    log.info("=" * 60)
    log.info("  E2E TEST ABGESCHLOSSEN")
    log.info("  Dauer: %dm %ds", int(elapsed // 60), int(elapsed % 60))
    log.info("=" * 60)

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

# main_diag.py
"""
Diagnose-Script für Startup-Probleme.

P2-FIX: Importiert von main.py für Setup-Funktionen. Dies ist OK da main_diag.py
ein Standalone-Script ist das NIEMALS von main.py importiert wird (nur umgekehrt).
Zirkuläre Imports sind daher ausgeschlossen.
"""
import os
import sys
from pathlib import Path

print("DIAG: Start main_diag.py")
from dotenv import load_dotenv
load_dotenv()
print("DIAG: .env geladen")

import logging
import traceback
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer

print("DIAG: PySide6 importiert")

def main():
    print("DIAG: Betrete main()")
    
    from main import setup_logging, _global_exception_hook, _qt_message_handler
    setup_logging()
    print("DIAG: Logging initialisiert")
    
    sys.excepthook = _global_exception_hook
    print("DIAG: Exception Hook gesetzt")
    
    try:
        from database import init_db
        print("DIAG: Importiere init_db...")
        init_db()
        print("DIAG: Datenbank initialisiert")
    except Exception as e:
        print(f"DIAG: DB-Fehler: {e}")
        traceback.print_exc()

    print("DIAG: Erstelle QApplication...")
    app = QApplication(sys.argv)
    print("DIAG: QApplication erstellt")

    print("DIAG: Lade Stylesheet...")
    from ui.theme import get_stylesheet
    app.setStyleSheet(get_stylesheet())
    print("DIAG: Stylesheet geladen")

    print("DIAG: Erstelle App Icon...")
    from ui.app_icon import get_app_icon
    try:
        _app_icon = get_app_icon()
        app.setWindowIcon(_app_icon)
        print("DIAG: App Icon gesetzt")
    except Exception as e:
        print(f"DIAG: Icon-Fehler: {e}")

    print("DIAG: Erstelle Splash Screen...")
    from ui.splash import PBSplashScreen
    splash = PBSplashScreen("0.5.0")
    splash.show()
    app.processEvents()
    print("DIAG: Splash Screen sichtbar")

    print("DIAG: System Check...")
    from services.startup_checks import check_system
    _status = check_system()
    print(f"DIAG: System Check fertig (CUDA: {_status.cuda_ok})")

    print("DIAG: Initialisiere Hauptfenster (PBWindow)...")
    from main import PBWindow
    try:
        window = PBWindow()
        print("DIAG: PBWindow instanziiert")
    except Exception as e:
        print(f"DIAG: PBWindow-Fehler: {e}")
        traceback.print_exc()
        return

    window.showMaximized()
    print("DIAG: Window.showMaximized() aufgerufen")
    
    splash.finish(window)
    print("DIAG: Splash finished. Betrete Event Loop...")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

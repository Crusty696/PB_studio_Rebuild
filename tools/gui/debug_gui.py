from pywinauto import Application
import sys

def debug_window():
    try:
        app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
        main_win = app.window(title_re=".*PB_studio.*")
        main_win.set_focus()
        print("Identifiziere Steuerelemente...")
        main_win.print_control_identifiers()
    except Exception as e:
        print(f"Fehler bei der Analyse: {e}")

if __name__ == "__main__":
    debug_window()

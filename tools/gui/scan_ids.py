from pywinauto import Application
import sys

def scan_ids():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    
    print("Scanne alle IDs im Fenster...")
    elements = main_win.descendants()
    for e in elements:
        aid = e.auto_id()
        if aid:
            print(f" - ID: '{aid}', Type: '{e.control_type()}', Text: '{e.window_text()}'")

if __name__ == "__main__":
    scan_ids()

import time
from pywinauto import Application, Desktop

def _click_button(window, title):
    button = window.child_window(title=title, control_type="Button")
    if button.exists(timeout=3):
        button.click_input()
        return
    for candidate in window.descendants(control_type="Button"):
        if candidate.window_text() == title:
            candidate.click_input()
            return
    raise RuntimeError(f"Button nicht gefunden: {title}")

def execute_video_import():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Aktiviere 'Video Modus' via Button...")
    _click_button(main_win, "Video Modus")
    time.sleep(2)
    
    print("Klicke 'Ordner importieren'...")
    _click_button(main_win, "Ordner importieren")
    time.sleep(2)
    
    print("Bediene Ordner-Dialog...")
    dialog = Desktop(backend="win32").window(title_re=".*Ordner.*|.*auswählen.*|.*Browse.*")
    dialog.set_focus()
    
    # Pfad eingeben
    edit = dialog.child_window(title="Ordner:", control_type="Edit")
    if not edit.exists():
        edit = dialog.descendants(control_type="Edit")[0]
        
    edit.type_keys("C:\\Users\\David Lochmann\\Documents\\Solo_Natur-20260406T220640Z-3-001\\Solo_Natur", with_spaces=True)
    time.sleep(1)
    edit.type_keys("{ENTER}")
    
    print("Video-Ordner-Import getriggert.")
    time.sleep(3)

if __name__ == "__main__":
    try:
        execute_video_import()
    except Exception as e:
        print(f"GUI Fehler: {e}")

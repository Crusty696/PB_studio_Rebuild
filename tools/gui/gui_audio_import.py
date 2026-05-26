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

def execute_audio_import():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Aktiviere 'Audio Modus' via Button...")
    _click_button(main_win, "Audio Modus")
    time.sleep(2)
    
    print("Klicke 'Audio importieren'...")
    _click_button(main_win, "Audio importieren")
    time.sleep(2)
    
    print("Auswahl der Audio-Datei...")
    dialog = Desktop(backend="uia").window(title_re=".*Audio importieren.*|.*Öffnen.*|.*Open.*")
    dialog.set_focus()
    
    # Eingabe des Pfads
    edit = dialog.child_window(title="Dateiname:", control_type="Edit")
    edit.type_keys("C:\\Users\\David Lochmann\\Music\\Audio\\Psy-Set\\Progressive_Psy_Summer_Dream.wav", with_spaces=True)
    time.sleep(1)
    edit.type_keys("{ENTER}")
    
    print("Audio-Import getriggert.")
    time.sleep(3)

if __name__ == "__main__":
    try:
        execute_audio_import()
    except Exception as e:
        print(f"GUI Fehler: {e}")

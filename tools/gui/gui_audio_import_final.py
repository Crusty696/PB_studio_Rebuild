import time
from pywinauto import Application, Desktop

def complete_audio_import():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Suche Dialog in main_win...")
    dialog = None
    # Wir suchen nach einem Fenster/Dialog Kind
    children = main_win.descendants(control_type="Window") + main_win.descendants(control_type="Dialog")
    for child in children:
        print(f" - Gefunden: '{child.window_text()}'")
        if "Öffnen" in child.window_text() or "öffnen" in child.window_text().lower() or "Open" in child.window_text():
            dialog = child
            break
            
    if dialog:
        print(f"Bediene Dialog '{dialog.window_text()}'...")
        dialog.set_focus()
        # Pfad eingeben
        edit = dialog.child_window(title="Dateiname:", control_type="Edit")
        if not edit.exists():
             edit = dialog.child_window(control_type="Edit", found_index=0)
             
        edit.type_keys("C:\\Users\\David Lochmann\\Music\\Audio\\Psy-Set\\Progressive_Psy_Summer_Dream.wav", with_spaces=True)
        time.sleep(1)
        edit.type_keys("{ENTER}")
        print("Import-Pfad gesendet.")
        return True
    else:
        print("Dialog nicht gefunden.")
        return False

if __name__ == "__main__":
    complete_audio_import()

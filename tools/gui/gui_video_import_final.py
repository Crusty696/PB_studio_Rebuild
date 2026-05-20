import time
from pywinauto import Application, Desktop

def complete_video_import():
    # Suche alle Fenster und nimm das erste funktionierende (win32)
    try:
        app = Application(backend="win32").connect(title_re=".*Ordner.*", found_index=0, timeout=5)
        dlg = app.window(title_re=".*Ordner.*", found_index=0)
    except:
        app = Application(backend="win32").connect(title_re=".*Ordner.*", found_index=1, timeout=5)
        dlg = app.window(title_re=".*Ordner.*", found_index=1)
        
    dlg.set_focus()
    print(f"Bediene Dialog: {dlg.window_text()}")
    
    # Pfad eingeben
    # Bei Ordner-Dialogen ist das Edit oft tief verschachtelt oder nur über Keys erreichbar
    # Wir versuchen es über type_keys direkt auf den Dialog oder suchen Edit
    try:
        edit = dlg.child_window(title="Ordner:", control_type="Edit")
        edit.type_keys("C:\\Users\\David Lochmann\\Documents\\Solo_Natur-20260406T220640Z-3-001\\Solo_Natur", with_spaces=True)
    except:
        # Fallback: Direktes Tippen
        dlg.type_keys("C:\\Users\\David Lochmann\\Documents\\Solo_Natur-20260406T220640Z-3-001\\Solo_Natur", with_spaces=True)
        
    time.sleep(1)
    dlg.type_keys("{ENTER}")
    
    print("Video-Ordner Pfad gesendet.")

if __name__ == "__main__":
    try:
        complete_video_import()
    except Exception as e:
        print(f"GUI Fehler: {e}")

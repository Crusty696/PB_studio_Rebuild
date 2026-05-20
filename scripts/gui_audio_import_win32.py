import time
from pywinauto import Application

def complete_audio_import():
    # Suche alle Fenster und nimm das erste funktionierende
    try:
        app = Application(backend="win32").connect(title="Audio importieren", found_index=0, timeout=5)
        dlg = app.window(title="Audio importieren", found_index=0)
    except:
        app = Application(backend="win32").connect(title="Audio importieren", found_index=1, timeout=5)
        dlg = app.window(title="Audio importieren", found_index=1)
        
    dlg.set_focus()
    print(f"Bediene Dialog: {dlg.window_text()}")
    
    # Pfad eingeben
    dlg.Edit.type_keys("C:\\Users\\David Lochmann\\Music\\Audio\\Psy-Set\\Progressive_Psy_Summer_Dream.wav", with_spaces=True)
    time.sleep(1)
    dlg.Edit.type_keys("{ENTER}")
    
    print("Audio-Import Pfad gesendet.")

if __name__ == "__main__":
    try:
        complete_audio_import()
    except Exception as e:
        print(f"GUI Fehler: {e}")

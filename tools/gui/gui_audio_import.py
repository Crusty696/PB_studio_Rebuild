import time
from pywinauto import Application, Desktop

def execute_audio_import():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Aktiviere 'Audio Modus' via RadioButton...")
    rb_audio = main_win.child_window(title="Audio Modus", control_type="RadioButton")
    rb_audio.click_input()
    time.sleep(2)
    
    print("Suche Import-Button...")
    # Wir suchen nach einem Button, der jetzt 'Audio importieren' heißt
    try:
        btn_import = main_win.child_window(title="Audio importieren", control_type="Button")
    except:
        # Fallback: Der Button-Name könnte sich nicht ändern, nur die Funktion
        btn_import = main_win.child_window(title="Video importieren", control_type="Button")
        print("Nutze 'Video importieren' Button (Titel evtl. noch statisch)...")
        
    btn_import.click_input()
    time.sleep(2)
    
    print("Auswahl der Audio-Datei...")
    # Ein Standard-Windows-Dateidialog öffnet sich
    dialog = Desktop(backend="uia").window(title_re=".*öffnen.*")
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

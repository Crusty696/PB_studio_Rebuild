import time
from pywinauto import Application, Desktop

def execute_video_import():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Aktiviere 'Video Modus' via RadioButton...")
    # Da wir vorher Audio hatten, suchen wir nun Video. 
    # Falls kein RadioButton 'Video Modus' da ist, schauen wir in gui_structure.txt.
    # Dort stand nur 'Audio Modus'. Wahrscheinlich ist der andere 'Video Modus'.
    try:
        rb_video = main_win.child_window(title="Video Modus", control_type="RadioButton")
        rb_video.click_input()
    except:
        print("'Video Modus' RadioButton nicht direkt gefunden. Versuche Klick auf Text...")
        # In gui_structure.txt nachschauen welche RadioButtons es gibt
        rbs = main_win.descendants(control_type="RadioButton")
        for rb in rbs:
            if "Video" in rb.window_text():
                rb.click_input()
                break
    
    time.sleep(2)
    
    print("Klicke 'Ordner importieren'...")
    btn_folder = main_win.child_window(title="Ordner importieren", control_type="Button")
    btn_folder.click_input()
    time.sleep(2)
    
    print("Bediene Ordner-Dialog...")
    # Ordner-Dialoge sind oft anders. Wir suchen nach 'Ordner auswählen' oder ähnlichem.
    dialog = Desktop(backend="win32").window(title_re=".*Ordner.*")
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

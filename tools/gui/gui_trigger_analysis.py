import time
from pywinauto import Application

def execute_gui_analysis():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Starte Audio-Analyse...")
    # Sicherstellen, dass Audio-Modus aktiv ist
    rb_audio = main_win.child_window(title="Audio Modus", control_type="RadioButton")
    rb_audio.click_input()
    time.sleep(1)
    
    # Button finden (aus list_all_buttons wissen wir die Namen)
    # Es könnte 'Audio komplett analysieren' oder ähnlich heißen
    try:
        btn_audio_ana = main_win.child_window(title="Audio analysieren", control_type="Button")
        btn_audio_ana.click_input()
        print("Audio-Analyse gestartet.")
    except Exception:
        print("Audio-Analyse Button nicht gefunden. Suche nach 'analysieren'...")
        btns = main_win.descendants(control_type="Button")
        for b in btns:
            if "Audio" in b.window_text() and "analysieren" in b.window_text():
                b.click_input()
                print(f"Geklickt: {b.window_text()}")
                break
                
    time.sleep(2)
    
    print("Starte Video-Analyse...")
    # Wechsel zu Video Modus
    rbs = main_win.descendants(control_type="RadioButton")
    for rb in rbs:
        if "Video" in rb.window_text():
            rb.click_input()
            break
    time.sleep(1)
    
    # Klicke 'Video komplett analysieren' (aus list_all_buttons bekannt)
    try:
        btn_video_ana = main_win.child_window(title="Video komplett analysieren", control_type="Button")
        btn_video_ana.click_input()
        print("Video-Analyse gestartet.")
    except Exception:
        print("Video-Analyse Button nicht gefunden.")

    print("Analyse-Phase physisch getriggert.")
    time.sleep(3)

if __name__ == "__main__":
    try:
        execute_gui_analysis()
    except Exception as e:
        print(f"GUI Fehler: {e}")

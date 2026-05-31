import time
from pywinauto import Application

def find_audio_tab_and_buttons():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Suche Tabs im Material-Workflow...")
    tabs = main_win.descendants(control_type="TabItem")
    for t in tabs:
        print(f" - Tab: '{t.window_text()}'")
        if "AUDIO" in t.window_text().upper():
            print(f"Wechsle zu Tab '{t.window_text()}'...")
            t.click_input()
            time.sleep(1)
            break
            
    print("Liste Buttons im aktuellen Tab:")
    buttons = main_win.descendants(control_type="Button")
    for b in buttons:
        try:
            print(f" - Title: '{b.window_text()}'")
        except Exception:
            pass

if __name__ == "__main__":
    find_audio_tab_and_buttons()

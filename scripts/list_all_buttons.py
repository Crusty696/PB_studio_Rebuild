from pywinauto import Application
import sys

def list_buttons():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    
    buttons = main_win.descendants(control_type="Button")
    print(f"Gefundene Buttons ({len(buttons)}):")
    for b in buttons:
        try:
            print(f" - Title: '{b.window_text()}'")
        except:
            print(" - (Kein Titel)")

    checkboxes = main_win.descendants(control_type="CheckBox")
    print(f"Gefundene CheckBoxes ({len(checkboxes)}):")
    for c in checkboxes:
        try:
            print(f" - Title: '{c.window_text()}'")
        except:
            print(" - (Kein Titel)")

if __name__ == "__main__":
    list_buttons()

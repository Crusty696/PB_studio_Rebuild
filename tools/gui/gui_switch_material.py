import time
from pywinauto import Application

def switch_to_material_and_list():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    print("Klicke 'Material und Analyse Workflow'...")
    tab_mat = main_win.child_window(title="Material und Analyse Workflow", control_type="CheckBox")
    tab_mat.click_input()
    time.sleep(2)
    
    print("Identifiziere Buttons im Material-Workflow...")
    buttons = main_win.descendants(control_type="Button")
    for b in buttons:
        try:
            print(f" - Title: '{b.window_text()}'")
        except Exception:
            pass

if __name__ == "__main__":
    switch_to_material_and_list()

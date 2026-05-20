import time
from pywinauto import Application, Desktop

def navigate_and_find_neu():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    time.sleep(1)
    
    print("Aktiviere 'Projekt Workflow'...")
    try:
        tab_proj = main_win.child_window(title="Projekt Workflow", control_type="CheckBox")
        tab_proj.click_input()
        time.sleep(1)
    except:
        print("'Projekt Workflow' Tab nicht gefunden oder bereits aktiv.")

    print("Suche '+ Neu' Button...")
    # Wir suchen rekursiv nach dem Button mit dem Namen '+ Neu'
    try:
        btn_neu = main_win.child_window(title="+ Neu", control_type="Button")
        btn_neu.click_input()
        print("'+ Neu' geklickt.")
        return True
    except:
        print("'+ Neu' nicht per Titel gefunden. Suche per ID...")
        try:
            btn_neu = main_win.child_window(auto_id="top_bar.btn_secondary", control_type="Button", found_index=0)
            btn_neu.click_input()
            print("Button per ID geklickt.")
            return True
        except:
            print("Button auch per ID nicht gefunden.")
            return False

if __name__ == "__main__":
    navigate_and_find_neu()

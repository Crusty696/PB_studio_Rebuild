import time
from pywinauto import Application, Desktop

def execute_gui_project_setup():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    main_win.set_focus()
    
    # Der Dialog könnte ein Kind des Hauptfensters sein
    print("Suche Dialog...")
    try:
        dialog = main_win.child_window(title="Neues Projekt erstellen", control_type="Window")
        if not dialog.exists():
             dialog = main_win.child_window(title="Neues Projekt erstellen", control_type="Dialog")
        dialog.set_focus()
    except:
        print("Dialog nicht in main_win gefunden. Suche auf Desktop...")
        dialog = Desktop(backend="uia").window(title="Neues Projekt erstellen")
        dialog.set_focus()
    
    print("Fülle Projektdaten aus...")
    edits = dialog.descendants(control_type="Edit")
    print(f"Gefundene Edit-Felder: {len(edits)}")
    
    # Name
    edits[0].type_keys("test", with_spaces=True)
    
    # Pfad
    edits[1].type_keys("^a{BACKSPACE}") 
    edits[1].type_keys("C:\\Users\\David Lochmann\\Downloads\\test", with_spaces=True)
    
    time.sleep(1)
    print("Klicke 'Erstellen'...")
    # Suche Button 'Erstellen'
    btn_create = dialog.child_window(title="Erstellen", control_type="Button")
    btn_create.click_input()
    
    time.sleep(3)
    print("Schritt 1 erfolgreich abgeschlossen.")

if __name__ == "__main__":
    try:
        execute_gui_project_setup()
    except Exception as e:
        print(f"GUI Fehler: {e}")
        import traceback
        traceback.print_exc()

from pywinauto import Application
import sys

def map_gui():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    
    with open("gui_structure.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        main_win.print_control_identifiers()
        sys.stdout = sys.__stdout__
    print("GUI-Struktur in 'gui_structure.txt' gespeichert.")

if __name__ == "__main__":
    map_gui()

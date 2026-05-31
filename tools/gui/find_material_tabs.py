from pywinauto import Application
import sys

def find_all_tabs():
    app = Application(backend="uia").connect(title_re=".*PB_studio.*", timeout=10)
    main_win = app.window(title_re=".*PB_studio.*")
    
    tabs = main_win.descendants(control_type="TabItem")
    print(f"Gefundene Tab-Items ({len(tabs)}):")
    for t in tabs:
        try:
            parent = t.parent()
            print(f" - Tab: '{t.window_text()}', Parent: '{parent.window_text() if parent else 'None'}'")
        except Exception:
            print(f" - Tab: '{t.window_text()}' (Parent error)")

if __name__ == "__main__":
    find_all_tabs()

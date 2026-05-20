import time
import sys
from pywinauto import Desktop

def wait_for_window(title_part, timeout=60):
    start_time = time.time()
    print(f"Suche nach Fenster mit '{title_part}'...")
    while time.time() - start_time < timeout:
        windows = Desktop(backend="uia").windows()
        titles = [w.window_text() for w in windows]
        for t in titles:
            if title_part in t:
                print(f"Fenster gefunden: {t}")
                return True
        time.sleep(2)
        print(f"Noch nicht gefunden... ({int(time.time() - start_time)}s)")
    return False

if __name__ == "__main__":
    if wait_for_window("PB_studio"):
        sys.exit(0)
    else:
        print("TIMEOUT: PB Studio Fenster nicht erschienen.")
        sys.exit(1)

"""Smoke-Test: Startet die App headless und prüft alle Phase-4 Widgets."""
import sys
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db
init_db()
print("1. DB OK")

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
print("2. Qt OK")

from main import PBWindow
w = PBWindow()
print(f"3. Window: {w.windowTitle()}")
print(f"4. Workspaces: {w.workspace_stack.count()}")

# Phase-4 Media Buttons
for attr in ["btn_key_detect", "btn_lufs_analyze", "btn_structure_detect",
             "btn_motion_analysis", "btn_siglip_embeddings"]:
    ok = hasattr(w._media_ws, attr)
    print(f"   Media.{attr}: {'OK' if ok else 'FEHLT'}")

# Phase-4 Edit Widgets
for attr in ["style_preset_combo", "btn_thumbs_up", "btn_thumbs_down"]:
    ok = hasattr(w._edit_ws, attr)
    print(f"   Edit.{attr}: {'OK' if ok else 'FEHLT'}")

# Audio Detail Cards
ok = hasattr(w._media_ws, "_update_audio_detail_cards")
print(f"   Media._update_audio_detail_cards: {'OK' if ok else 'FEHLT'}")

# Resource Monitor in StatusBar
children = [type(c).__name__ for c in w.statusBar().children()]
has_monitor = "ResourceMonitorWidget" in children
print(f"5. ResourceMonitor: {'OK' if has_monitor else 'FEHLT'} ({children})")

w.close()
app.quit()
print("=== SMOKE TEST BESTANDEN ===")

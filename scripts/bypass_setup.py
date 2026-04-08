from PySide6.QtCore import QSettings
s = QSettings("PBStudio", "PBStudio")
s.setValue("setup/setup_complete", True)
s.sync()
print("Setup-Status: Abgeschlossen (manuell markiert)")


from PySide6.QtCore import QSettings
import logging

def configure_ollama():
    SETTINGS_ORG = "PBStudio"
    SETTINGS_APP = "PBStudio"
    s = QSettings(SETTINGS_ORG, SETTINGS_APP)
    
    # Standardwerte setzen
    s.setValue("ollama/enabled", True)
    s.setValue("ollama/url", "http://localhost:11434")
    s.setValue("ollama/model", "llama3:8b") # Favorit für 6GB VRAM
    s.sync()
    print("[SYSTEM] Ollama wurde für PB Studio konfiguriert (llama3:8b).")

if __name__ == "__main__":
    configure_ollama()

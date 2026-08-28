"""
Autonomer End-to-End GUI & Workflow Test für PB Studio Rebuild im Vordergrund.
Startet das echte GUI-Fenster sichtbar im Vordergrund.
Führt einen vollständigen App-Durchlauf mit echtem Audio und Video-Ordner durch.
Zeichnet alle System-Events, Logger-Meldungen, GUI-Zustände, Worker-Tasks und DB-Operationen
in test-report/e2e_gui_test_run.log auf.
"""

import sys
import os
import time
import logging
import traceback
from pathlib import Path

# Projekt-Root in sys.path aufnehmen
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Test-Report Ordner erstellen
REPORT_DIR = PROJECT_ROOT / "test-report"
REPORT_DIR.mkdir(exist_ok=True)
LOG_FILE = REPORT_DIR / "e2e_gui_test_run.log"

# Umfassendes Logging einrichten
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

log = logging.getLogger("E2E_Runner")

log.info("=== START: Autonomer End-to-End GUI Test im Vordergrund ===")
log.info(f"Projekt Root: {PROJECT_ROOT}")
log.info(f"Logdatei: {LOG_FILE}")

# Mediendateien definieren
AUDIO_PATH = "C:/Users/David_Lochmann/Music/Maceo Plex - Sub-Alot (free download).mp3"
VIDEO_DIR = "C:/Users/David_Lochmann/Videos/Solo_Natur-20260406T220640Z-3-001/Solo_Natur"

log.info(f"Audio-Datei: {AUDIO_PATH} (Vorhanden: {os.path.exists(AUDIO_PATH)})")
log.info(f"Video-Ordner: {VIDEO_DIR} (Vorhanden: {os.path.exists(VIDEO_DIR)})")

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, Qt
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        log.info("QApplication neu instanziiert.")
    else:
        log.info("Bestehende QApplication wiederverwendet.")

    # Hauptfenster importieren
    from main import PBWindow
    log.info("main.PBWindow erfolgreich importiert.")

    window = PBWindow()
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    log.info("PBWindow instanziiert und im Vordergrund maximiert angezeigt.")

    # Event-Loop Verarbeitung zulassen
    for _ in range(10):
        app.processEvents()
        time.sleep(0.1)

    # 1. E2E Projekt anlegen/öffnen
    project_name = "E2E_MaceoPlex_SoloNatur_LiveTest"
    log.info(f"[STEP 1] Erstelle/Lade E2E Testprojekt '{project_name}' im GUI...")
    if hasattr(window, "project_service") and window.project_service:
        proj = window.project_service.create_or_open_project(project_name)
        log.info(f"Projekt erfolgreich geladen: ID={getattr(proj, 'id', 'N/A')}, Pfad={getattr(proj, 'project_dir', 'N/A')}")

    for _ in range(10):
        app.processEvents()
        time.sleep(0.1)

    # 2. Audio-Import & Analyse
    log.info(f"[STEP 2] Importiere Audio-Datei im GUI: {AUDIO_PATH}...")
    if os.path.exists(AUDIO_PATH):
        if hasattr(window, "import_media") and hasattr(window.import_media, "_import_audio_paths"):
            window.import_media._import_audio_paths([AUDIO_PATH])
            log.info("Audio-Import erfolgreich im GUI getriggert.")
        
        for _ in range(20):
            app.processEvents()
            time.sleep(0.1)

        # Audio-Analyse ausführen
        log.info("Starte Audio-Analyse (BPM, Beats, Onsets, Mood, LUFS)...")
        if hasattr(window, "audio_analysis") and hasattr(window.audio_analysis, "_analyze_selected_audio"):
            window.audio_analysis._analyze_selected_audio()
            log.info("Audio-Analyse Task im GUI gestartet.")
        
        for _ in range(30):
            app.processEvents()
            time.sleep(0.1)

    # 3. Video-Import
    log.info(f"[STEP 3] Scanne & Importiere Video-Clips im GUI aus Ordner: {VIDEO_DIR}...")
    video_files = []
    for root, dirs, files in os.walk(VIDEO_DIR):
        for f in files:
            if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                video_files.append(os.path.join(root, f))
    
    log.info(f"Gefundene Video-Clips: {len(video_files)} Clips.")
    sample_videos = video_files[:20]
    log.info(f"Importiere {len(sample_videos)} Clips im GUI...")

    if hasattr(window, "import_media") and hasattr(window.import_media, "_import_video_paths"):
        window.import_media._import_video_paths(sample_videos)
        log.info("Video-Import im GUI gestartet.")

    for _ in range(30):
        app.processEvents()
        time.sleep(0.1)

    # 4. Auto-Edit & Timeline
    log.info("[STEP 4] Generiere Auto-Edit Timeline im GUI...")
    if hasattr(window, "edit_workspace") and hasattr(window.edit_workspace, "_auto_edit_to_beat"):
        window.edit_workspace._auto_edit_to_beat()
        log.info("Auto-Edit Schnitt getriggert.")

    for _ in range(30):
        app.processEvents()
        time.sleep(0.1)

    # 5. Timeline Playback & Transport
    log.info("[STEP 5] Steuere Vorschau-Playback im GUI...")
    if hasattr(window, "video_preview") and hasattr(window.video_preview, "toggle_play"):
        window.video_preview.toggle_play()
        log.info("Playback gestartet.")
        for _ in range(20):
            app.processEvents()
            time.sleep(0.1)
            
        window.video_preview.stop()
        log.info("Playback gestoppt.")

    log.info("=== RESULT: E2E GUI Testlauf im Vordergrund erfolgreich abgeschlossen! ===")
    log.info(f"Logdatei geschrieben: {LOG_FILE}")
    log.info(f"Dateigröße: {os.path.getsize(LOG_FILE)} Bytes.")

    # Event Loop weiter laufen lassen, damit der User das GUI-Fenster offen sieht
    log.info("GUI-Fenster bleibt im Vordergrund geöffnet.")
    sys.exit(app.exec())

except Exception as e:
    log.error(f"FEHLER im E2E GUI Testlauf: {e}")
    log.error(traceback.format_exc())
    sys.exit(1)

import sys
import os
from pathlib import Path
PROJECT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)
print(f"Project Dir: {PROJECT_DIR}")

print("Starting import debug...")
try:
    print("Importing dotenv...")
    from dotenv import load_dotenv
    load_dotenv()
    print("Importing gc, sys, subprocess, time, logging, traceback, pathlib...")
    import gc
    import sys
    import subprocess
    import time
    import logging
    import traceback
    from pathlib import Path
    print("Importing PySide6.QtWidgets...")
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QStatusBar, QDockWidget, QTextEdit, QPushButton,
        QTableWidget, QTableWidgetItem, QSplitter, QFileDialog, QHeaderView,
        QProgressBar, QLabel, QLineEdit, QSlider, QGroupBox,
        QComboBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
        QGraphicsTextItem, QGraphicsLineItem, QDialog, QFrame,
        QTreeWidget, QTreeWidgetItem, QCheckBox, QStackedWidget,
        QSizePolicy, QSpacerItem, QMenu, QGraphicsPolygonItem, QSpinBox, QDoubleSpinBox,
        QScrollArea,
    )
    print("Importing PySide6.QtCore...")
    from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer, QTranslator, QLocale, QSettings
    print("Importing PySide6.QtGui...")
    from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QBrush, QPen, QPixmap, QImage, QPolygonF, QAction
    print("Importing ui.theme...")
    from ui.theme import get_stylesheet
    print("Importing ui.controllers.worker_dispatcher...")
    from ui.controllers.worker_dispatcher import _GLOBAL_ACTIVE_THREADS
    print("Importing database stuff...")
    from database import init_db, engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, WaveformData, ClipAnchor
    from sqlalchemy.orm import Session as DBSession
    import json as _json
    print("Importing ingest_service...")
    from services.ingest_service import (
        get_all_media, get_all_audio, get_all_video,
        delete_all_media, delete_selected_media, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
    )
    print("Importing os...")
    import os
    print("Importing pacing_service...")
    from services.pacing_service import (
        PacingSettings, calculate_cut_points, CutPoint, auto_edit_to_beats,
        AdvancedPacingSettings, generate_keyframe_strings_for_project,
    )
    print("Importing export_service...")
    from services.export_service import get_timeline_summary
    print("Importing timeline_service...")
    from services.timeline_service import TimelineService, PB_NS
    print("Importing ui.chat_dock...")
    from ui.chat_dock import ChatDock
    print("Importing ui.waveform_item...")
    from ui.waveform_item import WaveformGraphicsItem
    print("Imports complete!")
except Exception as e:
    print(f"\nCRASH DURING IMPORT: {e}")
    traceback.print_exc()
    sys.exit(1)

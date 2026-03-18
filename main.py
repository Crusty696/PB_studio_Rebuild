import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QDockWidget, QTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QSplitter, QFileDialog, QHeaderView,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

from database import init_db
from services.ingest_service import (
    ingest_audio, ingest_video, get_all_media,
    AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
from services.audio_service import AudioAnalyzer


# ── Background Worker für Audio-Analyse ───────────────────────────────

class AnalysisWorker(QObject):
    finished = Signal(int, dict)   # track_id, result
    error = Signal(int, str)       # track_id, error_msg
    started = Signal(int, str)     # track_id, title

    def __init__(self, track_id: int, title: str):
        super().__init__()
        self.track_id = track_id
        self.title = title
        self.analyzer = AudioAnalyzer()

    def run(self):
        self.started.emit(self.track_id, self.title)
        try:
            result = self.analyzer.analyze_and_store(self.track_id)
            self.finished.emit(self.track_id, result)
        except Exception as e:
            self.error.emit(self.track_id, str(e))


# ── Hauptfenster ──────────────────────────────────────────────────────

class PBWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PB_studio - Director's Cockpit")
        self.resize(1280, 720)
        self._active_threads: list[QThread] = []

        # Zentrales Widget und Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Tab-System
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_media_ingest_tab(), "Media Ingest")
        self.tabs.addTab(QWidget(), "Director's Desk")
        self.tabs.addTab(QWidget(), "Production")

        # Statusleiste
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("System bereit | CPU: 0% | VRAM: 0 GB")

        # System-Konsole
        self.setup_console()

        # Tabelle initial befüllen
        self._refresh_media_table()

    # ── Media Ingest Tab ──────────────────────────────────────────────

    def _build_media_ingest_tab(self) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tab_layout.addWidget(splitter)

        # Linke Seite: Buttons
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        btn_video = QPushButton("Video importieren")
        btn_video.setMinimumHeight(40)
        btn_video.clicked.connect(self._import_video)
        left_layout.addWidget(btn_video)

        btn_audio = QPushButton("Audio importieren")
        btn_audio.setMinimumHeight(40)
        btn_audio.clicked.connect(self._import_audio)
        left_layout.addWidget(btn_audio)

        self.btn_analyze = QPushButton("Gewähltes Audio analysieren")
        self.btn_analyze.setMinimumHeight(40)
        self.btn_analyze.clicked.connect(self._analyze_selected_audio)
        left_layout.addWidget(self.btn_analyze)

        splitter.addWidget(left_panel)

        # Rechte Seite: Media-Tabelle
        self.media_table = QTableWidget()
        self.media_table.setColumnCount(5)
        self.media_table.setHorizontalHeaderLabels(
            ["ID", "Typ", "Titel", "BPM", "Dateipfad"]
        )
        self.media_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.media_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.media_table.setAlternatingRowColors(True)

        header = self.media_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        splitter.addWidget(self.media_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        return tab

    # ── Import-Logik ──────────────────────────────────────────────────

    def _import_video(self):
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Videos importieren", "", ext_filter)
        self._process_imports(paths, "video")

    def _import_audio(self):
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Audio importieren", "", ext_filter)
        self._process_imports(paths, "audio")

    def _process_imports(self, paths: list[str], media_type: str):
        if not paths:
            return

        added = 0
        for p in paths:
            if media_type == "audio":
                result = ingest_audio(p)
            else:
                result = ingest_video(p)

            name = Path(p).name
            if result is None:
                self.console_text.append(f"[Warnung] Datei bereits importiert: {name}")
            else:
                self.console_text.append(f"[Ingest] {media_type.capitalize()} importiert: {name}")
                added += 1

        if added:
            self._refresh_media_table()
            self.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

    # ── Audio-Analyse ─────────────────────────────────────────────────

    def _analyze_selected_audio(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewählt.")
            return

        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien können analysiert werden.")
            return

        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        # Worker im Hintergrund-Thread starten
        thread = QThread()
        worker = AnalysisWorker(track_id, title)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self._on_analysis_started)
        worker.finished.connect(self._on_analysis_finished)
        worker.error.connect(self._on_analysis_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_thread(thread))

        # Referenz halten, damit der Thread nicht vom GC entfernt wird
        self._active_threads.append(thread)

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse läuft...")
        thread.start()

    def _on_analysis_started(self, track_id: int, title: str):
        self.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict):
        bpm = result["bpm"]
        duration = result["duration"]
        self.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Energie-Punkte: {len(result['energy_curve'])}"
        )
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Gewähltes Audio analysieren")
        self.status_bar.showMessage("Analyse abgeschlossen | System bereit")
        self._refresh_media_table()

    def _on_analysis_error(self, track_id: int, error_msg: str):
        self.console_text.append(f"[Fehler] Analyse fehlgeschlagen (ID {track_id}): {error_msg}")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Gewähltes Audio analysieren")
        self.status_bar.showMessage("Analyse-Fehler | System bereit")

    def _cleanup_thread(self, thread: QThread):
        if thread in self._active_threads:
            self._active_threads.remove(thread)

    # ── Tabelle ───────────────────────────────────────────────────────

    def _refresh_media_table(self):
        media = get_all_media()
        self.media_table.setRowCount(len(media))
        for row, item in enumerate(media):
            self.media_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.media_table.setItem(row, 1, QTableWidgetItem(item["type"]))
            self.media_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "—"
            self.media_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            self.media_table.setItem(row, 4, QTableWidgetItem(item["file_path"]))

    # ── System-Konsole ────────────────────────────────────────────────

    def setup_console(self):
        dock = QDockWidget("System-Konsole", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.append("[System] PB_studio Core Engine erfolgreich gestartet.")

        dock.setWidget(self.console_text)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)


def main():
    init_db()
    app = QApplication(sys.argv)
    window = PBWindow()
    window.console_text.append("[System] SQLite Datenbank (pb_studio.db) erfolgreich initialisiert.")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

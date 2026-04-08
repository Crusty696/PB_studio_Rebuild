"""SearchController — Refactored from SearchMixin."""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem
from workers import SemanticSearchWorker
from ui.base_component import PBComponent

class SearchController(PBComponent):
    """Semantic search methods for PBWindow."""

    def _run_semantic_search(self):
        """Startet SigLIP Text-zu-Video Suche."""
        query = self.window.search_input.text().strip()
        if not query:
            self.window.console_text.append("[Suche] Bitte Suchbegriff eingeben.")
            return

        self.window.btn_search.setEnabled(False)
        self.window.btn_search.setText("...")
        self.window.console_text.append(f"[Suche] SigLIP-Suche: '{query}'...")

        worker = SemanticSearchWorker(query, top_k=20)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_search_error)
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_search_finished(self, results: list):
        self.window.btn_search.setEnabled(True)
        self.window.btn_search.setText("Suchen")
        if not results:
            self.window.console_text.append("[Suche] Keine Ergebnisse gefunden.")
            return

        self.window.console_text.append(f"[Suche] {len(results)} Ergebnisse gefunden.")
        self.window.video_pool_table.setRowCount(len(results))
        for row, r in enumerate(results):
            video_name = Path(r["video_path"]).stem
            scene_info = f"Sz{r['scene_index']} ({r['scene_start']:.1f}-{r['scene_end']:.1f}s)"
            distance = f"dist:{r['_distance']:.3f}"
            motion = f"motion:{r['motion_score']:.2f}"

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.window.video_pool_table.setItem(row, 0, chk)
            self.window.video_pool_table.setItem(row, 1, QTableWidgetItem(str(r.get("id", ""))))
            self.window.video_pool_table.setItem(row, 2, QTableWidgetItem(f"{video_name} | {scene_info}"))
            self.window.video_pool_table.setItem(row, 3, QTableWidgetItem(motion))
            self.window.video_pool_table.setItem(row, 4, QTableWidgetItem(distance))
            self.window.video_pool_table.setItem(row, 5, QTableWidgetItem("-"))
            self.window.video_pool_table.setItem(row, 6, QTableWidgetItem(r["video_path"]))

    def _on_search_error(self, error_msg: str):
        self.window.btn_search.setEnabled(True)
        self.window.btn_search.setText("Suchen")
        self.window.console_text.append(f"[Suche-Fehler] {error_msg}")

    def _clear_search(self):
        """Suche zurücksetzen — normale Video-Pool Anzeige."""
        self.window.search_input.clear()
        self.window.media_table_controller._refresh_media_table()
        self.window.console_text.append("[Suche] Zurückgesetzt — alle Videos angezeigt.")

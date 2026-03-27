"""Search Mixin fuer PBWindow."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from workers import SemanticSearchWorker


class SearchMixin:
    """Semantic search methods for PBWindow."""

    def _run_semantic_search(self):
        """Startet SigLIP Text-zu-Video Suche."""
        query = self.search_input.text().strip()
        if not query:
            self.console_text.append("[Suche] Bitte Suchbegriff eingeben.")
            return

        self.btn_search.setEnabled(False)
        self.btn_search.setText("...")
        self.console_text.append(f"[Suche] SigLIP-Suche: '{query}'...")

        worker = SemanticSearchWorker(query, top_k=20)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_search_error)

        self._start_worker_thread(worker)

    def _on_search_finished(self, results: list):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Suchen")

        if not results:
            self.console_text.append("[Suche] Keine Ergebnisse gefunden.")
            return

        self.console_text.append(f"[Suche] {len(results)} Ergebnisse gefunden.")

        # Video Pool mit Suchergebnissen aktualisieren
        # Spalten-Layout muss mit _refresh_media_table uebereinstimmen:
        # col 0=Auswahl, col 1=ID, col 2=Titel, col 3=Aufloesung, col 4=FPS, col 5=Codec, col 6=Dateipfad
        self.video_pool_table.setRowCount(len(results))
        for row, r in enumerate(results):
            video_name = Path(r["video_path"]).stem
            scene_info = f"Sz{r['scene_index']} ({r['scene_start']:.1f}-{r['scene_end']:.1f}s)"
            distance = f"dist:{r['_distance']:.3f}"
            motion = f"motion:{r['motion_score']:.2f}"

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.video_pool_table.setItem(row, 0, chk)
            self.video_pool_table.setItem(row, 1, QTableWidgetItem(str(r.get("id", ""))))
            self.video_pool_table.setItem(row, 2, QTableWidgetItem(f"{video_name} | {scene_info}"))
            self.video_pool_table.setItem(row, 3, QTableWidgetItem(motion))
            self.video_pool_table.setItem(row, 4, QTableWidgetItem(distance))
            self.video_pool_table.setItem(row, 5, QTableWidgetItem("-"))
            self.video_pool_table.setItem(row, 6, QTableWidgetItem(r["video_path"]))

    def _on_search_error(self, error_msg: str):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Suchen")
        self.console_text.append(f"[Suche-Fehler] {error_msg}")

    def _clear_search(self):
        """Suche zurücksetzen — normale Video-Pool Anzeige."""
        self.search_input.clear()
        self._refresh_media_table()
        self.console_text.append("[Suche] Zurückgesetzt — alle Videos angezeigt.")

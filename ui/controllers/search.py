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
        
        # Transformiere Ergebnisse für das Model
        formatted_results = []
        for r in results:
            video_name = Path(r["video_path"]).stem
            scene_info = f"Sz{r['scene_index']} ({r['scene_start']:.1f}-{r['scene_end']:.1f}s)"
            formatted_results.append({
                "id": r.get("id", 0),
                "title": f"{video_name} | {scene_info}",
                "resolution": f"dist:{r.get('_distance', 0):.3f}", # Missbrauche Spalten für Search-Info
                "fps": f"mot:{r.get('motion_score', 0):.2f}",
                "codec": "-",
                "file_path": r["video_path"]
            })
        
        # Model aktualisieren
        if hasattr(self.window, "video_pool_model"):
            self.window.video_pool_model.set_items(formatted_results)

    def _on_search_error(self, error_msg: str):
        self.window.btn_search.setEnabled(True)
        self.window.btn_search.setText("Suchen")
        self.window.console_text.append(f"[Suche-Fehler] {error_msg}")

    def _clear_search(self):
        """Suche zurücksetzen — normale Video-Pool Anzeige."""
        self.window.search_input.clear()
        self.window.media_table_controller._refresh_media_table()
        self.window.console_text.append("[Suche] Zurückgesetzt — alle Videos angezeigt.")

import asyncio
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PySide6.QtCore import QCoreApplication

from services.brain_v3.embedding_scheduler import EmbeddingScheduler, SkipEmbeddingError, EmbeddingTask
from services.brain_v3.storage.embedding_cache import EmbeddingCache


class TestB576EmbeddingSkip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialisiere QCoreApplication falls noch nicht vorhanden
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def test_embedding_scheduler_skips_on_os_error(self):
        # Mock Cache und Serializer
        mock_cache = MagicMock(spec=EmbeddingCache)
        mock_serializer = MagicMock()
        
        # Simuliere, dass _embedder_factory ein OSError wirft (z.B. Datei unlesbar)
        def mock_embedder_factory(task, progress_cb, serializer):
            raise OSError("Konnte Video nicht oeffnen")
            
        scheduler = EmbeddingScheduler(
            n_workers=1,
            cache=mock_cache,
            embedder_factory=mock_embedder_factory,
            serializer=mock_serializer
        )
        
        # Mock Signals
        skipped_mock = MagicMock()
        progress_mock = MagicMock()
        
        scheduler.job_skipped.connect(skipped_mock)
        scheduler.job_progress.connect(progress_mock)
        
        scheduler.start()
        try:
            # Reiche einen Task ein
            job_id = scheduler.submit_path(
                media_hash="hash123",
                source_path="corrupt_video.mp4",
                media_type="video"
            )
            
            # Warte kurz, bis der Thread den Job abgearbeitet hat
            loop = asyncio.get_event_loop()
            # Da es ein QThread mit asyncio-Loop ist, lassen wir Qt Events verarbeiten
            for _ in range(20):
                self.app.processEvents()
                import time
                time.sleep(0.05)
                if skipped_mock.called:
                    break
                    
            # Checke, ob skipped Signal mit korrektem Hash und Fehlermeldung aufgerufen wurde
            skipped_mock.assert_called_once_with("hash123", "Konnte Video nicht oeffnen")
            
            # Cache darf nicht gespeichert worden sein
            mock_cache.store.assert_not_called()
            
        finally:
            scheduler.request_stop()


if __name__ == "__main__":
    unittest.main()

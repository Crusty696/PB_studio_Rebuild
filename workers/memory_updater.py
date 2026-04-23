import logging
import traceback
from PySide6.QtCore import QObject, Signal, QTimer, Slot
from services.memory.pattern_aggregator import PatternAggregator

logger = logging.getLogger(__name__)

class MemoryUpdaterWorker(QObject):
    """
    Background worker that orchestrates the PatternAggregator.
    Can be run periodically via a timer or triggered manually (on-demand).
    
    Signals:
        updated: Emitted when an aggregation cycle completes successfully.
        error: Emitted with an error message if an aggregation cycle fails.
    """
    updated = Signal()
    error = Signal(str)
    
    def __init__(self, interval_ms: int = 0):
        """
        Initializes the worker.
        Args:
            interval_ms: If > 0, sets up a timer to run aggregation periodically.
        """
        super().__init__()
        self.aggregator = PatternAggregator()
        self._timer = None
        
        if interval_ms > 0:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.run_aggregation_cycle)
            self._interval_ms = interval_ms
            logger.info(f"MemoryUpdaterWorker initialized with {interval_ms}ms interval")

    @Slot()
    def start(self):
        """Starts the periodic timer if configured."""
        if self._timer:
            self._timer.start(self._interval_ms)
            logger.info("MemoryUpdaterWorker periodic timer started.")
        else:
            logger.warning("MemoryUpdaterWorker.start() called but no interval was configured.")

    @Slot()
    def stop(self):
        """Stops the periodic timer."""
        if self._timer:
            self._timer.stop()
            logger.info("MemoryUpdaterWorker periodic timer stopped.")

    @Slot()
    def run_aggregation_cycle(self):
        """
        Triggers a single aggregation cycle.
        Can be called manually or via timer.
        """
        logger.debug("MemoryUpdaterWorker triggering aggregation cycle...")
        try:
            # Aggregator uses its own nullpool_session, so it's thread-safe
            self.aggregator.run_aggregation_cycle()
            self.updated.emit()
        except Exception as e:
            err_msg = f"Memory aggregation failed: {str(e)}"
            logger.error(f"{err_msg}\n{traceback.format_exc()}")
            self.error.emit(err_msg)

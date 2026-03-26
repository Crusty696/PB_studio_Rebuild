"""Base classes for background workers."""


class CancellableMixin:
    """Mixin for workers: adds a _cancelled flag checked via should_stop()."""
    _cancelled = False

    def cancel(self):
        self._cancelled = True

    def should_stop(self) -> bool:
        return self._cancelled

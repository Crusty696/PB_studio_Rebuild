"""Base classes for background workers."""


class CancellableMixin:
    """Mixin for workers: adds a _cancelled flag checked via should_stop()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cancelled = False
        self._errored = False

    def cancel(self):
        self._cancelled = True

    def should_stop(self) -> bool:
        return self._cancelled

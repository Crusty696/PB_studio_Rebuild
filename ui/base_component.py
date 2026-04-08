"""Base class for PBWindow components (controllers)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import PBWindow

class PBComponent:
    """Base class for components that extend PBWindow functionality via composition."""
    
    def __init__(self, window: 'PBWindow'):
        self.window = window
        self.logger = window.logger if hasattr(window, 'logger') else None

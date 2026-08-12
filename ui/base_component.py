"""Base class for PBWindow components (controllers)."""

import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from main import PBWindow

class PBComponent:
    """Base class for components that extend PBWindow functionality via composition.

    B-020: Die Rueckwaertskante ``controller.window -> PBWindow`` ist eine
    *nicht besitzende* Elternreferenz. Als starke Referenz bildete sie
    zusammen mit ``PBWindow.__dict__ -> controller`` einen Python-Zyklus,
    den der GC nachweislich nicht abraeumt (gemessen 2026-08-11: nach
    ``close()`` lebte der Wrapper samt komplettem Objektbaum in 6/6 Zyklen
    weiter, obwohl das C++-Fenster korrekt zerstoert war). Deshalb wird die
    Kante als ``weakref`` gehalten.

    Nur echte ``QObject``-Fenster werden schwach referenziert. Test-Doubles
    (``SimpleNamespace``, ``MagicMock``, Fake-Klassen) haben keinen anderen
    Besitzer und wuerden sofort sterben — sie bleiben stark referenziert.
    """

    def __init__(self, window: 'PBWindow'):
        self.window = window
        self.logger = window.logger if hasattr(window, 'logger') else None

    @property
    def window(self):
        """Das besitzende PBWindow, oder ``None`` wenn es bereits tot ist.

        Callbacks, die nach dem Fenster-Teardown noch feuern koennen
        (Worker-Signale, ``QTimer.singleShot``), muessen auf ``None`` pruefen.
        """
        ref = self.__dict__.get("_window_ref")
        if ref is not None:
            return ref()
        return self.__dict__.get("_window_strong")

    def _window_alive(self) -> bool:
        """True, wenn das Fenster noch existiert (Python *und* C++).

        Guard fuer asynchrone Rueckkanaele: ein Worker-``finished`` oder ein
        ``QTimer.singleShot`` kann nach dem Fenster-Teardown noch zugestellt
        werden. ``self.window`` ist dann ``None`` (weakref tot) oder ein
        Wrapper ohne C++-Objekt (``RuntimeError`` beim ersten Attributzugriff).
        """
        win = self.window
        if win is None:
            return False
        if isinstance(win, QObject):
            try:
                import shiboken6
                return bool(shiboken6.isValid(win))
            except Exception:
                return True
        return True

    @window.setter
    def window(self, value):
        if isinstance(value, QObject):
            try:
                self.__dict__["_window_ref"] = weakref.ref(value)
                self.__dict__["_window_strong"] = None
                return
            except TypeError:
                pass  # nicht weakref-faehig -> starke Referenz
        self.__dict__["_window_ref"] = None
        self.__dict__["_window_strong"] = value

"""Gemeinsame FFmpeg/FFprobe-Helfer (K4).

Zentraler Ersatz fuer ~25 Inline-Duplikate des CREATE_NO_WINDOW-Patterns
(dict-Literal, Ternaer, getattr-Variante — auf win32 funktional identisch).

Wichtig fuer Zyklusfreiheit: dieses Modul importiert auf Modul-Ebene KEINE
anderen ``services``-Module — ``services.startup_checks`` importiert
``subprocess_kwargs`` von hier.
"""

from __future__ import annotations

import subprocess
import sys


def subprocess_kwargs() -> dict:
    """Extra-kwargs fuer ``subprocess.run``/``Popen``.

    Auf Windows: ``creationflags=subprocess.CREATE_NO_WINDOW`` — verhindert
    das Aufblitzen eines Konsolenfensters bei ffmpeg/ffprobe-Aufrufen aus
    der GUI. Auf anderen Plattformen: leeres dict (entspricht dem Default
    ``creationflags=0``).

    Verwendung: ``subprocess.run(cmd, ..., **subprocess_kwargs())``.
    """
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw

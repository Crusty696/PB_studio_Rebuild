"""Ablageort fuer Auto-Ducking-Ergebnisse — eine Stelle fuer beide Aufrufer.

B-946: Der Ordner wurde an zwei Stellen unabhaengig gebildet, beide ueber
``Path(__file__).parent...`` — also relativ zum **Repo**, nicht zum aktiven
Projekt:

* ``ui/controllers/stems.py`` (Knopf in der Oberflaeche)
* ``workers/registry.py`` (Chat-Aktion, seit B-940)

Damit landeten die Ergebnisse aller Projekte im selben Ordner und vermischten
sich beim Projektwechsel; im Repo-Baum stoerten sie ausserdem den Handoff-Check.
Stems liegen laengst projektbezogen unter ``<APP_ROOT>/storage/stems`` — die
Ducking-Ausgabe gehoert daneben.

``APP_ROOT`` wird bewusst zur Laufzeit gelesen (nicht per ``from ... import``):
``set_project()`` biegt den Wert bei jedem Projektwechsel um, ein zum
Importzeitpunkt kopierter Wert waere danach veraltet.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_VERBOTEN = re.compile(r'[<>:"/\|?*]')


def projekt_wurzel() -> Path:
    """Aktiver Projektordner; faellt auf den Repo-Ordner zurueck."""
    try:
        from database import session as _session

        wurzel = getattr(_session, "APP_ROOT", None)
        if wurzel:
            return Path(wurzel)
    except Exception:  # noqa: BLE001 — darf den Ducking-Start nie verhindern
        logger.warning("APP_ROOT nicht lesbar, nutze den Repo-Ordner", exc_info=True)
    return Path(__file__).resolve().parent.parent


def ducked_ordner(*, anlegen: bool = True) -> Path:
    ordner = projekt_wurzel() / "storage" / "ducked"
    if anlegen:
        try:
            ordner.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Ducked-Ordner %s nicht anlegbar", ordner, exc_info=True)
    return ordner


def ducked_ausgabe(titel: str | None, *, anlegen: bool = True) -> str:
    """Vollstaendiger Ausgabepfad fuer einen Track-Titel."""
    sicher = _VERBOTEN.sub("_", titel or "track")
    return str(ducked_ordner(anlegen=anlegen) / f"{sicher}_ducked.wav")

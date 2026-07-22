"""AUFRAEUM B4: Auslagerungs-Package fuer reine, zustandslose Timeline-Teile.

Enthaelt ausschliesslich Qt-freie, self-freie Bausteine, die verbatim aus
``ui/timeline.py`` herausgezogen wurden. Der gesamte QGraphicsView/QWidget-
Zustand (``InteractiveTimeline`` + alle QGraphicsItem-Klassen) bleibt in
``ui/timeline.py``. ``ui.timeline`` re-exportiert die hier definierten Namen,
sodass die Public-API von ``ui.timeline`` unveraendert bleibt.
"""

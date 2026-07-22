"""Reine Layout-/Geometrie-Konstanten der Timeline.

AUFRAEUM B4: verbatim aus ``ui/timeline.py`` (Abschnitt ``# Constants``)
herausgezogen. Reine Zahlen-Literale — kein Qt, kein ``self``, kein
Widget-Zustand. ``ui.timeline`` re-exportiert diese Namen unveraendert.
"""

# ======================================================================
# Constants
# ======================================================================

PIXELS_PER_SECOND = 25
# Fixplan 2026-07-07 Schritt 8: 80 -> 110 px -> Maengelbehebung 140 px.
# Track-Hoehen und Zoom wirken zusammen. Alle Track-Geometrien leiten
# sich aus dieser Konstante ab (VIDEO_TRACK_Y, Thumb-Hoehe, Handles).
TRACK_HEIGHT = 140
MIN_READABLE_FIT_SCALE = 0.25
AUDIO_TRACK_Y = 10
VIDEO_TRACK_Y = AUDIO_TRACK_Y + TRACK_HEIGHT + 12
CUT_MARKERS_Y = VIDEO_TRACK_Y + TRACK_HEIGHT + 10
RULER_Y = CUT_MARKERS_Y + 30

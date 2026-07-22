"""Label-Confidence-Scoring (stateless).

AUFRAEUM B1: aus ``structure_detection_service`` verbatim ausgelagerte
Modul-Hilfsfunktion ``_label_confidence_multi``. Reine Funktion ohne State,
kein Logik-Change.
"""


def _label_confidence_multi(
    label: str,
    avg_energy: float,
    avg_centroid: float,
    avg_bass: float,
    avg_regularity: float,
    n_beats: int,
) -> float:
    """Berechnet Confidence fuer ein Segment basierend auf Multi-Feature-Uebereinstimmung.

    Hoehere Confidence wenn mehrere Features das Label gleichzeitig unterstuetzen.
    """
    conf = 0.35  # Niedrigere Basis — Multi-Feature muss bestaetigen

    # Laengere Segmente → mehr Sicherheit
    if n_beats >= 32:
        conf += 0.15
    elif n_beats >= 16:
        conf += 0.08
    elif n_beats >= 8:
        conf += 0.04

    # Label-spezifische Multi-Feature-Pruefung
    if label == "DROP":
        if avg_energy > 0.7:
            conf += 0.15
        if avg_bass > 0.6:
            conf += 0.15
        if avg_centroid > 0.6:
            conf += 0.10
        if avg_regularity > 0.8:
            conf += 0.10

    elif label == "BUILDUP":
        if 0.3 < avg_energy < 0.8:
            conf += 0.12
        if avg_centroid > 0.5:
            conf += 0.08
        if avg_regularity > 0.7:
            conf += 0.10

    elif label == "BREAKDOWN":
        if avg_energy < 0.4:
            conf += 0.15
        if avg_bass < 0.35:
            conf += 0.10
        if avg_centroid < 0.45:
            conf += 0.10

    elif label in ("INTRO", "OUTRO"):
        if avg_energy < 0.3:
            conf += 0.20
        if avg_bass < 0.3:
            conf += 0.10

    elif label == "CHORUS":
        if avg_energy >= 0.5:
            conf += 0.10
        if avg_centroid > 0.5:
            conf += 0.10

    elif label == "VERSE":
        if avg_energy < 0.5:
            conf += 0.10
        if avg_centroid < 0.55:
            conf += 0.05

    return round(min(1.0, conf), 3)

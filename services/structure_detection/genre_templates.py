"""Genre-spezifische Struktur-Templates (stateless).

AUFRAEUM B1: aus ``structure_detection_service.StructureDetectionService``
verbatim ausgelagerte @staticmethod-Templates. Reine Funktionen ueber
``labels``/``energy_norm``/``n_beats`` ohne ``self``-State. Kein Logik-Change.
"""


def _template_psytrance(labels: list[str], energy_norm, n_beats: int) -> list[str]:
    """Psytrance: CHORUS → DROP umwandeln bei hoher Energie (> 0.65)."""
    for i in range(n_beats):
        if labels[i] == "CHORUS" and energy_norm[i] > 0.65:
            labels[i] = "DROP"
    return labels


def _template_techno(labels: list[str], energy_norm, n_beats: int) -> list[str]:
    """Techno: VERSE/CHORUS → DROP bei mittlerer bis hoher Energie (> 0.45).

    Techno hat selten echte Verses — wenn Energie > 0.45, ist es eher ein Drop-Phase.
    """
    for i in range(n_beats):
        if labels[i] in ("VERSE", "CHORUS") and energy_norm[i] > 0.45:
            labels[i] = "DROP"
    return labels


def _template_house(labels: list[str], energy_norm, n_beats: int) -> list[str]:
    """House: DROP → CHORUS wenn Energie nicht extrem hoch (< 0.85).

    House hat weniger aggressive Drops — sehr hohe Energie-Sektionen sind CHORUS.
    """
    for i in range(n_beats):
        if labels[i] == "DROP" and energy_norm[i] < 0.85:
            labels[i] = "CHORUS"
    return labels

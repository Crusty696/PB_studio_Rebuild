"""Vision-Caption-Plausibilitaets-Validierung (Fixplan 2026-07-07 Schritt 2).

Reine, GPU-freie Text-/Dict-Parser: pruefen ob eine Vision-Caption eine
echte natuerlichsprachliche Beschreibung ist oder nur Metadaten-/JSON-Echo.
Byte-identisch aus services/video_analysis_service.py ausgelagert
(AUFRAEUM B2). Public-API bleibt ueber Re-Export im urspruenglichen Modul
unveraendert.
"""

from __future__ import annotations


_CAPTION_JUNK_MARKERS = (
    '"type"', "'type'", '"url"', "'url'", "file:///", '"size"', '"format"',
    '"quality"', '"encoding"', '"timestamp"', '.jpeg', '.jpg', '.png',
)


def _caption_text_is_plausible(text: str) -> bool:
    """Prueft ob ein Caption-Text eine natuerlichsprachliche Beschreibung ist.

    Fixplan 2026-07-07 Schritt 2: Vision-Modelle (Ollama) echoen teils
    Bild-Metadaten-JSON ('{"type": "image/jpeg", "url": ...}') statt einer
    Beschreibung. Solcher Muell wurde bisher ungeprueft in scenes.ai_caption
    gespeichert und vergiftete Mood-Matching + semantische Suche.
    """
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if len(t) < 15:
        return False
    # JSON-/Struktur-Echo statt Prosa
    if t.startswith("[") or t.startswith("{"):
        return False
    low = t.lower()
    if any(m in low for m in _CAPTION_JUNK_MARKERS):
        return False
    # Mindestens 3 Woerter mit Buchstaben (Prosa-Heuristik)
    alpha_words = [w for w in t.split() if any(c.isalpha() for c in w)]
    return len(alpha_words) >= 3


def _validate_caption_dict(parsed) -> dict | None:
    """Validiert das geparste Caption-Dict; None = unbrauchbar (Junk).

    Akzeptiert nur Dicts mit plausibler natuerlichsprachlicher description.
    Reine Metadaten-Dicts ({"type": "image/jpeg", "url": ...} oder
    Koordinaten {"x":..,"y":..}) haben keine/keine plausible description und
    fallen durch.
    """
    if not isinstance(parsed, dict):
        return None
    desc = parsed.get("description")
    if not _caption_text_is_plausible(desc if isinstance(desc, str) else ""):
        return None
    return parsed

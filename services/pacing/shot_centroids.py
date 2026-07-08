"""NEUBAU-VOLLINTEGRATION T2.5.4/T2.5.5: Shot-Klassen-Centroids via SigLIP.

shot_type_classifier.classify() und audio_mood_vector.compute_audio_mood_vector()
brauchen 1152-dim Centroids pro Shot-Klasse (vocal/drum/melody/bass_dominant).
Es gibt kein persistiertes Centroid-Artefakt im Repo — wir erzeugen sie wie
die Mood-Embeddings des Legacy-Pfads aus SigLIP-TEXT-Queries (einmal pro
Prozess, gecacht; GPU-Regel: SigLIP laeuft ueber den ModelManager auf cuda:0).

Fehlertolerant: ohne SigLIP/Modelle -> leeres Dict, alle Konsumenten
fallen auf ihre neutralen Pfade zurueck.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Text-Queries pro Shot-Klasse (analog SECTION_MOOD_QUERIES des Legacy-Pfads)
SHOT_CLASS_QUERIES: dict[str, list[str]] = {
    "vocal_dominant": [
        "close-up of a singer performing",
        "person singing into a microphone",
        "face of a vocalist, lips moving",
    ],
    "drum_dominant": [
        "drummer hitting drums",
        "rhythmic percussive motion, hands drumming",
        "fast rhythmic action shot",
    ],
    "melody_dominant": [
        "musician playing a melodic instrument",
        "flowing atmospheric scenery",
        "smooth camera movement over a landscape",
    ],
    "bass_dominant": [
        "dark pulsing club lights",
        "deep slow heavy movement",
        "subwoofer, low frequency vibration visuals",
    ],
}

_cache: dict[str, np.ndarray] | None = None


def get_shot_class_centroids() -> dict[str, np.ndarray]:
    """Liefert {klasse: 1152-dim L2-normalisierter Centroid} (Prozess-Cache)."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        from services.video_analysis_service import texts_to_embeddings_batch

        all_queries: list[str] = []
        owner: dict[str, str] = {}
        for cls, queries in SHOT_CLASS_QUERIES.items():
            for q in queries:
                all_queries.append(q)
                owner[q] = cls
        embeddings = texts_to_embeddings_batch(all_queries)
        if not embeddings:
            logger.warning("Shot-Centroids: SigLIP nicht verfuegbar — leer.")
            _cache = {}
            return _cache
        grouped: dict[str, list[np.ndarray]] = {}
        for q, emb in embeddings.items():
            cls = owner.get(q)
            if cls:
                grouped.setdefault(cls, []).append(np.asarray(emb, dtype=np.float32))
        result: dict[str, np.ndarray] = {}
        for cls, embs in grouped.items():
            mean = np.mean(embs, axis=0)
            norm = float(np.linalg.norm(mean))
            if norm > 1e-9:
                result[cls] = (mean / norm).astype(np.float32)
        _cache = result
        logger.info("Shot-Centroids berechnet: %d Klassen", len(result))
    except Exception as exc:
        logger.warning("Shot-Centroids nicht berechenbar: %s", exc)
        _cache = {}
    return _cache


def reset_cache() -> None:
    """Nur fuer Tests."""
    global _cache
    _cache = None

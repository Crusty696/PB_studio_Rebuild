"""LearnedPatternLookup — DB-backed pattern_lookup fuer den PacingScorer.

NEUBAU-VOLLINTEGRATION T1.5 (USE-008): mem_learned_pattern wurde vom
PatternAggregator geschrieben und vom Memory-Tab angezeigt, aber KEIN
Scorer las es — der w_memory-Term lief immer mit pattern_lookup=None auf
neutral 0.5, die Lernschleife war offen. Dieses Modul ist der produktive
Konsument: PacingScorer(pattern_lookup=LearnedPatternLookup(...)).

Dispatch-Vertrag des Scorers (services/pacing/scorer.py):
  historical_accept_rate -> lookup(fingerprint_tuple, scene_id)
                            -> (accepts, total)
  genre_prior            -> lookup("genre", audio_genre, style_bucket_id)
  key_prior              -> lookup("key", audio_key, clip_mood)
  spectral_fit           -> lookup("spectral", spectral_hash, style_bucket_id)

Nur pattern_type='context_preference' wird vom PatternAggregator
geschrieben — die drei String-Kinds haben (noch) keine Datenbasis und
liefern ehrlich Wilson-neutral 0.5.

Normalisierung: der Aggregator lowercased genre/section_type und bucketed
BPM auf ganze Zahlen (make_context_fingerprint). Der Scorer-Fingerprint
kommt roh aus dem AudioContext — hier wird deshalb identisch normalisiert,
sonst matcht der Lookup nie (gleiche Fehlerklasse wie B-159/B-182).

Ein Prozess-Cache pro Instanz haelt die Query-Last im Hot-Loop klein
(eine Instanz lebt genau einen Auto-Edit-Lauf lang).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)

_SQL = text("""
    SELECT stat_accept_count, stat_sample_size
    FROM mem_learned_pattern
    WHERE pattern_type = 'context_preference'
      AND json_extract(context_fingerprint, '$.genre')        IS :genre
      AND json_extract(context_fingerprint, '$.section_type') IS :section_type
      AND json_extract(context_fingerprint, '$.bpm_bucket')   IS :bpm_bucket
      AND json_extract(target_ref, '$.scene_id') = :scene_id
    LIMIT 1
""")


class LearnedPatternLookup:
    """Callable im pattern_lookup-Vertrag des PacingScorer, gebacked von
    mem_learned_pattern. Fehler duerfen das Scoring nie crashen — jede
    DB-Stoerung faellt auf neutral zurueck."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory
        self._cache: dict[tuple, tuple[int, int]] = {}

    def __call__(self, *args: Any) -> Any:
        first = args[0]
        if not isinstance(first, tuple):
            # "genre" / "key" / "spectral": kein Aggregator-Writer -> neutral.
            return 0.5
        scene_id = int(args[1])
        genre, section_type, bpm_str = (list(first) + [None, None, None])[:3]
        key = (
            genre.lower() if genre else None,
            section_type.lower() if section_type else None,
            str(bpm_str) if bpm_str is not None else None,
            scene_id,
        )
        if key in self._cache:
            return self._cache[key]
        result = (0, 0)
        try:
            with self._session_factory() as session:
                row = session.execute(_SQL, {
                    "genre": key[0],
                    "section_type": key[1],
                    "bpm_bucket": key[2],
                    "scene_id": scene_id,
                }).mappings().one_or_none()
                if row is not None:
                    result = (
                        int(row["stat_accept_count"]),
                        int(row["stat_sample_size"]),
                    )
        except Exception as exc:  # Lookup darf Pacing nie crashen
            logger.warning("LearnedPatternLookup fehlgeschlagen (%s) — "
                           "neutral 0/0.", exc)
        self._cache[key] = result
        return result


__all__ = ["LearnedPatternLookup"]

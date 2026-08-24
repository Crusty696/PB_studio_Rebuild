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

B-707 Befund 4: die drei String-Kinds lieferten hart 0.5 — fuer JEDEN
Kandidaten identisch, also eine Pseudo-Bewertung ohne Aussage. Der
PatternAggregator schreibt zwar nur pattern_type='context_preference' nach
mem_learned_pattern, ABER die Rohdaten liegen vollstaendig in `mem_decision`:
die Tabelle haelt pro Schnitt den Audio-Kontext (at_genre / at_key /
at_spectral_hash) UND die Clip-Labels (clip_style_bucket_id /
clip_mood_refined) plus das Nutzer-Urteil (user_verdict). Daraus werden die
drei Priors hier direkt aggregiert:

  genre    : accept-Rate je (at_genre, clip_style_bucket_id)
  key      : accept-Rate je (at_key, clip_mood_refined)
  spectral : accept-Rate je (at_spectral_hash, clip_style_bucket_id)

Bewertet wird mit dem neutral-zentrierten Wilson-Preference-Score — identisch
zum w_memory-Term, damit wenige Stichproben Richtung zeigen, aber gegen 0.5
gedaempft bleiben.

Solange es zu einem Kontext KEIN Nutzer-Feedback gibt, ist das Ergebnis
0/0 -> 0.5 fuer alle Kandidaten. Das ist dann ehrlich "kein Signal" (und
als solches in ``no_signal_kinds`` sichtbar), keine Bewertung: ein fuer alle
Kandidaten konstanter Summand verschiebt den Score, aber nicht die
Reihenfolge.

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

from services.stats.wilson_lower_bound import wilson_preference_score

logger = logging.getLogger(__name__)

# B-707: Das Verdict-Vokabular in den SQLs ('accept'/'good' bzw.
# 'reject'/'bad') ist identisch zu
# services/pacing/pattern_aggregator.normalize_user_verdict.
#
# Ein GROUP-BY pro (kind, Kontextwert) — nicht eine Query pro Kandidat.
# Damit bleibt es bei max. 3 Queries pro Auto-Edit-Lauf (der Kontextwert ist
# track-weit konstant), statt N+1 im Hot-Loop (30ms-Budget,
# tests/integration/test_pacing_performance.py).
_PRIOR_SQL: dict[str, str] = {
    # (at_genre, clip_style_bucket_id)
    "genre": """
        SELECT CAST(clip_style_bucket_id AS TEXT) AS target,
               SUM(CASE WHEN user_verdict IN ('accept','good') THEN 1 ELSE 0 END)
                   AS accepts,
               SUM(CASE WHEN user_verdict IN
                        ('accept','good','reject','bad') THEN 1 ELSE 0 END)
                   AS total
        FROM mem_decision
        WHERE LOWER(at_genre) = :ctx_value
        GROUP BY clip_style_bucket_id
    """,
    # (at_key, clip_mood_refined)
    "key": """
        SELECT LOWER(clip_mood_refined) AS target,
               SUM(CASE WHEN user_verdict IN ('accept','good') THEN 1 ELSE 0 END)
                   AS accepts,
               SUM(CASE WHEN user_verdict IN
                        ('accept','good','reject','bad') THEN 1 ELSE 0 END)
                   AS total
        FROM mem_decision
        WHERE at_key = :ctx_value
        GROUP BY LOWER(clip_mood_refined)
    """,
    # (at_spectral_hash, clip_style_bucket_id)
    "spectral": """
        SELECT CAST(clip_style_bucket_id AS TEXT) AS target,
               SUM(CASE WHEN user_verdict IN ('accept','good') THEN 1 ELSE 0 END)
                   AS accepts,
               SUM(CASE WHEN user_verdict IN
                        ('accept','good','reject','bad') THEN 1 ELSE 0 END)
                   AS total
        FROM mem_decision
        WHERE at_spectral_hash = :ctx_value
        GROUP BY clip_style_bucket_id
    """,
}

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
        # B-707: (kind, ctx_value) -> {target_key: (accepts, total)}
        self._prior_cache: dict[tuple[str, str], dict[str, tuple[int, int]]] = {}
        # Kinds, fuer die im aktuellen Lauf keinerlei Feedback-Datenbasis
        # existiert -> ihr Term ist ein konstanter Offset, keine Bewertung.
        self.no_signal_kinds: set[str] = set()

    def __call__(self, *args: Any) -> Any:
        first = args[0]
        if not isinstance(first, tuple):
            # B-707 Befund 4: "genre" / "key" / "spectral" aus mem_decision
            # aggregieren statt hart 0.5 zurueckzugeben.
            return self._prior(str(first), args[1], args[2])
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

    # ── B-707 Befund 4: genre / key / spectral Priors ────────────────────
    def _prior(self, kind: str, ctx_value: Any, target: Any) -> float:
        """Wilson-Lower-Bound der Accept-Rate fuer (ctx_value, target).

        ``target`` ist das CLIP-individuelle Merkmal (style_bucket_id bzw.
        mood_refined) — genau dadurch variiert der Term ueber die Kandidaten
        eines Cuts, sobald Feedback vorliegt.
        """
        if kind not in _PRIOR_SQL or ctx_value is None or target is None:
            return 0.5
        norm_ctx = self._normalize_ctx(kind, ctx_value)
        if norm_ctx is None:
            return 0.5
        table = self._prior_table(kind, norm_ctx)
        accepts, total = table.get(self._normalize_target(kind, target), (0, 0))
        return wilson_preference_score(accepts, total)

    @staticmethod
    def _normalize_ctx(kind: str, ctx_value: Any) -> str | None:
        """Kontext-Schluessel so normalisieren wie in der jeweiligen SQL.

        genre wird beidseitig lowercased (der Aggregator tut das auch —
        gleiche Fehlerklasse wie B-159/B-182). Musikalische Keys und
        Spectral-Hashes sind case-signifikant und bleiben roh.
        """
        s = str(ctx_value).strip()
        if not s:
            return None
        return s.lower() if kind == "genre" else s

    @staticmethod
    def _normalize_target(kind: str, target: Any) -> str:
        """Clip-Merkmal auf die Form bringen, die die GROUP-BY-Spalte liefert.

        key      -> clip_mood_refined, lowercased
        sonst    -> clip_style_bucket_id als Integer-String
        """
        if kind == "key":
            return str(target).strip().lower()
        try:
            return str(int(target))
        except (TypeError, ValueError):
            return str(target).strip()

    def _prior_table(self, kind: str, ctx_value: str) -> dict[str, tuple[int, int]]:
        """Accept/Total je Target-Auspraegung — eine Query, dann gecacht."""
        cache_key = (kind, ctx_value)
        cached = self._prior_cache.get(cache_key)
        if cached is not None:
            return cached
        table: dict[str, tuple[int, int]] = {}
        try:
            with self._session_factory() as session:
                rows = session.execute(
                    text(_PRIOR_SQL[kind]), {"ctx_value": ctx_value},
                ).mappings().all()
            for row in rows:
                target = row["target"]
                if target is None:
                    continue
                table[str(target)] = (int(row["accepts"] or 0),
                                      int(row["total"] or 0))
        except Exception as exc:  # Lookup darf Pacing nie crashen
            logger.warning(
                "LearnedPatternLookup-Prior '%s' fehlgeschlagen (%s) — "
                "kein Signal.", kind, exc,
            )
            table = {}
        if not any(total > 0 for _, total in table.values()):
            # Keine einzige bewertete Entscheidung -> der Term ist ein
            # konstanter Offset, keine Bewertung. Einmal pro Lauf melden.
            if kind not in self.no_signal_kinds:
                self.no_signal_kinds.add(kind)
                logger.info(
                    "Pacing-Prior '%s' ohne Datenbasis (kein Nutzer-Feedback "
                    "zu %r in mem_decision) — Term traegt kein Signal.",
                    kind, ctx_value,
                )
        else:
            self.no_signal_kinds.discard(kind)
        self._prior_cache[cache_key] = table
        return table


__all__ = ["LearnedPatternLookup"]

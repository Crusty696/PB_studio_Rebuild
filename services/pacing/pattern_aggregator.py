"""PatternAggregator — aggregates mem_decision + feedback into mem_learned_pattern.

Design §4.3: patterns are separate from decisions. Decisions are immutable truth;
patterns are the aggregated, Wilson-confidence-scored view that the PacingScorer's
w_memory term consults. This class runs periodically (after each run or N=20
feedback events, see MemoryUpdaterWorker T7.3).

Five bugs from the previous failed attempt that this rewrite deliberately avoids:
  - G: at_enricher_version filter — decisions from stale enricher-versions are skipped.
  - H: BPM bucketing — floats like 139.98 and 140.01 are bucketed into a single
       "140" key so they aggregate into the same pattern.
  - I: N+1 queries — uses a single JOIN between mem_decision and mem_pacing_run
       to fetch run-level ratings in one shot.
  - J: pattern lookup by fingerprint — uses a DB WHERE clause on (pattern_type,
       context_fingerprint JSON match) rather than loading-all + Python-loop.
  - L: datetime.utcnow is deprecated — uses datetime.now(timezone.utc).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import text

from services.enrichment import ENRICHER_VERSION
from services.stats.wilson_lower_bound import wilson_lower_bound

logger = logging.getLogger(__name__)


# ── Context Fingerprint bucketing ───────────────────────────────────────────


def bpm_bucket(bpm: float | None) -> str | None:
    """Bucket a float BPM to integer-rounded string. Bug H: floats like 139.98
    and 140.01 must aggregate into the same pattern ("140")."""
    if bpm is None:
        return None
    return str(int(round(bpm)))


def make_context_fingerprint(
    at_genre: str | None,
    at_section_type: str | None,
    at_bpm: float | None,
) -> dict[str, Any]:
    """Stable, JSON-serialisable fingerprint used as the pattern key.

    All three dimensions are normalised: genre/section strings are lowercased;
    BPM is bucketed (bug H). Missing fields are stored as None (null in JSON)
    so patterns with partial context can still aggregate.
    """
    return {
        "genre": at_genre.lower() if at_genre else None,
        "section_type": at_section_type.lower() if at_section_type else None,
        "bpm_bucket": bpm_bucket(at_bpm),
    }


@dataclass(frozen=True)
class PatternUpdate:
    """One upsert target: combination of fingerprint + clip_id + counts."""

    fingerprint: dict[str, Any]
    target_clip_id: int
    accept_count: int
    reject_count: int
    sample_size: int


# ── PatternAggregator ────────────────────────────────────────────────────────


RUN_RATING_DAMPENING_WEIGHT: float = 0.3  # spec §4.3 "Run-Rating-Dämpfung"
CURRENT_ENRICHER_VERSION: str = ENRICHER_VERSION  # Bug G: filter on this


class PatternAggregator:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        enricher_version: str | None = None,
    ) -> None:
        """Args:
        session_factory: returns a SQLAlchemy session or session-context-manager.
        enricher_version: override the current version (tests use this to seed
                          stale-version decisions). Defaults to
                          services.enrichment.ENRICHER_VERSION.
        """
        self._session_factory = session_factory
        self._current_version = (
            enricher_version
            if enricher_version is not None
            else CURRENT_ENRICHER_VERSION
        )

    def run(self) -> int:
        """Run one aggregation cycle.

        Returns the number of patterns upserted. One SQL SELECT joins mem_decision
        with mem_pacing_run (bug I), filters to current enricher_version (bug G).
        Then a Python aggregation pass groups by (fingerprint, target_clip_id)
        (bug H — BPM bucketed). Then a per-fingerprint UPSERT (bug J).
        """
        decisions = self._fetch_decisions_with_run_rating()
        updates = self._aggregate(decisions)
        n = self._upsert_patterns(updates)
        logger.info(
            "PatternAggregator: upserted %d patterns from %d decisions",
            n,
            len(decisions),
        )
        return n

    # ── Private methods ─────────────────────────────────────────────────────

    def _fetch_decisions_with_run_rating(self) -> list[dict[str, Any]]:
        """Single JOIN-based fetch (bug I). Filters at_enricher_version (bug G)."""
        sql = text("""
            SELECT
                d.id                  AS decision_id,
                d.scene_id            AS scene_id,
                d.at_genre            AS at_genre,
                d.at_section_type     AS at_section_type,
                d.at_bpm              AS at_bpm,
                d.user_verdict        AS user_verdict,
                d.user_rating         AS user_rating,
                r.user_rating         AS run_rating,
                r.id                  AS run_id
            FROM mem_decision d
            JOIN mem_pacing_run r ON d.run_id = r.id
            WHERE d.at_enricher_version = :version
        """)
        session = self._session_factory()
        ownership = False
        try:
            if hasattr(session, "__enter__") and not hasattr(session, "execute"):
                session = session.__enter__()
                ownership = True
            rows = (
                session.execute(sql, {"version": self._current_version})
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]
        finally:
            try:
                if ownership:
                    session.__exit__(None, None, None)
                else:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
            except Exception as cleanup_exc:  # broad: cleanup must not crash caller
                # B-166: Cleanup-Errors loggen statt verschlucken (DB-lock-expired,
                # I/O-error etc. sind heimtueckisch wenn sie unsichtbar sind).
                logger.warning(
                    "PatternAggregator session cleanup error: %s", cleanup_exc,
                )

    @staticmethod
    def _aggregate(decisions: Iterable[Mapping[str, Any]]) -> list[PatternUpdate]:
        """Group decisions by (fingerprint, scene_id). For each group sum weighted
        accept/reject counts.

        Weighting rules (design §4.3):
          - user_verdict == "accept"  → weight 1.0, accept++
          - user_verdict == "reject"  → weight 1.0, reject++
          - user_verdict in None/other → fall back to run_rating dampening:
              run_rating >= 4 → weight 0.3, accept
              run_rating <= 2 → weight 0.3, reject
              otherwise → skip (no signal)
        """
        groups: dict[tuple[str, int], dict[str, Any]] = {}
        for d in decisions:
            fp = make_context_fingerprint(
                at_genre=d.get("at_genre"),
                at_section_type=d.get("at_section_type"),
                at_bpm=d.get("at_bpm"),
            )
            # Use a stable JSON string as dict key component (bug H: bucketed BPM)
            fp_key = json.dumps(fp, sort_keys=True)
            clip_id = int(d["scene_id"])
            key = (fp_key, clip_id)

            if key not in groups:
                groups[key] = {
                    "fingerprint": fp,
                    "target_clip_id": clip_id,
                    "accept": 0.0,
                    "reject": 0.0,
                    "sample": 0.0,
                }

            verdict = d.get("user_verdict")
            if verdict == "accept":
                groups[key]["accept"] += 1.0
                groups[key]["sample"] += 1.0
            elif verdict == "reject":
                groups[key]["reject"] += 1.0
                groups[key]["sample"] += 1.0
            else:
                run_rating = d.get("run_rating")
                if run_rating is None:
                    continue
                if run_rating >= 4:
                    groups[key]["accept"] += RUN_RATING_DAMPENING_WEIGHT
                    groups[key]["sample"] += RUN_RATING_DAMPENING_WEIGHT
                elif run_rating <= 2:
                    groups[key]["reject"] += RUN_RATING_DAMPENING_WEIGHT
                    groups[key]["sample"] += RUN_RATING_DAMPENING_WEIGHT
                # else: neutral run rating → no signal, skip

        return [
            PatternUpdate(
                fingerprint=g["fingerprint"],
                target_clip_id=g["target_clip_id"],
                accept_count=int(round(g["accept"])),
                reject_count=int(round(g["reject"])),
                sample_size=int(round(g["sample"])),
            )
            for g in groups.values()
            if g["sample"] > 0
        ]

    def _upsert_patterns(self, updates: Iterable[PatternUpdate]) -> int:
        """Upsert each pattern by fingerprint + target_clip_id (bug J: use DB lookup
        instead of loading all patterns into Python).

        SQLite JSON1 extension is used to match on the JSON columns.
        context_fingerprint is stored as JSON text via SQLAlchemy JSON type.
        target_ref has shape {"scene_id": <int>}.
        """
        session = self._session_factory()
        ownership = False
        try:
            if hasattr(session, "__enter__") and not hasattr(session, "execute"):
                session = session.__enter__()
                ownership = True

            now = datetime.now(timezone.utc)  # Bug L: NOT utcnow()
            upserted = 0

            for upd in updates:
                fp_json = json.dumps(upd.fingerprint, sort_keys=True)
                target_json = json.dumps(
                    {"scene_id": upd.target_clip_id}, sort_keys=True
                )
                confidence = wilson_lower_bound(upd.accept_count, upd.sample_size)

                # Lookup via SQL JSON extract, NOT Python iteration (bug J).
                existing = session.execute(
                    text("""
                        SELECT id FROM mem_learned_pattern
                        WHERE pattern_type = 'context_preference'
                          AND json_extract(context_fingerprint, '$.genre')        IS :genre
                          AND json_extract(context_fingerprint, '$.section_type') IS :section_type
                          AND json_extract(context_fingerprint, '$.bpm_bucket')   IS :bpm_bucket
                          AND json_extract(target_ref, '$.scene_id') = :scene_id
                        LIMIT 1
                    """),
                    {
                        "genre": upd.fingerprint["genre"],
                        "section_type": upd.fingerprint["section_type"],
                        "bpm_bucket": upd.fingerprint["bpm_bucket"],
                        "scene_id": upd.target_clip_id,
                    },
                ).fetchone()

                if existing is not None:
                    session.execute(
                        text("""
                            UPDATE mem_learned_pattern
                            SET stat_accept_count = :a,
                                stat_reject_count = :r,
                                stat_sample_size  = :s,
                                confidence        = :c,
                                last_updated      = :ts
                            WHERE id = :id
                        """),
                        {
                            "a": upd.accept_count,
                            "r": upd.reject_count,
                            "s": upd.sample_size,
                            "c": confidence,
                            "ts": now,
                            "id": int(existing[0]),
                        },
                    )
                else:
                    session.execute(
                        text("""
                            INSERT INTO mem_learned_pattern
                                (pattern_type, context_fingerprint, target_ref,
                                 stat_accept_count, stat_reject_count, stat_sample_size,
                                 confidence, last_updated)
                            VALUES
                                ('context_preference', :fp, :tr,
                                 :a, :r, :s, :c, :ts)
                        """),
                        {
                            "fp": fp_json,
                            "tr": target_json,
                            "a": upd.accept_count,
                            "r": upd.reject_count,
                            "s": upd.sample_size,
                            "c": confidence,
                            "ts": now,
                        },
                    )
                upserted += 1

            session.commit()
            return upserted
        finally:
            try:
                if ownership:
                    session.__exit__(None, None, None)
                else:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
            except Exception as cleanup_exc:  # broad: cleanup must not crash caller
                # B-166: Cleanup-Errors loggen statt verschlucken (DB-lock-expired,
                # I/O-error etc. sind heimtueckisch wenn sie unsichtbar sind).
                logger.warning(
                    "PatternAggregator session cleanup error: %s", cleanup_exc,
                )

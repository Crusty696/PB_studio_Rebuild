"""Brain V3 — FeedbackLogger (Plan-Doc 05) mit Credit-Assignment.

Ein Klick aktualisiert 6 Backoff-Levels (0..5) x bis zu 18 Achsen in EINER
Transaktion.

CREDIT-ASSIGNMENT (2026-07-27)
------------------------------
Bis dahin bekam **jede** der 17 Achsen bei **jedem** Klick exakt denselben
alpha/beta-Delta. Ergebnis in der echten ``weights.db``: alle 17 Achsen auf
Level 0 standen auf identischen Werten. ``Scorer.score`` bildet aber einen
GEWICHTETEN Mittelwert — sind alle Gewichte gleich, ist das ein arithmetisches
Mittel und die Kandidaten-Reihenfolge aendert sich durch Feedback NIE. Jeder
Klick verpuffte.

Jetzt gilt: der Aufrufer liefert ``axis_contributions`` — den Beitrag jeder
Achse an genau DIESER Entscheidung (Quelle: ``mem_decision.agent_rationale``,
Feld ``brain_v3_scores`` = die Sub-Scores des Scorers, ersatzweise das
Pacing-``contribs``-Dict ueber ``PACING_TERM_TO_AXES``). Daraus werden
relative Credits gebildet und alpha/beta pro Achse skaliert:

    credit_i     = |contribution_i| / max_j |contribution_j|      (in [0, 1])
    alpha_delta_i = alpha_delta * credit_i
    beta_delta_i  = beta_delta  * credit_i

Die staerkste Achse bekommt damit unveraendert den vollen Plan-Doc-Delta,
schwaechere anteilig weniger, Achsen ohne Beitrag GAR NICHTS (kein Write).
Bei negativen Ratings werden dieselben Achsen bestraft, die den Ausschlag
gegeben haben — Verantwortung und Konsequenz treffen dieselbe Achse.

Ohne ``axis_contributions`` bleibt der alte Uniform-Pfad erhalten (Legacy-
Kompatibilitaet), wird aber als ``credit_mode='uniform'`` markiert und
geloggt, damit sichtbar ist wo noch Signal verloren geht.

Roh-Klick-Log in feedback_events (state.db) ist Phase-4-Zuständigkeit
und nicht hier.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Literal, Mapping, Optional

from services.brain.cold_start import BRIDGE_AXES
from services.brain.weight_store import WeightStore

logger = logging.getLogger(__name__)

Rating = Literal["perfect", "fits", "not_quite", "no_match"]

# Plan-Doc 05 Tabelle
RATING_MAP: dict[str, tuple[float, float]] = {
    "perfect":   (2.0, 0.0),
    "fits":      (1.0, 0.0),
    "not_quite": (0.0, 1.0),
    "no_match":  (0.0, 2.0),
}

# Credits unterhalb dieser Schwelle zaehlen als "kein Beitrag".
MIN_CREDIT = 1e-6

# Prozessweiter Schreib-Lock. Modul-global, weil Caller (UI-Worker,
# FeedbackService, BrainV3Service) je eigene Store-/Logger-Instanzen bauen,
# aber alle in dieselbe weights.db schreiben. Hier — und nicht nur in
# BrainV3Service — weil seit dem Credit-Assignment auch Aufrufer ohne
# Service-Fassade schreiben (siehe submit_feedback).
_FEEDBACK_WRITE_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# Pacing-Term -> Bridge-Achsen
# ---------------------------------------------------------------------------
# HEURISTISCHE BRUECKE. Nur noetig, wenn eine Entscheidung OHNE Brain-V3-
# Reranker gefallen ist (dann fehlt ``brain_v3_scores`` im Rationale und es
# gibt nur die 15 Pacing-Terme aus services/pacing/scorer.py:583-598).
# Jede Zuordnung unten hat eine nachvollziehbare Entsprechung in
# services/brain/bridge_dimensions.py; Pacing-Terme ohne Bridge-Analogon
# (memory, freshness) sind bewusst NICHT gemappt und vergeben keinen Credit.
PACING_TERM_TO_AXES: dict[str, tuple[str, ...]] = {
    # energy_match(at_energy, clip.motion_score) == _compute_motion_match_weight
    "energy":     ("energy_weight", "energy_threshold", "motion_match_weight"),
    # groove_fit(at_groove_template, ...) -> Drum-Achsen
    "groove":     ("beat_weight", "kick_weight", "snare_weight", "hihat_weight"),
    # pacing_fit(spectral_flux, percussive_ratio, motion) -> Tempo/Onset
    "pacing":     ("pace_match_weight", "onset_weight", "onset_sensitivity"),
    # spectral_fit ~ Spektral-Zentroid == _compute_brightness_match_weight
    "spectral":   ("brightness_match_weight",),
    "mood_audio": ("mood_match_weight", "color_temp_match_weight"),
    "mood_video": ("mood_match_weight",),
    "key":        ("mood_match_weight",),
    "tension":    ("mood_match_weight", "color_temp_match_weight"),
    "style":      ("semantic_match_weight",),
    "role":       ("role_match_weight",),
    "genre":      ("semantic_match_weight",),
    "stem_class": ("semantic_match_weight",),
    # collision = Nachbarschafts-Vertraeglichkeit zweier Shots == Schnittguete
    "collision":  ("scene_cut_weight",),
    # NICHT gemappt (kein Bridge-Analogon): "memory", "freshness".
}


def axis_contributions_from_rationale(
    rationale: Mapping[str, object] | None,
) -> dict[str, float]:
    """Zieht die Achsen-Beitraege einer Entscheidung aus dem Rationale.

    Prioritaet:
      1. ``brain_v3_scores`` — die Sub-Scores (bridge_value * weight) des
         Brain-V3-Scorers. Exakt, kein Raten. Wird von
         services/pacing/pipeline.py in jedes Rationale geschrieben, sobald
         der Reranker lief (Produktpfad: services/pacing_service.py
         ``use_brain_v3=True``).
      2. ``contribs`` — die 15 Pacing-Terme, uebersetzt via
         PACING_TERM_TO_AXES. Heuristisch, aber immer noch achsenspezifisch.
      3. leer -> Aufrufer faellt auf den Uniform-Pfad zurueck.
    """
    if not isinstance(rationale, Mapping):
        return {}

    raw_scores = rationale.get("brain_v3_scores")
    if isinstance(raw_scores, Mapping) and raw_scores:
        direct = {
            str(axis): float(value)
            for axis, value in raw_scores.items()
            if str(axis) in BRIDGE_AXES and _is_finite_number(value)
        }
        if direct:
            return direct

    contribs = rationale.get("contribs")
    if not isinstance(contribs, Mapping) or not contribs:
        return {}
    mapped: dict[str, float] = {}
    for term, value in contribs.items():
        if not _is_finite_number(value):
            continue
        axes = PACING_TERM_TO_AXES.get(str(term))
        if not axes:
            continue
        share = abs(float(value)) / float(len(axes))
        for axis in axes:
            mapped[axis] = mapped.get(axis, 0.0) + share
    return mapped


def credit_weights(
    axis_contributions: Mapping[str, float] | None,
) -> dict[str, float]:
    """Normiert Achsen-Beitraege auf relative Credits in [0, 1].

    Der Betrag zaehlt: ein stark negativer Beitrag (z. B. Collision-Penalty)
    hat die Entscheidung genauso gepraegt wie ein stark positiver.
    Normiert wird auf das Maximum, damit die dominante Achse exakt den
    Plan-Doc-Delta behaelt und die Lernrate pro Klick nicht schrumpft.

    Achsen mit Credit ~ 0 fehlen im Ergebnis und lernen nicht mit.
    """
    if not axis_contributions:
        return {}
    values = {
        str(axis): abs(float(value))
        for axis, value in axis_contributions.items()
        if str(axis) in BRIDGE_AXES and _is_finite_number(value)
    }
    if not values:
        return {}
    largest = max(values.values())
    if largest <= MIN_CREDIT:
        return {}
    credits = {axis: value / largest for axis, value in values.items()}
    return {axis: c for axis, c in credits.items() if c > MIN_CREDIT}


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


class FeedbackLogger:
    """Atomic-Update auf weights.db pro Klick."""

    def __init__(self, weights: WeightStore):
        self.weights = weights

    def log_feedback(
        self,
        rating: str,
        context_keys_by_level: list[str],
        axis_contributions: Optional[Mapping[str, float]] = None,
    ) -> dict:
        """Atomarer Update aller betroffenen Buckets in einer Transaktion.

        Args:
            rating: 'perfect' | 'fits' | 'not_quite' | 'no_match'
            context_keys_by_level: Liste mit 6 Strings (Level 0..5),
                                   konstruiert via context_resolver.context_keys()
            axis_contributions: Beitrag pro Bridge-Achse an DIESER Entscheidung.
                None/leer -> Legacy-Uniform-Pfad (alle Achsen gleich, das
                Ranking kann sich dadurch nicht aendern).

        Returns:
            Diagnostik-Dict mit alpha_delta, beta_delta, n_buckets_updated,
            credit_mode ('weighted'|'uniform') und n_axes_credited.

        Raises:
            ValueError bei unbekanntem Rating.
        """
        if rating not in RATING_MAP:
            raise ValueError(f"Unbekanntes Rating: {rating!r}. Verfügbar: {list(RATING_MAP)}")
        if len(context_keys_by_level) != 6:
            raise ValueError(
                f"context_keys_by_level muss 6 Einträge haben (Level 0..5), "
                f"hatte {len(context_keys_by_level)}"
            )

        alpha_delta, beta_delta = RATING_MAP[rating]
        credits = credit_weights(axis_contributions)
        if credits:
            credit_mode = "weighted"
        else:
            credit_mode = "uniform"
            credits = {axis: 1.0 for axis in BRIDGE_AXES}
            if axis_contributions:
                logger.warning(
                    "FeedbackLogger: axis_contributions ohne verwertbaren "
                    "Beitrag (%d Eintraege) — Uniform-Fallback, dieser Klick "
                    "kann das Ranking nicht veraendern.",
                    len(axis_contributions),
                )
            else:
                logger.info(
                    "FeedbackLogger: kein Credit-Signal fuer rating=%s — "
                    "Uniform-Fallback (Ranking bleibt unveraendert).", rating,
                )

        updates: list[tuple[str, int, str, float, float]] = []
        for axis, credit in credits.items():
            a = alpha_delta * credit
            b = beta_delta * credit
            for level, key in enumerate(context_keys_by_level):
                updates.append((axis, level, key, a, b))

        with _FEEDBACK_WRITE_LOCK:
            n_updated = self.weights.update_many(updates)

        logger.info(
            "FeedbackLogger.log_feedback rating=%s mode=%s α=+%.1f β=+%.1f "
            "axes=%d → %d buckets",
            rating, credit_mode, alpha_delta, beta_delta, len(credits), n_updated,
        )
        return {
            "rating": rating,
            "alpha_delta": alpha_delta,
            "beta_delta": beta_delta,
            "n_buckets_updated": n_updated,
            "credit_mode": credit_mode,
            "n_axes_credited": len(credits),
            "axis_credits": dict(credits),
        }


def submit_feedback(
    rating: str,
    context: object = None,
    axis_contributions: Optional[Mapping[str, float]] = None,
    weight_store: Optional[WeightStore] = None,
) -> dict:
    """Ein Feedback-Klick MIT Credit-Assignment, ohne Service-Fassade.

    Existiert, weil ``BrainV3Service.feedback()`` die Achsen-Beitraege
    (noch) nicht durchreicht — sie kennt nur ``rating`` + ``CutContext``.
    Aufrufer, die die Beitraege haben (FeedbackService, Timeline-Hotkeys),
    schreiben deshalb direkt hierueber. Der Schreibpfad ist derselbe
    ``FeedbackLogger`` und derselbe prozessweite Lock.

    Args:
        rating: 'perfect' | 'fits' | 'not_quite' | 'no_match'
        context: ``CutContext`` oder None (None -> neutraler Default).
        axis_contributions: Beitrag pro Bridge-Achse an dieser Entscheidung.
        weight_store: optionaler, bereits offener Store (Tests). Sonst wird
            pro Aufruf ein frischer geoeffnet und wieder geschlossen — noetig,
            weil die sqlite3-Connection thread-local ist.

    Returns:
        Diagnostik-Dict von ``FeedbackLogger.log_feedback``.
    """
    from services.brain.context_resolver import CutContext, context_keys

    ctx = context if context is not None else CutContext()
    keys = context_keys(ctx)

    owned = weight_store is None
    store = weight_store
    if store is None:
        from services.brain.storage.brain_store import BrainStore

        store = WeightStore(BrainStore().weights_path)
    try:
        return FeedbackLogger(store).log_feedback(
            rating, keys, axis_contributions=axis_contributions,
        )
    finally:
        if owned:
            try:
                store.close()
            except Exception as exc:  # Close-Fehler darf Feedback nicht killen
                logger.warning("submit_feedback: WeightStore.close failed: %s", exc)


__all__ = [
    "FeedbackLogger",
    "RATING_MAP",
    "PACING_TERM_TO_AXES",
    "axis_contributions_from_rationale",
    "credit_weights",
    "submit_feedback",
]

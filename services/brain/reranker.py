"""Brain V3 — Reranker (Phase 4, Plan-Doc 06 Z.317-323).

Eingriff in `services.pacing.pipeline.PacingPipeline.select_best()` Stage 4:
- Input: `scored`-Liste aus Pacing-Pipeline (passed_stage2 == True)
- Brain-V3-Reranker bewertet jeden Kandidaten ueber 17 Achsen x 6 Levels
- Output: re-sortierte Liste + `brain_v3_scores` pro Kandidat

Stages 1-3 (Hard-Rules, Variations-Budget, Collision-Check) bleiben
unangetastet — der Reranker ersetzt nur die Stage-4-Sortierung.

Blend mit Original-Soft-Score:
    final = brain_score * brain_weight + pacing_soft_score * (1 - brain_weight)
brain_weight = 1.0 (default) → reine Brain-V3-Sortierung
brain_weight = 0.0 → kein Reranking (aequivalent zu disabled)

B-707: Der Default 1.0 bleibt der explizite API-Vertrag dieser Klasse, ist
aber NICHT das, was im Produkt laeuft — `services/pacing/pipeline.py` reicht
`DEFAULT_BRAIN_V3_WEIGHT` (bzw. das Setting `pacing.brain_v3_weight`) durch,
damit Pacing- und Brain-Score gemeinsam wirken.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from services.brain.bridge_dimensions import BridgeDimensions, ClipCandidate
from services.brain.context_mapping import (
    ContextMappingConfig,
    build_cut_context,
    map_mood,
)
from services.brain.context_resolver import (
    CutContext,
    quantize_tertile,
)
from services.brain.scorer import Scorer
from services.brain.weight_store import WeightStore

logger = logging.getLogger(__name__)


# B-707 Befund 2: Bridge-Achsen, fuer die es in der Pacing-Pipeline
# STRUKTURELL kein pro-Clip-Signal gibt.
#
# - brightness/color_temp: es existiert nirgends eine per-Scene-Bild-Statistik.
#   `scenes` hat kein brightness/saturation/color_temp (database/models.py:
#   250-282); die einzige `brightness`-Spalte im Schema haengt an
#   `timeline_entries` und ist ein EDIT-Parameter, keine Analyse.
# - scene_cut_weight: liest ausschliesslich ctx.raw_audio_features["on_beat"] —
#   Audio-Seite, per Definition fuer alle Kandidaten eines Cuts gleich.
# - die 10 Audio-Achsen: dito, sie beschreiben den Cut, nicht den Clip.
#
# Diese Achsen sind damit KONSTANT ueber die Kandidaten eines Cuts. Konstante
# Summanden verschieben den Score nur, sie aendern die Reihenfolge nicht — sie
# "verwaessern" das Ranking also nicht. Sie duerfen aber auch nicht als
# Bewertung durchgehen: `RerankedCandidate.no_signal_axes` markiert sie
# explizit, damit UI/Audit sie nicht als bewertete Achse liest.
#
# (Die Achsen ganz aus dem gewichteten Mittel zu nehmen wuerde
# `services/brain/scorer.py` bzw. `bridge_dimensions.py` erfordern — beide
# liegen ausserhalb des fuer diese Aufgabe freigegebenen Datei-Sets.)
STRUCTURAL_NO_SIGNAL_AXES: frozenset[str] = frozenset({
    "beat_weight",
    "onset_weight",
    "kick_weight",
    "snare_weight",
    "hihat_weight",
    "energy_weight",
    "energy_threshold",
    "onset_sensitivity",
    "scene_cut_weight",
    "brightness_match_weight",
    "color_temp_match_weight",
})


@dataclass
class RerankedCandidate:
    """Ergebnis pro Kandidat: original + brain-final + sub-scores."""
    clip_id: int
    original_soft_score: float
    brain_score: float
    final_score: float
    brain_v3_scores: dict[str, float]
    # B-707: Achsen ohne clip-individuelles Signal fuer DIESEN Kandidaten.
    # Enthaelt die strukturell toten Achsen plus die, deren Quelle bei diesem
    # Clip fehlt (kein Embedding, keine Motion-Kurve, kein Mood-Label).
    no_signal_axes: frozenset[str] = field(default_factory=frozenset)


class BrainV3Reranker:
    """Stateless-Reranker. Eine Instanz pro Pacing-Run (oder Singleton)."""

    def __init__(
        self,
        weight_store: WeightStore,
        bridge: Optional[BridgeDimensions] = None,
        mapping_config: Optional[ContextMappingConfig] = None,
        brain_weight: float = 1.0,
        min_confidence: float = 0.0,
    ):
        self._weights = weight_store
        self._bridge = bridge or BridgeDimensions()
        self._scorer = Scorer(self._bridge, self._weights)
        self._mapping = mapping_config or ContextMappingConfig()
        if not 0.0 <= brain_weight <= 1.0:
            raise ValueError(f"brain_weight muss in [0,1] sein, war {brain_weight}")
        self._brain_weight = float(brain_weight)
        self._min_confidence = float(min_confidence)

    # ------------------------------------------------------------------
    # Hauptmethode: bekommt das Pacing-Stage-4-Output, gibt re-sortiert zurueck
    # ------------------------------------------------------------------
    def rerank(
        self,
        scored: Sequence[tuple[Any, float, dict[str, float]]],
        ctx: Any,
        recent_clip_ids: Optional[Sequence[int]] = None,
    ) -> list[RerankedCandidate]:
        """Rerank stage-4 candidates.

        Args:
            scored: Liste von (ClipFeatures-aehnlich, soft_score, contribs)
                aus PacingPipeline. ClipFeatures muss `clip_id`,
                `motion_score`, optional `embedding` exposen.
            ctx: AudioContext aus PacingPipeline (with `at_section_type`,
                `at_mood_audio`, `at_bpm`, ...).
            recent_clip_ids: optionale Liste der letzten gewaehlten Clips
                (fuer pace_class derive_pace_class).

        Returns:
            Liste `RerankedCandidate`, sortiert absteigend nach `final_score`.
        """
        cut_context = self._build_cut_context_from_audio(ctx, recent_clip_ids)
        # B-707: ohne Audio-Mood-Prototyp kann `semantic_match_weight` nicht
        # bewerten (BridgeDimensions gibt dann fuer alle 0.5 zurueck).
        ctx_missing_axes: frozenset[str] = frozenset()
        if "mood_prototype" not in (cut_context.raw_audio_features or {}):
            ctx_missing_axes = frozenset({"semantic_match_weight"})
        results: list[RerankedCandidate] = []
        for clip_feat, soft_score, contribs in scored:
            candidate, no_signal_axes = self._adapt_clip(clip_feat, contribs)
            no_signal_axes = no_signal_axes | ctx_missing_axes
            scored_brain = self._scorer.score(candidate, cut_context)
            blended = (
                self._brain_weight * scored_brain.final_score
                + (1.0 - self._brain_weight) * float(soft_score or 0.0)
            )
            if blended < self._min_confidence:
                continue
            results.append(RerankedCandidate(
                clip_id=int(getattr(clip_feat, "clip_id", -1)),
                original_soft_score=float(soft_score or 0.0),
                brain_score=float(scored_brain.final_score),
                final_score=blended,
                brain_v3_scores=dict(scored_brain.brain_v3_scores),
                no_signal_axes=no_signal_axes,
            ))
        results.sort(key=lambda r: r.final_score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_cut_context_from_audio(
        self,
        ctx: Any,
        recent_clip_ids: Optional[Sequence[int]],
    ) -> CutContext:
        recent_cut_count = len(recent_clip_ids) if recent_clip_ids else 0
        raw_section = (getattr(ctx, "at_section_type", None) or "verse")
        raw_mood = (getattr(ctx, "at_mood_audio", None) or "neutral")
        raw_bpm = getattr(ctx, "at_bpm", None)
        raw_energy = getattr(ctx, "at_energy", None)
        # Energy-Quantize: tertile auf [0..1]
        if raw_energy is None:
            energy_class = "medium"
        else:
            energy_class = quantize_tertile(float(raw_energy), p33=0.33, p66=0.66)
        # Audio-Subtrack-Position: ohne Subtrack-Info → middle
        subpos = "middle"
        # Motion-Klasse: kommt vom Reranker erst beim Per-Candidate-Scoring;
        # fuer den Backoff-Key aber nur grob: median Motion = "medium".
        motion_class = "medium"
        raw_features: dict[str, Any] = {
            "energy": float(raw_energy) if raw_energy is not None else 0.5,
            "bpm": float(raw_bpm) if raw_bpm else 120.0,
            "section_type": raw_section,
            "mood": raw_mood,
            "harmonic_tension": float(getattr(ctx, "at_harmonic_tension", None) or 0.0),
        }
        # B-707 Befund 2: `_compute_semantic_match_weight` braucht einen
        # "mood_prototype" im selben Embedding-Raum wie das Clip-Embedding.
        # Genau das ist `AudioContext.at_audio_mood_vec` (SigLIP-Raum,
        # services/pacing/audio_mood_vector.py). Ohne ihn lieferte die Achse
        # fuer JEDEN Kandidaten 0.5. Fehlt der Vektor (keine Stems / keine
        # Shot-Centroids), bleibt der Key weg -> Achse ohne Signal.
        mood_vec = getattr(ctx, "at_audio_mood_vec", None)
        if mood_vec is not None:
            raw_features["mood_prototype"] = mood_vec
        return build_cut_context(
            raw_section=raw_section,
            raw_mood=raw_mood,
            raw_subtrack_position=subpos,
            raw_energy_level=energy_class,
            raw_motion_class=motion_class,
            cfg=self._mapping,
            recent_cut_count=recent_cut_count,
            audio_bpm=raw_bpm,
            raw_audio_features=raw_features,
        )

    def _adapt_clip(
        self, clip_feat: Any, contribs: dict[str, float]
    ) -> tuple[ClipCandidate, frozenset[str]]:
        """Adapter PacingPipeline.ClipFeatures → brain_v3.ClipCandidate.

        B-707 Befund 2: die frueher hier gelesenen `contribs`-Keys
        (`brightness`, `saturation`, `color_temp`, `duration_s`, `mood_tags`,
        `style_tags`) existierten NIE. `services/pacing/scorer.py` liefert in
        `contribs` die GEWICHTETEN Term-Beitraege
        (role/style/mood_video/mood_audio/genre/key/tension/energy/spectral/
        groove/pacing/memory/stem_class/collision/freshness) — jeder `.get()`
        lief also in seinen Default und 16 der 17 Bridge-Achsen waren pro Cut
        konstant. Die Quelle sind die `ClipFeatures` selbst.

        Returns:
            (candidate, no_signal_axes) — die zweite Komponente listet die
            Achsen, die fuer DIESEN Clip kein eigenes Signal haben.
        """
        no_signal: set[str] = set(STRUCTURAL_NO_SIGNAL_AXES)

        emb = getattr(clip_feat, "embedding", None)
        emb_arr: Optional[np.ndarray] = None
        if emb is not None:
            try:
                emb_arr = np.asarray(emb, dtype=np.float32)
            except Exception:
                emb_arr = None
        if emb_arr is None or emb_arr.size == 0:
            emb_arr = None
            no_signal.add("semantic_match_weight")

        # Dauer: ClipFeatures hat kein Dauer-Feld, aber `motion_curve` ist die
        # 100ms-Kurve AB dem Abspiel-Offset (services/pacing/bridge_mapping.py
        # build_motion_curve) — ihre Laenge ist die real verbleibende
        # Clip-Laufzeit ab dem Cut-Punkt. Genau die Groesse, die
        # min/max_clip_length und pace_match_weight meinen.
        duration_s = self._duration_from_motion_curve(clip_feat)
        if duration_s is None:
            duration_s = 1.0  # ClipCandidate braucht einen float
            no_signal.update(
                {"min_clip_length", "max_clip_length", "pace_match_weight"}
            )

        motion_raw = getattr(clip_feat, "motion_score", None)
        if motion_raw is None:
            no_signal.add("motion_match_weight")
            motion = 0.5
        else:
            motion = float(motion_raw)

        # Mood: `mood_refined` ist das per-Clip-Label aus dem struct-Enrichment.
        # `_compute_mood_match_weight` testet `ctx.audio_mood in c.mood_tags`,
        # und `ctx.audio_mood` liegt im 3er-Vokabular dark/neutral/uplifting
        # (context_resolver.VALID_MOOD). Deshalb Rohlabel UND gemapptes Label
        # in die Tags — ohne Mapping wuerde "euphoric" nie treffen.
        # "unknown"/leer -> keine Tags, denn ein erfundenes "neutral" waere
        # eine Bewertung, die es nicht gibt.
        mood_raw = getattr(clip_feat, "mood_refined", None)
        mood_tags: list[str] = []
        if mood_raw and str(mood_raw).strip().lower() not in ("", "unknown"):
            raw = str(mood_raw).strip().lower()
            mood_tags.append(raw)
            mapped = map_mood(raw, self._mapping)
            if mapped != raw:
                mood_tags.append(mapped)
        else:
            no_signal.add("mood_match_weight")

        # style_tags: aktuell wertet KEINE Bridge-Achse sie aus. Trotzdem
        # ehrlich befuellen (role + Style-Bucket sind echte per-Clip-Labels),
        # statt eine leere Liste zu uebergeben.
        style_tags: list[str] = []
        role = getattr(clip_feat, "role", None)
        if role and str(role).strip().lower() not in ("", "unknown"):
            style_tags.append(f"role:{str(role).strip().lower()}")
        bucket = getattr(clip_feat, "style_bucket_id", None)
        if bucket:  # 0 ist das Sentinel fuer "unbekannter Bucket"
            style_tags.append(f"style_bucket:{int(bucket)}")

        candidate = ClipCandidate(
            clip_id=str(getattr(clip_feat, "clip_id", "?")),
            duration_s=float(duration_s),
            motion_score=motion,
            # brightness/saturation/color_temp: es gibt keine Bildstatistik pro
            # Scene im Schema -> Defaults bleiben stehen, die zugehoerigen
            # Achsen sind ueber STRUCTURAL_NO_SIGNAL_AXES als "kein Signal"
            # markiert und werden nicht als Bewertung ausgegeben.
            embedding=emb_arr,
            mood_tags=mood_tags,
            style_tags=style_tags,
        )
        return candidate, frozenset(no_signal)

    @staticmethod
    def _duration_from_motion_curve(clip_feat: Any) -> float | None:
        """Rest-Laufzeit des Clips ab dem Cut-Punkt in Sekunden, oder None."""
        curve = getattr(clip_feat, "motion_curve", None)
        if curve is None:
            return None
        try:
            n = len(curve)
        except TypeError:
            return None
        if n <= 0:
            return None
        try:
            from services.pacing.audio_video_curves import DEFAULT_BIN_MS
        except ImportError:
            return None
        return float(n) * (float(DEFAULT_BIN_MS) / 1000.0)

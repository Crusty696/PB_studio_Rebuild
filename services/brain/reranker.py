"""Brain V3 — Reranker (Phase 4, Plan-Doc 06 Z.317-323).

Eingriff in `services.pacing.pipeline.PacingPipeline.select_best()` Stage 4:
- Input: `scored`-Liste aus Pacing-Pipeline (passed_stage2 == True)
- Brain-V3-Reranker bewertet jeden Kandidaten ueber 18 Achsen x 6 Levels
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
from dataclasses import dataclass, field, replace
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
    quantize_quartile,
    quantize_tertile,
)
from services.brain.scorer import Scorer
from services.brain.weight_store import WeightStore

logger = logging.getLogger(__name__)


# B-736: Bridge-Achsen, die AUSSCHLIESSLICH die Musikstelle beschreiben.
#
# Sie sind fuer alle Kandidaten EINES Cuts gleich — das ist keine Luecke,
# sondern ihre Definition (`bridge_dimensions._compute_beat_weight` & Co.
# lesen nur `ctx.raw_audio_features`, nie den Clip). Innerhalb eines Cuts
# aendern sie die Rangfolge deshalb nicht; ueber CUTS HINWEG unterscheiden
# sie sehr wohl (Drop vs. Breakdown) und sie gehen ins Credit-Assignment der
# Lernschleife ein.
#
# Bis B-736 liefen sie mangels Quelle auf dem konstanten 0.5-Fallback aus
# `BridgeDimensions.compute`. Jetzt speist `_build_cut_context_from_audio`
# sie aus `beatgrids` + `av_pacing_data` am Cut-Zeitpunkt. Der Name der
# Konstante bleibt fuer die Kompatibilitaet mit B-707 erhalten, sie ist aber
# nur noch die OBERGRENZE: `_cut_no_signal_axes` streicht jede Achse, fuer
# die der AudioContext einen echten Messwert liefert.
CUT_LEVEL_AXES: frozenset[str] = frozenset({
    "beat_weight",
    "onset_weight",
    "kick_weight",
    "snare_weight",
    "hihat_weight",
    "energy_weight",
    "energy_threshold",
    "onset_sensitivity",
    "scene_cut_weight",
})

# Achsen, die Clip UND Musikstelle gegeneinander bewerten. Sie brauchen auf
# BEIDEN Seiten ein Signal; fehlt eines, sind sie ohne Aussage.
#   brightness_match_weight  = 1 - |clip.brightness - spectral_centroid_norm|
#   color_temp_match_weight  = 1 - |clip.color_temp - mood_target| / 2
# Bis B-734 fehlte die Clip-Seite komplett (keine per-Scene-Bildstatistik im
# Schema); seit Migration f2a3b4c5d6e7 liefert `struct_clip_tags`
# avg_brightness/avg_saturation/color_temp aus echten Keyframe-Messungen.
COUPLED_VISUAL_AXES: frozenset[str] = frozenset({
    "brightness_match_weight",
    "color_temp_match_weight",
})

# Mapping Bridge-Achse -> Key in `raw_audio_features` -> AudioContext-Feld.
# Ein `None`-Feld heisst "Quelle fehlt fuer diesen Track" -> Key wird NICHT
# gesetzt -> BridgeDimensions faellt auf 0.5 zurueck UND die Achse wird als
# `no_signal` gemeldet. Ohne diese Meldung waere eine Nicht-Messung von einer
# Messung, die zufaellig 0.5 ergibt, nicht unterscheidbar.
_AUDIO_AXIS_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("beat_weight", "beat_strength", "at_beat_strength"),
    ("onset_weight", "onset_strength", "at_onset_strength"),
    ("kick_weight", "kick_present", "at_kick_strength"),
    ("snare_weight", "snare_present", "at_snare_strength"),
    ("hihat_weight", "hihat_present", "at_hihat_strength"),
    ("onset_sensitivity", "onset_sensitivity", "at_onset_density"),
    ("scene_cut_weight", "on_beat", "at_on_beat"),
)


def _opt_metric(clip_feat: Any, name: str) -> Optional[float]:
    """Gemessene Bildmetrik vom ClipFeatures-Objekt, oder None.

    Ein fehlendes Attribut (aelteres ClipFeatures-Stub in Tests) und ein
    NULL-Wert aus der DB sind hier bewusst dasselbe: kein Messwert.
    """
    raw = getattr(clip_feat, name, None)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return None if val != val else val  # NaN -> kein Messwert


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
        # B-893: Feedback rekonstruiert den gespeicherten Cut-Kontext aus
        # `mem_decision.at_bpm`; eine spaetere recent-cuts-Historie existiert
        # dort nicht mehr. Der Produkt-Default muss deshalb dieselbe stabile
        # Pace-Quelle verwenden, sonst schreibt Lernen in andere Buckets als
        # der Reranker liest. Explizit injizierte Config bleibt unveraendert.
        self._mapping = mapping_config or ContextMappingConfig(pace_source="audio_bpm")
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
        # B-736: welche Achsen fuer DIESEN Cut ohne Audio-Signal bleiben —
        # einmal pro Cut, nicht pro Kandidat.
        ctx_missing_axes = self._cut_no_signal_axes(cut_context)
        results: list[RerankedCandidate] = []
        for clip_feat, soft_score, contribs in scored:
            candidate, no_signal_axes = self._adapt_clip(clip_feat, contribs)
            no_signal_axes = no_signal_axes | ctx_missing_axes
            candidate_context = self._context_for_candidate(cut_context, clip_feat)
            scored_brain = self._scorer.score(candidate, candidate_context)
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
        # B-888: gleiche Scores duerfen nicht von DB-/Input-Reihenfolge
        # abhaengen. Kleinere persistente Clip-ID gewinnt den Tie-Break.
        results.sort(key=lambda r: (-r.final_score, r.clip_id))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _context_for_candidate(
        cut_context: CutContext,
        clip_feat: Any,
    ) -> CutContext:
        """Setzt denselben Motion-Bucket, den Feedback spaeter rekonstruiert."""
        raw_motion = getattr(clip_feat, "motion_score", None)
        motion_class = (
            quantize_quartile(float(raw_motion), 0.25, 0.5, 0.75)
            if raw_motion is not None
            else "medium"
        )
        return replace(cut_context, video_motion_class=motion_class)

    @staticmethod
    def _cut_no_signal_axes(cut_context: CutContext) -> frozenset[str]:
        """Achsen, die fuer diesen Cut mangels Audio-Quelle nichts aussagen.

        Eine Achse gilt als "hat Signal", sobald ihr Feature-Key wirklich in
        `raw_audio_features` steht. Fehlt er, laeuft `BridgeDimensions` auf
        seinen 0.5-Fallback — dann muss das auch so gemeldet werden, statt
        0.5 als Bewertung durchgehen zu lassen.

        `energy_weight`/`energy_threshold` lesen "energy", das seit jeher
        gesetzt ist; sie bleiben aber Cut-Level (fuer alle Kandidaten gleich).
        """
        feats = cut_context.raw_audio_features or {}
        missing: set[str] = set()
        for axis, feature_key, _attr in _AUDIO_AXIS_SOURCES:
            if feature_key not in feats:
                missing.add(axis)
        if "energy" not in feats:
            missing.update({"energy_weight", "energy_threshold"})
        # B-707: ohne Audio-Mood-Prototyp kann `semantic_match_weight` nicht
        # bewerten (BridgeDimensions gibt dann fuer alle 0.5 zurueck).
        if "mood_prototype" not in feats:
            missing.add("semantic_match_weight")
        # Audio-Seite von brightness_match_weight. Die Clip-Seite prueft
        # `_adapt_clip` separat — beide muessen da sein.
        if "spectral_centroid_norm" not in feats:
            missing.add("brightness_match_weight")
        return frozenset(missing)

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
        # B-893: Basis-Context bleibt neutral; `rerank()` ersetzt Motion vor
        # jedem Scorer-Aufruf durch das Quartil des jeweiligen Kandidaten.
        motion_class = "medium"
        raw_features: dict[str, Any] = {
            "bpm": float(raw_bpm) if raw_bpm else 120.0,
            "section_type": raw_section,
            "mood": raw_mood,
            "harmonic_tension": float(getattr(ctx, "at_harmonic_tension", None) or 0.0),
        }
        # B-736: "energy" nur setzen, wenn wirklich gemessen. Der frueher hier
        # eingesetzte 0.5-Default war von einer echten Messung 0.5 nicht zu
        # unterscheiden. Numerisch aendert das nichts (BridgeDimensions liest
        # `.get("energy", 0.5)`), aber `_cut_no_signal_axes` kann die Achsen
        # jetzt ehrlich als "kein Signal" melden.
        if raw_energy is not None:
            raw_features["energy"] = float(raw_energy)
        # B-707 Befund 2: `_compute_semantic_match_weight` braucht einen
        # "mood_prototype" im selben Embedding-Raum wie das Clip-Embedding.
        # Genau das ist `AudioContext.at_audio_mood_vec` (SigLIP-Raum,
        # services/pacing/audio_mood_vector.py). Ohne ihn lieferte die Achse
        # fuer JEDEN Kandidaten 0.5. Fehlt der Vektor (keine Stems / keine
        # Shot-Centroids), bleibt der Key weg -> Achse ohne Signal.
        mood_vec = getattr(ctx, "at_audio_mood_vec", None)
        if mood_vec is not None:
            raw_features["mood_prototype"] = mood_vec

        # B-736: die neun Achsen, die "passt dieser Clip zur Musik AN DIESER
        # STELLE" beantworten sollen, liefen auf dem konstanten 0.5-Fallback,
        # weil hier nur energy/bpm/section/mood/tension gesetzt wurden. Die
        # Quellen existieren (beatgrids: Beats/Downbeats/Kick/Snare/Hihat/
        # Onset-Huellkurve; av_pacing_data: spectral_centroid) und liegen im
        # AudioContext bereits AM CUT-ZEITPUNKT vor —
        # services/pacing/bridge_mapping.py fuellt sie einmal pro Cut ueber
        # AVPacingCurves.rhythm_at.
        #
        # Hier wird nur umgeschrieben, nichts gerechnet: diese Methode laeuft
        # einmal pro rerank()-Aufruf (= pro Cut), das Ergebnis wird ueber alle
        # Kandidaten wiederverwendet. Keine Query, keine Kurvenauswertung pro
        # Kandidat — das Latenzbudget aus
        # tests/integration/test_pacing_performance.py bleibt unberuehrt.
        for _axis, feature_key, ctx_attr in _AUDIO_AXIS_SOURCES:
            value = getattr(ctx, ctx_attr, None)
            if value is not None:
                raw_features[feature_key] = float(value)

        # spectral_centroid_norm speist brightness_match_weight (Clip-Helligkeit
        # gegen spektralen Schwerpunkt der Musik) — die Audio-Seite einer
        # gekoppelten Achse, deshalb nicht in _AUDIO_AXIS_SOURCES.
        centroid = getattr(ctx, "at_spectral_centroid_norm", None)
        if centroid is not None:
            raw_features["spectral_centroid_norm"] = float(centroid)

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
        # B-736: hier werden AUSSCHLIESSLICH clip-seitige Luecken gesammelt.
        # Ueber die Cut-Achsen entscheidet `_cut_no_signal_axes` anhand des
        # AudioContext; `rerank` vereinigt beide Mengen.
        #
        # Vorher stand hier `set(STRUCTURAL_NO_SIGNAL_AXES)` — eine feste
        # Liste. Da `rerank` die beiden Mengen ver-ODER-t, konnte eine Achse
        # damit NIE wieder aus dem no-signal-Status herauskommen, egal wie
        # gut die Datenlage war.
        no_signal: set[str] = set()

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

        # style_tags bleiben Diagnostik; D-080 führt Rolle zusätzlich als
        # explizites Candidate-Feld für die lernbare Brain-Bridge-Achse.
        style_tags: list[str] = []
        role = getattr(clip_feat, "role", None)
        normalized_role: Optional[str] = None
        if role and str(role).strip().lower() not in ("", "unknown"):
            normalized_role = str(role).strip().lower()
            style_tags.append(f"role:{normalized_role}")
        else:
            no_signal.add("role_match_weight")
        bucket = getattr(clip_feat, "style_bucket_id", None)
        if bucket:  # 0 ist das Sentinel fuer "unbekannter Bucket"
            style_tags.append(f"style_bucket:{int(bucket)}")

        # B-734: Bildmetriken pro Szene. Sie kommen aus `struct_clip_tags`
        # (Migration f2a3b4c5d6e7, gemessen von
        # services/enrichment/visual_metrics.py auf den Keyframe-JPEGs) und
        # liegen seit services/pacing/bridge_mapping.py auf den ClipFeatures.
        #
        # `None` heisst "nie gemessen" (Szene vor der Migration angereichert,
        # oder Keyframes fehlten). Dann bleibt der neutrale ClipCandidate-
        # Default stehen UND die Achse wird als `no_signal` gemeldet — ein
        # stilles 0.5 wuerde als echte Bewertung gelesen und war genau der
        # Grund, warum diese Achsen jahrelang unbemerkt wirkungslos waren.
        brightness = _opt_metric(clip_feat, "brightness")
        saturation = _opt_metric(clip_feat, "saturation")
        color_temp = _opt_metric(clip_feat, "color_temp")
        if brightness is None:
            no_signal.add("brightness_match_weight")
        if color_temp is None:
            no_signal.add("color_temp_match_weight")

        kwargs: dict[str, Any] = {}
        if brightness is not None:
            kwargs["brightness"] = brightness
        if saturation is not None:
            # Aktuell wertet KEINE der 18 Achsen die Saettigung aus. Sie wird
            # trotzdem durchgereicht (echter Messwert, kein Default) — damit
            # ein spaeterer Term sie vorfindet, statt still 0.5 zu lesen.
            kwargs["saturation"] = saturation
        if color_temp is not None:
            kwargs["color_temp"] = color_temp

        candidate = ClipCandidate(
            clip_id=str(getattr(clip_feat, "clip_id", "?")),
            duration_s=float(duration_s),
            motion_score=motion,
            embedding=emb_arr,
            mood_tags=mood_tags,
            style_tags=style_tags,
            role=normalized_role,
            role_confidence=getattr(clip_feat, "role_confidence", None),
            **kwargs,
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

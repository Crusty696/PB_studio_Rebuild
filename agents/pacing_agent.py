"""
Pacing Agent — PhD-Level DJ-Pacing-KI für beat-synchrone Video-Timelines.

Spezialisiert auf:
- Automatische Cut-Rate-Berechnung basierend auf Stems (Drums, Bass, Vocals, Other)
- Drop-Detektion via Bass-Stem RMS-Analyse
- Makro-Strukturerkennung über mehrstündige DJ-Sets
- Multimodales Video-Matching (RAFT Motion + SigLIP Semantik)
- Vocal-Aware Pacing (weniger Schnitte bei Vocals)

AXIOM: Audio ist der Master, Video ist der Sklave.
AXIOM: Jeder Schnitt fällt AUSNAHMSLOS auf einen Beat-Timestamp.
AXIOM: Nutze STEMS, nicht die Stereo-Summe.

Siehe docs/pacing_logic_phd.md für die vollständige Spezifikation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.base_agent import BaseAgent, extract_id_from_text

logger = logging.getLogger(__name__)

# Keywords die auf Pacing-Anfragen hindeuten
PACING_KEYWORDS = [
    "pacing", "pace", "schnittrate", "cut rate", "cut-rate",
    "auto edit", "auto_edit", "auto-edit", "autoedit", "automatisch schneiden",
    "beat sync", "beat-sync", "beatsync", "beat", "zum beat", "beat schnitt",
    "schneide", "schnitt",
    "drop", "breakdown", "buildup", "build-up",
    "energy", "energie", "reaktivität", "reactivity",
    "dj set", "dj-set", "djset", "mix schneiden",
    "cuts pro bar", "cuts per bar", "schnitte pro takt",
    "vibe", "stimmung", "mood",
    "timeline generieren", "timeline erstellen",
    "motion match", "motion-match",
    "drum cuts", "drum-cuts", "kick-basiert",
    "bass drop", "bass-drop",
    "vocal aware", "vocal-aware",
    "kurve", "curve", "density curve", "pacing curve",
    "anker", "anchor",
    "phase 3", "phase3", "advanced pacing",
    "schnittlänge", "schnittdichte",
]

# PhD-Level System Prompt — kondensierte operative Anweisungen
PACING_SYSTEM_PROMPT = """\
DU BIST DIE PACING-KI VON PB STUDIO.

DEINE AUFGABE: Generiere beat-synchrone Video-Timelines für DJ-Sets (1-4h).
Du bist ein PhD-Level Algorithmus-Designer für musiksynchrone Videoproduktion.

AXIOM: Audio = Master. Video = Sklave. Timeline-Länge = Audio-Dauer.
AXIOM: JEDER Schnitt fällt auf einen Beat-Timestamp. Keine Ausnahmen.
AXIOM: Nutze STEMS (Drums, Bass, Vocals, Other), NICHT die Stereo-Summe.

STEM-SEMANTIK:
  Drums → Cut-Trigger (Onset-Detection auf Kick/Snare)
  Bass  → Drop-Detektor (RMS-Sprung > 0.5 = Drop → maximale Cuts)
  Vocals → Ruhiger schneiden (vocal_active → S_eff × 2)
  Other → Mood-Indikator (hoher Other-RMS bei Breakdowns)

CUT-RATE BERECHNUNG:
  S_eff = f(S_base, Energy, Reactivity, Breakdown, Curve, Motion)

  Hohe Energie (>0.7):  S_eff ÷ speed_boost (1.0 + (E-0.7)×3×R)
  Niedrige Energie (<0.3): halve/force16/none je nach Setting
  Motion-Korrektur: combined = E×0.6 + M×0.4 → Skalierung

  Minimum: 1 Beat zwischen Schnitten
  Default: 4 Beats (= 1 Bar, Downbeat-Schnitte)

DJ-SET MAKRO-STRUKTUR:
  WARMUP (0-15min): Langsame Cuts, ruhige Videos, Crossfades
  BUILDUP: Beschleunigende Cuts, steigende Motion
  DROP: Maximale Cut-Rate (S_eff=1), Action-Videos, Hard Cuts
  BREAKDOWN: Minimale Cuts (S_eff×4), atmosphärische Videos, Dissolves
  TRANSITION: Moderate Cuts, Themenwechsel, Crossfades
  COOLDOWN: Verlangsamend, ruhige Abschluss-Bilder

VIDEO-AUSWAHL PRIORITÄT:
  1. Anker (manuell gesetzt) → Exakter Clip+Szene
  2. Vibe-Keyword → SigLIP/LanceDB Semantic Search
  3. Motion-Match → |motion - energy| minimieren
  4. Round-Robin → Vermeidung der letzten 3 Clips

DROP-ERKENNUNG:
  Bass-RMS vorher < 0.2, nachher > 0.6 → HARD DROP
  Pacing: Beat 0 = Szenenwechsel, Beats 1-16 = S_eff=1, dann zurück

STEM-GEWICHTETE ENERGIE:
  E_weighted = 0.40×E_drums + 0.30×E_bass + 0.10×E_vocals + 0.20×E_other

  Spezial-Modi:
    DROP:      w_bass=0.70, w_drums=0.30
    VOCAL:     w_vocals=0.50 (weniger Schnitte)
    BREAKDOWN: w_other=0.60 (Atmosphäre dominiert)

BEAT-HIERARCHIE (4/4):
  base_cut_rate=1  → Jeder Beat (4 Cuts/Bar)
  base_cut_rate=2  → Jeder 2. Beat (2 Cuts/Bar)
  base_cut_rate=4  → Jeder Downbeat (1 Cut/Bar) ← DEFAULT
  base_cut_rate=8  → Jeder 2. Bar (0.5 Cuts/Bar)
  base_cut_rate=16 → Jeder 4. Bar (0.25 Cuts/Bar)

VERBOTENE AKTIONEN:
  - Schnitt zwischen Beats (Axiom-Verletzung)
  - Segment < 0.5s (Ausnahme: Energy > 0.9 → min 0.25s)
  - Gleicher Clip 3× hintereinander
  - Timeline länger als Audio
  - Source-Start ignorieren (MUSS korrekt sein)

MOTION-ENERGY MATCHING:
  match_score(E, M) = 1.0 - |E - M|
  Optimal: ≥ 0.7 | Akzeptabel: ≥ 0.4 | Vermeiden: < 0.4

TEMPORAL COHERENCE:
  - Section-Boundary: Video mit max Δmotion zum vorherigen Segment
  - Vocal-Active: S_eff × 2 (visuelle Stabilität für Textverständnis)
  - Transition: Crossfade statt Hard Cut"""


class PacingAgent(BaseAgent):
    """PhD-Level Pacing Agent für beat-synchrone DJ-Set Video-Timelines.

    Orchestriert die gesamte Pacing-Pipeline:
    1. Stem-Analyse (Drums → Cuts, Bass → Drops, Vocals → Ducking)
    2. Makro-Struktur-Erkennung (Warmup, Buildup, Drop, Breakdown)
    3. Video-Matching (Motion + SigLIP Semantik)
    4. Timeline-Generierung (OTIO-konform)
    """

    name = "pacing"
    domain = "pacing"
    model_id = None  # Nutzt kein eigenes ML-Modell, sondern die Pacing-Services

    def __init__(self):
        super().__init__()
        self._pattern = re.compile(
            "|".join(re.escape(kw) for kw in PACING_KEYWORDS),
            re.IGNORECASE,
        )

    @property
    def system_prompt(self) -> str:
        """Gibt den PhD-Level System-Prompt zurück."""
        return PACING_SYSTEM_PROMPT

    def can_handle(self, user_text: str) -> float:
        """Erkennt Pacing-relevante Anfragen mit hoher Konfidenz."""
        text_lower = user_text.lower()
        matches = self._pattern.findall(text_lower)
        if not matches:
            return 0.0
        # Pacing-Agent hat höhere Basis-Konfidenz als Editor für Pacing-Anfragen
        return min(0.4 + 0.15 * len(matches), 0.98)

    def process(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Verarbeitet Pacing-Anfragen und delegiert an die Pacing-Services.

        Routing:
        1. "auto edit" / "pacing" → auto_edit_phase3 mit optimalen Settings
        2. "drum cuts" → calculate_drum_cuts
        3. Informationsanfragen → Keyframe-String + Pacing-Info
        """
        from services.action_registry import action_registry

        logger.info("PacingAgent verarbeitet: %s", user_text[:80])

        result = {
            "agent": self.name,
            "action": "none",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        text_lower = user_text.lower()
        ctx = context or {}

        # --- 1. Auto-Edit / Pacing generieren ---
        if any(kw in text_lower for kw in [
            "auto edit", "auto_edit", "auto-edit",
            "timeline generieren", "timeline erstellen",
            "automatisch schneiden", "beat sync", "beatsync",
        ]):
            return self._handle_auto_edit(user_text, ctx)

        # --- 2. Drum-basierte Cuts ---
        if any(kw in text_lower for kw in [
            "drum cuts", "drum-cuts", "kick-basiert", "kick cuts",
        ]):
            return self._handle_drum_cuts(user_text, ctx)

        # --- 3. Cross-Modal-Matching: Audio-Strukturpunkt -> passende Clips ---
        if self._wants_cross_modal_clip_match(text_lower):
            return self._handle_cross_modal_clip_match(user_text, ctx)

        # --- 4. Drop-Analyse ---
        if any(kw in text_lower for kw in [
            "drop", "bass drop", "bass-drop", "drops finden",
            "drop erkennung", "drop detection",
        ]):
            return self._handle_drop_analysis(user_text, ctx)

        # --- 5. Informationsanfragen ---
        if any(kw in text_lower for kw in [
            "keyframe", "szenen", "motion", "video info",
        ]):
            return self._handle_info_query(user_text, ctx)

        # --- 6. Pacing-Einstellungen erklären ---
        result["message"] = self._explain_pacing(text_lower)
        return result

    @staticmethod
    def _wants_cross_modal_clip_match(text_lower: str) -> bool:
        has_visual_target = any(
            kw in text_lower
            for kw in ["clip", "clips", "video", "videos", "visuell", "visual"]
        )
        has_audio_segment = any(
            kw in text_lower
            for kw in ["drop", "breakdown", "buildup", "build-up", "intro", "outro"]
        )
        has_match_intent = any(
            kw in text_lower
            for kw in ["passt", "passen", "match", "vorschlag", "vorschlaege", "finde"]
        )
        return has_visual_target and has_audio_segment and has_match_intent

    @staticmethod
    def _segment_label_from_text(text_lower: str) -> str:
        if "breakdown" in text_lower:
            return "BREAKDOWN"
        if "buildup" in text_lower or "build-up" in text_lower:
            return "BUILDUP"
        if "intro" in text_lower:
            return "INTRO"
        if "outro" in text_lower:
            return "OUTRO"
        return "DROP"

    def _handle_cross_modal_clip_match(
        self, user_text: str, ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """B-246: Route Clip/Video+Segment-Fragen zum Cross-Modal-Tool."""
        from services.action_registry import action_registry

        result = {
            "agent": self.name,
            "action": "match_clips_to_segment",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        text_lower = user_text.lower()
        track_id = ctx.get("audio_track_id") or ctx.get("track_id") or ctx.get("extracted_id")
        if track_id is None:
            track_id = extract_id_from_text(user_text)

        params = {
            "track_id": track_id,
            "segment_label": self._segment_label_from_text(text_lower),
            "top_n": 5,
            "max_segments": 10,
        }
        if params["track_id"] is None:
            params.pop("track_id")

        try:
            result["params"] = params
            result["result"] = action_registry.execute("match_clips_to_segment", params)
            if isinstance(result["result"], dict):
                result["message"] = result["result"].get("message")
        except (KeyError, ImportError, ValueError, RuntimeError, OSError) as e:
            result["error"] = f"Cross-Modal-Matching fehlgeschlagen: {e}"

        return result

    def _handle_auto_edit(
        self, user_text: str, ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """Führt Phase 3 Auto-Edit mit intelligenten Settings aus."""
        from services.action_registry import action_registry

        result = {
            "agent": self.name,
            "action": "auto_edit",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        # Audio-Track-ID extrahieren
        audio_id = ctx.get("audio_track_id") or ctx.get("track_id") or ctx.get("extracted_id")
        if audio_id is None:
            # B-131: anchored extraction.
            audio_id = extract_id_from_text(user_text)

        if audio_id is None:
            result["message"] = (
                "Pacing-Agent: Benötige eine audio_track_id. "
                "Beispiel: 'auto edit für Audio 1'"
            )
            return result

        # Settings aus Text extrahieren
        settings_params = self._extract_settings_from_text(user_text)
        settings_params["audio_track_id"] = audio_id

        try:
            result["params"] = settings_params
            result["result"] = action_registry.execute("auto_edit", settings_params)
            result["message"] = (
                f"Phase 3 Auto-Edit ausgeführt für Audio {audio_id}. "
                f"Settings: base_cut_rate={settings_params.get('base_cut_rate', 4)}, "
                f"energy_reactivity={settings_params.get('energy_reactivity', 50)}%, "
                f"breakdown={settings_params.get('breakdown_behavior', 'halve')}"
            )
        except (KeyError, ImportError, ValueError, RuntimeError, OSError) as e:
            result["error"] = f"Auto-Edit fehlgeschlagen: {e}"

        return result

    def _handle_drum_cuts(
        self, user_text: str, ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """Berechnet Schnittpunkte basierend auf dem Drums-Stem."""
        result = {
            "agent": self.name,
            "action": "drum_cuts",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        audio_id = ctx.get("audio_track_id") or ctx.get("track_id") or ctx.get("extracted_id")
        if audio_id is None:
            # B-131: anchored extraction.
            audio_id = extract_id_from_text(user_text)

        if audio_id is None:
            result["message"] = "Drum-Cuts benötigen eine audio_track_id."
            return result

        try:
            from services.pacing_service import calculate_drum_cuts, _get_audio_duration
            duration = _get_audio_duration(audio_id)
            cuts = calculate_drum_cuts(audio_id, total_duration=duration)
            result["result"] = {
                "num_cuts": len(cuts),
                "cuts": [{"time": c.time, "strength": c.strength} for c in cuts[:50]],
            }
            result["message"] = (
                f"Drum-Stem Analyse: {len(cuts)} potentielle Schnittpunkte gefunden "
                f"in {duration:.0f}s Audio."
            )
        except (KeyError, ImportError, ValueError, RuntimeError, OSError) as e:
            result["error"] = f"Drum-Cut-Analyse fehlgeschlagen: {e}"

        return result

    def _handle_drop_analysis(
        self, user_text: str, ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """Analysiert Bass-Stem auf Drop-Momente."""
        result = {
            "agent": self.name,
            "action": "drop_analysis",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        audio_id = ctx.get("audio_track_id") or ctx.get("track_id") or ctx.get("extracted_id")
        if audio_id is None:
            # B-131: anchored extraction.
            audio_id = extract_id_from_text(user_text)

        if audio_id is None:
            result["message"] = "Drop-Analyse benötigt eine audio_track_id."
            return result

        try:
            from services.pacing_service import _get_beat_data_combined, _get_audio_duration
            import numpy as np

            duration = _get_audio_duration(audio_id)
            beats, _, energy = _get_beat_data_combined(audio_id)

            if not energy:
                result["message"] = "Keine Energie-Daten vorhanden. Bitte zuerst Audio analysieren."
                return result

            # Drop-Detektion: RMS-Sprünge finden
            energy_arr = np.array(energy)
            gradient = np.gradient(energy_arr)

            drops = []
            for i in range(len(energy_arr)):
                if i < 8:
                    continue
                prev_avg = float(np.mean(energy_arr[max(0, i - 8):i]))
                curr = float(energy_arr[i])

                if prev_avg < 0.2 and curr > 0.6 and gradient[i] > 0.1:
                    beat_time = beats[i] if i < len(beats) else i * (duration / len(energy_arr))
                    confidence = min(1.0, (curr - prev_avg) * 1.5)
                    drops.append({
                        "time": round(beat_time, 2),
                        "confidence": round(confidence, 3),
                        "energy_before": round(prev_avg, 3),
                        "energy_after": round(curr, 3),
                    })

            result["result"] = {"drops": drops, "total_drops": len(drops)}
            if drops:
                drop_times = ", ".join(f"{d['time']:.1f}s ({d['confidence']:.0%})" for d in drops[:10])
                result["message"] = f"Drop-Analyse: {len(drops)} Drops erkannt: {drop_times}"
            else:
                result["message"] = "Keine signifikanten Drops erkannt."

        except (KeyError, ImportError, ValueError, RuntimeError, OSError) as e:
            result["error"] = f"Drop-Analyse fehlgeschlagen: {e}"

        return result

    def _handle_info_query(
        self, user_text: str, ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """Gibt Keyframe-Strings und Video-Informationen zurück."""
        result = {
            "agent": self.name,
            "action": "info",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        try:
            from services.pacing_service import (
                generate_keyframe_strings_for_project,
            )
            project_id = ctx.get("project_id", 1)
            keyframes = generate_keyframe_strings_for_project(project_id)
            result["result"] = {"keyframes": keyframes}
            result["message"] = keyframes
        except (KeyError, ImportError, ValueError, RuntimeError, OSError) as e:
            result["error"] = f"Info-Abfrage fehlgeschlagen: {e}"

        return result

    @staticmethod
    def _extract_settings_from_text(user_text: str) -> dict[str, Any]:
        """Extrahiert Pacing-Settings aus natürlichsprachigem Text.

        Beispiele:
            "auto edit mit 2 beats pro schnitt" → base_cut_rate=2
            "schnelle schnitte, hohe energie" → base_cut_rate=1, energy_reactivity=80
            "ruhig, breakdown halbe rate" → base_cut_rate=8, breakdown_behavior="halve"
        """
        text_lower = user_text.lower()
        params: dict[str, Any] = {}

        # Base Cut Rate
        rate_match = re.search(r'(\d+)\s*beat', text_lower)
        if rate_match:
            rate = int(rate_match.group(1))
            if rate in (1, 2, 4, 8, 16):
                params["base_cut_rate"] = rate

        # Schnell/Langsam Hinweise
        if any(kw in text_lower for kw in ["schnell", "fast", "aggressiv", "hart"]):
            params.setdefault("base_cut_rate", 1)
            params.setdefault("energy_reactivity", 80)
        elif any(kw in text_lower for kw in ["langsam", "slow", "ruhig", "sanft"]):
            params.setdefault("base_cut_rate", 8)
            params.setdefault("energy_reactivity", 30)

        # Energy Reactivity
        react_match = re.search(r'reactivity\s*[=:]\s*(\d+)', text_lower)
        if react_match:
            params["energy_reactivity"] = min(100, int(react_match.group(1)))

        # Breakdown Behavior
        if "force16" in text_lower or "force 16" in text_lower:
            params["breakdown_behavior"] = "force16"
        elif "no cuts" in text_lower or "keine schnitte" in text_lower:
            params["breakdown_behavior"] = "none"
        elif "halve" in text_lower or "halbieren" in text_lower:
            params["breakdown_behavior"] = "halve"

        # Vibe Keyword
        vibe_match = re.search(r'vibe[=:\s]+["\']?([^"\']+)["\']?', text_lower)
        if vibe_match:
            params["vibe"] = vibe_match.group(1).strip()

        return params

    @staticmethod
    def _explain_pacing(text_lower: str) -> str:
        """Erklärt Pacing-Konzepte basierend auf der Anfrage."""
        if "drop" in text_lower:
            return (
                "DROP-ERKENNUNG: Ein Drop wird erkannt wenn der Bass-Stem-RMS "
                "von < 0.2 auf > 0.6 springt. Bei einem Drop wird die Cut-Rate "
                "auf S_eff=1 (jeden Beat) maximiert für 16-32 Beats."
            )
        if "breakdown" in text_lower:
            return (
                "BREAKDOWN-VERHALTEN: Bei Energie < 0.3 wird die Cut-Rate reduziert. "
                "'halve' = doppelte Schnittlänge, 'force16' = alle 4 Bars, "
                "'none' = keine Schnitte. Atmosphärische Videos mit niedrigem Motion-Score."
            )
        if "energy" in text_lower or "energie" in text_lower:
            return (
                "ENERGY REACTIVITY: 0-100% Regler. Bei hoher Energie (>0.7) werden "
                "Schnitte beschleunigt (speed_boost bis 1.9×). Bei niedriger Energie (<0.3) "
                "wird der Breakdown-Modus aktiviert. Formel: S_eff ÷ (1 + (E-0.7)×3×R)"
            )
        if "stem" in text_lower:
            return (
                "STEM-GEWICHTE: Drums=0.40 (Cut-Trigger), Bass=0.30 (Drop-Detektor), "
                "Vocals=0.10 (weniger Schnitte), Other=0.20 (Mood). "
                "Bei Drops: Bass=0.70, Drums=0.30. Bei Vocals: Vocals=0.50."
            )
        return (
            "PACING-KI: Ich generiere beat-synchrone Video-Timelines für DJ-Sets. "
            "Sage 'auto edit für Audio 1' oder frage nach 'drop analyse', "
            "'drum cuts', oder 'keyframe info'."
        )

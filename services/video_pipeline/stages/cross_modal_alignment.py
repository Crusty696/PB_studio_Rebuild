"""Cross-Modal AV-Alignment.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 39 (Tier 3 Workspace+Services)

Liest V2-Audio-Outputs (beats, sections, drops) + Video-Outputs (scenes, motion).
Generiert Cut-Plan via Heuristik (Fallback) oder LLM-Reasoner (Plan B, optional).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


__all__ = ["CutSuggestion", "CrossModalAlignmentService", "ReasonerProtocol"]


@dataclass
class CutSuggestion:
    time_s: float
    confidence: float
    reason: str
    scene_idx: int | None = None
    beat_idx: int | None = None


class ReasonerProtocol(Protocol):
    def reason_cut_plan(self, payload: dict) -> list[dict]: ...


class CrossModalAlignmentService:
    """Findet Cut-Punkte indem Scene-Boundaries + Audio-Beats abgeglichen werden.

    Heuristik (kein LLM noetig): pro Audio-Beat, der innerhalb ``snap_window_s``
    einer Scene-Boundary liegt, ist starker Cut-Kandidat.
    """

    def __init__(
        self,
        *,
        reasoner: ReasonerProtocol | None = None,
        snap_window_s: float = 0.25,
    ):
        self.reasoner = reasoner
        self.snap_window_s = snap_window_s

    def align(
        self,
        *,
        scenes: list[dict],
        beats: list[float],
        sections: list[dict] | None = None,
        drops: list[float] | None = None,
    ) -> list[CutSuggestion]:
        """Heuristisches Alignment.

        Args:
            scenes: ``[{index, start_s, end_s}, ...]``
            beats: ``[time_s, ...]`` von V2.
            sections: optional, fuer Bonus-Confidence.
            drops: optional.
        """
        scene_starts = [(i, s["start_s"]) for i, s in enumerate(scenes) if s["start_s"] > 0]
        # erste Szene (start=0) ist kein "Cut" sondern Anfang -> auslassen
        suggestions: list[CutSuggestion] = []

        for scene_idx, sc_start in scene_starts:
            # Bester Beat in der Naehe
            best_beat = None
            best_dist = self.snap_window_s + 0.01
            best_beat_idx = None
            for bi, bt in enumerate(beats):
                dist = abs(bt - sc_start)
                if dist < best_dist:
                    best_dist = dist
                    best_beat = bt
                    best_beat_idx = bi
            if best_beat is not None:
                # Confidence: 1.0 bei dist=0, 0.0 bei dist=snap_window
                conf = max(0.0, 1.0 - best_dist / self.snap_window_s)
                # Bonus wenn Drop oder Section-Start in der Naehe
                if drops:
                    for dp in drops:
                        if abs(dp - best_beat) < 0.5:
                            conf = min(1.0, conf + 0.2)
                            break
                suggestions.append(CutSuggestion(
                    time_s=best_beat,
                    confidence=conf,
                    reason=f"scene-{scene_idx} boundary snapped to beat (dist={best_dist:.3f}s)",
                    scene_idx=scene_idx,
                    beat_idx=best_beat_idx,
                ))

        # Optional: Reasoner verfeinert
        if self.reasoner is not None:
            payload = {
                "scenes": scenes,
                "beats": beats,
                "sections": sections or [],
                "drops": drops or [],
                "heuristic_suggestions": [
                    {"time_s": s.time_s, "confidence": s.confidence, "reason": s.reason}
                    for s in suggestions
                ],
            }
            try:
                refined = self.reasoner.reason_cut_plan(payload)
                if refined:
                    suggestions = [
                        CutSuggestion(
                            time_s=r["time_s"],
                            confidence=r.get("confidence", 0.5),
                            reason=r.get("reason", "reasoner"),
                            scene_idx=r.get("scene_idx"),
                            beat_idx=r.get("beat_idx"),
                        ) for r in refined
                    ]
            except Exception:
                # Fallback auf Heuristik
                pass

        return suggestions

    def save_plan(self, suggestions: list[CutSuggestion], target_json: Path) -> Path:
        target_json = Path(target_json)
        target_json.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "time_s": s.time_s, "confidence": s.confidence, "reason": s.reason,
                "scene_idx": s.scene_idx, "beat_idx": s.beat_idx,
            }
            for s in suggestions
        ]
        target_json.write_text(json.dumps(payload, indent=2))
        return target_json

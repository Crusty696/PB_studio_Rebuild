"""Direct Ollama EDL Reasoning service for DJ music pacing.

Generates Edit Decision Lists (EDLs) from audio structures and video SigLIP tags
using local models (Phi-4 Mini / Gemma 4) via Ollama.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from database import engine, AudioTrack, VideoClip, Scene, StructureSegment
from sqlalchemy.orm import Session, selectinload
from services.ollama_client import get_ollama_client
from services.settings_store import get_ollama_settings
from services.pacing_beat_grid import TimelineSegment, CutPoint

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du bist ein professioneller DJ-Videoschnitt-Director.
Deine Aufgabe ist es, eine Edit Decision List (EDL) im JSON-Format zu erstellen, um einen Video-Clip-Schnitt synchronisiert zur Musik-Struktur eines DJ-Mixes zu pacen.

Bedeutung des Audio-Sektions-Inputs:
- WARMUP/BREAKDOWN/COOLDOWN (niedrige Energie): Lange Szenen, ruhige Stimmung (atmospheric, calm). Schnitte alle 8-16 Beats (ca. 4-8 Sekunden).
- DROP/BUILDUP (hohe Energie): Schnelle Schnitte, explosive Stimmung (energetic, strobe, action). Schnitte alle 1-4 Beats (ca. 0.5-2 Sekunden).

Bedeutung des Video-Inputs:
- Jedes Video hat mehrere Szenen mit Start- und Endzeit und semantischen Tags.
- Wähle Videos und Szenen aus, deren Stimmung und Tags zur Musik passen.

Ausgabe-Format:
{
  "edl": [
    {
      "start": 0.0,
      "end": 8.0,
      "video_id": 1,
      "scene_id": 101,
      "transition": "crossfade"
    }
  ]
}

Regeln:
1. Die gesamte EDL MUSS lückenlos sein und den gesamten Zeitbereich des Audio-Mixes abdecken.
2. Gib AUSSCHLIESSLICH das valide JSON-Dokument zurück. Keine Einleitung, kein Markdown!"""


class OllamaPacingService:
    """Service to directly generate video timeline cut plans (EDLs) via Ollama."""

    def __init__(self):
        cfg = get_ollama_settings()
        self.enabled = cfg.get("enabled", True)
        self.url = cfg.get("url", "http://localhost:11434")
        self.model = cfg.get("model", "llama3.2")
        self._client = get_ollama_client(self.url)

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        try:
            return self._client.is_available()
        except Exception:
            return False

    def generate_edl(
        self,
        audio_id: int,
        video_clip_ids: list[int],
        user_preferences: str = "",
    ) -> list[dict[str, Any]] | None:
        """Loads metadata, builds prompt, queries Ollama, and parses the resulting EDL."""
        if not self.is_available():
            logger.info("Ollama is not available for direct pacing.")
            return None

        # 1. Load Audio and Video Metadata
        audio_sections = []
        video_data = []
        duration = 0.0
        bpm = 120.0

        with Session(engine) as session:
            track = session.query(AudioTrack).filter(
                AudioTrack.id == audio_id,
                AudioTrack.deleted_at.is_(None)
            ).first()
            if not track:
                return None
            duration = track.duration or 300.0
            bpm = track.bpm or 120.0

            # Sort segments chronologically
            segs = sorted(track.structure_segments, key=lambda s: s.start_time)
            for s in segs:
                audio_sections.append({
                    "t": s.label,
                    "s": round(s.start_time, 1),
                    "e": round(s.end_time, 1),
                    "en": round(s.energy or 0.5, 2)
                })

            # Load videos and scenes
            # B-090: scenes ist jetzt lazy='select' (Model-Default eager entfernt).
            # selectinload batcht die Scene-Loads gegen N+1 im for-c-Loop unten.
            clips = session.query(VideoClip).options(
                selectinload(VideoClip.scenes)
            ).filter(
                VideoClip.id.in_(video_clip_ids),
                VideoClip.deleted_at.is_(None)
            ).all()
            for c in clips:
                scenes_data = []
                for s in c.scenes:
                    scenes_data.append({
                        "id": s.id,
                        "s": round(s.start_time, 1),
                        "e": round(s.end_time, 1),
                        "m": s.ai_mood or "",
                        "tags": s.ai_tags or []
                    })
                video_data.append({
                    "id": c.id,
                    "name": Path(c.file_path).name,
                    "d": round(c.duration or 10.0, 1),
                    "scenes": scenes_data
                })

        if not audio_sections or not video_data:
            logger.warning("Missing audio sections or video data for EDL reasoning.")
            return None

        # 2. Build token-minimized JSON structure
        payload = {
            "m": {
                "d": round(duration, 1),
                "b": round(bpm, 1),
                "pref": user_preferences
            },
            "audio": audio_sections,
            "videos": video_data
        }

        json_payload = json.dumps(payload, indent=1)
        user_message = f"Hier sind die Metadaten des Projekts:\n\n{json_payload}\n\nErstelle die EDL für die gesamte Mix-Dauer."

        # 3. Query local Ollama model
        logger.info("OllamaPacingService: Querying model '%s' for direct EDL reasoning...", self.model)
        try:
            raw_reply = self._client.chat(
                model=self.model,
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=4096
            )
            logger.info("OllamaPacingService: Reply received (%d chars)", len(raw_reply))
            return self._parse_edl(raw_reply)
        except Exception as e:
            logger.warning("Ollama direct EDL reasoning failed: %s", e)
            return None

    def _parse_edl(self, raw: str) -> list[dict[str, Any]] | None:
        """Helper to extract and parse the EDL JSON array robustly."""
        json_str = raw.strip()
        if "```json" in raw:
            start = raw.find("```json") + 7
            end = raw.find("```", start)
            if end != -1:
                json_str = raw[start:end].strip()
        elif "```" in raw:
            start = raw.find("```") + 3
            end = raw.find("```", start)
            if end != -1:
                json_str = raw[start:end].strip()

        # Parse JSON
        try:
            data = json.loads(json_str)
            if isinstance(data, dict) and "edl" in data:
                edl = data["edl"]
            elif isinstance(data, list):
                edl = data
            else:
                edl = None

            if not isinstance(edl, list):
                return None

            # Validate each EDL item
            valid_edl = []
            for item in edl:
                if not isinstance(item, dict):
                    continue
                start = item.get("start")
                end = item.get("end")
                video_id = item.get("video_id")
                scene_id = item.get("scene_id")
                transition = item.get("transition", "hard_cut")

                if None in (start, end, video_id):
                    continue

                valid_edl.append({
                    "start": float(start),
                    "end": float(end),
                    "video_id": int(video_id),
                    "scene_id": int(scene_id) if scene_id is not None else None,
                    "transition": str(transition)
                })

            return valid_edl if valid_edl else None

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse Ollama EDL response: %s", e)
            # Fallback search for brace
            brace_start = raw.find("{")
            brace_end = raw.rfind("}") + 1
            if brace_start >= 0 and brace_end > brace_start:
                try:
                    data = json.loads(raw[brace_start:brace_end])
                    if "edl" in data:
                        return self._parse_edl(json.dumps(data))
                except Exception:
                    pass
            return None

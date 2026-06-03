"""Vision-Analyse Service — Ollama Vision Backend.

Analysiert Video-Frames mit einem Vision-faehigen Ollama-Modell
(Standard: ``moondream:latest``) ueber ``OllamaClient.chat_vision``.
Extrahiert Frame-Beschreibungen fuer die Video-Szenen-Datenbank.

B-463 (2026-06-03): Umbau weg vom HF-transformers-Pfad
(``vikhyatk/moondream2``), der in der GPU-Hartregel-Umgebung
(torch 1.12.1+cu113 / torchvision 0.13.1) nicht laeuft — die moondream2
remote-code-Module importieren ``torchvision.transforms.v2`` (nur torch 2.x).
Der existierende Ollama-Vision-Pfad (auch von ``video_analysis_service``
genutzt) laeuft dagegen out-of-process auf der GTX 1060.
"""

import base64
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

# L-38 FIX: Move heavy imports to module level (was inside method)
import cv2

logger = logging.getLogger(__name__)

# Vision-faehiges Ollama-Modell (~1.6 GB, passt in GTX-1060-VRAM).
# Ueber PB_VISION_MODEL env-var ueberschreibbar (siehe video_analysis_service).
_VISION_MODEL = "moondream:latest"

_VISION_QUESTION = "Describe this video frame in detail. What do you see?"


def get_ollama_client():
    """Wrapper, damit Tests den Client monkeypatchen koennen."""
    from services.ollama_client import get_ollama_client as _get
    return _get()


def _resolve_vision_model() -> str:
    return os.environ.get("PB_VISION_MODEL") or _VISION_MODEL


@dataclass
class VisionAnalysisResult:
    """Ergebnis einer Video-Inhaltsanalyse."""
    descriptions: list[dict] = field(default_factory=list)  # [{time, description}, ...]
    summary: str = ""
    frame_count: int = 0


class VisionAnalysisService:
    """Analysiert Video-Frames via Ollama Vision (moondream:latest).

    Extrahiert Frames in regelmaessigen Abstaenden und beschreibt sie
    ueber den Ollama-Vision-Endpunkt (``chat_vision``).
    """

    def analyze(self, video_path: str, interval_sec: float = 5.0,
                max_frames: int = 10, progress_cb=None) -> VisionAnalysisResult:
        """Analysiert ein Video Frame fuer Frame.

        Args:
            video_path: Pfad zur Video-Datei
            interval_sec: Abstand zwischen Frames in Sekunden
            max_frames: Maximale Anzahl zu analysierender Frames
            progress_cb: Optional callback(int, str)
        """
        from services.errors import (
            OllamaNotAvailableError,
            OllamaModelNotFoundError,
            OllamaPausedError,
        )

        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video nicht gefunden: {video_path}")

        if progress_cb:
            progress_cb(0, "Verbinde mit Ollama Vision...")

        client = get_ollama_client()
        model = _resolve_vision_model()

        if progress_cb:
            progress_cb(10, "Extrahiere Frames...")

        # Frames extrahieren (als base64-JPEG fuer Ollama)
        cap = cv2.VideoCapture(str(video_path))
        frames: list[tuple[float, str]] = []  # (time_sec, base64_jpeg)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps else 0.0

            frame_times = []
            t = 0.0
            while t < duration and len(frame_times) < max_frames:
                frame_times.append(t)
                t += interval_sec

            for time_sec in frame_times:
                frame_idx = int(time_sec * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame_bgr = cap.read()
                if not ret:
                    continue
                ok, buf = cv2.imencode(".jpg", frame_bgr)
                if not ok:
                    continue
                b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
                frames.append((time_sec, b64))
        finally:
            cap.release()

        if not frames:
            logger.warning("[Vision] Keine Frames extrahiert aus %s", path.name)
            return VisionAnalysisResult()

        if progress_cb:
            progress_cb(20, f"Analysiere {len(frames)} Frames...")

        descriptions = []
        for i, (time_sec, b64) in enumerate(frames):
            if progress_cb:
                pct = 20 + int(75 * (i + 1) / len(frames))
                progress_cb(pct, f"Frame {i+1}/{len(frames)} ({time_sec:.1f}s)...")

            try:
                answer = client.chat_vision(
                    model=model,
                    user_message=_VISION_QUESTION,
                    images_base64=[b64],
                )
            except (OllamaNotAvailableError, OllamaModelNotFoundError, OllamaPausedError) as e:
                # Vision-Backend nicht nutzbar -> graceful degradation.
                # Bei i==0 nichts Brauchbares; sonst behalte was schon da ist.
                logger.warning("[Vision] Ollama Vision nicht verfuegbar: %s", e)
                if progress_cb:
                    progress_cb(100, "Ollama Vision nicht verfuegbar")
                if not descriptions:
                    result = VisionAnalysisResult()
                    result.summary = (
                        f"Ollama-Vision-Modell '{model}' nicht verfuegbar: {e}. "
                        "Bitte Ollama starten und Modell laden: ollama pull moondream"
                    )
                    return result
                break
            except (OSError, ValueError, RuntimeError, AttributeError) as e:
                logger.warning("[Vision] Frame bei %.1fs fehlgeschlagen: %s", time_sec, e)
                descriptions.append({
                    "time": round(time_sec, 2),
                    "description": f"[Analyse-Fehler: {e}]",
                })
                continue

            descriptions.append({
                "time": round(time_sec, 2),
                "description": (answer or "").strip(),
            })

        # Summary aus allen erfolgreichen Beschreibungen
        good = [d["description"] for d in descriptions if not d["description"].startswith("[")]
        summary = " | ".join(good[:5])

        if progress_cb:
            progress_cb(100, "Fertig")

        logger.info("[Vision] Analyse fertig: %s, %d Frames, %d Beschreibungen",
                    path.name, len(frames), len(descriptions))

        return VisionAnalysisResult(
            descriptions=descriptions,
            summary=summary,
            frame_count=len(frames),
        )

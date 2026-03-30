"""Vision-Analyse Service — Moondream2 Backend.

Analysiert Video-Frames mit dem Moondream2 Vision-Language-Modell.
Extrahiert Frame-Beschreibungen fuer die Video-Szenen-Datenbank.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VisionAnalysisResult:
    """Ergebnis einer Video-Inhaltsanalyse."""
    descriptions: list[dict] = field(default_factory=list)  # [{time, description}, ...]
    summary: str = ""
    frame_count: int = 0


class VisionAnalysisService:
    """Analysiert Video-Frames via Moondream2.

    Extrahiert Frames in regelmaessigen Abstaenden und beschreibt sie
    mit dem Moondream2 Vision-Language-Modell.
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
        import cv2
        from services.model_manager import ModelManager, GPU_LOAD_LOCK

        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video nicht gefunden: {video_path}")

        if progress_cb:
            progress_cb(0, "Lade Moondream2 Modell...")

        # Modell laden (mit trust_remote_code fuer Moondream2)
        with GPU_LOAD_LOCK:
            mm = ModelManager()
            model, tokenizer = mm.load_vision("vikhyatk/moondream2")

        if progress_cb:
            progress_cb(10, "Extrahiere Frames...")

        # Frames extrahieren
        cap = cv2.VideoCapture(str(video_path))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps

            frame_times = []
            t = 0.0
            while t < duration and len(frame_times) < max_frames:
                frame_times.append(t)
                t += interval_sec

            frames = []
            for time_sec in frame_times:
                frame_idx = int(time_sec * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret:
                    # BGR → RGB, resize fuer Moondream2
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append((time_sec, frame_rgb))
        finally:
            cap.release()

        if not frames:
            logger.warning("[Vision] Keine Frames extrahiert aus %s", path.name)
            return VisionAnalysisResult()

        if progress_cb:
            progress_cb(20, f"Analysiere {len(frames)} Frames...")

        # Frames mit Moondream2 beschreiben
        from PIL import Image
        import torch

        descriptions = []
        for i, (time_sec, frame_rgb) in enumerate(frames):
            if progress_cb:
                pct = 20 + int(70 * (i + 1) / len(frames))
                progress_cb(pct, f"Frame {i+1}/{len(frames)} ({time_sec:.1f}s)...")

            try:
                pil_image = Image.fromarray(frame_rgb)

                # Moondream2 API: model.answer_question(image, question, tokenizer)
                with torch.no_grad():
                    answer = model.answer_question(
                        tokenizer=tokenizer,
                        image=pil_image,
                        question="Describe this video frame in detail. What do you see?",
                    )

                descriptions.append({
                    "time": round(time_sec, 2),
                    "description": answer.strip(),
                })
            except Exception as e:
                logger.warning("[Vision] Frame bei %.1fs fehlgeschlagen: %s", time_sec, e)
                descriptions.append({
                    "time": round(time_sec, 2),
                    "description": f"[Analyse-Fehler: {e}]",
                })

        # Summary aus allen Beschreibungen
        if descriptions:
            all_texts = [d["description"] for d in descriptions if not d["description"].startswith("[")]
            summary = " | ".join(all_texts[:5])  # Erste 5 Beschreibungen als Summary
        else:
            summary = ""

        if progress_cb:
            progress_cb(95, "Aufraemen...")

        # VRAM freigeben
        mm.unload()

        if progress_cb:
            progress_cb(100, "Fertig")

        logger.info("[Vision] Analyse fertig: %s, %d Frames, %d Beschreibungen",
                    path.name, len(frames), len(descriptions))

        return VisionAnalysisResult(
            descriptions=descriptions,
            summary=summary,
            frame_count=len(frames),
        )

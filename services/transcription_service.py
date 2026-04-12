"""Transkription-Service — faster-whisper Backend.

Transkribiert Audio-Dateien zu Text mit GPU-Beschleunigung.
Nutzt den ModelManager fuer VRAM-Management (GTX 1060 kompatibel).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _seg_val(seg, key):
    """Access a segment field by *key*, whether *seg* is a dict or an object.

    faster-whisper may return Segment namedtuples (attribute access) **or**
    plain dicts depending on the installed version.  This helper handles both
    transparently.
    """
    if isinstance(seg, dict):
        return seg[key]
    return getattr(seg, key)


@dataclass
class TranscriptionResult:
    """Ergebnis einer Transkription."""
    text: str = ""
    language: str = ""
    language_probability: float = 0.0
    segments: list[dict] = field(default_factory=list)
    duration: float = 0.0


class TranscriptionService:
    """Transkribiert Audio via faster-whisper.

    Modell-Groessen (VRAM auf GTX 1060 6GB):
    - tiny:  ~1 GB  (schnellste, niedrigste Qualitaet)
    - base:  ~1 GB  (schnell, OK Qualitaet)
    - small: ~2 GB  (gut, empfohlen fuer 6GB GPU)
    - medium: ~5 GB (sehr gut, knapp auf 6GB)
    - large: >6 GB  (beste, passt NICHT auf GTX 1060)
    """

    DEFAULT_MODEL = "small"  # Bester Kompromiss fuer GTX 1060

    def __init__(self, model_size: str | None = None):
        self._model_size = model_size or self.DEFAULT_MODEL

    def transcribe(self, audio_path: str, language: str | None = None,
                   progress_cb=None) -> TranscriptionResult:
        """Transkribiert eine Audio-Datei.

        Args:
            audio_path: Pfad zur Audio-Datei (WAV, MP3, FLAC etc.)
            language: ISO-Sprachcode (z.B. "de", "en"). None = Auto-Detect.
            progress_cb: Optional callback(int, str) fuer Fortschritt.

        Returns:
            TranscriptionResult mit Text, Sprache und Segmenten.
        """
        from faster_whisper import WhisperModel
        from services.model_manager import ModelManager, GPU_LOAD_LOCK, GPU_EXECUTION_LOCK

        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio-Datei nicht gefunden: {audio_path}")

        if progress_cb:
            progress_cb(0, "Lade Whisper-Modell...")

        # GPU-Lock: Nur ein Modell gleichzeitig auf der GPU
        with GPU_LOAD_LOCK:
            # Andere Modelle entladen (VRAM freigeben)
            mm = ModelManager()
            mm.unload()

            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

            logger.info("[Whisper] Lade Modell '%s' auf %s (%s)...",
                        self._model_size, device, compute_type)

            try:
                model = WhisperModel(
                    self._model_size,
                    device=device,
                    compute_type=compute_type,
                )
            except (OSError, EnvironmentError) as e:
                # Modell nicht lokal gecacht — kleineres Modell als Fallback versuchen
                if self._model_size not in ("tiny", "base"):
                    fallback_size = "base"
                    logger.warning(
                        "[Whisper] Modell '%s' nicht gefunden — versuche Fallback '%s': %s",
                        self._model_size, fallback_size, e,
                    )
                    try:
                        model = WhisperModel(fallback_size, device=device, compute_type=compute_type)
                        self._model_size = fallback_size  # merken fuer naechste transcription
                    except (OSError, EnvironmentError) as e2:
                        from services.errors import MLModelNotFoundError
                        raise MLModelNotFoundError(
                            f"whisper-{self._model_size}",
                            hint=(
                                "Whisper-Modell nicht lokal gecacht. "
                                "Beim ersten Start mit Internetverbindung wird es automatisch "
                                "heruntergeladen. Offline-Download: "
                                f"huggingface-cli download Systran/faster-whisper-{fallback_size}"
                            ),
                        ) from e2
                else:
                    from services.errors import MLModelNotFoundError
                    raise MLModelNotFoundError(
                        f"whisper-{self._model_size}",
                        hint=(
                            "Whisper-Modell nicht lokal gecacht. "
                            "Offline-Download: "
                            f"huggingface-cli download Systran/faster-whisper-{self._model_size}"
                        ),
                    ) from e

        if progress_cb:
            progress_cb(20, "Transkribiere...")

        logger.info("[Whisper] Starte Transkription: %s", path.name)

        # C-5 FIX: GPU_EXECUTION_LOCK prevents concurrent GPU operations during inference
        # (other models could crash CUDA if they try to load while Whisper is running)
        with GPU_EXECUTION_LOCK:
            segments_list, info = model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                vad_filter=True,       # Voice Activity Detection — filtert Stille
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                ),
            )

            # Segmente sammeln
            result_segments = []
            full_text_parts = []
            total_duration = 0.0

            for i, segment in enumerate(segments_list):
                seg_start = _seg_val(segment, "start")
                seg_end = _seg_val(segment, "end")
                seg_text = _seg_val(segment, "text").strip()

                result_segments.append({
                    "start": round(seg_start, 2),
                    "end": round(seg_end, 2),
                    "text": seg_text,
                })
                full_text_parts.append(seg_text)
                total_duration = max(total_duration, seg_end)

                if progress_cb and i % 10 == 0:
                    progress_cb(20 + int(70 * seg_end / max(total_duration, 1)),
                                f"Segment {i+1}...")

            full_text = " ".join(full_text_parts)

        if progress_cb:
            progress_cb(95, "Aufraemen...")

        # VRAM freigeben
        del model
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if progress_cb:
            progress_cb(100, "Fertig")

        logger.info("[Whisper] Transkription fertig: %s, Sprache=%s (%.0f%%), %d Segmente, %.0fs",
                    path.name, info.language, info.language_probability * 100,
                    len(result_segments), total_duration)

        return TranscriptionResult(
            text=full_text,
            language=info.language,
            language_probability=info.language_probability,
            segments=result_segments,
            duration=total_duration,
        )

    def transcribe_and_store(self, track_id: int, language: str | None = None,
                             progress_cb=None) -> TranscriptionResult:
        """Transkribiert und speichert das Ergebnis in der DB."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session

        # Audio-Pfad aus DB lesen
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if not track:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            audio_path = track.file_path

        # Transkribieren
        result = self.transcribe(audio_path, language=language, progress_cb=progress_cb)

        # M-20 FIX: Store transcription result in database
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track:
                # Serialize result to JSON
                track.transcription = {
                    "text": result.text,
                    "language": result.language,
                    "language_probability": result.language_probability,
                    "duration": result.duration,
                    "segments": [
                        {
                            "start": _seg_val(seg, "start"),
                            "end": _seg_val(seg, "end"),
                            "text": _seg_val(seg, "text"),
                        }
                        for seg in result.segments
                    ]
                }
                session.commit()
                logger.info("[Whisper] Transkription fuer Track #%d gespeichert: %d Zeichen, %d Segmente",
                            track_id, len(result.text), len(result.segments))

        return result

"""Brain V3 — CLAP-Embedder (laion/larger_clap_music).

Plan-Doc 02 #15, #17. Phase-0-Spike (2026-05-03) bestaetigt:
- CLAP belegt ~742 MB allocated VRAM FP32 auf GTX 1060 6 GB
- Inferenz auf 10 s Random-Audio: ~1.7 s reine Inferenz
- Saubere Unload via `del model + empty_cache`

Window-Konfiguration: 10 s @ 48 kHz, 5 s Hop (50 % Overlap).
Aggregation: window-Embeddings → section-Embeddings (Mittel je Subtrack)
→ mix-Embedding (Mittel ueber alle Sections), L2-normalisiert.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

import numpy as np

from services.brain.gpu_serializer import GpuSerializer, get_default_serializer

logger = logging.getLogger(__name__)

CLAP_MODEL_ID = "laion/larger_clap_music"
CLAP_MODEL_VERSION = "1.0"  # erhoehe bei jedem Modell-Update (Plan-Doc 07 R07)
CLAP_DIM = 512
CLAP_SAMPLE_RATE = 48000
CLAP_WINDOW_SECONDS = 10.0
CLAP_HOP_SECONDS = 5.0


@dataclass
class WindowEmbedding:
    start_time: float
    end_time: float
    embedding: np.ndarray  # shape (512,) float32


@dataclass
class SectionEmbedding:
    start_time: float
    end_time: float
    embedding: np.ndarray  # shape (512,) float32, gemittelt ueber Windows


@dataclass
class MixEmbeddingResult:
    audio_hash: str
    duration_seconds: float
    sample_rate: int
    n_windows: int
    n_sections: int
    mix_embedding: np.ndarray             # shape (512,) float32, L2-normalisiert
    section_embeddings: list[SectionEmbedding] = field(default_factory=list)
    window_embeddings: list[WindowEmbedding] = field(default_factory=list)


class ClapAudioEmbedder:
    """Singleton-Holder fuer CLAP-Modell. Lazy-Load beim ersten embed()-Call.

    Lifecycle:
        emb = ClapAudioEmbedder(serializer=...)
        result = emb.embed_mix(audio_path, audio_hash="...")
        emb.unload()  # gibt VRAM frei

    Mit GpuSerializer umschlossen — verhindert paralleles SigLIP-/Demucs-/...
    Loading.
    """

    def __init__(
        self,
        device: Optional[str] = None,
        serializer: Optional[GpuSerializer] = None,
        sections_seconds: float = 30.0,
    ):
        self.device = device or _autodetect_device()
        self.serializer = serializer or get_default_serializer()
        self.sections_seconds = sections_seconds  # default 30 s Section-Window
        self._model = None
        self._processor = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from transformers import ClapModel, ClapProcessor  # type: ignore
        logger.info("ClapAudioEmbedder: loading %s on %s ...", CLAP_MODEL_ID, self.device)
        self._processor = ClapProcessor.from_pretrained(CLAP_MODEL_ID)
        model = ClapModel.from_pretrained(CLAP_MODEL_ID).eval()
        self._model = model.to(self.device)

    def unload(self) -> None:
        """Gibt CLAP-VRAM frei. Sicher erneut aufrufbar."""
        import gc
        if self._model is not None:
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None
        gc.collect()
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------
    # Inferenz
    # ------------------------------------------------------------------
    def embed_mix(
        self,
        audio_path: Path | str,
        audio_hash: str,
        section_boundaries_seconds: Optional[list[float]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> MixEmbeddingResult:
        """Volle Pipeline: Window-Embeddings → Section-Aggregation → Mix-Embedding.

        Args:
            audio_path: Pfad zur Mix-Datei.
            audio_hash: sha256 von services.brain.hashing.
            section_boundaries_seconds: optional Subtrack-Grenzen aus
                SubtrackDetector. Wenn None → fixe 30-s-Sections.
            should_stop: Optionaler Callback zur Abbruch-Pruefung.
            progress_cb: Optionaler Callback fuer Fortschritts-Anzeige (0-100%, msg).

        Returns:
            MixEmbeddingResult mit window/section/mix Embeddings.
        """
        import librosa  # type: ignore

        with self.serializer.acquire(holder="clap_embed_mix"):
            self._ensure_loaded()
            assert self._model is not None and self._processor is not None

            # B-519: Audio-Dauer per Header-Read ermitteln und chunk-weise laden (streamend)
            duration = float(librosa.get_duration(path=str(audio_path)))
            if duration <= 0:
                raise ValueError(f"Audio leer: {audio_path}")

            sr = CLAP_SAMPLE_RATE
            window_samples = int(CLAP_WINDOW_SECONDS * sr)
            hop_samples = int(CLAP_HOP_SECONDS * sr)

            hop_sec = CLAP_HOP_SECONDS
            win_sec = CLAP_WINDOW_SECONDS

            # Vorab-Berechnung der Windows fuer praezisen Fortschritt und Abbruch-Sicherheit
            expected_starts = []
            curr = 0.0
            while curr < duration:
                clip_dur = min(win_sec, duration - curr)
                if clip_dur < win_sec / 2:
                    break
                expected_starts.append(curr)
                curr += hop_sec

            total_windows = len(expected_starts)

            # Window-Embeddings
            windows: list[WindowEmbedding] = []
            for idx, start_sec in enumerate(expected_starts):
                if should_stop is not None and should_stop():
                    logger.info("ClapAudioEmbedder: embedding mix abgebrochen")
                    raise RuntimeError("Embedding mix cancelled")

                if progress_cb is not None and total_windows > 0:
                    pct = int(idx / total_windows * 100)
                    progress_cb(pct, f"CLAP Audio-Embedding: Window {idx+1}/{total_windows}")

                # Lade streamend nur das aktuelle Fenster in den Speicher
                clip, _ = librosa.load(
                    str(audio_path),
                    sr=sr,
                    mono=True,
                    offset=start_sec,
                    duration=win_sec,
                )

                if len(clip) < window_samples // 2:
                    continue  # zu kurzer Rest

                emb = self._embed_audio_window(clip, sr)
                windows.append(WindowEmbedding(
                    start_time=start_sec,
                    end_time=start_sec + float(len(clip) / sr),
                    embedding=emb,
                ))

            if not windows:
                raise RuntimeError(f"Keine Windows aus Audio extrahiert: {audio_path}")

            # Section-Aggregation
            section_marks = section_boundaries_seconds or self._fixed_sections(duration)
            sections = self._aggregate_to_sections(windows, section_marks, duration)

            # Mix-Embedding = L2-normalisiertes Mittel der Section-Embeddings
            mix_emb = np.mean([s.embedding for s in sections], axis=0)
            mix_emb = _l2_normalize(mix_emb).astype("float32")

            return MixEmbeddingResult(
                audio_hash=audio_hash,
                duration_seconds=duration,
                sample_rate=sr,
                n_windows=len(windows),
                n_sections=len(sections),
                mix_embedding=mix_emb,
                section_embeddings=sections,
                window_embeddings=windows,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _embed_audio_window(self, audio: np.ndarray, sr: int) -> np.ndarray:
        import torch  # type: ignore
        inputs = self._processor(
            audios=audio.astype("float32"),
            sampling_rate=sr,
            return_tensors="pt",
        ).to(self.device)
        with torch.no_grad():
            features = self._model.get_audio_features(**inputs)
        # features shape: (1, 512)
        emb = features.detach().cpu().numpy().squeeze(0)
        return _l2_normalize(emb).astype("float32")

    def _fixed_sections(self, duration: float) -> list[float]:
        """Fixe sections_seconds-Boundaries als Fallback wenn kein Subtrack-Detector lief."""
        marks = []
        t = self.sections_seconds
        while t < duration:
            marks.append(t)
            t += self.sections_seconds
        return marks

    @staticmethod
    def _aggregate_to_sections(
        windows: list[WindowEmbedding],
        boundaries_seconds: list[float],
        duration: float,
    ) -> list[SectionEmbedding]:
        marks = [0.0] + sorted(boundaries_seconds) + [duration]
        sections: list[SectionEmbedding] = []
        for s, e in zip(marks[:-1], marks[1:]):
            window_embs = [w.embedding for w in windows
                           if w.start_time >= s and w.end_time <= e + 0.01]
            if not window_embs:
                # Fallback: Window dessen Mitte im Segment liegt
                window_embs = [w.embedding for w in windows
                               if s <= ((w.start_time + w.end_time) / 2.0) <= e]
            if not window_embs:
                continue
            sec_emb = np.mean(window_embs, axis=0)
            sections.append(SectionEmbedding(
                start_time=float(s), end_time=float(e),
                embedding=_l2_normalize(sec_emb).astype("float32"),
            ))
        return sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm < 1e-12:
        return v
    return v / norm


def _autodetect_device() -> str:
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"

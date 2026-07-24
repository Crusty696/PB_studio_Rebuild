"""Brain V3 — SigLIP-2-Embedder (google/siglip2-base-patch16-384, Vision-Tower).

Plan-Doc 02 #16, #17. Phase-0-Spike (2026-05-03) bestaetigt:
- SigLIP-2 Vision belegt ~355 MB allocated, batch=8 mit 758 MB reserved
- LESSON aus Spike: AutoImageProcessor statt AutoProcessor — sonst crasht
  Tokenizer-Loader in transformers 4.38.2 mit
  TypeError: expected str/bytes/PathLike, not NoneType
- Coexistenz mit CLAP funktioniert (1178 MB reserved fuer beide)

Frame-Sampling: 1 Frame pro Scene-Mitte (Plan-Doc 06 Phase 2).
Aggregation: Scene-Embeddings → Clip-Embedding (gewichtet mit Scene-Dauer).

VRAM-Auto-Tuning bleibt als Defensive (Plan-Doc 07 R10), wird aber bei
batch=8 nicht aktiv da Spike ihn als sicher bestaetigte.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from services.brain.gpu_serializer import GpuSerializer, get_default_serializer

logger = logging.getLogger(__name__)


class InvalidVideoError(ValueError):
    """B-279: Video hat ungueltige/nonstandard Metadaten (z.B. .stem.mp4 mit
    fps<=0 oder frames=-1). Subklasse von ValueError fuer Rueckwaerts-
    kompatibilitaet; der Embedding-Scheduler faengt diesen Typ gezielt ab und
    behandelt ihn als sauberen Skip-mit-Grund statt als fehlgeschlagenen Job."""


SIGLIP2_MODEL_ID = "google/siglip2-base-patch16-384"
SIGLIP2_MODEL_VERSION = "1.0"
SIGLIP2_DIM = 768
DEFAULT_BATCH_SIZE = 8        # Spike-Bestaetigung
MIN_BATCH_SIZE = 1
DEFAULT_IMG_SIZE = 384


@dataclass
class SceneSpec:
    """Eingabe: ein Scene-Segment innerhalb eines Clips."""
    start_time: float
    end_time: float
    representative_frame_time: Optional[float] = None  # default: Mitte


@dataclass
class SceneEmbedding:
    start_time: float
    end_time: float
    embedding: np.ndarray  # shape (768,) float32


@dataclass
class ClipEmbeddingResult:
    video_hash: str
    duration_seconds: float
    fps: float
    n_scenes: int
    clip_embedding: np.ndarray             # shape (768,) float32, dauer-gewichtet + L2
    scene_embeddings: list[SceneEmbedding] = field(default_factory=list)


class Siglip2VideoEmbedder:
    """Singleton-Holder fuer SigLIP-2 Vision-Tower.

    Lifecycle:
        emb = Siglip2VideoEmbedder(serializer=...)
        result = emb.embed_clip(video_path, video_hash, scenes=[SceneSpec(...)])
        emb.unload()
    """

    def __init__(
        self,
        device: Optional[str] = None,
        serializer: Optional[GpuSerializer] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.device = device or _autodetect_device()
        self.serializer = serializer or get_default_serializer()
        self.batch_size = batch_size
        self._vision = None
        self._processor = None
        self._img_size = DEFAULT_IMG_SIZE

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._vision is not None:
            return
        # LESSON aus Phase-0-Spike: AutoImageProcessor statt AutoProcessor
        # (vermeidet Tokenizer-Loader-Crash mit transformers 4.38.2)
        from transformers import AutoModel, AutoImageProcessor  # type: ignore
        logger.info("Siglip2VideoEmbedder: loading %s on %s ...",
                    SIGLIP2_MODEL_ID, self.device)
        # B-554 (Fix B): Modell zuerst NUR aus dem lokalen HF-Cache laden
        # (local_files_only=True). Vermeidet einen potenziell blockierenden
        # HF-Hub-Netzwerk-Check (etag/Revision), der waehrend des gehaltenen
        # GpuSerializer-Locks haengen kann. Nur wenn das Modell nicht im Cache
        # liegt, einmalig online laden.
        def _load(local_only: bool):
            proc = AutoImageProcessor.from_pretrained(
                SIGLIP2_MODEL_ID, local_files_only=local_only)
            mdl = AutoModel.from_pretrained(
                SIGLIP2_MODEL_ID, local_files_only=local_only).eval()
            return proc, mdl
        try:
            self._processor, full = _load(local_only=True)
        except (OSError, EnvironmentError) as exc:
            logger.warning(
                "Siglip2: nicht im lokalen HF-Cache (%s) — lade online (einmalig)", exc)
            self._processor, full = _load(local_only=False)
        vision = full.vision_model if hasattr(full, "vision_model") else full
        self._vision = vision.to(self.device)
        del full
        # Auflaesung defensiv ableiten (Spike-Lesson):
        try:
            sz = self._processor.size
            if isinstance(sz, dict):
                self._img_size = sz.get("height") or sz.get("shortest_edge") or DEFAULT_IMG_SIZE
            elif isinstance(sz, int):
                self._img_size = sz
        except Exception:
            self._img_size = DEFAULT_IMG_SIZE

    def unload(self) -> None:
        import gc
        logger.info("Siglip2VideoEmbedder: Entlade Modell und gebe GPU-VRAM frei...")
        # B-684: Der GPU-Cleanup (``.cpu()`` / ``empty_cache`` / ``synchronize``)
        # MUSS unter demselben GpuSerializer laufen wie die embed-Pfade
        # (``embed_clip`` haelt ``serializer.acquire``). Sonst feuert dieser
        # un-serialisierte Cleanup aus dem Scheduler-Thread gegen live laufende
        # ModelManager-Kernels in einem anderen Thread -> Heap-Corruption
        # (0xC0000374). Genau davor warnt services/video_analysis_service.py:329.
        with self.serializer.acquire(holder="siglip2_unload"):
            if self._vision is not None:
                try:
                    self._vision.cpu()
                except Exception as e:
                    logger.debug("Modell konnte nicht auf CPU verschoben werden: %s", e)
                del self._vision
                self._vision = None
            if self._processor is not None:
                del self._processor
                self._processor = None
            gc.collect()
            try:
                import torch  # type: ignore
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    gc.collect()
                    torch.cuda.empty_cache()
            except Exception as e:
                logger.warning("CUDA Cache-Freigabe fehlgeschlagen: %s", e)

    @property
    def is_loaded(self) -> bool:
        return self._vision is not None

    # ------------------------------------------------------------------
    # Inferenz
    # ------------------------------------------------------------------
    def embed_clip(
        self,
        video_path: Path | str,
        video_hash: str,
        scenes: Optional[list[SceneSpec]] = None,
    ) -> ClipEmbeddingResult:
        """Volle Pipeline: Frame-Sampling pro Scene → Embedding → Clip-Aggregation."""
        import cv2  # type: ignore

        with self.serializer.acquire(holder="siglip2_embed_clip"):
            self._ensure_loaded()
            assert self._vision is not None and self._processor is not None

            cap = cv2.VideoCapture(str(video_path))
            try:
                if not cap.isOpened():
                    raise IOError(f"Video nicht oeffnbar: {video_path}")
                fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
                n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if fps <= 0 or n_frames <= 0:
                    raise InvalidVideoError(f"Ungueltige Video-Metadaten: fps={fps} frames={n_frames}")
                duration = float(n_frames / fps)

                effective_scenes = scenes or [SceneSpec(start_time=0.0, end_time=duration)]
                # F-8 (B-340): keep scene<->frame alignment. Unreadable frames are
                # skipped inside _sample_frames; it returns only the scenes whose
                # frame was actually read, so zip() below cannot shift embeddings
                # onto the wrong scenes.
                sampled_scenes, frames = self._sample_frames(
                    cap, effective_scenes, fps, n_frames, cv2)

                # Batch-Inferenz mit Auto-Tuning bei OOM
                embeddings = self._embed_in_batches(frames)

                scene_embs: list[SceneEmbedding] = []
                nan_count = 0
                for spec, emb in zip(sampled_scenes, embeddings):
                    normed = _l2_normalize(emb)
                    if not np.isfinite(normed).all():
                        nan_count += 1
                        logger.warning(
                            "B-511: NaN/Inf-Werte im Scene-Embedding erkannt (Zaehler=%d). "
                            "Scene wird uebersprungen: start=%.2f, end=%.2f",
                            nan_count, spec.start_time, spec.end_time
                        )
                        continue
                    scene_embs.append(SceneEmbedding(
                        start_time=spec.start_time,
                        end_time=spec.end_time,
                        embedding=normed.astype("float32"),
                    ))

                clip_emb = self._aggregate_clip(scene_embs)
                return ClipEmbeddingResult(
                    video_hash=video_hash,
                    duration_seconds=duration,
                    fps=fps,
                    n_scenes=len(scene_embs),
                    clip_embedding=clip_emb,
                    scene_embeddings=scene_embs,
                )
            finally:
                cap.release()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _sample_frames(self, cap, scenes: list[SceneSpec], fps: float,
                       n_frames: int, cv2_mod) -> tuple[list[SceneSpec], list[np.ndarray]]:
        """Liest pro Scene den repraesentativen Frame (default: Mitte).

        Returns ``(kept_scenes, frames)`` — beide gleich lang und positionell
        ausgerichtet. Scenes mit nicht lesbarem Frame werden in BEIDEN Listen
        ausgelassen, damit der Aufrufer Scene und Embedding korrekt paaren kann
        (F-8).
        """
        kept_scenes: list[SceneSpec] = []
        frames: list[np.ndarray] = []
        for spec in scenes:
            mid_t = spec.representative_frame_time
            if mid_t is None:
                mid_t = (spec.start_time + spec.end_time) / 2.0
            frame_idx = max(0, min(n_frames - 1, int(mid_t * fps)))
            cap.set(cv2_mod.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame_bgr = cap.read()
            if not ok or frame_bgr is None:
                logger.warning("Frame %d nicht lesbar, skip Scene [%.1f, %.1f]",
                               frame_idx, spec.start_time, spec.end_time)
                continue
            # BGR → RGB fuer transformers
            frame_rgb = cv2_mod.cvtColor(frame_bgr, cv2_mod.COLOR_BGR2RGB)
            kept_scenes.append(spec)
            frames.append(frame_rgb)
        return kept_scenes, frames

    def _embed_in_batches(self, frames: list[np.ndarray]) -> list[np.ndarray]:
        if not frames:
            return []
        from PIL import Image
        import torch  # type: ignore

        pil = [Image.fromarray(f) for f in frames]
        out: list[np.ndarray] = []
        bs = self.batch_size
        i = 0
        while i < len(pil):
            chunk = pil[i:i + bs]
            try:
                inputs = self._processor(images=chunk, return_tensors="pt").to(self.device)
                with torch.no_grad():
                    res = self._vision(**inputs)
                feats = self._extract_features(res)
                for row in feats:
                    out.append(row.detach().cpu().numpy())
                i += len(chunk)
            except Exception as exc:
                if not _is_oom(exc) or bs <= MIN_BATCH_SIZE:
                    raise
                logger.warning("SigLIP-2 OOM bei batch=%d → halbiere", bs)
                bs = max(MIN_BATCH_SIZE, bs // 2)
                # cuda cache freiraeumen + retry
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
        return out

    @staticmethod
    def _extract_features(model_output) -> "Tensor":  # noqa: F821 (typing only)
        # SigLIP/SigLIP-2 Vision-Output: bevorzugt pooler_output, sonst last_hidden_state.mean
        if hasattr(model_output, "pooler_output") and model_output.pooler_output is not None:
            return model_output.pooler_output
        if hasattr(model_output, "last_hidden_state"):
            return model_output.last_hidden_state.mean(dim=1)
        raise RuntimeError(
            f"SigLIP-Output hat weder pooler_output noch last_hidden_state: "
            f"{type(model_output)}"
        )

    @staticmethod
    def _aggregate_clip(scenes: list[SceneEmbedding]) -> np.ndarray:
        if not scenes:
            raise RuntimeError("Keine Scene-Embeddings — Clip-Aggregation unmoeglich")
        weights = np.array(
            [max(0.001, s.end_time - s.start_time) for s in scenes],
            dtype="float32",
        )
        weights = weights / weights.sum()
        stacked = np.stack([s.embedding for s in scenes])  # (n, 768)
        agg = (stacked * weights[:, None]).sum(axis=0)
        return _l2_normalize(agg).astype("float32")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm < 1e-12 or not np.isfinite(norm):
        return v
    return v / norm


def _autodetect_device() -> str:
    try:
        import torch  # type: ignore
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _is_oom(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return ("outofmemory" in type(exc).__name__.lower()
            or "out of memory" in msg
            or "cuda out of memory" in msg)

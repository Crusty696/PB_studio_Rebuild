"""Video Analysis Pipeline — Phase 2, SEKTOR 1.

3-Schritt Pipeline:
  1. SceneDetect (ContentDetector) + RAFT Optical Flow Motion Score
  2. Keyframe-Extraktion (Mitte jeder Szene)
  3. SigLIP Embedding-Generierung → LanceDB

Nutzt ModelManager Singleton für VRAM-Schutz.
"""

from __future__ import annotations

import gc
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from services.timeout_constants import (
    FFMPEG_PROBE_TIMEOUT_SEC,
    FFMPEG_THUMBNAIL_TIMEOUT_SEC,
    HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC,
)

from services.ffmpeg_utils import probe_duration, subprocess_kwargs
from services.model_manager import oom_recovery
from services import analysis_status_service
from services.errors import OllamaPausedError

logger = logging.getLogger(__name__)


def _keyframe_dir() -> Path:
    """Returns keyframe directory for the current project (lazy APP_ROOT read)."""
    import database.session as _session
    return _session.APP_ROOT / "storage" / "keyframes"


@dataclass
class SceneInfo:
    """Ergebnis einer erkannten Szene."""
    index: int
    start_time: float
    end_time: float
    motion_score: float = 0.0
    motion_is_fallback: bool = False  # B3: Markiert ob Motion per CPU-Fallback berechnet wurde
    keyframe_path: str | None = None
    embedding: np.ndarray | None = None
    # AUD-128: Gemma 4 Vision captioning
    ai_caption: dict | None = None   # {description, mood, motion, tags}
    ai_mood: str | None = None       # energetic|calm|dramatic|ambient
    ai_tags: list | None = None      # ['tag1', 'tag2', ...]


@dataclass
class PipelineResult:
    """Gesamtergebnis der Video-Analyse-Pipeline."""
    video_path: str
    scenes: list[SceneInfo] = field(default_factory=list)
    total_duration: float = 0.0
    embeddings_stored: int = 0


# ======================================================================
# Schritt 1: Scene Detection + RAFT Motion
# ======================================================================

def detect_scenes(
    video_path: str,
    threshold: float = 27.0,
    min_scene_len: float = 1.0,
    fps: float = 30.0,
    progress_cb: Callable[[int, str], None] | None = None,
) -> list[SceneInfo]:
    """Erkennt Szenen mit PySceneDetect ContentDetector.

    Args:
        video_path: Pfad zum Video
        threshold: ContentDetector Schwellwert (niedriger = mehr Szenen)
        min_scene_len: Minimale Szenenlänge in Sekunden
        fps: Framerate des Videos (default 30.0)
        progress_cb: Callback(percent, message)

    Returns:
        Liste von SceneInfo mit start/end Zeiten
    """
    if progress_cb:
        progress_cb(0, "Szenen-Erkennung...")

    if not video_path or not Path(video_path).exists():
        logger.error("Video-Datei nicht gefunden: %s", video_path)
        return []

    try:
        from scenedetect import detect, ContentDetector
        from scenedetect.video_stream import VideoOpenFailure
        import logging as _logging
        # F-025 Fix: Deaktiviere pyscenedetect Info-Logs um Main-Thread zu entlasten
        _logging.getLogger("pyscenedetect").setLevel(_logging.WARNING)
    except ImportError:
        logger.warning("PySceneDetect nicht installiert — Fallback: eine Szene pro Video")
        return _fallback_single_scene(video_path)

    try:
        scene_list = detect(
            video_path,
            ContentDetector(threshold=threshold, min_scene_len=int(min_scene_len * fps)),
        )
    except VideoOpenFailure as e:
        # Bug B Fix: VideoOpenFailure ist KEIN Subclass von RuntimeError/OSError und
        # wuerde sonst den outer except in workers/video.py triggern (→ Worker-Crash,
        # QThread-Race, 0xC0000409). In RuntimeError uebersetzen, damit der existierende
        # C-04 Skip-Block in workers/video.py den Fehler pro Clip auffaengt und die
        # Pipeline weiterlaeuft.
        raise RuntimeError(
            f"Video '{Path(video_path).name}' ist beschädigt oder nicht lesbar "
            f"(z.B. fehlender moov-atom): {e}"
        ) from e
    except (OSError, IOError, ValueError, RuntimeError) as e:
        logger.error("SceneDetect Fehler: %s — Fallback", e)
        return _fallback_single_scene(video_path)

    scenes = []
    for i, (start, end) in enumerate(scene_list):
        scenes.append(SceneInfo(
            index=i,
            start_time=start.get_seconds(),
            end_time=end.get_seconds(),
        ))

    if not scenes:
        return _fallback_single_scene(video_path)

    logger.info("SceneDetect: %d Szenen erkannt in %s", len(scenes), Path(video_path).name)
    return scenes


def _load_raft_model():
    """Lädt RAFT Optical Flow Modell via ModelManager (GPU-koordiniert).

    ModelManager registriert RAFT sodass andere GPU-Konsumenten
    (SigLIP, beat_this) es automatisch entladen können.

    Returns:
        (raft_model, device) oder (None, None) bei Fehler.
    """
    try:
        from services.model_manager import GPU_LOAD_LOCK, ModelManager
        with GPU_LOAD_LOCK:
            return ModelManager().load_raft()
    except (ImportError, RuntimeError, OSError, MemoryError) as e:
        logger.warning("RAFT nicht verfügbar (%s) — nutze CPU-Fallback", e)
        return None, None


def _normalize_motion(raw_px: float) -> float:
    """Normalisiert eine rohe Flow-Magnitude (px auf 520x320) auf 0.0–1.0.

    Fixplan 2026-07-07 Schritt 1: vorher hartes ``min(1.0, raw/40)`` — auf dem
    Testmaterial saturierten damit 41/42 Szenen auf exakt 1.0 (gemessen:
    Median 156 px bei 1s-Frame-Abstand). Jetzt saettigungsfreie
    Exponential-Kurve statt Clamp: ``1 - exp(-raw/40)``. Die Frame-Paare
    werden mit fixem Zeitabstand ~1/30 s gesampelt (siehe
    compute_motion_scores), gemessene Rohwerte 14–255 px mappen damit auf
    ~0.3–1.0 mit echter Streuung (29 px Median → ~0.52).
    """
    if raw_px <= 0.0:
        return 0.0
    return round(1.0 - float(np.exp(-raw_px / 40.0)), 4)


@oom_recovery
def _raft_motion_score(
    raft_model, device, frame1_bgr: np.ndarray, frame2_bgr: np.ndarray,
) -> float:
    """Berechnet Motion-Score via RAFT auf GPU.

    Nimmt zwei BGR-Frames, skaliert auf 520x320, berechnet Optical Flow
    und gibt einen normalisierten Score (0.0 – 1.0) zurück.
    """
    import torch

    try:
        model_dtype = next(raft_model.parameters()).dtype
    except (StopIteration, AttributeError):
        model_dtype = torch.float32

    def prep(bgr: np.ndarray) -> torch.Tensor:
        rgb = bgr[..., ::-1].copy()  # BGR → RGB
        t = torch.from_numpy(rgb).permute(2, 0, 1).float()  # HWC → CHW
        # Auf 520x320 skalieren (RAFT braucht durch 8 teilbare Dimensionen)
        t = torch.nn.functional.interpolate(
            t.unsqueeze(0), size=(320, 520), mode="bilinear", align_corners=False
        )
        return t.to(device=device, dtype=model_dtype)

    img1 = prep(frame1_bgr)
    img2 = prep(frame2_bgr)

    with torch.no_grad():
        try:
            flows = raft_model(img1, img2)
        except RuntimeError as exc:
            if "not implemented for 'Half'" in str(exc):
                cpu = torch.device("cpu")
                raft_model = raft_model.float().to(cpu)
                img1 = img1.float().to(cpu)
                img2 = img2.float().to(cpu)
                try:
                    flows = raft_model(img1, img2)
                except RuntimeError as retry_exc:
                    if "not implemented for 'Half'" in str(retry_exc):
                        return _cpu_motion_score(frame1_bgr, frame2_bgr)
                    raise
            else:
                raise
        flow = flows[-1].float()  # Letzte Iteration = bester Flow
        magnitude = torch.sqrt(flow[:, 0] ** 2 + flow[:, 1] ** 2)
        raw = float(magnitude.mean().cpu())

    # Fixplan 2026-07-07 Schritt 1: saettigungsfreie Normalisierung
    # (vorher min(1.0, raw/40) → 41/42 Szenen identisch 1.0).
    return _normalize_motion(raw)


def compute_motion_scores(
    video_path: str,
    scenes: list[SceneInfo],
    progress_cb: Callable[[int, str], None] | None = None,
    raft_model_device: tuple | None = None,
) -> list[SceneInfo]:
    """Berechnet Motion-Scores via RAFT Optical Flow auf CUDA (oder CPU-Fallback).

    Args:
        raft_model_device: Optional (raft_model, device) Tupel fuer Batch-Modus.
            Wenn uebergeben, wird RAFT NICHT pro Video geladen/entladen.
    """
    if progress_cb:
        progress_cb(30, "Motion-Analyse...")

    if not video_path or not Path(video_path).exists():
        logger.error("Video-Datei nicht gefunden (Motion-Analyse abgebrochen): %s", video_path)
        return scenes

    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV nicht verfügbar — Motion-Scores bleiben 0.0")
        return scenes

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        logger.error("Video konnte nicht geöffnet werden: %s", video_path)
        return scenes

    _owns_raft = False  # Ob WIR RAFT geladen haben (dann muessen wir es entladen)
    raft_model = None
    use_raft = False
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        if raft_model_device is not None:
            raft_model, raft_device = raft_model_device
        else:
            raft_model, raft_device = _load_raft_model()
            _owns_raft = True
        use_raft = raft_model is not None

        # Fixplan 2026-07-07 Schritt 1: Frame-Paare mit fixem Zeitabstand
        # ~1/30 s (Literatur-Standard: consecutive frames). Vorher lagen die
        # zwei Sample-Frames 1 s auseinander → Flow-Magnituden 41–397 px →
        # alle Szenen saturierten auf motion=1.0 (gemessen auf Testmaterial).
        frame_step = max(1, int(round(fps / 30.0)))

        for scene in scenes:
            start_frame = int(scene.start_time * fps)
            end_frame = int(scene.end_time * fps)
            span = max(1, end_frame - start_frame)

            # 3 Messpaare bei 25 % / 50 % / 75 % der Szene; Median ist robust
            # gegen Ausreisser (Schnitt-Frames, RAFT-Fehlmessungen).
            anchor_frames = sorted({
                min(max(start_frame, start_frame + int(span * frac)),
                    max(start_frame, end_frame - 1 - frame_step))
                for frac in (0.25, 0.5, 0.75)
            })

            pair_scores: list[float] = []
            is_fallback = not use_raft
            for fnum in anchor_frames:
                pair = []
                for f in (fnum, fnum + frame_step):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
                    ret, frame = cap.read()
                    if ret:
                        pair.append(frame)
                if len(pair) != 2:
                    continue
                if use_raft:
                    try:
                        pair_scores.append(_raft_motion_score(
                            raft_model, raft_device, pair[0], pair[1]))
                    except (RuntimeError, OSError) as e:
                        logger.warning(
                            "RAFT Fehler bei Szene %d: %s — CPU-Fallback",
                            scene.index, e)
                        pair_scores.append(_cpu_motion_score(pair[0], pair[1]))
                        is_fallback = True
                else:
                    pair_scores.append(_cpu_motion_score(pair[0], pair[1]))
                # F-019 Fix: Frame-Buffer sofort freigeben
                pair.clear()

            if pair_scores:
                scene.motion_score = round(float(np.median(pair_scores)), 4)
                scene.motion_is_fallback = is_fallback
                logger.debug(
                    "Motion Szene %d: pairs=%s median=%.4f (fallback=%s, step=%d)",
                    scene.index, [f"{s:.3f}" for s in pair_scores],
                    scene.motion_score, scene.motion_is_fallback, frame_step)
            else:
                scene.motion_score = 0.0
                scene.motion_is_fallback = is_fallback

            # Periodischer VRAM-Cleanup NUR wenn wir RAFT selbst geladen haben.
            # Im Batch-Modus (raft_model_device uebergeben) KEIN empty_cache() —
            # das korrumpiert den Heap wenn SigLIP/RAFT noch resident sind (0xC0000374).
            if use_raft and _owns_raft and scene.index % 8 == 7:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
    finally:
        cap.release()
        # RAFT nur entladen wenn WIR es geladen haben (nicht im Batch-Modus)
        # M-13 Fix: Only unload if RAFT is still current (avoid evicting concurrent model)
        if _owns_raft and use_raft and raft_model is not None:
            from services.model_manager import ModelManager
            try:
                mgr = ModelManager()
                # B-194: RAFT lebt jetzt im aux-Slot (siehe model_manager.py).
                # ``unload_raft()`` ist idempotent und faesst main (z.B. SigLIP)
                # bewusst nicht an.
                mgr.unload_raft()
                logger.info("RAFT entladen via ModelManager.unload_raft()")
            except (RuntimeError, AttributeError) as exc:
                logger.warning("ModelManager.unload_raft() failed after RAFT cleanup: %s", exc)
            raft_model = None  # Lokale Referenz freigeben

    logger.info("Motion-Scores berechnet für %d Szenen (%s)", len(scenes),
                "RAFT/CUDA" if use_raft else "CPU-Fallback")
    return scenes


def _cpu_motion_score(frame1_bgr: np.ndarray, frame2_bgr: np.ndarray) -> float:
    """CPU-Fallback: Frame-Differenz-basierter Motion-Score.

    B3: Skalenkonsistent zu RAFT mittels exponentialer Normalisierung.
    """
    import cv2

    gray1 = cv2.cvtColor(frame1_bgr, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2_bgr, cv2.COLOR_BGR2GRAY)
    # Auf 320px Breite skalieren für Speed
    h, w = gray1.shape
    if w > 320:
        scale = 320 / w
        gray1 = cv2.resize(gray1, (320, int(h * scale)))
        gray2 = cv2.resize(gray2, (320, int(h * scale)))
    diff = np.abs(gray1.astype(np.float32) - gray2.astype(np.float32))
    raw_score = float(np.mean(diff)) / 255.0
    # Skalenkonsistent zu RAFT (1 - exp(-x / 40.0) mit Median ~0.52 bei raw_px=29)
    # raw_score 0.05 entspricht typischer mittlerer Helligkeitsaenderung.
    # 1 - exp(-0.05 * 15) = 0.52 -> K=15 passt perfekt.
    return round(1.0 - float(np.exp(-raw_score * 15.0)), 4)


def _fallback_single_scene(video_path: str) -> list[SceneInfo]:
    """Fallback: Ganzes Video als eine Szene."""
    duration = _get_video_duration(video_path)
    return [SceneInfo(index=0, start_time=0.0, end_time=duration)]


def _get_video_duration(video_path: str) -> float:
    """Ermittelt Video-Dauer via ffprobe."""
    from services.startup_checks import get_ffprobe_bin
    ffprobe_bin = get_ffprobe_bin()

    try:
        return probe_duration(
            video_path, fallback=60.0,
            timeout=FFMPEG_PROBE_TIMEOUT_SEC, ffprobe_bin=ffprobe_bin,
        )
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        logger.warning("ffprobe Dauer-Abfrage fehlgeschlagen für '%s': %s", video_path, e)
    return 60.0


# ======================================================================
# Schritt 2: Keyframe Extraktion
# ======================================================================

def extract_keyframes(
    video_path: str,
    scenes: list[SceneInfo],
    output_dir: Path | None = None,
    progress_cb: Callable[[int, str], None] | None = None,
) -> list[SceneInfo]:
    """Extrahiert einen Keyframe pro Szene (Mitte der Szene).

    Verwendet FFmpeg für schnelle, GPU-unabhängige Extraktion.
    """
    if progress_cb:
        progress_cb(50, "Keyframes extrahieren...")

    if not video_path or not Path(video_path).exists():
        logger.error("Video-Datei nicht gefunden (Keyframe-Extraktion abgebrochen): %s", video_path)
        return scenes

    from services.startup_checks import get_ffmpeg_bin
    ffmpeg_bin = get_ffmpeg_bin()

    out_dir = output_dir or _keyframe_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    video_stem = Path(video_path).stem

    def _extract_one(scene: SceneInfo) -> None:
        """Extrahiert Keyframe für eine Szene (mutiert scene.keyframe_path)."""
        # Keyframe in der Mitte der Szene
        mid_time = (scene.start_time + scene.end_time) / 2.0
        kf_path = out_dir / f"{video_stem}_scene{scene.index:04d}.jpg"

        if kf_path.exists():
            scene.keyframe_path = str(kf_path)
            return

        cmd = [
            ffmpeg_bin, "-y", "-ss", str(mid_time),
            "-i", video_path,
            "-frames:v", "1",
            "-vf", "scale=384:384:force_original_aspect_ratio=decrease,pad=384:384:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "2",
            "-v", "quiet",
            str(kf_path),
        ]

        kwargs = subprocess_kwargs()

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_THUMBNAIL_TIMEOUT_SEC,
                                    stdin=subprocess.DEVNULL, **kwargs)
            if kf_path.exists():
                scene.keyframe_path = str(kf_path)
            else:
                stderr = (result.stderr or b"")[:200]
                logger.warning("Keyframe-Extraktion fehlgeschlagen: Szene %d (rc=%d, %s)",
                               scene.index, result.returncode, stderr)
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logger.warning("Keyframe-Fehler Szene %d: %s", scene.index, e)

    # E10: Szenen sind unabhängig — ffmpeg-Spawns parallelisieren.
    # max_workers=4 fest gemaess E10-Plan.
    # Ergebnisse werden in-place auf den scene-Objekten gesetzt; die
    # Rückgabe-Liste `scenes` behält damit die ursprüngliche Reihenfolge.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_extract_one, scene) for scene in scenes]
        for future in futures:
            future.result()

    extracted = sum(1 for s in scenes if s.keyframe_path)
    logger.info("Keyframes extrahiert: %d/%d", extracted, len(scenes))
    return scenes


# ======================================================================
# Schritt 3: SigLIP Embeddings → LanceDB
# ======================================================================

@oom_recovery
def generate_embeddings(
    scenes: list[SceneInfo],
    progress_cb: Callable[[int, str], None] | None = None,
    siglip_model_processor: tuple | None = None,
) -> list[SceneInfo]:
    """Generiert SigLIP 1152-dim Embeddings aus Keyframes.

    Nutzt ModelManager Singleton für VRAM-Schutz.
    Scenes ohne Keyframe werden übersprungen.

    Args:
        siglip_model_processor: Optional (model, processor) Tupel für Batch-Modus.
            Wenn übergeben, wird SigLIP NICHT geladen/entladen (Caller ist verantwortlich).
            Spart 5-15s pro Video bei Batch-Verarbeitung.
    """
    if progress_cb:
        progress_cb(65, "SigLIP Embeddings generieren...")

    keyframe_scenes = [s for s in scenes if s.keyframe_path and Path(s.keyframe_path).exists()]
    if not keyframe_scenes:
        logger.warning("Keine Keyframes vorhanden — keine Embeddings generiert")
        return scenes

    from services.model_manager import ModelManager
    mm = ModelManager()

    # Batch-Modus: SigLIP wurde vom Caller vorgeladen → wiederverwenden.
    # In dem Fall hält der Caller bereits GPU_EXECUTION_LOCK
    # (workers/video.py:VideoAnalysisPipelineWorker.run).
    owns_model = siglip_model_processor is None
    if siglip_model_processor is not None:
        model, processor = siglip_model_processor
        logger.info("[SIGLIP] Verwende vorgeladenes SigLIP Modell (Batch-Modus)")
    else:
        logger.info("[SIGLIP] Lade SigLIP Modell...")
        from services.model_manager import GPU_LOAD_LOCK

        # Robust: Torch explizit laden bevor mm.load_siglip gerufen wird (HF Fix)
        import torch

        try:
            with GPU_LOAD_LOCK:
                model, processor = mm.load_siglip()

            if model is None or processor is None:
                raise RuntimeError("Modell oder Processor konnte nicht geladen werden")

            logger.info("[SIGLIP] SigLIP geladen auf %s", mm.device)
        except Exception as e:  # broad catch intentional — MLModelNotFoundError, OOM, ImportError, RuntimeError
            from services.errors import MLModelNotFoundError
            error_msg = str(e)
            if "PyTorch library but it was not found" in error_msg:
                logger.error("[SIGLIP] HuggingFace findet Torch nicht (Version-Mismatch). Überspringe Embeddings.")
            elif isinstance(e, MLModelNotFoundError):
                logger.warning("[SIGLIP] SigLIP nicht heruntergeladen: %s", e)
            else:
                logger.error("[SIGLIP] SigLIP FEHLER: %s", e)
            return scenes

    import torch
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    from services.model_manager import GPU_EXECUTION_LOCK

    def _load_image(scene):
        """Lädt ein Keyframe-Bild (I/O-bound, parallelisierbar)."""
        try:
            return scene, Image.open(scene.keyframe_path).convert("RGB")
        except (OSError, IOError, ValueError) as e:
            logger.warning("Bild konnte nicht geladen werden: %s — %s", scene.keyframe_path, e)
            return scene, None

    # B-068: Inferenz unter GPU_EXECUTION_LOCK schützt gegen Modell-Eviction
    # während laufender Inferenz (z.B. wenn parallel beat_this/RAFT geladen
    # werden und H17-Fix SigLIP auf CPU schiebt). RLock erlaubt re-entry,
    # damit der Batch-Worker (workers/video.py) den Lock bereits halten darf.
    # Batch-Verarbeitung in Gruppen von 8 (VRAM-schonend für GTX 1060)
    batch_size = 8
    with GPU_EXECUTION_LOCK:
        for batch_start in range(0, len(keyframe_scenes), batch_size):
            batch = keyframe_scenes[batch_start:batch_start + batch_size]

            # Paralleles Laden der Bilder (I/O-bound → ThreadPool)
            images = []
            valid_scenes = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                for scene, img in pool.map(_load_image, batch):
                    if img is not None:
                        images.append(img)
                        valid_scenes.append(scene)

            if not images:
                continue

            try:
                inputs = processor(images=images, return_tensors="pt", padding=True)
                inputs = {k: v.to(mm.device) for k, v in inputs.items()}
                model_dtype = next(model.parameters()).dtype
                inputs = {k: (v.to(model_dtype) if v.is_floating_point() else v) for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = model.get_image_features(**inputs)
                    # Robust: handle both raw tensor and BaseModelOutputWithPooling
                    if not isinstance(outputs, torch.Tensor):
                        outputs = outputs.pooler_output if hasattr(outputs, 'pooler_output') else outputs[0]
                    # L2-Normalisierung
                    embeddings = outputs / outputs.norm(p=2, dim=-1, keepdim=True)
                    embeddings = embeddings.cpu().numpy().astype(np.float32)

                nan_count = 0
                for i, scene in enumerate(valid_scenes):
                    emb = embeddings[i]
                    if not np.isfinite(emb).all():
                        nan_count += 1
                        logger.warning(
                            "B-511: Video-Analyse Batch-Embedding enthaelt NaN/Inf (Zaehler=%d). "
                            "Scene wird uebersprungen: %s", nan_count, scene
                        )
                        continue
                    scene.embedding = emb

                # F-019 Fix: Explicit cleanup to prevent unbounded memory growth
                del inputs, outputs, embeddings
                images.clear()
                valid_scenes.clear()

            except RuntimeError as batch_err:
                torch.cuda.empty_cache()
                gc.collect()
                # B-194: ``RuntimeError`` ist NICHT immer OOM — z.B. ein
                # Mixed-Device-Error (Modell auf CPU, Inputs auf CUDA) wird
                # ebenfalls hier gefangen. Vorher pauschal als "OOM" geloggt
                # → grosse Mis-Diagnose. Wir unterscheiden jetzt anhand der
                # Fehlermeldung.
                _err_lower = str(batch_err).lower()
                _is_oom = "out of memory" in _err_lower or "cuda" in _err_lower and "memory" in _err_lower
                if _is_oom:
                    logger.warning(
                        "OOM bei SigLIP Batch (size=%d) — Retry einzeln...", len(images)
                    )
                else:
                    logger.warning(
                        "RuntimeError bei SigLIP Batch (size=%d) — Retry einzeln (%s)...",
                        len(images), batch_err,
                    )
                for j, (img, scene) in enumerate(zip(images, valid_scenes)):
                    try:
                        # B-154: VOR jedem Einzel-Call empty_cache, sonst kaskadiert
                        # OOM weil per-sample Memory zwischen Iterationen nicht
                        # freigegeben wurde. Adaptive-Retry war bisher no-op.
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        inp = processor(images=[img], return_tensors="pt", padding=True)
                        inp = {k: v.to(mm.device) for k, v in inp.items()}
                        model_dtype = next(model.parameters()).dtype
                        inp = {k: (v.to(model_dtype) if v.is_floating_point() else v) for k, v in inp.items()}
                        with torch.no_grad():
                            out = model.get_image_features(**inp)
                            if not isinstance(out, torch.Tensor):
                                out = out.pooler_output if hasattr(out, 'pooler_output') else out[0]
                            emb = out / out.norm(p=2, dim=-1, keepdim=True)
                            emb_np = emb.cpu().numpy().astype(np.float32)[0]
                            if not np.isfinite(emb_np).all():
                                logger.warning(
                                    "B-511: Video-Analyse Einzel-Embedding enthaelt NaN/Inf. "
                                    "Scene wird uebersprungen: %s", scene
                                )
                            else:
                                scene.embedding = emb_np
                        del inp, out, emb
                    except RuntimeError as single_err:
                        torch.cuda.empty_cache()
                        # B-194: Auch hier: nicht jeden RuntimeError als OOM loggen.
                        _se_lower = str(single_err).lower()
                        _se_oom = "out of memory" in _se_lower or ("cuda" in _se_lower and "memory" in _se_lower)
                        if _se_oom:
                            logger.error("OOM auch bei Einzel-Inference — ueberspringe Bild %d", j)
                        else:
                            logger.error(
                                "RuntimeError bei Einzel-Inference Bild %d — ueberspringe (%s)",
                                j, single_err,
                            )
                # F-019 Fix: Clear buffers after OOM recovery
                images.clear()
                valid_scenes.clear()
            except (RuntimeError, ValueError, AttributeError) as e:
                logger.error("SigLIP Embedding-Fehler: %s", e)
                # F-019 Fix: Clear buffers on exception
                images.clear()
                valid_scenes.clear()

            # Inter-batch GPU-Cleanup NUR wenn wir SigLIP selbst geladen haben.
            # Im Batch-Modus (siglip_model_processor uebergeben) KEIN empty_cache() —
            # das korrumpiert den Heap wenn Modelle noch resident sind (0xC0000374).
            if owns_model and torch.cuda.is_available():
                torch.cuda.empty_cache()

    # SigLIP nur entladen wenn WIR es geladen haben (nicht im Batch-Modus)
    if owns_model:
        mm.unload()

    embedded = sum(1 for s in scenes if s.embedding is not None)
    logger.info("SigLIP Embeddings generiert: %d/%d", embedded, len(scenes))
    return scenes


# ======================================================================
# Schritt 4: Gemma Vision Captioning (AUD-128)
# ======================================================================

# Ollama-Modell für Vision-Captioning (muss Vision-fähig sein)
# Fixplan 2026-07-07 (User-Auftrag): ``gemma4:e4b`` ist inzwischen ein
# offizieller multimodaler Ollama-Tag (Vision + Tool-Calling, Edge-Klasse)
# und ersetzt moondream als Default — moondream (1.8B) halluzinierte auf
# komplexen Szenen und lieferte mood=NULL/Junk-Captions (real gemessen,
# 42/42 Szenen im final-check-Projekt). Prioritaet: bestes installiertes
# Modell zuerst, moondream nur noch Not-Fallback.
# Caller koennen ``vision_model`` Parameter explizit ueberschreiben
# (z.B. ueber Settings oder PB_VISION_MODEL env-var).
_VISION_MODEL = "gemma4:e4b"
_VISION_MODEL_CANDIDATES = [
    "gemma4:e4b",
    "gemma4:e2b",
    "qwen3-vl:4b",
    "qwen2.5vl:3b",
    "gemma3:4b",
    "openbmb/minicpm-o2.6:latest",
    "moondream:latest",
    "moondream:1.8b",
]

_CAPTION_SYSTEM_PROMPT = """\
You are a video scene analyzer for a DJ/music video editor.
Analyze the provided keyframe(s) and respond with EXACTLY ONE JSON object.
Do not write any text before or after the JSON. Do not use markdown fences.
Do not explain. Output ONLY the JSON object.

Schema (all four fields required):
{"description": "...", "mood": "...", "motion": "...", "tags": [...]}

Field rules:
- description: 1-2 short English sentences describing what is visible
- mood: one of energetic, calm, dramatic, ambient
- motion: one of static, slow, medium, fast
- tags: 3 to 6 short lowercase strings

Example:
{"description": "A lone dancer silhouetted against pulsing red strobe lights.", "mood": "energetic", "motion": "fast", "tags": ["dancer", "strobe", "club", "silhouette"]}
"""

_CAPTION_USER_PROMPT = "Describe this scene as JSON. Reply with the JSON object only."
_CAPTION_PLAIN_TEXT_FALLBACK_PROMPT = "Describe this scene in one short sentence."


def get_ollama_client():
    from services.ollama_client import get_ollama_client as _get_ollama_client
    return _get_ollama_client()


def _ollama_model_exists(client, model: str) -> bool:
    try:
        return bool(client.model_exists(model))
    except AttributeError:
        pass
    try:
        return model in set(client.list_models())
    except AttributeError:
        # B-360: client exposes neither model_exists nor list_models — model
        # presence cannot be verified. Treat as not-confirmed so the caller
        # falls back to the requested model instead of raising AttributeError.
        return False


def _resolve_vision_caption_model(client, requested_model: str) -> str:
    """Choose an installed vision-capable Ollama model for captioning.

    Reihenfolge:
    1. ``PB_VISION_MODEL`` env-var, wenn installiert
    2. Auto-Auswahl ``select_best_model("vision")``: bestes installiertes
       Vision-faehiges Modell das in den VRAM (GTX 1060, 6 GB) passt
    3. Fallback: ``requested_model`` bzw. feste ``_VISION_MODEL_CANDIDATES``
    """
    import os

    env_model = os.environ.get("PB_VISION_MODEL")
    if env_model and _ollama_model_exists(client, env_model):
        return env_model

    # B-650: per-Aufgabe-Router bevorzugt Vision-First-Modelle (qwen3-vl vor
    # gemma3:4b — gemma3 kann zwar vision, ist aber ein Text-Modell). Faellt
    # auf select_best_model("vision") zurueck.
    try:
        from services.model_router import resolve_model_for_task
        best = resolve_model_for_task(client, "caption")
    except Exception:
        try:
            best = client.select_best_model("vision")
        except AttributeError:
            best = None
    if best:
        if best != requested_model:
            logger.info("[CAPTION] Auto-Vision-Modell '%s' (statt Default '%s').",
                        best, requested_model)
        return best

    # Fallback: feste Kandidaten-Reihenfolge.
    candidates: list[str] = []
    for model in (requested_model, *_VISION_MODEL_CANDIDATES):
        if model and model not in candidates:
            candidates.append(model)
    for model in candidates:
        if _ollama_model_exists(client, model):
            if model != requested_model:
                logger.warning(
                    "[CAPTION] Vision-Modell '%s' nicht installiert; nutze '%s'.",
                    requested_model,
                    model,
                )
            return model

    return requested_model


_CAPTION_JUNK_MARKERS = (
    '"type"', "'type'", '"url"', "'url'", "file:///", '"size"', '"format"',
    '"quality"', '"encoding"', '"timestamp"', '.jpeg', '.jpg', '.png',
)


def _caption_text_is_plausible(text: str) -> bool:
    """Prueft ob ein Caption-Text eine natuerlichsprachliche Beschreibung ist.

    Fixplan 2026-07-07 Schritt 2: Vision-Modelle (Ollama) echoen teils
    Bild-Metadaten-JSON ('{"type": "image/jpeg", "url": ...}') statt einer
    Beschreibung. Solcher Muell wurde bisher ungeprueft in scenes.ai_caption
    gespeichert und vergiftete Mood-Matching + semantische Suche.
    """
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if len(t) < 15:
        return False
    # JSON-/Struktur-Echo statt Prosa
    if t.startswith("[") or t.startswith("{"):
        return False
    low = t.lower()
    if any(m in low for m in _CAPTION_JUNK_MARKERS):
        return False
    # Mindestens 3 Woerter mit Buchstaben (Prosa-Heuristik)
    alpha_words = [w for w in t.split() if any(c.isalpha() for c in w)]
    return len(alpha_words) >= 3


def _validate_caption_dict(parsed) -> dict | None:
    """Validiert das geparste Caption-Dict; None = unbrauchbar (Junk).

    Akzeptiert nur Dicts mit plausibler natuerlichsprachlicher description.
    Reine Metadaten-Dicts ({"type": "image/jpeg", "url": ...} oder
    Koordinaten {"x":..,"y":..}) haben keine/keine plausible description und
    fallen durch.
    """
    if not isinstance(parsed, dict):
        return None
    desc = parsed.get("description")
    if not _caption_text_is_plausible(desc if isinstance(desc, str) else ""):
        return None
    return parsed


def analyze_scene_with_caption(
    scenes: list[SceneInfo],
    progress_cb: Callable[[int, str], None] | None = None,
    vision_model: str = _VISION_MODEL,
    caption_failure_state: dict[str, int] | None = None,
) -> list[SceneInfo]:
    """Analysiert Szenen mit Gemma Vision und befüllt ai_caption, ai_mood, ai_tags.

    Schritt 4 der Pipeline: SceneDetect → RAFT → SigLIP → Gemma Caption (dieser Step).
    Nutzt OllamaClient für multimodales Inference via base64-codierten Keyframes.
    Max. 3 Keyframes pro Szene werden übergeben.

    Graceful degradation: Wenn Ollama nicht erreichbar → Warning, skip, Pipeline läuft weiter.

    Args:
        scenes: Liste von SceneInfo mit keyframe_path gesetzt
        progress_cb: Callback(percent, message)
        vision_model: Ollama-Modellname (Standard: gemma3:4b)

    Returns:
        scenes mit befüllten ai_caption / ai_mood / ai_tags Feldern
    """
    if progress_cb:
        progress_cb(85, "Gemma 4 Vision Captioning...")

    keyframe_scenes = [s for s in scenes if s.keyframe_path and Path(s.keyframe_path).exists()]
    if not keyframe_scenes:
        logger.info("[CAPTION] Keine Keyframes vorhanden — Caption-Schritt übersprungen")
        return scenes

    from services.ollama_service import OllamaService
    svc = OllamaService.get()
    
    if not svc.is_ready:
        logger.warning(
            "[CAPTION] Ollama nicht erreichbar — Vision-Captioning übersprungen. "
            "Modell: %s", vision_model
        )
        return scenes

    client = get_ollama_client()

    if client.is_paused:
        logger.info("[CAPTION] Ollama ist pausiert (GPU-Task aktiv) — überspringe Captions.")
        return scenes

    vision_model = _resolve_vision_caption_model(client, vision_model)

    logger.info("[CAPTION] Starte Vision-Captioning für %d Szenen mit '%s' via OllamaService...",
                len(keyframe_scenes), vision_model)

    import json
    import re as _re

    # B-195: Circuit-Breaker — wenn das Ollama-Modell konstant fehlschlaegt
    # (typisch: 404 weil nicht installiert), stoppe nach N consecutive Errors
    # statt fuer jede Szene 15s in den httpx-Timeout zu rennen. Bei 218
    # Videos a 15s wuerden sonst stundenlange Hintergrund-Hangs entstehen.
    _CAPTION_FAIL_THRESHOLD = 3
    _FAILURE_STATE_KEY = "consecutive_failures"
    _consecutive_failures = (
        int(caption_failure_state.get(_FAILURE_STATE_KEY, 0))
        if caption_failure_state is not None
        else 0
    )
    if _consecutive_failures >= _CAPTION_FAIL_THRESHOLD:
        logger.error(
            "[CAPTION] Batch-Circuit bereits offen (%d Fehler) — "
            "Vision-Captioning fuer %d Szenen uebersprungen.",
            _consecutive_failures,
            len(keyframe_scenes),
        )
        return scenes

    for scene in keyframe_scenes:
        # B-034 Fix: Check pause state in loop to handle GPU operations starting mid-captioning
        if client.is_paused:
            logger.debug("[CAPTION] Szene %d: Ollama pausiert — überspringe verbleibende Szenen", scene.index)
            break

        try:
            # Fixplan 2026-07-07: _CAPTION_SYSTEM_PROMPT (JSON-Schema +
            # Feld-Regeln) war toter Code — der Vision-Call sendete nur den
            # duerren User-Prompt, weshalb Modelle beliebige JSON-Strukturen
            # halluzinierten (real gemessen: Metadaten-Echos, Fremd-Schemata).
            # OllamaService.vision() hat keinen system-Parameter, daher wird
            # das Schema dem Prompt vorangestellt.
            raw = svc.vision(
                image_paths=[scene.keyframe_path],
                prompt=f"{_CAPTION_SYSTEM_PROMPT}\n\n{_CAPTION_USER_PROMPT}",
                model=vision_model,
                # Fix 2026-07-17: 256 war zu wenig fuer Thinking-Modelle. qwen3-vl
                # denkt im 'thinking'-Feld und verbrauchte das ganze 256-Budget ->
                # content blieb LEER (done_reason=length) -> Caption scheiterte. Mit
                # 1024 passt Denken + JSON (~12s auf GPU/0.21.2, verifiziert). Das
                # alte 256-Limit war ein CPU-Era-Workaround. think:false wird von
                # qwen3-vl ignoriert, daher hilft nur mehr Token-Budget.
                num_predict=1024,
                read_timeout_s=HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC,
                task="caption",  # B-650: Status-Feld zeigt "caption" + Modell
            )
            if not raw.strip():
                logger.info(
                    "[CAPTION] Szene %d: Modell '%s' lieferte leere JSON-Antwort — "
                    "retry mit Plain-Text-Prompt.",
                    scene.index, vision_model,
                )
                raw = svc.vision(
                    image_paths=[scene.keyframe_path],
                    prompt=_CAPTION_PLAIN_TEXT_FALLBACK_PROMPT,
                    model=vision_model,
                    read_timeout_s=HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC,
                    task="caption",  # B-650
                )

            # B-195: ``OllamaService.vision()`` returnt bei HTTP-Error
            # einen ``"Fehler: <code>"``-String statt zu raisen. Wir
            # erkennen das hier und behandeln es wie eine Exception
            # (Circuit-Breaker greift).
            if raw.startswith("Fehler:") or raw.startswith("Fehler "):
                raise RuntimeError(f"Ollama Vision: {raw}")

            cleaned = raw.strip()
            if "```" in cleaned:
                fence = _re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, _re.DOTALL)
                if fence:
                    cleaned = fence.group(1).strip()
            elif "{" in cleaned:
                cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}")+1]

            # B-249: Tolerant-Parsing. Wenn das Vision-Modell freien Text
            # liefert statt JSON (typisch fuer Moondream / kleinere Vision-LLMs
            # die das Schema ignorieren), dann den Plain-Text als
            # ``description`` uebernehmen statt die Szene zu skippen.
            # Damit erreichen wir 100 % Pipeline-Coverage auch ohne
            # mood/motion/tags — User sieht zumindest die Beschreibung.
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                fallback_text = raw.strip()
                if fallback_text:
                    parsed = {
                        "description": fallback_text[:500],
                        "mood": None,
                        "motion": None,
                        "tags": [],
                    }
                    logger.info(
                        "[CAPTION] Szene %d: Plain-Text-Fallback (Modell '%s' lieferte "
                        "kein JSON), %d Zeichen description.",
                        scene.index, vision_model, len(parsed["description"]),
                    )
                else:
                    raise  # leerer Response -> echter Fehler, Circuit-Breaker greift

            # Fixplan 2026-07-07 Schritt 2: Plausibilitaets-Validierung.
            # Vision-Modelle echoen teils Bild-Metadaten-JSON statt einer
            # Beschreibung — sowas darf nicht in scenes.ai_caption landen.
            valid = _validate_caption_dict(parsed)
            if valid is None:
                logger.warning(
                    "[CAPTION] Szene %d: Antwort verworfen (Metadaten-Echo/"
                    "keine plausible description) — Retry mit Plain-Text-Prompt. "
                    "Anfang: %r", scene.index, str(cleaned)[:80],
                )
                retry_raw = svc.vision(
                    image_paths=[scene.keyframe_path],
                    prompt=_CAPTION_PLAIN_TEXT_FALLBACK_PROMPT,
                    model=vision_model,
                    read_timeout_s=HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC,
                    task="caption",  # B-650
                ).strip()
                if _caption_text_is_plausible(retry_raw):
                    valid = {
                        "description": retry_raw[:500],
                        "mood": None,
                        "motion": None,
                        "tags": [],
                    }
                else:
                    logger.warning(
                        "[CAPTION] Szene %d: auch Plain-Text-Retry unbrauchbar "
                        "— Szene bleibt ohne Caption.", scene.index,
                    )

            if valid is not None:
                scene.ai_caption = valid
                scene.ai_mood = valid.get("mood")
                scene.ai_tags = valid.get("tags", []) or []
                logger.debug(
                    "[CAPTION] Szene %d: mood=%s",
                    scene.index, scene.ai_mood,
                )
                _consecutive_failures = 0
                if caption_failure_state is not None:
                    caption_failure_state[_FAILURE_STATE_KEY] = 0

        except OllamaPausedError:
            # B-146 Fix: explizite Pause-Exception statt fragiler
            # String-Match auf "pausiert"/"paused". Ollama wird per
            # ModelManager pausiert wenn GPU-intensive Operationen
            # starten — kein Caption-Crash, sauberer Abbruch.
            logger.debug(
                "[CAPTION] Szene %d: Ollama pausiert — Caption-Loop abgebrochen",
                scene.index,
            )
            break
        except Exception as e:
            # Fallback fuer alte Ollama-Server die OllamaPausedError noch
            # nicht raisen (string-basierte Heuristik bleibt als Safety-Net).
            if "pausiert" in str(e).lower() or "paused" in str(e).lower():
                logger.debug("[CAPTION] Szene %d: Ollama pausiert (legacy string-match) — Abbruch", scene.index)
                break
            logger.warning("[CAPTION] Szene %d: Fehler: %s — übersprungen", scene.index, e)
            _consecutive_failures += 1
            if caption_failure_state is not None:
                caption_failure_state[_FAILURE_STATE_KEY] = _consecutive_failures
            # B-195: Circuit-Breaker fuer dauerhaft scheiternde Modelle
            # (z.B. nicht installiertes Ollama-Modell → 404 in Schleife).
            if _consecutive_failures >= _CAPTION_FAIL_THRESHOLD:
                logger.error(
                    "[CAPTION] %d aufeinanderfolgende Fehler — Caption-Loop "
                    "abgebrochen (Modell '%s' wahrscheinlich nicht installiert "
                    "oder Ollama-Service down). Pipeline laeuft ohne Captions weiter.",
                    _consecutive_failures, vision_model,
                )
                break

    captioned = sum(1 for s in scenes if s.ai_caption is not None)
    logger.info("[CAPTION] Vision-Captioning abgeschlossen: %d/%d Szenen", captioned, len(scenes))
    return scenes


def store_embeddings(
    video_path: str,
    scenes: list[SceneInfo],
    video_clip_id: int,
) -> int:
    """Speichert Embeddings in LanceDB via VectorDBService.

    Returns:
        Anzahl der gespeicherten Embeddings
    """
    from services.vector_db_service import VectorDBService

    vdb = VectorDBService()
    logger.info("[VectorDB] count=%d", vdb.count())

    # B-148 Fix: clip_id-basiertes Loeschen statt Path-basiert. Wenn der
    # User die Quell-Datei umbenennt/verschiebt, ist der Path-Key obsolet
    # und alte Embeddings haengen forever in VectorDB. clip_id ist
    # immutable — Rename-immune.
    try:
        vdb.delete_by_clip_ids([video_clip_id])
    except (OSError, RuntimeError, ValueError) as e:
        logger.exception(
            "VectorDB delete_by_clip_ids fehlgeschlagen fuer Clip %d; "
            "Embedding-Write abgebrochen, um stale Rows zu vermeiden.",
            video_clip_id,
        )
        raise RuntimeError(
            f"VectorDB cleanup failed for clip {video_clip_id}; embeddings not stored."
        ) from e

    entries = []
    for scene in scenes:
        if scene.embedding is None:
            continue

        entries.append({
            "video_path": video_path,
            "scene_index": scene.index,
            "scene_start": scene.start_time,
            "scene_end": scene.end_time,
            "motion_score": scene.motion_score,
            "description": "",
            "embedding": scene.embedding.tolist(),
        })

    if entries:
        logger.info("[VectorDB] add_embeddings_batch (%d entries) fuer Clip %d...", len(entries), video_clip_id)
        vdb.add_embeddings_batch(video_clip_id, entries)
        logger.info("[VectorDB] %d Embeddings gespeichert fuer %s", len(entries), Path(video_path).name)

    return len(entries)


def _current_db_url() -> str:
    """B-490 Followup (CRF-005): aktuelle Projekt-Identitaet als Engine-URL.

    Robustester vorhandener Anker fuer "welches Projekt ist aktiv": die
    SQLite-URL der globalen Engine (eindeutig pro Projektordner, wird bei
    ``set_project()`` via EngineProxy.swap() ausgetauscht).
    """
    from database.session import engine
    return str(engine.url)


def store_scenes_in_db(
    video_clip_id: int,
    scenes: list[SceneInfo],
    expected_db_url: str | None = None,
) -> bool:
    """Speichert erkannte Szenen in der SQLite-DB (NullPool).

    Args:
        expected_db_url: B-490 Followup (CRF-005) — Projekt-Token vom
            Pipeline-Start (``_current_db_url()``). Wenn gesetzt und die
            aktive Engine-URL davon abweicht (Projektwechsel mid-run),
            wird NICHT gespeichert.

    Returns:
        True wenn die Szenen gespeichert wurden, False bei Skip
        (VideoClip fehlt in aktiver DB oder Projekt-Mismatch). Caller
        muessen bei False ``mark_error`` statt ``mark_done`` setzen.
    """
    from database import nullpool_session, Scene, VideoClip

    # B-490 Followup (CRF-005): Projekt-Token-Check VOR dem DB-Zugriff.
    # Ohne diesen Check konnte ein mid-run Projektwechsel dazu fuehren,
    # dass clip_id zufaellig auch im NEUEN Projekt existiert und die
    # Szenen still in die falsche Projekt-DB geschrieben wurden.
    if expected_db_url is not None:
        active_url = _current_db_url()
        if active_url != expected_db_url:
            logger.error(
                "store_scenes_in_db: Projekt-Mismatch — Pipeline startete auf "
                "'%s', aktive DB ist '%s'. Szenen fuer VideoClip %d werden "
                "NICHT gespeichert.", expected_db_url, active_url, video_clip_id,
            )
            return False

    with nullpool_session() as session:
        # B-490: Existenz des VideoClips in der AKTUELLEN DB pruefen. Lief die
        # Pipeline auf Projekt A und wurde mid-run zu Projekt B gewechselt (oder
        # ist die clip_id stale), zeigt nullpool_session auf eine DB ohne diese
        # Zeile -> der Scene-Foreign-Key crasht beim Commit (sqlite3.IntegrityError
        # 'FOREIGN KEY constraint failed') und riss die ganze Pipeline-Task ab.
        # Statt zu crashen ueberspringen wir die Szenen-Speicherung.
        if session.query(VideoClip.id).filter_by(id=video_clip_id).first() is None:
            logger.warning(
                "store_scenes_in_db: VideoClip %d existiert nicht in der aktiven DB "
                "— Szenen werden uebersprungen (verhindert FK-Crash).", video_clip_id,
            )
            return False
        try:
            # Alte Szenen löschen
            session.query(Scene).filter_by(video_clip_id=video_clip_id).delete()

            for scene in scenes:
                db_scene = Scene(
                    video_clip_id=video_clip_id,
                    start_time=scene.start_time,
                    end_time=scene.end_time,
                    energy=scene.motion_score,
                    label=f"Scene {scene.index}",
                    ai_caption=scene.ai_caption if scene.ai_caption else None,
                    ai_mood=scene.ai_mood,
                    ai_tags=scene.ai_tags if scene.ai_tags else None,
                )
                session.add(db_scene)

            session.commit()
        except Exception:  # broad catch intentional — SQLAlchemy commit can raise many error types
            session.rollback()
            logger.exception("Fehler beim Speichern der Szenen für VideoClip %d", video_clip_id)
            raise

    logger.info("SQLite: %d Szenen gespeichert für VideoClip %d", len(scenes), video_clip_id)
    return True


# ======================================================================
# Text-zu-Video Suche (SigLIP Text Encoder)
# ======================================================================

def text_to_embedding(query: str) -> np.ndarray | None:
    """Konvertiert einen Text-Query in einen SigLIP-Vektor.

    Nutzt ModelManager Singleton — lädt SigLIP nur wenn nötig.
    F-012 Fix: Gesamte load→inference→unload Sequenz unter Lock.

    Returns:
        1152-dim numpy array oder None bei Fehler
    """
    from services.model_manager import ModelManager
    mm = ModelManager()

    # B-069: GPU_EXECUTION_LOCK serialisiert Inferenz; GPU_LOAD_LOCK
    # serialisiert NUR das Laden. Vorher hielt diese Funktion den
    # LOAD_LOCK über die gesamte Inferenz und blockierte dadurch parallele
    # Loads (RAFT, Demucs etc.) mehrere Sekunden.
    from services.model_manager import GPU_LOAD_LOCK, GPU_EXECUTION_LOCK
    with GPU_EXECUTION_LOCK:
        with GPU_LOAD_LOCK:
            try:
                model, processor = mm.load_siglip()
            except Exception as e:  # broad catch intentional — MLModelNotFoundError, OOM, ImportError, RuntimeError
                from services.errors import MLModelNotFoundError
                if isinstance(e, MLModelNotFoundError):
                    logger.warning("SigLIP nicht heruntergeladen — Text-Suche nicht verfuegbar: %s", e)
                else:
                    logger.error("SigLIP fuer Text-Suche nicht verfuegbar: %s", e)
                return None

        import torch

        try:
            inputs = processor(text=[query], return_tensors="pt", padding=True)
            inputs = {k: v.to(mm.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = model.get_text_features(**inputs)
                # Robust: handle both raw tensor and BaseModelOutputWithPooling
                if not isinstance(outputs, torch.Tensor):
                    outputs = outputs.pooler_output if hasattr(outputs, 'pooler_output') else outputs[0]
                embedding = outputs / outputs.norm(p=2, dim=-1, keepdim=True)
                result = embedding.cpu().numpy().astype(np.float32)[0]

            # SigLIP entladen um VRAM freizugeben
            mm.unload()
            return result

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error("Text-Embedding Fehler: %s", e)
            mm.unload()
            return None


def texts_to_embeddings_batch(queries: list[str]) -> dict[str, np.ndarray]:
    """Konvertiert mehrere Text-Queries in SigLIP-Vektoren in EINEM Model-Load.

    Laedt SigLIP einmal, berechnet alle Embeddings, entlaedt sofort.
    Spart ~15s pro zusaetzlichem Query gegenueber einzelnem text_to_embedding().

    Returns:
        Dict[query_text, 1152-dim numpy array]. Fehlgeschlagene Queries fehlen.
    """
    if not queries:
        return {}

    from services.model_manager import ModelManager, GPU_LOAD_LOCK, GPU_EXECUTION_LOCK
    mm = ModelManager()

    # B-069: EXECUTION_LOCK über Inferenz, LOAD_LOCK nur über load_siglip().
    with GPU_EXECUTION_LOCK:
        with GPU_LOAD_LOCK:
            try:
                model, processor = mm.load_siglip()
            except Exception as e:  # broad catch intentional — MLModelNotFoundError, OOM, ImportError, RuntimeError
                from services.errors import MLModelNotFoundError
                if isinstance(e, MLModelNotFoundError):
                    logger.warning(
                        "SigLIP nicht heruntergeladen — Batch-Embedding nicht verfuegbar: %s", e
                    )
                else:
                    logger.error("SigLIP fuer Batch-Text-Embedding nicht verfuegbar: %s", e)
                return {}

        import torch
        results: dict[str, np.ndarray] = {}

        try:
            # Alle Queries in einem Batch verarbeiten
            inputs = processor(text=queries, return_tensors="pt", padding=True, truncation=True)
            inputs = {k: v.to(mm.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = model.get_text_features(**inputs)
                if not isinstance(outputs, torch.Tensor):
                    outputs = outputs.pooler_output if hasattr(outputs, 'pooler_output') else outputs[0]
                embeddings = outputs / outputs.norm(p=2, dim=-1, keepdim=True)
                embeddings_np = embeddings.cpu().numpy().astype(np.float32)

            for i, query in enumerate(queries):
                results[query] = embeddings_np[i]

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error("Batch Text-Embedding Fehler: %s", e)
        finally:
            mm.unload()

    logger.info("SigLIP Batch: %d/%d Text-Embeddings berechnet", len(results), len(queries))
    return results


def search_videos_by_text(
    query: str,
    top_k: int = 10,
    motion_filter: float | None = None,
) -> list[dict]:
    """Semantische Text-zu-Video Suche über LanceDB.

    Args:
        query: Natürlichsprachiger Suchtext
        top_k: Anzahl der Ergebnisse
        motion_filter: Optionaler Motion-Score Filter

    Returns:
        Liste von Dicts mit video_path, scene_start, scene_end, motion_score, _distance
    """
    embedding = text_to_embedding(query)
    if embedding is None:
        return []

    from services.vector_db_service import VectorDBService
    vdb = VectorDBService()

    try:
        results = vdb.search(embedding, top_k=top_k, motion_filter=motion_filter)
        results = _filter_active_video_search_results(results)
        logger.info("Suche '%s': %d aktive Ergebnisse", query, len(results))
        return results
    except (OSError, RuntimeError, ValueError) as e:
        logger.error("LanceDB Suche fehlgeschlagen: %s", e)
        return []


def _filter_active_video_search_results(results: list[dict]) -> list[dict]:
    clip_ids = {
        int(row["id"]) // 1_000_000
        for row in results
        if row.get("id") is not None
    }
    if not clip_ids:
        return []

    from sqlalchemy.orm import Session as _Session
    from database import engine as _engine, VideoClip as _VideoClip

    with _Session(_engine) as session:
        active_ids = {
            row[0]
            for row in session.query(_VideoClip.id)
            .filter(_VideoClip.id.in_(clip_ids), _VideoClip.deleted_at.is_(None))
            .all()
        }

    return [
        row for row in results
        if row.get("id") is not None and int(row["id"]) // 1_000_000 in active_ids
    ]


# ======================================================================
# Vollständige Pipeline (alle 3 Schritte)
# ======================================================================

def _run_structure_enrichment(video_clip_id: int) -> None:
    """Best-effort Studio-Brain enrichment after scene storage."""
    try:
        from workers.structure_enrichment import StructureEnrichmentWorker

        enrichment_worker = StructureEnrichmentWorker(clip_id=video_clip_id)
        enrichment_result = enrichment_worker.run()
        if "error" in enrichment_result:
            logger.warning(
                "[PIPELINE] structure_enrichment failed for clip %d: %s",
                video_clip_id, enrichment_result["error"],
            )
        else:
            logger.info(
                "[PIPELINE] structure_enrichment done for clip %d (mode=%s, scenes=%d)",
                video_clip_id,
                enrichment_result.get("mode", "?"),
                enrichment_result.get("scenes_enriched", 0),
            )
    except Exception as enrichment_exc:
        logger.warning(
            "[PIPELINE] structure_enrichment raised unexpectedly for clip %d: %s",
            video_clip_id, enrichment_exc,
        )


def run_deferred_captioning(
    video_clip_id: int,
    scenes: list[SceneInfo],
    progress_cb: Callable[[int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    caption_failure_state: dict[str, int] | None = None,
) -> list[SceneInfo]:
    """Run Ollama/Gemma captioning after batch GPU models were unloaded."""
    # B-490 Followup (CRF-005): Projekt-Token am Funktions-Eintritt festhalten.
    # Deferred Captioning laeuft NACH dem Batch — ein Projektwechsel waehrend
    # dieser Funktion darf die Szenen nicht in die falsche Projekt-DB schreiben.
    # (Restluecke: Wechsel ZWISCHEN Pipeline-Ende und diesem Eintritt faengt nur
    # der VideoClip-Existenz-Check in store_scenes_in_db ab.)
    deferred_db_url = _current_db_url()
    analysis_status_service.mark_started("video", video_clip_id, "ai_scene_caption")
    try:
        logger.info("[PIPELINE] Deferred Gemma Vision Captioning fuer Clip %d...", video_clip_id)
        if progress_cb:
            progress_cb(85, "Gemma Vision Captioning...")
        if should_stop and should_stop():
            analysis_status_service.mark_error("video", video_clip_id, "ai_scene_caption", "cancelled")
            return scenes

        scenes = analyze_scene_with_caption(
            scenes,
            caption_failure_state=caption_failure_state,
        )
        captioned_count = sum(1 for s in scenes if hasattr(s, 'ai_caption') and s.ai_caption)
        analysis_status_service.mark_done("video", video_clip_id, "ai_scene_caption", {
            "captioned_scenes": captioned_count,
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "ai_scene_caption", str(e))
        raise

    analysis_status_service.mark_started("video", video_clip_id, "scene_db_storage")
    try:
        if progress_cb:
            progress_cb(93, "Szenen-Captions in DB speichern...")
        stored = store_scenes_in_db(
            video_clip_id, scenes, expected_db_url=deferred_db_url,
        )
        if not stored:
            # B-490 Followup (CRF-005): Skip ist KEIN Erfolg. Vorher wurde hier
            # mark_done gesetzt obwohl die DB leer blieb -> Status "done" log.
            reason = (
                f"Szenen nicht gespeichert: VideoClip {video_clip_id} fehlt in "
                "der aktiven DB oder das Projekt wurde waehrend des Laufs "
                "gewechselt (Projekt-Token-Mismatch)."
            )
            analysis_status_service.mark_error(
                "video", video_clip_id, "scene_db_storage", reason,
            )
            logger.error("[PIPELINE] %s", reason)
            # Kein Structure-Enrichment auf einer DB ohne diese Szenen.
            return scenes
        analysis_status_service.mark_done("video", video_clip_id, "scene_db_storage", {
            "scenes": len(scenes),
            "captions_updated": True,
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "scene_db_storage", str(e))
        raise

    _run_structure_enrichment(video_clip_id)
    return scenes


def run_full_pipeline(
    video_path: str,
    video_clip_id: int,
    threshold: float = 27.0,
    progress_cb: Callable[[int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    siglip_model_processor: tuple | None = None,
    raft_model_device: tuple | None = None,
    defer_captioning: bool = False,
) -> PipelineResult:
    """Führt die komplette 3-Schritt Video-Analyse-Pipeline aus.

    B-150: APP_ROOT-Snapshot am Pipeline-Start. Wenn der User waehrend
    des Runs Project switched, liefert _keyframe_dir() spaeter andere
    Pfade. Wir snapshotten einmal und reichen es durch.
    """
    if not video_path or not Path(video_path).exists():
        logger.error("Video-Pipeline abgebrochen: Datei fehlt -> %s", video_path)
        raise FileNotFoundError(f"Video-Datei fehlt: {video_path}")

    # B-150: Snapshot der projekt-abhaengigen Pfade am Pipeline-Eintritt.
    pipeline_keyframe_dir = _keyframe_dir()
    # B-490 Followup (CRF-005): Projekt-Token am Pipeline-Start festhalten.
    # Wird an store_scenes_in_db durchgereicht — bei Engine-Swap mid-run
    # (set_project) wird NICHT in die fremde Projekt-DB geschrieben.
    pipeline_db_url = _current_db_url()
    # Proxy-First: video_path kann Proxy sein — Original aus DB laden für LanceDB-Storage
    try:
        from sqlalchemy.orm import Session as _Session
        from database import engine as _engine, VideoClip as _VideoClip
        with _Session(_engine) as _s:
            _clip = (
                _s.query(_VideoClip)
                .filter(_VideoClip.id == video_clip_id, _VideoClip.deleted_at.is_(None))
                .first()
            )
            if _clip is None:
                raise ValueError(f"VideoClip {video_clip_id} nicht gefunden oder geloescht.")
            original_video_path = _clip.file_path
    except ValueError:
        raise
    except Exception:  # broad catch intentional — SQLAlchemy query at startup, DB may not be ready
        original_video_path = video_path

    result = PipelineResult(video_path=original_video_path)

    # Schritt 1: Scene Detection
    analysis_status_service.mark_started("video", video_clip_id, "scene_detection")
    try:
        logger.info("[PIPELINE] Schritt 1/7: Szenen erkennen für %s (Analyse-Pfad: %s)...",
                    Path(original_video_path).name, Path(video_path).name)
        if progress_cb:
            progress_cb(5, "Szenen erkennen...")
        if should_stop and should_stop():
            # B-147: cancel-branch markiert Status als error("cancelled")
            # damit der Clip nicht forever auf "running" steht.
            analysis_status_service.mark_error(
                "video", video_clip_id, "scene_detection", "cancelled"
            )
            return result

        scenes = detect_scenes(video_path, threshold=threshold)
        result.scenes = scenes
        result.total_duration = scenes[-1].end_time if scenes else 0.0
        logger.info("[PIPELINE] Szenen-Erkennung FERTIG: %d Szenen gefunden", len(scenes))
        analysis_status_service.mark_done("video", video_clip_id, "scene_detection", {
            "scenes": len(scenes),
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "scene_detection", str(e))
        raise

    # Schritt 1b: Motion Scores
    analysis_status_service.mark_started("video", video_clip_id, "motion_scores")
    try:
        logger.info("[PIPELINE] Schritt 2/7: RAFT Motion-Analyse für %d Szenen...", len(scenes))
        if progress_cb:
            progress_cb(20, f"Motion-Analyse ({len(scenes)} Szenen)...")
        if should_stop and should_stop():
            analysis_status_service.mark_error(  # B-147
                "video", video_clip_id, "motion_scores", "cancelled"
            )
            return result

        scenes = compute_motion_scores(video_path, scenes, raft_model_device=raft_model_device)
        logger.info("[PIPELINE] Motion-Analyse FERTIG")
        avg_motion = sum(s.motion_score for s in scenes if s.motion_score) / len(scenes) if scenes else 0.0
        analysis_status_service.mark_done("video", video_clip_id, "motion_scores", {
            "avg_motion": round(avg_motion, 3),
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "motion_scores", str(e))
        raise

    # Schritt 2: Keyframes
    analysis_status_service.mark_started("video", video_clip_id, "keyframe_extraction")
    try:
        logger.info("[PIPELINE] Schritt 3/7: Keyframes extrahieren...")
        if progress_cb:
            progress_cb(40, "Keyframes extrahieren...")
        if should_stop and should_stop():
            analysis_status_service.mark_error(  # B-147
                "video", video_clip_id, "keyframe_extraction", "cancelled"
            )
            return result

        # B-150: Snapshot-Pfad nutzen statt _keyframe_dir() neu aufzurufen.
        scenes = extract_keyframes(video_path, scenes, output_dir=pipeline_keyframe_dir)
        logger.info("[PIPELINE] Keyframes FERTIG")
        keyframe_count = sum(1 for s in scenes if s.keyframe_path)
        analysis_status_service.mark_done("video", video_clip_id, "keyframe_extraction", {
            "keyframes": keyframe_count,
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "keyframe_extraction", str(e))
        raise

    # Schritt 3: SigLIP Embeddings
    analysis_status_service.mark_started("video", video_clip_id, "siglip_embeddings")
    try:
        logger.info("[PIPELINE] Schritt 4/7: Lade SigLIP Modell + Embeddings generieren...")
        if progress_cb:
            progress_cb(55, "SigLIP Embeddings generieren...")
        if should_stop and should_stop():
            analysis_status_service.mark_error(  # B-147
                "video", video_clip_id, "siglip_embeddings", "cancelled"
            )
            return result

        scenes = generate_embeddings(scenes, siglip_model_processor=siglip_model_processor)
        logger.info("[PIPELINE] SigLIP Embeddings FERTIG")
        embedding_count = sum(1 for s in scenes if s.embedding is not None)
        analysis_status_service.mark_done("video", video_clip_id, "siglip_embeddings", {
            "dimension": 1152,
            "embeddings": embedding_count,
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "siglip_embeddings", str(e))
        raise

    # Schritt 4: Gemma Vision Captioning
    if defer_captioning:
        logger.info(
            "[PIPELINE] Schritt 6/7: Gemma Vision Captioning deferred bis nach GPU-Batch-Cleanup"
        )
    else:
        analysis_status_service.mark_started("video", video_clip_id, "ai_scene_caption")
        try:
            logger.info("[PIPELINE] Schritt 6/7: Gemma Vision Captioning...")
            if progress_cb:
                progress_cb(85, "Gemma Vision Captioning...")
            if should_stop and should_stop():
                analysis_status_service.mark_error(  # B-147
                    "video", video_clip_id, "ai_scene_caption", "cancelled"
                )
                return result

            scenes = analyze_scene_with_caption(scenes)
            logger.info("[PIPELINE] Vision-Captioning FERTIG")
            captioned_count = sum(1 for s in scenes if hasattr(s, 'ai_caption') and s.ai_caption)
            analysis_status_service.mark_done("video", video_clip_id, "ai_scene_caption", {
                "captioned_scenes": captioned_count,
            })
        except Exception as e:
            analysis_status_service.mark_error("video", video_clip_id, "ai_scene_caption", str(e))
            raise

    # Szenen in SQLite speichern
    analysis_status_service.mark_started("video", video_clip_id, "scene_db_storage")
    try:
        logger.info("[PIPELINE] Schritt 7/7: Szenen in SQLite speichern...")
        if progress_cb:
            progress_cb(93, "Szenen in DB speichern...")

        stored = store_scenes_in_db(
            video_clip_id, scenes, expected_db_url=pipeline_db_url,
        )
        if not stored:
            # B-490 Followup (CRF-005): Skip ist KEIN Erfolg. Vorher wurde hier
            # mark_done({"scenes": N}) gesetzt obwohl die DB leer blieb.
            reason = (
                f"Szenen nicht gespeichert: VideoClip {video_clip_id} fehlt in "
                "der aktiven DB oder das Projekt wurde waehrend des Laufs "
                "gewechselt (Projekt-Token-Mismatch)."
            )
            analysis_status_service.mark_error(
                "video", video_clip_id, "scene_db_storage", reason,
            )
            logger.error("[PIPELINE] %s", reason)
            # B-368-Konsistenz: ohne SQLite-Szenen keine VectorDB-Writes
            # (sonst entstehen Embedding-Orphans) und kein Enrichment.
            return result
        logger.info("[PIPELINE] Pipeline KOMPLETT für %s", Path(original_video_path).name)
        analysis_status_service.mark_done("video", video_clip_id, "scene_db_storage", {
            "scenes": len(scenes),
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "scene_db_storage", str(e))
        raise

    # Schritt 7b: In LanceDB speichern, nachdem SQLite-Szenen committed sind.
    analysis_status_service.mark_started("video", video_clip_id, "vector_db_storage")
    try:
        logger.info("[PIPELINE] Schritt 7b/7: In LanceDB speichern...")
        if progress_cb:
            progress_cb(96, "In LanceDB speichern...")
        if should_stop and should_stop():
            analysis_status_service.mark_error(  # B-147
                "video", video_clip_id, "vector_db_storage", "cancelled"
            )
            return result

        # Original-Pfad fuer LanceDB-Storage verwenden (nicht Proxy-Pfad).
        # B-368: erst nach erfolgreichem SQLite-Commit schreiben, damit bei
        # DB-Fehlern keine VectorDB-Orphans entstehen.
        result.embeddings_stored = store_embeddings(original_video_path, scenes, video_clip_id)
        logger.info("[PIPELINE] LanceDB FERTIG: %d Embeddings", result.embeddings_stored)
        analysis_status_service.mark_done("video", video_clip_id, "vector_db_storage", {
            "vectors": result.embeddings_stored,
        })
    except Exception as e:
        analysis_status_service.mark_error("video", video_clip_id, "vector_db_storage", str(e))
        raise

    if not defer_captioning:
        _run_structure_enrichment(video_clip_id)

    # VRAM-Schutz: GPU-Speicher nach Pipeline freigeben
    # Im Batch-Modus (siglip_model_processor/raft_model_device uebergeben) KEIN
    # empty_cache() — das korrumpiert den Heap wenn Modelle noch resident sind
    # (Windows 0xC0000374). Batch-Cleanup passiert im Worker nach der gesamten Batch.
    is_batch = siglip_model_processor is not None or raft_model_device is not None
    if not is_batch:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("[PIPELINE] VRAM-Cleanup: torch.cuda.empty_cache()")
        except ImportError as exc:
            logger.warning("torch not available for VRAM cleanup in pipeline: %s", exc)
    gc.collect()

    logger.info(
        "Pipeline komplett: %s — %d Szenen, %d Embeddings",
        Path(video_path).name, len(scenes), result.embeddings_stored,
    )
    return result

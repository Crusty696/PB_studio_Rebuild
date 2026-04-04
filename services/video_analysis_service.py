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
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


def _keyframe_dir() -> Path:
    """Returns keyframe directory for the current project (lazy APP_ROOT read)."""
    from database import APP_ROOT
    return APP_ROOT / "storage" / "keyframes"


@dataclass
class SceneInfo:
    """Ergebnis einer erkannten Szene."""
    index: int
    start_time: float
    end_time: float
    motion_score: float = 0.0
    keyframe_path: str | None = None
    embedding: np.ndarray | None = None


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

    try:
        from scenedetect import detect, ContentDetector
    except ImportError:
        logger.warning("PySceneDetect nicht installiert — Fallback: eine Szene pro Video")
        return _fallback_single_scene(video_path)

    try:
        scene_list = detect(
            video_path,
            ContentDetector(threshold=threshold, min_scene_len=int(min_scene_len * fps)),
        )
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
    (Whisper, SigLIP, beat_this) es automatisch entladen können.

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


def _raft_motion_score(
    raft_model, device, frame1_bgr: np.ndarray, frame2_bgr: np.ndarray,
) -> float:
    """Berechnet Motion-Score via RAFT auf GPU.

    Nimmt zwei BGR-Frames, skaliert auf 520x320, berechnet Optical Flow
    und gibt einen normalisierten Score (0.0 – 1.0) zurück.
    """
    import torch
    import torchvision.transforms.functional as F

    def prep(bgr: np.ndarray) -> torch.Tensor:
        rgb = bgr[..., ::-1].copy()  # BGR → RGB
        t = torch.from_numpy(rgb).permute(2, 0, 1).float()  # HWC → CHW
        # Auf 520x320 skalieren (RAFT braucht durch 8 teilbare Dimensionen)
        t = torch.nn.functional.interpolate(
            t.unsqueeze(0), size=(320, 520), mode="bilinear", align_corners=False
        )
        return t.to(device)

    img1 = prep(frame1_bgr)
    img2 = prep(frame2_bgr)

    with torch.no_grad():
        flows = raft_model(img1, img2)
        flow = flows[-1]  # Letzte Iteration = bester Flow
        magnitude = torch.sqrt(flow[:, 0] ** 2 + flow[:, 1] ** 2)
        raw = float(magnitude.mean().cpu())

    # Normalisierung: typische Werte 0-50px → 0.0-1.0
    return round(min(1.0, raw / 40.0), 4)


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

        for scene in scenes:
            start_frame = int(scene.start_time * fps)
            end_frame = int(scene.end_time * fps)
            mid_frame = (start_frame + end_frame) // 2

            # Sample 2 Frames um die Szenen-Mitte für Motion-Berechnung
            sample_frames = [
                max(start_frame, mid_frame - int(fps * 0.5)),
                min(end_frame - 1, mid_frame + int(fps * 0.5)),
            ]

            frames_bgr = []
            for fnum in sample_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
                ret, frame = cap.read()
                if ret:
                    frames_bgr.append(frame)

            if len(frames_bgr) == 2:
                if use_raft:
                    # GPU-beschleunigte RAFT Motion-Analyse
                    try:
                        scene.motion_score = _raft_motion_score(
                            raft_model, raft_device, frames_bgr[0], frames_bgr[1]
                        )
                    except (RuntimeError, OSError) as e:
                        logger.warning("RAFT Fehler bei Szene %d: %s — CPU-Fallback", scene.index, e)
                        scene.motion_score = _cpu_motion_score(frames_bgr[0], frames_bgr[1])
                    # Periodischer VRAM-Cleanup NUR wenn wir RAFT selbst geladen haben.
                    # Im Batch-Modus (raft_model_device uebergeben) KEIN empty_cache() —
                    # das korrumpiert den Heap wenn SigLIP/RAFT noch resident sind (0xC0000374).
                    if _owns_raft and scene.index % 8 == 7:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                else:
                    scene.motion_score = _cpu_motion_score(frames_bgr[0], frames_bgr[1])
            else:
                scene.motion_score = 0.0
    finally:
        cap.release()
        # RAFT nur entladen wenn WIR es geladen haben (nicht im Batch-Modus)
        if _owns_raft and use_raft and raft_model is not None:
            from services.model_manager import ModelManager
            try:
                ModelManager().unload()
            except (RuntimeError, AttributeError) as exc:
                logger.warning("ModelManager.unload() failed after RAFT cleanup: %s", exc)
            raft_model = None  # Lokale Referenz freigeben
            logger.info("RAFT entladen via ModelManager")

    logger.info("Motion-Scores berechnet für %d Szenen (%s)", len(scenes),
                "RAFT/CUDA" if use_raft else "CPU-Fallback")
    return scenes


def _cpu_motion_score(frame1_bgr: np.ndarray, frame2_bgr: np.ndarray) -> float:
    """CPU-Fallback: Frame-Differenz-basierter Motion-Score."""
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
    return round(min(1.0, raw_score * 3.0), 4)


def _fallback_single_scene(video_path: str) -> list[SceneInfo]:
    """Fallback: Ganzes Video als eine Szene."""
    duration = _get_video_duration(video_path)
    return [SceneInfo(index=0, start_time=0.0, end_time=duration)]


def _get_video_duration(video_path: str) -> float:
    """Ermittelt Video-Dauer via ffprobe."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if p.returncode == 0 and p.stdout.strip():
            return float(p.stdout.strip())
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

    out_dir = output_dir or _keyframe_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    video_stem = Path(video_path).stem

    for scene in scenes:
        # Keyframe in der Mitte der Szene
        mid_time = (scene.start_time + scene.end_time) / 2.0
        kf_path = out_dir / f"{video_stem}_scene{scene.index:04d}.jpg"

        if kf_path.exists():
            scene.keyframe_path = str(kf_path)
            continue

        cmd = [
            "ffmpeg", "-y", "-ss", str(mid_time),
            "-i", video_path,
            "-frames:v", "1",
            "-vf", "scale=384:384:force_original_aspect_ratio=decrease,pad=384:384:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "2",
            "-v", "quiet",
            str(kf_path),
        ]

        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15,
                                    stdin=subprocess.DEVNULL, **kwargs)
            if kf_path.exists():
                scene.keyframe_path = str(kf_path)
            else:
                stderr = (result.stderr or b"")[:200]
                logger.warning("Keyframe-Extraktion fehlgeschlagen: Szene %d (rc=%d, %s)",
                               scene.index, result.returncode, stderr)
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logger.warning("Keyframe-Fehler Szene %d: %s", scene.index, e)

    extracted = sum(1 for s in scenes if s.keyframe_path)
    logger.info("Keyframes extrahiert: %d/%d", extracted, len(scenes))
    return scenes


# ======================================================================
# Schritt 3: SigLIP Embeddings → LanceDB
# ======================================================================

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

    # Batch-Modus: SigLIP wurde vom Caller vorgeladen → wiederverwenden
    owns_model = siglip_model_processor is None
    if siglip_model_processor is not None:
        model, processor = siglip_model_processor
        logger.info("[SIGLIP] Verwende vorgeladenes SigLIP Modell (Batch-Modus)")
    else:
        logger.info("[SIGLIP] Lade SigLIP Modell...")
        from services.model_manager import GPU_LOAD_LOCK
        try:
            with GPU_LOAD_LOCK:
                model, processor = mm.load_siglip()
            logger.info("[SIGLIP] SigLIP geladen auf %s", mm.device)
        except (ImportError, RuntimeError, OSError, MemoryError) as e:
            logger.error("[SIGLIP] SigLIP FEHLER: %s", e)
            logger.error("SigLIP konnte nicht geladen werden: %s", e)
            return scenes

    import torch
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor

    def _load_image(scene):
        """Lädt ein Keyframe-Bild (I/O-bound, parallelisierbar)."""
        try:
            return scene, Image.open(scene.keyframe_path).convert("RGB")
        except (OSError, IOError, ValueError) as e:
            logger.warning("Bild konnte nicht geladen werden: %s — %s", scene.keyframe_path, e)
            return scene, None

    # Batch-Verarbeitung in Gruppen von 8 (VRAM-schonend für GTX 1060)
    batch_size = 8
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

            with torch.no_grad():
                outputs = model.get_image_features(**inputs)
                # Robust: handle both raw tensor and BaseModelOutputWithPooling
                if not isinstance(outputs, torch.Tensor):
                    outputs = outputs.pooler_output if hasattr(outputs, 'pooler_output') else outputs[0]
                # L2-Normalisierung
                embeddings = outputs / outputs.norm(p=2, dim=-1, keepdim=True)
                embeddings = embeddings.cpu().numpy().astype(np.float32)

            for i, scene in enumerate(valid_scenes):
                scene.embedding = embeddings[i]

        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            # Adaptive Retry: Batch halbieren und einzeln verarbeiten
            logger.warning("OOM bei SigLIP Batch (size=%d) — Retry einzeln...", len(images))
            for j, (img, scene) in enumerate(zip(images, valid_scenes)):
                try:
                    inp = processor(images=[img], return_tensors="pt", padding=True)
                    inp = {k: v.to(mm.device) for k, v in inp.items()}
                    with torch.no_grad():
                        out = model.get_image_features(**inp)
                        if not isinstance(out, torch.Tensor):
                            out = out.pooler_output if hasattr(out, 'pooler_output') else out[0]
                        emb = out / out.norm(p=2, dim=-1, keepdim=True)
                        scene.embedding = emb.cpu().numpy().astype(np.float32)[0]
                    del inp, out, emb
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    logger.error("OOM auch bei Einzel-Inference — ueberspringe Bild %d", j)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error("SigLIP Embedding-Fehler: %s", e)

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

    # Alte Embeddings für dieses Video löschen
    try:
        vdb.delete_by_video(video_path)
    except (OSError, RuntimeError, ValueError) as e:
        logger.debug("delete_by_video fehlgeschlagen (ignoriert): %s", e)

    entries = []
    for scene in scenes:
        if scene.embedding is None:
            continue

        entries.append({
            "id": video_clip_id * 1_000_000 + scene.index,
            "video_path": video_path,
            "scene_index": scene.index,
            "scene_start": scene.start_time,
            "scene_end": scene.end_time,
            "motion_score": scene.motion_score,
            "description": "",
            "embedding": scene.embedding.tolist(),
        })

    if entries:
        logger.info("[VectorDB] add_embeddings_batch (%d entries)...", len(entries))
        vdb.add_embeddings_batch(entries)
        logger.info("[VectorDB] %d Embeddings gespeichert fuer %s", len(entries), Path(video_path).name)

    return len(entries)


def store_scenes_in_db(
    video_clip_id: int,
    scenes: list[SceneInfo],
) -> None:
    """Speichert erkannte Szenen in der SQLite-DB (NullPool)."""
    from database import nullpool_session, Scene

    with nullpool_session() as session:
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
                )
                session.add(db_scene)

            session.commit()
        except Exception:  # broad catch intentional — SQLAlchemy commit can raise many error types
            session.rollback()
            logger.exception("Fehler beim Speichern der Szenen für VideoClip %d", video_clip_id)
            raise

    logger.info("SQLite: %d Szenen gespeichert für VideoClip %d", len(scenes), video_clip_id)


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

    # F-012 + C-03 Fix: GPU_LOAD_LOCK statt _swap_lock — serialisiert
    # mit allen anderen GPU-Model-Loads (Demucs, beat_this, Moondream etc.)
    from services.model_manager import GPU_LOAD_LOCK
    with GPU_LOAD_LOCK:
        try:
            model, processor = mm.load_siglip()
        except (ImportError, RuntimeError, OSError) as e:
            logger.error("SigLIP für Text-Suche nicht verfügbar: %s", e)
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

    from services.model_manager import ModelManager, GPU_LOAD_LOCK
    mm = ModelManager()

    with GPU_LOAD_LOCK:
        try:
            model, processor = mm.load_siglip()
        except (ImportError, RuntimeError, OSError) as e:
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
        logger.info("Suche '%s': %d Ergebnisse", query, len(results))
        return results
    except (OSError, RuntimeError, ValueError) as e:
        logger.error("LanceDB Suche fehlgeschlagen: %s", e)
        return []


# ======================================================================
# Vollständige Pipeline (alle 3 Schritte)
# ======================================================================

def run_full_pipeline(
    video_path: str,
    video_clip_id: int,
    threshold: float = 27.0,
    progress_cb: Callable[[int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    siglip_model_processor: tuple | None = None,
    raft_model_device: tuple | None = None,
) -> PipelineResult:
    """Führt die komplette 3-Schritt Video-Analyse-Pipeline aus.

    1. SceneDetect + RAFT Motion
    2. Keyframe-Extraktion
    3. SigLIP Embeddings → LanceDB

    Args:
        video_path: Pfad zum Video
        video_clip_id: DB-ID des VideoClip
        threshold: SceneDetect Schwellwert
        progress_cb: Callback(step, total, message)
        should_stop: Abbruch-Check Callback
        siglip_model_processor: Optional (model, processor) Tupel für Batch-Modus.
            Wenn übergeben, wird SigLIP NICHT pro Video geladen/entladen.

    Returns:
        PipelineResult mit allen Szenen und Embedding-Count
    """
    # Proxy-First: video_path kann Proxy sein — Original aus DB laden für LanceDB-Storage
    try:
        from sqlalchemy.orm import Session as _Session
        from database import engine as _engine, VideoClip as _VideoClip
        with _Session(_engine) as _s:
            _clip = _s.get(_VideoClip, video_clip_id)
            original_video_path = _clip.file_path if _clip else video_path
    except Exception:  # broad catch intentional — SQLAlchemy query at startup, DB may not be ready
        original_video_path = video_path

    result = PipelineResult(video_path=original_video_path)

    # Schritt 1: Scene Detection
    logger.info("[PIPELINE] Schritt 1/6: Szenen erkennen für %s (Analyse-Pfad: %s)...",
                Path(original_video_path).name, Path(video_path).name)
    if progress_cb:
        progress_cb(5, "Szenen erkennen...")
    if should_stop and should_stop():
        return result

    scenes = detect_scenes(video_path, threshold=threshold)
    result.scenes = scenes
    result.total_duration = scenes[-1].end_time if scenes else 0.0
    logger.info("[PIPELINE] Szenen-Erkennung FERTIG: %d Szenen gefunden", len(scenes))

    # Schritt 1b: Motion Scores
    logger.info("[PIPELINE] Schritt 2/6: RAFT Motion-Analyse für %d Szenen...", len(scenes))
    if progress_cb:
        progress_cb(20, f"Motion-Analyse ({len(scenes)} Szenen)...")
    if should_stop and should_stop():
        return result

    scenes = compute_motion_scores(video_path, scenes, raft_model_device=raft_model_device)
    logger.info("[PIPELINE] Motion-Analyse FERTIG")

    # Schritt 2: Keyframes
    logger.info("[PIPELINE] Schritt 3/6: Keyframes extrahieren...")
    if progress_cb:
        progress_cb(40, "Keyframes extrahieren...")
    if should_stop and should_stop():
        return result

    scenes = extract_keyframes(video_path, scenes)
    logger.info("[PIPELINE] Keyframes FERTIG")

    # Schritt 3: SigLIP Embeddings
    logger.info("[PIPELINE] Schritt 4/6: Lade SigLIP Modell + Embeddings generieren...")
    if progress_cb:
        progress_cb(55, "SigLIP Embeddings generieren...")
    if should_stop and should_stop():
        return result

    scenes = generate_embeddings(scenes, siglip_model_processor=siglip_model_processor)
    logger.info("[PIPELINE] SigLIP Embeddings FERTIG")

    # Schritt 3b: In LanceDB speichern
    logger.info("[PIPELINE] Schritt 5/6: In LanceDB speichern...")
    if progress_cb:
        progress_cb(80, "In LanceDB speichern...")
    if should_stop and should_stop():
        return result

    # Original-Pfad für LanceDB-Storage verwenden (nicht Proxy-Pfad)
    result.embeddings_stored = store_embeddings(original_video_path, scenes, video_clip_id)
    logger.info("[PIPELINE] LanceDB FERTIG: %d Embeddings", result.embeddings_stored)

    # Szenen in SQLite speichern
    logger.info("[PIPELINE] Schritt 6/6: Szenen in SQLite speichern...")
    if progress_cb:
        progress_cb(90, "Szenen in DB speichern...")

    store_scenes_in_db(video_clip_id, scenes)
    logger.info("[PIPELINE] Pipeline KOMPLETT für %s", Path(original_video_path).name)

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

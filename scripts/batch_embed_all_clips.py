"""Batch SigLIP Embedding Analysis fuer alle Video-Clips ohne Embeddings.

AUD-77: Analysiert die 917 Clips, die noch kein SigLIP-Embedding haben.
Laedt SigLIP und RAFT EINMAL fuer alle Videos (VRAM-effizient).

Aufruf:
    .venv/Scripts/python.exe scripts/batch_embed_all_clips.py [--dry-run] [--limit N] [--start-from ID]

Optionen:
    --dry-run     Zeigt an welche Clips verarbeitet wuerden, ohne es zu tun
    --limit N     Verarbeite maximal N Clips (fuer Tests)
    --start-from  Starte ab Clip-ID N (fuer Restart nach Unterbrechung)
"""

from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
import time
from pathlib import Path

# Projekt-Root zum sys.path hinzufuegen
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "logs" / "batch_embed.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("batch_embed")


def get_clips_without_embeddings(start_from: int = 0) -> list[tuple[int, str, str | None, float]]:
    """Gibt alle Clips zurueck, die noch keine Szenen/Embeddings haben.

    Returns:
        Liste von (clip_id, file_path, proxy_path, duration)
    """
    import sqlite3

    conn = sqlite3.connect(str(PROJECT_ROOT / "pb_studio.db"))
    c = conn.cursor()
    c.execute(
        """
        SELECT vc.id, vc.file_path, vc.proxy_path, COALESCE(vc.duration, 0)
        FROM video_clips vc
        LEFT JOIN scenes s ON s.video_clip_id = vc.id
        WHERE s.id IS NULL
          AND vc.id >= ?
        GROUP BY vc.id
        ORDER BY vc.id
        """,
        (start_from,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch SigLIP Embedding fuer alle Video-Clips")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht verarbeiten")
    parser.add_argument("--limit", type=int, default=0, help="Max Clips verarbeiten (0=alle)")
    parser.add_argument("--start-from", type=int, default=0, help="Ab Clip-ID starten")
    args = parser.parse_args()

    logger.info("=== Batch SigLIP Embedding Analysis (AUD-77) ===")
    logger.info("Suche Clips ohne Embeddings (ab ID=%d)...", args.start_from)

    clips = get_clips_without_embeddings(start_from=args.start_from)
    total_missing = len(clips)

    if args.limit > 0:
        clips = clips[: args.limit]

    logger.info("Clips ohne Embeddings: %d (verarbeite: %d)", total_missing, len(clips))

    if not clips:
        logger.info("Alle Clips haben bereits Embeddings. Nichts zu tun.")
        return 0

    if args.dry_run:
        logger.info("DRY RUN — keine Aenderungen:")
        for clip_id, file_path, proxy_path, dur in clips[:20]:
            logger.info("  Clip #%d: %s (%.1fs)", clip_id, Path(file_path).name, dur)
        if len(clips) > 20:
            logger.info("  ... und %d weitere", len(clips) - 20)
        return 0

    # Pruefen ob Dateien existieren
    valid_clips = []
    skipped = 0
    for clip_id, file_path, proxy_path, dur in clips:
        analysis_path = proxy_path if proxy_path and Path(proxy_path).exists() else None
        if analysis_path is None:
            if Path(file_path).exists():
                analysis_path = file_path
            else:
                logger.warning("Clip #%d: Datei nicht gefunden: %s — uebersprungen", clip_id, file_path)
                skipped += 1
                continue
        valid_clips.append((clip_id, analysis_path))

    logger.info(
        "Gueltige Clips: %d (uebersprungen wegen fehlender Datei: %d)",
        len(valid_clips),
        skipped,
    )

    if not valid_clips:
        logger.error("Keine gueltigen Clips gefunden. Abbruch.")
        return 1

    from services.video_analysis_service import run_full_pipeline
    from services.model_manager import ModelManager, GPU_LOAD_LOCK

    # SigLIP + RAFT EINMAL laden fuer alle Videos
    siglip_model_processor = None
    raft_model_device = None
    mm = ModelManager()

    logger.info("Lade SigLIP + RAFT einmalig fuer %d Videos...", len(valid_clips))
    with GPU_LOAD_LOCK:
        try:
            siglip_model_processor = mm.load_siglip()
            logger.info("SigLIP vorgeladen auf %s", mm.device)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("SigLIP Vorladen fehlgeschlagen (%s) — Fallback: pro Video laden", e)
            siglip_model_processor = None

        try:
            raft_result = mm.load_raft()
            if raft_result[0] is not None:
                raft_model_device = raft_result
                logger.info("RAFT vorgeladen")
            else:
                raft_model_device = None
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("RAFT Vorladen fehlgeschlagen (%s) — CPU-Fallback", e)
            raft_model_device = None
            # RAFT-OOM kann SigLIP evictet haben
            if siglip_model_processor is not None and mm.model_type != "siglip":
                logger.warning("RAFT-OOM hat SigLIP evictet — SigLIP-Referenz invalidiert")
                siglip_model_processor = None

    total_clips = len(valid_clips)
    done = 0
    errors = 0
    total_scenes = 0
    total_embeddings = 0
    start_time = time.monotonic()

    try:
        for idx, (clip_id, video_path) in enumerate(valid_clips, start=1):
            elapsed = time.monotonic() - start_time
            eta_str = ""
            if idx > 1:
                avg_sec = elapsed / (idx - 1)
                eta_sec = avg_sec * (total_clips - idx + 1)
                eta_str = f" | ETA: {eta_sec/60:.1f}min"

            logger.info(
                "[%d/%d] Clip #%d: %s%s",
                idx, total_clips, clip_id, Path(video_path).name, eta_str,
            )

            try:
                result = run_full_pipeline(
                    video_path=video_path,
                    video_clip_id=clip_id,
                    progress_cb=lambda pct, msg: logger.debug("  [%d%%] %s", pct, msg),
                    siglip_model_processor=siglip_model_processor,
                    raft_model_device=raft_model_device,
                )
                done += 1
                total_scenes += len(result.scenes)
                total_embeddings += result.embeddings_stored
                logger.info(
                    "  -> OK: %d Szenen, %d Embeddings",
                    len(result.scenes),
                    result.embeddings_stored,
                )

            except FileNotFoundError as e:
                logger.error("  -> Datei nicht gefunden: %s", e)
                errors += 1
            except (OSError, RuntimeError, ValueError) as e:
                logger.error("  -> FEHLER: %s", e, exc_info=True)
                errors += 1
            finally:
                # Kein empty_cache() im Batch-Modus — korrumpiert CUDA-Heap
                gc.collect()

            # Fortschritt alle 50 Clips loggen
            if idx % 50 == 0:
                elapsed_min = (time.monotonic() - start_time) / 60
                logger.info(
                    "=== Fortschritt: %d/%d (%.1f%%) | %d Fehler | %.1f min ===",
                    idx, total_clips, idx / total_clips * 100,
                    errors, elapsed_min,
                )

    finally:
        # RAFT entladen
        if raft_model_device is not None:
            try:
                import torch
                raft_m, _ = raft_model_device
                if raft_m is not None:
                    raft_m.cpu()
                    del raft_m
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("RAFT entladen")
            except (RuntimeError, OSError, AttributeError) as e:
                logger.warning("RAFT Entladen fehlgeschlagen: %s", e)
            raft_model_device = None

        # SigLIP entladen
        if siglip_model_processor is not None:
            try:
                mm.unload()
                logger.info("SigLIP entladen")
            except (RuntimeError, OSError, AttributeError) as e:
                logger.warning("SigLIP Entladen fehlgeschlagen: %s", e)

    elapsed_total = time.monotonic() - start_time
    logger.info(
        "=== FERTIG: %d/%d Clips verarbeitet, %d Fehler | "
        "%d Szenen, %d Embeddings | %.1f min ===",
        done, total_clips, errors,
        total_scenes, total_embeddings,
        elapsed_total / 60,
    )

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

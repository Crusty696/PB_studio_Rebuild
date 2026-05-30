"""B-222-A: Model-Warmup-Helper — Pre-Download von SigLIP/RAFT.

Verhindert dass die Pipeline einen ~2.5 GB SigLIP-Download in einem
Background-Worker-Thread startet, waehrend der User parallel im UI
interagiert. Das Stress-Szenario hat Cross-Thread Use-After-Free in
Qt's Event-Dispatch ausgeloest (B-222).

Public API:
- ``is_siglip_cached(model_id)`` -> bool
- ``is_raft_cached()`` -> bool
- ``warmup_siglip(model_id, progress_cb=None)`` -> bool
- ``warmup_all(progress_cb=None)`` -> dict mit Status pro Modell

Alle Funktionen sind sync, blockierend, und sollten NICHT aus dem
Qt-Main-Thread direkt gerufen werden (sonst friert UI). Aufrufer
verwenden eigenen Worker-Thread + Progress-Dialog ODER rufen aus
einem einmaligen Setup-Script (scripts/warmup_models.py).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Default-Modelle die die Pipeline braucht. Synchron mit
# `services/model_manager.py:load_siglip` und `load_raft`.
SIGLIP_DEFAULT_MODEL = "google/siglip-so400m-patch14-384"
SIGLIP_REQUIRED_FILES = ("config.json", "preprocessor_config.json")
SIGLIP_LARGE_FILES = ("model.safetensors",)  # die >1 GB Gewichts-Datei


def is_siglip_cached(model_id: str = SIGLIP_DEFAULT_MODEL) -> tuple[bool, list[str]]:
    """Prueft ob SigLIP-Modell-Files vollstaendig im HF-Cache sind.

    Returns:
        (vollstaendig, fehlende_files). vollstaendig=True wenn alle
        SIGLIP_REQUIRED_FILES + SIGLIP_LARGE_FILES im Cache sind.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError as exc:
        logger.warning("huggingface_hub nicht verfuegbar: %s", exc)
        return False, ["huggingface_hub fehlt"]

    missing: list[str] = []
    for f in (*SIGLIP_REQUIRED_FILES, *SIGLIP_LARGE_FILES):
        path = try_to_load_from_cache(model_id, f)
        if path is None:
            missing.append(f)
    return (not missing), missing


def is_raft_cached() -> bool:
    """Prueft ob RAFT-Small-Weights von torchvision im Cache sind.

    torchvision speichert in ~/.cache/torch/hub/checkpoints/.
    """
    cache_root = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
    if not cache_root.exists():
        return False
    # Filename basiert auf torchvision-Version, suchen wir nach Pattern.
    for f in cache_root.glob("raft_small_*.pth"):
        try:
            if f.stat().st_size > 1_000_000:  # > 1 MB = nicht-leer
                return True
        except OSError:
            continue
    return False


def warmup_siglip(
    model_id: str = SIGLIP_DEFAULT_MODEL,
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """Lädt SigLIP-Files in den HF-Cache (Download wenn nötig).

    Verwendet ``snapshot_download`` — lädt alle Files atomar, mit
    Resume-Support und Verifikation. Idempotent.

    Returns:
        True bei Erfolg, False bei Fehlschlag (Network/Disk).
    """
    cached, missing = is_siglip_cached(model_id)
    if cached:
        if progress_cb:
            progress_cb(f"SigLIP {model_id} bereits im Cache.")
        return True

    if progress_cb:
        progress_cb(
            f"SigLIP {model_id} unvollstaendig (fehlt: {', '.join(missing)}) "
            f"— starte Download (~2.5 GB, kann mehrere Minuten dauern)..."
        )

    try:
        from huggingface_hub import snapshot_download
        # B-037 / B615: model_id stammt aus LOCKED-ADR-Liste (D-008),
        # kein User-Input. Latest-Pull ist gewollt; safetensors-Load
        # blockiert Code-Execution-Vektoren.
        snapshot_download(  # nosec B615
            repo_id=model_id,
            allow_patterns=[
                "config.json",
                "preprocessor_config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "*.safetensors",
                "spiece.model",
            ],
            # B-222 / huggingface_hub default: shows tqdm in console
            # — fuer GUI-Progress muss der Caller progress_cb selber
            # an einen Dialog routen (z.B. via QThread + Signal).
        )
    except Exception as exc:
        logger.error("SigLIP-Download fehlgeschlagen: %s", exc)
        if progress_cb:
            progress_cb(f"SigLIP-Download FEHLER: {exc}")
        return False

    cached_now, still_missing = is_siglip_cached(model_id)
    if cached_now:
        if progress_cb:
            progress_cb(f"SigLIP {model_id} jetzt vollstaendig im Cache.")
        return True

    logger.warning(
        "SigLIP-Download abgeschlossen, aber Cache weiterhin unvollstaendig: %s",
        still_missing,
    )
    if progress_cb:
        progress_cb(f"SigLIP-Download fertig, aber fehlt noch: {still_missing}")
    return False


def warmup_raft(progress_cb: Callable[[str], None] | None = None) -> bool:
    """Lädt RAFT-Small-Weights via torchvision (klein, ~5 MB).

    Returns:
        True wenn jetzt vorhanden, False bei Network/Disk-Fehler.
    """
    if is_raft_cached():
        if progress_cb:
            progress_cb("RAFT-Small bereits im Cache.")
        return True

    if progress_cb:
        progress_cb("RAFT-Small wird heruntergeladen (~5 MB)...")

    try:
        # Trick: torchvision laedt das Gewicht beim raft_small()-Aufruf.
        # Wir laden NICHT das Modell — wir triggern nur den Download.
        from torchvision.models.optical_flow import raft_small, Raft_Small_Weights
        _ = raft_small(weights=Raft_Small_Weights.DEFAULT)
        # Modell wieder freigeben — wir wollten nur den Cache-Download.
        del _
    except Exception as exc:
        logger.error("RAFT-Download fehlgeschlagen: %s", exc)
        if progress_cb:
            progress_cb(f"RAFT-Download FEHLER: {exc}")
        return False

    if progress_cb:
        progress_cb("RAFT-Small heruntergeladen.")
    return True


def warmup_all(progress_cb: Callable[[str], None] | None = None) -> dict[str, bool]:
    """Lädt SigLIP + RAFT in einem Aufruf, atomar.

    Returns:
        ``{"siglip": bool, "raft": bool}`` mit Erfolg/Fehler pro Modell.
    """
    return {
        "siglip": warmup_siglip(progress_cb=progress_cb),
        "raft": warmup_raft(progress_cb=progress_cb),
    }


def check_pipeline_models_ready() -> tuple[bool, list[str]]:
    """Pre-Flight-Check fuer Pipeline-Worker.

    Returns:
        (ready, gaps). ready=True wenn beide Modelle komplett sind.
        gaps ist eine Liste von Strings die der Caller dem User
        zeigen kann.
    """
    gaps: list[str] = []
    siglip_ok, missing = is_siglip_cached()
    if not siglip_ok:
        gaps.append(f"SigLIP fehlt im Cache: {', '.join(missing)}")
    if not is_raft_cached():
        gaps.append("RAFT-Small fehlt im Cache")
    return (not gaps), gaps

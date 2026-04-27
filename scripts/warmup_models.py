"""B-222-A: Model-Warmup CLI — laedt SigLIP + RAFT in den HF/torch-Cache.

Hintergrund (B-222): Wenn die Pipeline mit kaltem Cache startet, laeuft
der ~2.5 GB SigLIP-Download in einem Worker-Thread waehrend der User im
UI interagieren kann. Das Stress-Szenario hat Cross-Thread Use-After-Free
in Qt-Event-Dispatch ausgeloest.

Loesung: Modelle einmal vor dem ersten Pipeline-Run mit diesem Script
herunterladen. Idempotent — wenn bereits gecached, keine Operation.

Aufruf:
    python scripts/warmup_models.py
    python scripts/warmup_models.py --check-only    # nur Status, kein Download

Exit:
    0  = alle Modelle gecached (oder erfolgreich heruntergeladen)
    1  = Download fehlgeschlagen / Cache weiterhin unvollstaendig
    2  = HF / torchvision nicht installiert
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Project-Root in PYTHONPATH
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _print_progress(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PB Studio Model-Warmup (SigLIP + RAFT pre-download)."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Nur Cache-Status anzeigen, kein Download.",
    )
    args = parser.parse_args()

    try:
        from services.model_warmup import (
            check_pipeline_models_ready,
            is_siglip_cached,
            warmup_all,
            SIGLIP_DEFAULT_MODEL,
        )
    except ImportError as exc:
        print(f"FEHLER: services.model_warmup nicht importierbar: {exc}", file=sys.stderr)
        return 2

    print("=" * 70)
    print("PB Studio Model-Warmup")
    print("=" * 70)

    siglip_ok, missing = is_siglip_cached(SIGLIP_DEFAULT_MODEL)
    print(f"\nSigLIP ({SIGLIP_DEFAULT_MODEL}):")
    if siglip_ok:
        print("  [OK] vollstaendig im Cache.")
    else:
        print(f"  [FEHLT] {', '.join(missing)}")

    ready, gaps = check_pipeline_models_ready()
    print(f"\nRAFT-Small:")
    raft_ok = "RAFT" not in str(gaps)
    print(f"  [{'OK' if raft_ok else 'FEHLT'}]")

    print(f"\nGesamt-Status: {'OK' if ready else 'INCOMPLETE'}")
    if gaps:
        print("Luecken:")
        for g in gaps:
            print(f"  - {g}")

    if args.check_only:
        return 0 if ready else 1

    if ready:
        print("\nAlles bereits gecached — kein Download notwendig.")
        return 0

    print("\nStarte Download...")
    print("(Bei SigLIP: ~2.5 GB, bei langsamer Verbindung 5-15 min.)")
    print()
    results = warmup_all(progress_cb=_print_progress)

    print("\nErgebnis:")
    for name, ok in results.items():
        print(f"  {name}: {'OK' if ok else 'FEHLER'}")

    if all(results.values()):
        print("\nAlle Modelle erfolgreich gecached. Pipeline kann jetzt ohne")
        print("zusaetzlichen Background-Download laufen.")
        return 0

    print("\nMindestens ein Download fehlgeschlagen. Pruefe Internet,")
    print("Disk-Space (~3 GB benoetigt) und Logs oben.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

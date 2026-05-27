"""B-331 Repro + Instrumentierung: Demucs Full-Mix haengt nach Chunk ~51.

Symptom (Vault B-331): bei einem langen Mix bleibt die Demucs-Stem-Separation
nach "Verarbeite Chunk 51/403 ... " stehen — keine weiteren Logs, Prozess bei
~6.4 GB, nvidia-smi timeoutet, nur Stop-Process beendet ihn. Root-Cause
unbekannt (vermutlich CUDA-Hang in apply_model auf der GTX 1060).

Dieses Skript faehrt den ECHTEN Produktionspfad
(services.ai_audio_service.StemSeparator.separate) und instrumentiert ihn:

  - PB_STEM_MAX_CHUNKS begrenzt die Chunk-Zahl -> schneller Repro (Default 55,
    also knapp ueber den problematischen Chunk 51).
  - Heartbeat-Watchdog im Hauptthread loggt Wall-Clock + letzten Fortschritt.
  - faulthandler dumpt nach --stall-timeout ALLE Thread-Stacks -> zeigt, WO der
    Hang sitzt (z.B. innerhalb apply_model / CUDA-Call).

GPU-Hartregel: separate() nutzt intern cuda:0 (GTX 1060). Nichts geaendert.

Nutzung (im conda-env pb-studio, GPU aktiv):
    python tools/diag_b331_demucs_chunk_hang.py --audio "C:\\...\\langer_mix.mp3"
    python tools/diag_b331_demucs_chunk_hang.py --audio mix.mp3 --max-chunks 55 --stall-timeout 180

WICHTIG: Echter Demucs-GPU-Lauf -> NICHT parallel zu anderen GPU-Jobs starten.
Wenn der Hang auftritt, anschliessend in separater Shell `nvidia-smi` pruefen.
"""
from __future__ import annotations

import argparse
import faulthandler
import os
import sys
import threading
import time


def main() -> int:
    ap = argparse.ArgumentParser(description="B-331 Demucs Chunk-Hang Repro (cuda:0)")
    ap.add_argument("--audio", required=True, help="Pfad zum langen Audio-Mix")
    ap.add_argument("--max-chunks", type=int, default=55,
                    help="PB_STEM_MAX_CHUNKS — Chunk-Limit fuer schnellen Repro (Default 55)")
    ap.add_argument("--model", default="htdemucs_ft", help="Demucs-Modell (Default = service-Default)")
    ap.add_argument("--stall-timeout", type=int, default=180,
                    help="Sekunden ohne Abschluss bis Thread-Stack-Dump (Hang-Beweis)")
    ap.add_argument("--heartbeat", type=int, default=5, help="Heartbeat-Intervall in Sekunden")
    args = ap.parse_args()

    if not os.path.isfile(args.audio):
        print(f"FEHLER: Audio-Datei nicht gefunden: {args.audio}")
        return 2

    # Chunk-Limit fuer Repro setzen, BEVOR der Service importiert/laeuft.
    os.environ["PB_STEM_MAX_CHUNKS"] = str(args.max_chunks)

    import torch
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}  capability={torch.cuda.get_device_capability(0)}")
    else:
        print("WARNUNG: CUDA nicht verfuegbar — der Hang ist GPU-spezifisch; CPU-Lauf reproduziert ihn evtl. nicht.")

    from services.ai_audio_service import StemSeparator

    # faulthandler: dumpt nach stall-timeout ALLE Thread-Stacks (repeat) ->
    # zeigt die genaue Hang-Stelle, auch wenn Python im CUDA-Call blockiert.
    faulthandler.enable()
    faulthandler.dump_traceback_later(args.stall_timeout, repeat=True, exit=False)

    state = {"last_msg": "start", "last_pct": 0, "last_ts": time.time(), "done": False, "error": None, "result": None}
    lock = threading.Lock()

    def _progress(pct, msg):
        with lock:
            state["last_msg"] = msg
            state["last_pct"] = pct
            state["last_ts"] = time.time()

    def _worker():
        try:
            sep = StemSeparator()
            res = sep.separate(args.audio, model=args.model, progress_cb=_progress)
            with lock:
                state["result"] = res
        except Exception as exc:  # noqa: BLE001 — Diagnose-Tool, alles berichten
            with lock:
                state["error"] = repr(exc)
        finally:
            with lock:
                state["done"] = True

    t0 = time.time()
    worker = threading.Thread(target=_worker, name="demucs-separate", daemon=True)
    worker.start()

    hang_reported = False
    while worker.is_alive():
        time.sleep(args.heartbeat)
        with lock:
            elapsed = time.time() - t0
            since = time.time() - state["last_ts"]
            msg, pct = state["last_msg"], state["last_pct"]
        print(f"[heartbeat] t+{elapsed:6.1f}s  last='{msg}' ({pct}%)  seit letztem Fortschritt: {since:5.1f}s",
              flush=True)
        if since >= args.stall_timeout and not hang_reported:
            print(f"\n!!! WAHRSCHEINLICHER HANG: {since:.0f}s kein Fortschritt seit '{msg}'.\n"
                  f"    Thread-Stacks wurden via faulthandler oben gedumpt (Hang-Stelle).\n"
                  f"    Jetzt in SEPARATER Shell pruefen: nvidia-smi (timeoutet ggf. -> GPU-Stuck bestaetigt).\n",
                  flush=True)
            hang_reported = True

    faulthandler.cancel_dump_traceback_later()
    with lock:
        if state["error"]:
            print(f"\nSeparate endete mit Fehler: {state['error']}")
            # RuntimeError mit 'Diagnose-Limit' = sauberer Stop am Chunk-Limit (KEIN Hang).
            if "Diagnose-Limit" in (state["error"] or ""):
                print("-> Chunk-Limit sauber erreicht, KEIN Hang bis hier. "
                      "Fuer echten Repro --max-chunks hochsetzen.")
            return 0
        print(f"\nFertig in {time.time() - t0:.1f}s. Stems: {state['result']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

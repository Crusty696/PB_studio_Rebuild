"""Prozess-, GPU- und Speicher-Sampler fuer autonome App-Testlaeufe.

Schreibt im festen Takt eine Zeile je beobachtetem Prozess in eine Logdatei:
PID, Name, CPU-Prozent, RSS, Anzahl Threads und offene Dateien, dazu eine
Systemzeile mit GPU-Auslastung und freiem Speicher. Laeuft bis er beendet wird.

Aufruf: python scripts/process_sampler.py <logdatei> [intervall_sekunden]
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover
    print("psutil fehlt", file=sys.stderr)
    raise SystemExit(2)

WATCH = ("python", "pythonw", "pb_studio", "ffmpeg", "ffprobe", "ollama")
LOG = Path(sys.argv[1] if len(sys.argv) > 1 else "process_sample.log")
INTERVAL = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0


def gpu_line() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip().replace("\n", " | ") or "n/a"
    except (OSError, subprocess.SubprocessError):
        return "n/a"


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"# Sampler gestartet {datetime.now():%Y-%m-%d %H:%M:%S}, "
                 f"Intervall {INTERVAL}s\n")
        fh.flush()
        seen: dict[int, str] = {}
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            vm = psutil.virtual_memory()
            fh.write(f"[{now}] SYS gpu={gpu_line()} | "
                     f"ram_used={vm.used / 2**30:.1f}G/{vm.total / 2**30:.1f}G\n")
            alive: set[int] = set()
            for proc in psutil.process_iter(["pid", "name"]):
                name = (proc.info["name"] or "").lower()
                if not any(w in name for w in WATCH):
                    continue
                pid = proc.info["pid"]
                alive.add(pid)
                if pid not in seen:
                    try:
                        cmd = " ".join(proc.cmdline())[:160]
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        cmd = "?"
                    seen[pid] = name
                    fh.write(f"[{now}] NEU  pid={pid} {name} :: {cmd}\n")
                try:
                    with proc.oneshot():
                        cpu = proc.cpu_percent(None)
                        rss = proc.memory_info().rss / 2**20
                        threads = proc.num_threads()
                    fh.write(f"[{now}] PROC pid={pid} {name:<12} "
                             f"cpu={cpu:5.1f}% rss={rss:8.1f}M threads={threads}\n")
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            for pid in [p for p in seen if p not in alive]:
                fh.write(f"[{now}] ENDE pid={pid} {seen.pop(pid)}\n")
            fh.flush()
            time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass

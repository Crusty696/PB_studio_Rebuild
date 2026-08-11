"""Vollstaendige Aufzeichnung einer manuellen PB-Studio-Sitzung.

Der User fahrt den Durchlauf selbst; dieses Skript protokolliert, was die
App dabei *tut* — nicht nur was geklickt wurde. Zusammengefuehrt in eine
Datei, damit sich Ursache und Wirkung nebeneinander lesen lassen:

* jede Zeile aus ``logs/pb_studio.log`` (DEBUG, live mitgeschrieben)
* Traceback-/Crash-Erkennung, gesondert markiert
* alle 5 s ein Zustandsabbild: RAM, Threads, GPU-VRAM, GPU-Last
* DB-Zeilenzahlen der wichtigsten Tabellen, sobald sie sich aendern
* Start/Ende von Worker-Tasks (aus dem App-Log gefiltert)
* neu entstandene Dateien in ``storage/`` und ``outputs/``

Aufruf::

    python tools/session_recorder.py [--out PFAD] [--interval 5]

Beenden mit Strg-C; die Datei wird sauber abgeschlossen.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_LOG = ROOT / "logs" / "pb_studio.log"

# Tabellen, deren Zeilenzahl beim Arbeiten aussagekraeftig ist.
WATCH_TABLES = [
    "projects", "video_clips", "audio_tracks", "timeline_entries",
    "scenes", "struct_clip_tags", "waveform_data",
]

# Zeilen, die einen Worker-/Task-Wechsel anzeigen.
TASK_PAT = re.compile(
    r"TaskEngine|Worker|Task |task_id|gestartet|abgeschlossen|abgebrochen|"
    r"finished|cancel", re.IGNORECASE,
)
ERROR_PAT = re.compile(r"Traceback|ERROR|CRITICAL|Fatal|Exception|0x[0-9a-fA-F]{8}")


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class Recorder:
    def __init__(self, out_path: Path, interval: float) -> None:
        self.out = out_path.open("a", encoding="utf-8", buffering=1)
        self.interval = interval
        self.stop = threading.Event()
        self._last_counts: dict[str, int] = {}
        self._last_files: set[str] = set()

    def write(self, kategorie: str, text: str) -> None:
        self.out.write(f"[{_stamp()}] {kategorie:<10} | {text}\n")

    # ---------------------------------------------------------------- App-Log
    def tail_app_log(self) -> None:
        """Haengt sich an das App-Log und schreibt jede Zeile mit."""
        while not self.stop.is_set() and not APP_LOG.exists():
            time.sleep(0.5)
        if self.stop.is_set():
            return
        with APP_LOG.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            while not self.stop.is_set():
                line = fh.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                line = line.rstrip("\n")
                if ERROR_PAT.search(line):
                    self.write("FEHLER", line)
                elif TASK_PAT.search(line):
                    self.write("TASK", line)
                else:
                    self.write("APPLOG", line)

    # ------------------------------------------------------------- Ressourcen
    def _gpu(self) -> str:
        try:
            r = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=memory.used,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            used, util, temp = (x.strip() for x in r.stdout.strip().split(","))
            return f"VRAM {used} MiB, GPU {util} %, {temp} C"
        except Exception as exc:
            return f"nicht lesbar ({type(exc).__name__})"

    def _proc(self) -> str:
        try:
            import psutil
            rows = []
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                cl = " ".join(p.info.get("cmdline") or [])
                if "main.py" in cl and "python" in (p.info.get("name") or "").lower():
                    with p.oneshot():
                        rss = p.memory_info().rss / 1048576
                        rows.append(
                            f"PID {p.info['pid']}: RAM {rss:.0f} MB, "
                            f"Threads {p.num_threads()}, CPU {p.cpu_percent():.0f} %"
                        )
            return " | ".join(rows) if rows else "keine App-Instanz gefunden"
        except Exception as exc:
            return f"nicht lesbar ({type(exc).__name__})"

    # ---------------------------------------------------------------- DB / FS
    def _db_counts(self) -> None:
        for db in sorted(ROOT.glob("outputs/*/pb_studio.db")) + [ROOT / "pb_studio.db"]:
            if not db.exists():
                continue
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
                for tbl in WATCH_TABLES:
                    # Der Tabellenname laesst sich nicht parametrisieren (SQLite
                    # erlaubt Platzhalter nur fuer Werte, nicht fuer Bezeichner).
                    # Statt sich darauf zu verlassen, dass WATCH_TABLES eine
                    # Code-Konstante ist, wird hier explizit dagegen validiert —
                    # das haelt auch, falls die Liste spaeter befuellt wird.
                    if tbl not in WATCH_TABLES:
                        continue
                    sql = f"SELECT COUNT(*) FROM {tbl}"  # nosec B608 - Bezeichner gegen WATCH_TABLES validiert
                    try:
                        n = con.execute(sql).fetchone()[0]
                    except sqlite3.Error:
                        continue
                    key = f"{db.parent.name}/{tbl}"
                    if self._last_counts.get(key) != n:
                        vorher = self._last_counts.get(key)
                        if vorher is not None:
                            self.write("DB", f"{key}: {vorher} -> {n}")
                        self._last_counts[key] = n
                con.close()
            except sqlite3.Error as exc:
                self.write("DB", f"{db.name} nicht lesbar: {exc}")

    def _new_files(self) -> None:
        aktuell: set[str] = set()
        for base in ("storage", "outputs"):
            d = ROOT / base
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file():
                    aktuell.add(str(f.relative_to(ROOT)))
        if self._last_files:
            for neu in sorted(aktuell - self._last_files)[:25]:
                self.write("DATEI", f"neu: {neu}")
            for weg in sorted(self._last_files - aktuell)[:25]:
                self.write("DATEI", f"entfernt: {weg}")
        self._last_files = aktuell

    # ------------------------------------------------------------------ Schleife
    def sample_loop(self) -> None:
        while not self.stop.is_set():
            self.write("ZUSTAND", f"{self._proc()} || GPU: {self._gpu()}")
            self._db_counts()
            try:
                self._new_files()
            except Exception as exc:
                self.write("FEHLER", f"Datei-Scan: {type(exc).__name__}: {exc}")
            self.stop.wait(self.interval)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--interval", type=float, default=5.0)
    args = ap.parse_args()

    out = Path(args.out) if args.out else (
        ROOT / "logs" / f"manuelle-session-{datetime.now():%Y-%m-%d_%H%M%S}.log"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    rec = Recorder(out, args.interval)
    rec.write("START", f"Aufzeichnung beginnt. Ablage: {out}")
    rec.write("START", f"App-Log: {APP_LOG} | Abtastung alle {args.interval:.0f} s")
    rec._new_files()          # Ausgangsbestand, ohne ihn als "neu" zu melden
    rec._db_counts()          # Ausgangszaehlung, dito

    threads = [
        threading.Thread(target=rec.tail_app_log, daemon=True),
        threading.Thread(target=rec.sample_loop, daemon=True),
    ]
    for t in threads:
        t.start()

    print(f"Aufzeichnung laeuft -> {out}")
    print("Beenden mit Strg-C.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop.set()
        time.sleep(0.5)
        rec.write("ENDE", "Aufzeichnung beendet.")
        rec.out.close()
        print(f"\nFertig. Datei: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

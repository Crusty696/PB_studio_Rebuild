"""Regressions-Baseline: meldet nur die Differenz zum festgehaltenen Stand.

Hintergrund (Selbstpruefung 2026-08-31): Elf Fixes hintereinander wurden je mit
einem ``-k``-gefilterten Lauf als "Regression gruen" verbucht. Der erste volle
Lauf zeigte 19 rote Tests — deren Herkunft musste danach einzeln gegen den
Ausgangsstand geprueft werden. Ein gefilterter Lauf beweist nichts ueber den
Gesamtstand, und ein voller Lauf ohne Vergleichsmassstab ist nur eine Zahl.

Gebrauch:

    python tools/regression_baseline.py record     # vollen Lauf als Baseline festhalten
    python tools/regression_baseline.py check      # vollen Lauf gegen die Baseline
    python tools/regression_baseline.py check -k "pacing"   # Teilmenge, gleicher Vergleich

``check`` endet mit Exit-Code 1, sobald ein Test rot ist, der in der Baseline
gruen war. Vorbestehende rote Tests fuehren nicht zum Fehlschlag, werden aber
gezaehlt — und ein Test, der in der Baseline rot war und jetzt gruen ist, wird
als Verbesserung gemeldet, damit die Baseline nachgezogen werden kann.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Ueber PB_BASELINE_FILE umlenkbar — noetig, um das Werkzeug selbst gegen einen
# kuenstlich roten Test zu pruefen, ohne die echte Baseline zu ueberschreiben.
BASELINE = Path(os.environ.get(
    "PB_BASELINE_FILE", REPO_ROOT / "tests" / "known_failures.json"))

# "FAILED tests/foo.py::test_bar - AssertionError: ..." -> "tests/foo.py::test_bar"
#
# Die erste Fassung nahm ``\S+?`` fuer den Testnamen und verlor damit jeden
# parametrisierten Test, dessen Parameter ein Leerzeichen enthaelt — etwa
# ``test_recall_question_does_not_route_to_vision[Was weisst du ueber Clip X?]``.
# Im ersten Baseline-Lauf fehlten dadurch 4 von 20 roten Tests; sie waeren
# beim naechsten ``check`` faelschlich als NEU ROT gemeldet worden.
# Deshalb: ganze Zeile nehmen, Begruendung hinter " - " abschneiden.
_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(.+)$", re.M)


def _testname(zeile: str) -> str:
    """'tests/a.py::test_b[Was ist X?] - AssertionError: ...' -> Testname.

    Leerer String, wenn die Zeile kein Testknoten ist. Das ist noetig, weil
    pytest auch Log-Zeilen mit ``ERROR`` am Zeilenanfang ausgibt:

        ERROR [root] StemSeparationWorker[1] crashed: AudioTrack 1 nicht gefunden

    Im zweiten Baseline-Lauf standen dadurch 23 Eintraege in der Datei, obwohl
    nur 19 Tests rot waren. Die erste Fassung des Musters war zu eng (verlor
    parametrisierte Namen mit Leerzeichen), die zweite zu weit. Verlaesslich
    ist nur: ein Testknoten enthaelt einen Dateipfad auf .py.
    """
    name = zeile.split(" - ", 1)[0].strip()
    return name if ".py" in name else ""


def _python() -> str:
    return sys.executable


def lauf(k_filter: str | None = None) -> tuple[set[str], str]:
    """Fuehrt pytest aus und liefert (rote Tests, Zusammenfassungszeile)."""
    cmd = [_python(), "-m", "pytest", "tests/", "-p", "no:randomly", "--tb=no", "-q"]
    if k_filter:
        cmd += ["-k", k_filter]
    fertig = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    ausgabe = fertig.stdout + fertig.stderr
    rot = {_testname(treffer) for treffer in _FAILED.findall(ausgabe)}
    rot.discard("")
    letzte = [z for z in ausgabe.splitlines() if " passed" in z or " failed" in z]
    return rot, (letzte[-1].strip() if letzte else "keine Zusammenfassung")


def baseline_lesen() -> dict:
    if not BASELINE.is_file():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def cmd_record(args) -> int:
    rot, summary = lauf(args.k)
    daten = {
        "aufgenommen_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True).stdout.strip(),
        "zusammenfassung": summary,
        "bekannte_rote_tests": sorted(rot),
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(daten, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"Baseline geschrieben: {len(rot)} bekannte rote Tests")
    print(f"  {summary}")
    try:
        anzeige = BASELINE.relative_to(REPO_ROOT)
    except ValueError:  # per PB_BASELINE_FILE ausserhalb des Repos umgelenkt
        anzeige = BASELINE
    print(f"  -> {anzeige}")
    return 0


def cmd_check(args) -> int:
    daten = baseline_lesen()
    if not daten:
        print("Keine Baseline vorhanden. Erst 'record' ausfuehren.")
        return 2

    bekannt = set(daten.get("bekannte_rote_tests", []))
    rot, summary = lauf(args.k)

    neu = sorted(rot - bekannt)
    # Bei einem gefilterten Lauf sagt eine fehlende Zeile nichts ueber den Test aus.
    repariert = sorted(bekannt - rot) if not args.k else []

    print(summary)
    print(f"Baseline vom {daten.get('aufgenommen_am', '?')} "
          f"({len(bekannt)} bekannte rote Tests, HEAD {daten.get('head', '?')[:8]})")

    if repariert:
        print(f"\nNicht mehr rot ({len(repariert)}) — Baseline nachziehen:")
        for t in repariert:
            print(f"  + {t}")

    if neu:
        print(f"\nNEU ROT ({len(neu)}):")
        for t in neu:
            print(f"  - {t}")
        return 1

    print("\nKeine neuen roten Tests.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name, hilfe in (("record", "vollen Lauf als Baseline festhalten"),
                        ("check", "Lauf gegen die Baseline vergleichen")):
        s = sub.add_parser(name, help=hilfe)
        s.add_argument("-k", default=None, help="pytest -k Ausdruck (optional)")
    args = p.parse_args()
    return cmd_record(args) if args.command == "record" else cmd_check(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Pruefstand — startet alle Pruefwerkzeuge und schreibt einen Bericht.

Die fuenf Werkzeuge vom 2026-08-31 liefern jedes fuer sich Zahlen. Wer sie
einzeln aufruft, vergisst eines oder vergleicht Aepfel mit Birnen. Dieses
Skript fuehrt sie nacheinander aus und legt das Ergebnis als Markdown ab —
gedacht als Eingabe fuer eine Bewertung (etwa durch /consulting-team).

    python tools/pruefstand.py
    python tools/pruefstand.py --projekt <pfad>     # auch Pacing-Kennzahlen
    python tools/pruefstand.py --schnell            # ohne vollen Testlauf

Werkzeuge:

* regression_baseline check  — neue rote Tests gegenueber der Baseline
* inventory_audit            — unerreichbare Knoepfe, tote Spalten/Aktionen
* session_learning relevant  — Lehren zum gerade geaenderten Code
* pacing_metrics             — Kennzahlen eines Auto-Edit-Laufs (nur mit --projekt)
* clip_pools                 — die Randfall-Tests dazu

Das Skript **bewertet nichts**. Es sammelt und zeigt Differenzen; ob eine Zahl
gut oder schlecht ist, entscheidet der Leser.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BERICHT = REPO_ROOT / "test-report" / "pruefstand.md"


def _lauf(name: str, argumente: list[str], timeout: int = 2400) -> dict:
    """Fuehrt ein Werkzeug aus und faengt alles ab, was schiefgehen kann."""
    print(f"  ... {name}", flush=True)
    befehl = [sys.executable, *argumente]
    try:
        fertig = subprocess.run(
            befehl, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
        return {
            "name": name,
            "befehl": " ".join(argumente),
            "code": fertig.returncode,
            "ausgabe": (fertig.stdout + fertig.stderr).strip(),
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "befehl": " ".join(argumente), "code": -1,
                "ausgabe": f"Zeitueberschreitung nach {timeout}s"}
    except Exception as exc:  # noqa: BLE001 — ein Werkzeug darf den Lauf nicht kippen
        return {"name": name, "befehl": " ".join(argumente), "code": -2,
                "ausgabe": f"Start fehlgeschlagen: {exc}"}


def _kuerzen(text: str, zeilen: int = 40) -> str:
    teile = text.splitlines()
    if len(teile) <= zeilen:
        return text
    weg = len(teile) - zeilen
    return "\n".join(teile[:zeilen] + [f"... ({weg} weitere Zeilen)"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--projekt", default=None,
                   help="Projektordner fuer die Pacing-Kennzahlen")
    p.add_argument("--preset", default="Standard")
    p.add_argument("--schnell", action="store_true",
                   help="Regression nur ueber die Werkzeug-Tests statt vollem Lauf")
    p.add_argument("--out", default=str(BERICHT))
    args = p.parse_args()

    print("Pruefstand laeuft — das dauert, der volle Testlauf allein ~20 min.")
    ergebnisse = []

    regression = ["tools/regression_baseline.py", "check"]
    if args.schnell:
        regression += ["-k", "werkzeuge or b944 or clip_pools"]
    ergebnisse.append(_lauf("Regression gegen die Baseline", regression))

    ergebnisse.append(_lauf(
        "Inventar (unerreichbare Knoepfe, tote Spalten)",
        ["tools/inventory_audit.py"], timeout=900))

    ergebnisse.append(_lauf(
        "Passende Lehren zum geaenderten Code",
        ["tools/session_learning.py", "relevant", "--changed", "--limit", "5"],
        timeout=120))

    ergebnisse.append(_lauf(
        "Randfall-Pools (Laengenlogik)",
        ["-m", "pytest", "tests/test_services/test_b944_randfall_pools.py",
         "-q", "-p", "no:randomly", "--tb=line"], timeout=600))

    if args.projekt:
        ergebnisse.append(_lauf(
            f"Pacing-Kennzahlen ({args.preset})",
            ["tools/pacing_metrics.py", "--projekt", args.projekt,
             "--preset", args.preset], timeout=1800))
    else:
        ergebnisse.append({
            "name": "Pacing-Kennzahlen", "befehl": "--projekt fehlt",
            "code": None,
            "ausgabe": "Uebersprungen: ohne --projekt <pfad> laesst sich kein "
                       "Auto-Edit fahren.",
        })

    zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M")
    kopf = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True).stdout.strip()

    zeilen = [
        f"# Pruefstand {zeitpunkt}", "",
        f"Stand: `{kopf}`", "",
        "Dieser Bericht **bewertet nichts**. Er sammelt, was die Werkzeuge "
        "gemessen haben.", "",
        "## Ueberblick", "",
        "| Werkzeug | Ergebnis |", "|---|---|",
    ]
    for e in ergebnisse:
        if e["code"] is None:
            stand = "uebersprungen"
        elif e["code"] == 0:
            stand = "ohne Befund"
        elif e["code"] < 0:
            stand = "**nicht gelaufen**"
        else:
            stand = f"**Befund** (Code {e['code']})"
        zeilen.append(f"| {e['name']} | {stand} |")

    zeilen += ["", "## Ausgaben", ""]
    for e in ergebnisse:
        zeilen += [f"### {e['name']}", "", f"`{e['befehl']}`", "",
                   "```", _kuerzen(e["ausgabe"]) or "(keine Ausgabe)", "```", ""]

    zeilen += [
        "## Was das Sammeln nicht kann", "",
        "Diese Werkzeuge finden Struktur- und Regressionsfehler. Sie finden",
        "**nicht**, ob eine Funktion inhaltlich das Richtige tut — dafuer",
        "braucht es einen Live-Test am laufenden Programm oder ein Urteil.",
        "",
    ]

    ziel = Path(args.out)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(zeilen), encoding="utf-8")

    print("")
    for e in ergebnisse:
        marke = {None: "-", 0: "ok"}.get(e["code"], "BEFUND")
        print(f"  {marke:>6}  {e['name']}")
    print(f"\nBericht: {ziel}")

    return 1 if any(e["code"] for e in ergebnisse if e["code"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

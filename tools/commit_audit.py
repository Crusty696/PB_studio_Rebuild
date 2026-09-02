"""Commit-Prueferin — haelt jede Commit-Nachricht gegen ihren eigenen Diff.

Am 2026-09-01 fand ein Pruef-Agent den bis dahin unsichtbarsten Fehler des
Projekts: Commit ``bc19d9b`` trug eine Nachricht, die eine h265-NVENC-Pruefung
und vier neue Tests beschreibt. Eingecheckt waren vier geloeschte Importzeilen
in zwei Dateien. Fix und Tests fehlten vollstaendig.

Kein Werkzeug haette das gefunden. Die Nachricht war plausibel, der Bug-Eintrag
stand auf behoben, und der Code funktionierte auf der Entwicklungsmaschine,
weil sie NVENC hat. Sichtbar wird so etwas nur, wenn jemand die Zusage gegen
den Diff haelt.

Geprueft wird:

* **Genannte Dateien**: Pfade in der Nachricht, die der Commit nicht anfasst.
* **Versprochene Tests**: Nachricht spricht von Tests, der Diff enthaelt aber
  keine Datei unter ``tests/``.
* **Nur-Loeschung**: Nachricht beschreibt eine Reparatur, der Diff loescht
  ausschliesslich Zeilen.

    python tools/commit_audit.py                 # letzte 20 Commits
    python tools/commit_audit.py --anzahl 100
    python tools/commit_audit.py --commit bc19d9b

Exit 1, sobald ein Commit auffaellt. Das Werkzeug **bewertet nicht**, ob die
Abweichung schlimm ist - es zeigt sie.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Pfade in der Nachricht: mindestens ein Schraegstrich und eine bekannte Endung.
_PFAD = re.compile(r"\b((?:[\w.-]+/)+[\w.-]+\.(?:py|yaml|yml|json|md|spec|toml))\b")
# "vier neue Tests", "Tests:", "pytest ..." - Hinweise auf zugesagte Tests.
#
# Die Wortgrenze steht bewusst nur am Anfang jeder Alternative. Ein `\b` am
# Ende laesst "Tests:" durchrutschen: nach dem Doppelpunkt folgt ein Leerzeichen,
# also zwei Nicht-Wortzeichen und damit keine Grenze. Genau daran lief die
# Pruefung beim ersten Lauf am 2026-09-01 vorbei - beim eigenen Zielfall.
_TESTZUSAGE = re.compile(
    r"(\d+\s+(?:neue\s+)?Tests?\b|\bTests?:|\bneue[rn]?\s+Test|\bpytest\b"
    r"|\bRegressionstest|\bTestfall)",
    re.I,
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def _commits(anzahl: int, einzeln: str | None) -> list[str]:
    if einzeln:
        return [einzeln]
    return [z for z in _git("log", f"-{anzahl}", "--format=%H").splitlines() if z]


# Betreffe, bei denen eine reine Loeschung genau die Reparatur ist.
_LOESCH_ABSICHT = re.compile(
    # Ohne Wortgrenzen: "removes", "entfernt" und "geloescht" sollen alle
    # treffen. Ein erster Versuch mit \b scheiterte daran, dass die Sequenz
    # beim Schreiben der Datei zu einem Backspace-Zeichen wurde - der Ausdruck
    # suchte danach woertlich nach 0x08 und traf nie.
    "remove|delete|drop|entfern|loesch|cleanup|dead code|toter code|toten code",
    re.I,
)


def _pruefe(sha: str) -> tuple[list[str], list[str]]:
    nachricht = _git("log", "-1", "--format=%B", sha)
    dateien = [z for z in _git("show", "--name-only", "--format=", sha).splitlines() if z]
    zahlen = _git("show", "--shortstat", "--format=", sha).strip()

    befunde: list[str] = []
    hinweise: list[str] = []

    # Merge-Commits haben keinen eigenen Diff — `git show --name-only` liefert
    # nichts, und jede Pruefung schlaegt dann falsch an. Gemessen ueber 400
    # Commits war 22f96b86 genau so ein Fall.
    if len(_git("log", "-1", "--format=%P", sha).split()) > 1:
        return [], []

    genannt = {p for p in _PFAD.findall(nachricht)}
    # Nur Pfade werten, die es im Repo auch gibt - sonst schlagen Beispiele an.
    genannt = {p for p in genannt if (REPO_ROOT / p).exists()}
    fehlend = sorted(p for p in genannt if p not in dateien)
    if fehlend:
        # Gemessen am 2026-09-01 ueber 60 Commits: 18 von 22 Befunden kamen aus
        # dieser Pruefung. Eine Nachricht nennt eine Datei sehr oft als Verweis
        # ("wie in services/pacing_service.py beschrieben"), ohne sie aendern zu
        # wollen. Deshalb Hinweis statt Befund - sonst uebertoent das Rauschen
        # die beiden aussagekraeftigen Pruefungen.
        hinweise.append(
            "nennt Dateien, die der Commit nicht anfasst: " + ", ".join(fehlend)
        )

    if _TESTZUSAGE.search(nachricht) and not any(
        d.startswith("tests/") or "/tests/" in d for d in dateien
    ):
        befunde.append("Nachricht spricht von Tests, der Diff enthaelt keine Testdatei")

    if zahlen and "insertion" not in zahlen and "deletion" in zahlen:
        erste = nachricht.strip().splitlines()[0] if nachricht.strip() else ""
        # Ein Commit, der ausdruecklich Totes entfernt, DARF nur loeschen.
        # 89f76b3e ("remove dead ...") war so ein Fall - die Loeschung ist die
        # Reparatur, nicht ihr Fehlen.
        if erste.lower().startswith(("fix", "feat")) and not _LOESCH_ABSICHT.search(erste):
            befunde.append(f"Nur Loeschungen ({zahlen}), aber Betreff lautet: {erste[:60]}")

    return befunde, hinweise


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--anzahl", type=int, default=20)
    p.add_argument("--commit", default=None)
    args = p.parse_args()

    shas = _commits(args.anzahl, args.commit)
    if not shas:
        print("Keine Commits gefunden.")
        return 0

    print(f"Geprueft: {len(shas)} Commits\n")
    auffaellig = mit_hinweis = 0
    for sha in shas:
        befunde, hinweise = _pruefe(sha)
        if befunde:
            auffaellig += 1
        if hinweise:
            mit_hinweis += 1
        if not befunde and not hinweise:
            continue
        betreff = _git("log", "-1", "--format=%s", sha).strip()
        print(f"  {sha[:8]}  {betreff[:66]}")
        for b in befunde:
            print(f"            BEFUND  {b}")
        for h in hinweise:
            print(f"            hinweis {h}")
        print()

    print(f"{auffaellig} von {len(shas)} Commits mit Befund "
          f"(zusaetzlich {mit_hinweis} mit Hinweis).")
    print()
    print("Befund heisst: die Nachricht verspricht Tests, die im Diff fehlen, oder sie")
    print("beschreibt eine Reparatur, waehrend der Diff nur loescht. Hinweis heisst:")
    print("die Nachricht nennt eine Datei, die sie nicht anfasst - das ist oft ein")
    print("legitimer Verweis. Gemessen ueber 60 Commits kamen 18 von 22 Meldungen aus")
    print("dieser Kategorie, deshalb zaehlt sie nicht als Befund.")
    return 1 if auffaellig else 0


if __name__ == "__main__":
    raise SystemExit(main())

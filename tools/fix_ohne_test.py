"""Sucht Reparaturen, die kein Test absichert.

Am 2026-09-01 fiel zweimal dasselbe Muster auf: ein Fix stand im Produktivcode,
war live belegt - und kein einziger Test sicherte ihn gegen Regression ab.
Bei B-964 bemerkte es ein Pruef-Agent, bei B-963 die Commit-Prueferin.

Beides waren Zufallsfunde. Dieses Werkzeug macht daraus eine Messung:

* Es sammelt alle Bug-IDs, die im Produktivcode als Kommentar auftauchen -
  ``# B-964: ...`` markiert eine Stelle, die wegen dieses Bugs so aussieht,
  wie sie aussieht.
* Es sammelt alle Bug-IDs, die irgendwo unter ``tests/`` vorkommen.
* Die Differenz ist die Antwort: Reparaturen im Code, die kein Test nennt.

Das ist ein Naeherungswert, kein Beweis. Ein Test kann eine Reparatur
absichern, ohne die Bug-ID zu nennen, und eine genannte ID heisst nicht, dass
der Test die richtige Sache prueft. Als Suchhilfe reicht es - genau die zwei
Faelle, die heute per Zufall auffielen, stehen darin.

    python tools/fix_ohne_test.py
    python tools/fix_ohne_test.py --seit B-900     # nur neuere IDs
    python tools/fix_ohne_test.py --json bericht.json

Zusaetzlich meldet es Bug-IDs, die im Code stehen, aber im Vault gar nicht
existieren. Der erste Lauf fand genau so einen Fall: ``FIX B-1001`` in
``agents/orchestrator_agent.py`` - die hoechste vergebene Nummer war B-964.

Exit 1, sobald mindestens eine Bug-ID nur im Produktivcode steht.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# B-964, B-1024 - immer mit Bindestrich, immer mit fuehrendem B.
_BUG_ID = re.compile(r"\bB-(\d{3,4})\b")

PRODUKTIV = ("services", "ui", "workers", "agents", "database", "tools")
AUSGESCHLOSSEN = {".git", "__pycache__", ".venv", "node_modules", "qa_artifacts"}
# Das Werkzeug selbst nennt Bug-IDs als Beispiel - sonst findet es sich selbst.
SELBST = {"tools/fix_ohne_test.py"}
VAULT_BUGS = Path(
    r"C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\bugs"
)


def _dateien(wurzel: Path) -> list[Path]:
    if not wurzel.exists():
        return []
    return [
        p for p in wurzel.rglob("*.py")
        if not any(teil in AUSGESCHLOSSEN for teil in p.parts)
        and p.relative_to(REPO_ROOT).as_posix() not in SELBST
    ]


def _ids_in_dateinamen(dateien: list[Path]) -> dict[str, list[str]]:
    """Bug-IDs, die nur im Dateinamen stehen: ``test_b907_...py`` -> ``B-907``.

    Am 2026-09-03 bei der Mutationsprobe aufgefallen: ``fix_ohne_test`` fuehrte
    B-907 und B-878 als ungedeckt, obwohl
    ``tests/test_ui/test_b907_version_checker_shutdown.py`` und
    ``tests/test_services/test_b878_missing_media_candidates.py`` existieren.
    Beide nennen die ID **nur** im Dateinamen, nie im Inhalt - und das Werkzeug
    las ausschliesslich Inhalte. 345 Testdateien tragen die ID so.
    """
    muster = re.compile(r"^test_b(\d{3,4})_", re.I)
    treffer: dict[str, list[str]] = defaultdict(list)
    for p in dateien:
        m = muster.match(p.name)
        if m:
            try:
                pfad = p.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                # Datei ausserhalb des Repos (z.B. ein tmp_path im Test).
                pfad = p.as_posix()
            treffer[f"B-{int(m.group(1)):03d}"].append(pfad)
    return treffer


def _ids_in(dateien: list[Path]) -> dict[str, list[str]]:
    """Bug-ID -> Liste der Fundstellen als 'pfad:zeile'."""
    treffer: dict[str, list[str]] = defaultdict(list)
    for p in dateien:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for nr, zeile in enumerate(text.splitlines(), 1):
            for m in _BUG_ID.finditer(zeile):
                rel = p.relative_to(REPO_ROOT).as_posix()
                treffer[f"B-{m.group(1)}"].append(f"{rel}:{nr}")
    return treffer


def _symbol_an_zeile(pfad: Path, zeile: int) -> str | None:
    """Name der Funktion oder Methode, in der ``zeile`` steht.

    Loop 6 hat gezeigt, dass die reine ID-Suche zu grob ist: 89 Bug-IDs standen
    in keinem Test, aber ein Test kann die Reparatur sehr wohl absichern, ohne
    die Nummer zu nennen. Deshalb wird zusaetzlich geprueft, ob das Symbol, in
    dem der Fix sitzt, unter ``tests/`` ueberhaupt vorkommt.

    Fehlt beides - ID und Symbol -, ist die Reparatur nachweislich ungedeckt.
    Steht das Symbol in den Tests, ist es nur eine fehlende Beschriftung.
    """
    try:
        import ast

        baum = ast.parse(pfad.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None

    treffer: tuple[int, str] | None = None
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        ende = getattr(knoten, "end_lineno", None) or knoten.lineno
        if knoten.lineno <= zeile <= ende:
            # Das engste umschliessende Symbol gewinnt: eine Methode ist
            # aussagekraeftiger als ihre Klasse.
            spanne = ende - knoten.lineno
            if treffer is None or spanne < treffer[0]:
                treffer = (spanne, knoten.name)
    return treffer[1] if treffer else None


def _symbol_in_tests(name: str, testquelle: str) -> bool:
    """Kommt ``name`` unter ``tests/`` vor?

    Sehr kurze und sehr allgemeine Namen (``run``, ``main``, ``setUp``) sagen
    nichts aus - sie treffen in jeder Suite. Die werden nicht als Abdeckung
    gewertet, sonst verschwaende die Trennung genau die Faelle, die zaehlen.
    """
    if not name or len(name) < 5 or name in {"setUp", "tearDown"}:
        return False
    return re.search(r"\b" + re.escape(name) + r"\b", testquelle) is not None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seit", default=None, help="nur IDs ab dieser Nummer, z.B. B-900")
    p.add_argument("--json", default=None)
    p.add_argument("--top", type=int, default=25)
    args = p.parse_args()

    produktiv: list[Path] = []
    for ordner in PRODUKTIV:
        produktiv += _dateien(REPO_ROOT / ordner)
    fuer_main = REPO_ROOT / "main.py"
    if fuer_main.exists():
        produktiv.append(fuer_main)

    im_code = _ids_in(produktiv)
    testdateien = _dateien(REPO_ROOT / "tests")
    in_tests = _ids_in(testdateien)
    # Eine Testdatei, die die ID im Namen traegt, zaehlt genauso.
    im_dateinamen = _ids_in_dateinamen(testdateien)
    for bug, pfade in im_dateinamen.items():
        in_tests.setdefault(bug, []).extend(pfade)

    untergrenze = 0
    if args.seit:
        m = _BUG_ID.search(args.seit)
        if m:
            untergrenze = int(m.group(1))

    ohne = {
        bug: stellen for bug, stellen in im_code.items()
        if bug not in in_tests and int(bug.split("-")[1]) >= untergrenze
    }

    print(f"Produktivdateien geprueft : {len(produktiv)}")
    print(f"Testdateien geprueft      : {len(_dateien(REPO_ROOT / 'tests'))}")
    print(f"Bug-IDs im Produktivcode  : {len(im_code)}")
    print(f"Bug-IDs in Tests          : {len(in_tests)}")
    if args.seit:
        print(f"Betrachtet ab             : {args.seit}")
    print()
    # Zweite Stufe: sichert vielleicht doch ein Test die Stelle ab, ohne die
    # Nummer zu nennen? Geprueft wird ueber das umschliessende Symbol.
    testquelle = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in _dateien(REPO_ROOT / "tests")
    )
    hart: dict[str, list[str]] = {}
    nur_beschriftung: dict[str, list[str]] = {}
    for bug, stellen in ohne.items():
        gedeckte: list[str] = []
        for s in stellen:
            rel, _, nr = s.rpartition(":")
            symbol = _symbol_an_zeile(REPO_ROOT / rel, int(nr))
            if symbol and _symbol_in_tests(symbol, testquelle):
                gedeckte.append(f"{s} ({symbol})")
        if len(gedeckte) == len(stellen):
            nur_beschriftung[bug] = gedeckte
        else:
            hart[bug] = stellen

    print(f"=== Im Code markiert, in keinem Test genannt: {len(ohne)} ===")
    print(f"    davon nachweislich ungedeckt (auch das Symbol fehlt in tests/): {len(hart)}")
    print(f"    davon nur unbeschriftet (Symbol kommt in tests/ vor)         : "
          f"{len(nur_beschriftung)}")
    print()

    for bug in sorted(hart, key=lambda b: -int(b.split("-")[1]))[:args.top]:
        stellen = hart[bug]
        print(f"  {bug}  ({len(stellen)} Stelle{'n' if len(stellen) != 1 else ''})")
        for s in stellen[:3]:
            print(f"          {s}")
        if len(stellen) > 3:
            print(f"          ... ({len(stellen) - 3} weitere)")
    if len(hart) > args.top:
        print(f"\n  ... ({len(hart) - args.top} weitere IDs)")

    if nur_beschriftung:
        print()
        print(f"=== Nur unbeschriftet: {len(nur_beschriftung)} IDs ===")
        print("    Das Symbol, in dem der Fix sitzt, kommt unter tests/ vor. Ein Test")
        print("    kann die Sache also pruefen, ohne die Nummer zu nennen. Kein Befund,")
        print("    aber eine Stelle, an der eine Beschriftung fehlt.")
        print()
        for bug in sorted(nur_beschriftung, key=lambda b: -int(b.split("-")[1]))[:10]:
            print(f"  {bug}  {nur_beschriftung[bug][0]}")
        if len(nur_beschriftung) > 10:
            print(f"  ... ({len(nur_beschriftung) - 10} weitere)")

    if args.json:
        Path(args.json).write_text(
            json.dumps({b: s for b, s in sorted(ohne.items())}, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON: {args.json}")

    # Bug-IDs, die es im Vault gar nicht gibt. Der erste Lauf fand FIX B-1001,
    # obwohl die hoechste vergebene Nummer B-964 war.
    if VAULT_BUGS.exists():
        bekannt = set()
        for f in VAULT_BUGS.glob("B-*.md"):
            m = _BUG_ID.search(f.name)
            if m:
                bekannt.add(f"B-{m.group(1)}")
        erfunden = sorted(
            (b for b in im_code if b not in bekannt),
            key=lambda b: -int(b.split("-")[1]),
        )
        print()
        print(f"=== Im Code genannt, im Vault nicht vorhanden: {len(erfunden)} ===")
        print()
        for bug in erfunden[:args.top]:
            print(f"  {bug}")
            for s in im_code[bug][:3]:
                print(f"          {s}")
        if erfunden:
            print()
            print("  Ein Kommentar behauptet hier eine Reparatur fuer einen Bug, den es")
            print("  nicht gibt. Entweder ist die Nummer falsch oder der Verweis erfunden.")

    print()
    print("Naeherungswert, kein Beweis: ein Test kann eine Reparatur absichern, ohne")
    print("die Bug-ID zu nennen, und eine genannte ID heisst nicht, dass der Test die")
    print("richtige Sache prueft. Die Liste sagt, wo nachzusehen ist.")
    return 1 if ohne else 0


if __name__ == "__main__":
    raise SystemExit(main())

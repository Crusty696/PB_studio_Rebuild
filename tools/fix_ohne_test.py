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
    in_tests = _ids_in(_dateien(REPO_ROOT / "tests"))

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
    print(f"=== Im Code markiert, in keinem Test genannt: {len(ohne)} ===")
    print()

    for bug in sorted(ohne, key=lambda b: -int(b.split("-")[1]))[:args.top]:
        stellen = ohne[bug]
        print(f"  {bug}  ({len(stellen)} Stelle{'n' if len(stellen) != 1 else ''})")
        for s in stellen[:3]:
            print(f"          {s}")
        if len(stellen) > 3:
            print(f"          ... ({len(stellen) - 3} weitere)")
    if len(ohne) > args.top:
        print(f"\n  ... ({len(ohne) - args.top} weitere IDs)")

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

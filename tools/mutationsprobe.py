"""Prueft, ob ein Test die Reparatur wirklich absichert - durch Umkehren.

Am 2026-09-03 kam der Anstoss aus dem Consulting-Team: bevor Tests
nachgeliefert werden, muss gemessen werden, ob die vorhandenen ueberhaupt
etwas halten. Das Verfahren:

1. Nimm eine Stelle im Produktivcode, die eine Bug-ID traegt.
2. Kehre die Zeile darunter um - neutralisiere sie.
3. Lass die Tests laufen, die diese Datei betreffen.
4. Werden sie **rot**, sichert der Test die Stelle ab. Bleiben sie **gruen**,
   ist die Deckung Fiktion.
5. Stelle die Datei wieder her - immer, auch bei Abbruch.

Der erste Lauf von Hand fand sofort einen Fall: B-888 galt bei
``fix_ohne_test`` als gedeckt und war an allen fuenf markierten Stellen
ungedeckt. B-680 und B-800 danach ebenso.

    python tools/mutationsprobe.py --bug B-888
    python tools/mutationsprobe.py --alle-unbeschrifteten
    python tools/mutationsprobe.py --bug B-680 --json bericht.json

**Was dieses Werkzeug nicht kann:** eine Zeile sinnvoll umkehren, ohne zu
wissen, was sie tut. Es verwendet generische Mutationen (Bedingung auf
``True``/``False`` zwingen, Sortierschluessel kuerzen, Anweisung durch ``pass``
ersetzen) und meldet ehrlich ``uebersprungen``, wenn keine davon passt. Ein
uebersprungener Fall ist **kein** Freispruch - er ist ungemessen.

Exit 1, sobald mindestens eine Stelle gruen bleibt (also ungedeckt ist).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_BUG_ID = re.compile(r"\bB-(\d{3,4})\b")


# Wo der Originalinhalt liegt, solange eine Mutation aktiv ist.
#
# Am 2026-09-03 starb ein Lauf mitten in der Arbeit - der nohup-Wrapper meldete
# exit 0, der Prozess selbst verschwand ohne Bilanz (er hatte zuletzt 8 GB
# belegt). Das ``finally`` lief dadurch nie, und ZWEI Produktivdateien blieben
# mutiert im Arbeitsverzeichnis liegen:
#
#   services/ai_audio_service.py      gc.collect()  ->  pass
#   ui/controllers/video_analysis.py  Warteschlange -> direkter Worker-Start
#
# Aufgefallen ist es nur, weil ``git status`` danach zufaellig geprueft wurde.
# Ein Werkzeug, das Produktivcode anfasst, darf sich darauf nicht verlassen.
# Deshalb: der Originalinhalt wird VOR der Mutation auf Platte gesichert und
# beim naechsten Start zurueckgespielt, falls die Sicherung noch existiert.
_SICHERUNG = REPO_ROOT / "test-report" / ".mutationsprobe-offen.json"


def _sicherung_anlegen(pfad: Path, inhalt: str) -> None:
    _SICHERUNG.parent.mkdir(parents=True, exist_ok=True)
    _SICHERUNG.write_text(
        json.dumps({"pfad": str(pfad), "inhalt": inhalt}, ensure_ascii=False),
        encoding="utf-8",
    )


def _sicherung_loeschen() -> None:
    _SICHERUNG.unlink(missing_ok=True)


def _offene_mutation_zuruecknehmen() -> str | None:
    """Beim Start: haengt noch eine Mutation vom letzten Lauf in der Datei?

    Gibt den zurueckgesetzten Pfad zurueck, oder ``None``.
    """
    if not _SICHERUNG.exists():
        return None
    try:
        daten = json.loads(_SICHERUNG.read_text(encoding="utf-8"))
        pfad = Path(daten["pfad"])
        if pfad.exists() and _lies(pfad) != daten["inhalt"]:
            _schreib(pfad, daten["inhalt"])
            _sicherung_loeschen()
            return str(pfad)
        _sicherung_loeschen()
    except (OSError, ValueError, KeyError):
        return None
    return None


def _lies(pfad: Path) -> str:
    """Zeilenenden erhalten.

    Der erste Lauf von Hand schrieb CRLF als LF zurueck und machte sechs
    Dateien dirty, ohne eine einzige Zeile inhaltlich zu aendern.
    """
    with open(pfad, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _schreib(pfad: Path, inhalt: str) -> None:
    with open(pfad, "w", encoding="utf-8", newline="") as f:
        f.write(inhalt)


def _mutiere_anweisung(quelle: str, zeilennr: int) -> tuple[str, str] | None:
    """Ganze Anweisung per AST umkehren, statt eine Zeile per Regex zu schneiden.

    Die erste Fassung schnitt Sortierschluessel mit einem regulaeren Ausdruck.
    Bei ``services/brain/reranker.py:205``, ``scorer.py:67`` und
    ``pacing_edit_helpers.py:1662`` erzeugte das jedes Mal einen Syntaxfehler -
    vier von fuenf Stellen blieben ungemessen. Ueber den AST bleibt der
    Ausdruck gueltig.

    Umgekehrt wird der **Tie-Break**, nicht die Sortierung selbst: aus
    ``sort(key=lambda t: (-t[0], t[2], t[1]))`` wird ``sort(key=lambda t: (-t[0],))``.
    Die Sortierung ganz zu entfernen waere zu grob - ein Test, der nur die
    Score-Reihenfolge prueft, wuerde dann rot und die Stelle faelschlich als
    gedeckt gelten.

    Rueckgabe: (neuer Quelltext der ganzen Datei, Kurzbeschreibung).
    """
    try:
        baum = ast.parse(quelle)
    except SyntaxError:
        return None

    zeilen = quelle.splitlines(keepends=True)

    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Expr) or not isinstance(knoten.value, ast.Call):
            continue
        if knoten.lineno != zeilennr:
            continue
        aufruf = knoten.value
        if not (isinstance(aufruf.func, ast.Attribute) and aufruf.func.attr == "sort"):
            continue
        for kw in aufruf.keywords:
            if kw.arg != "key" or not isinstance(kw.value, ast.Lambda):
                continue
            rumpf = kw.value.body
            if not isinstance(rumpf, ast.Tuple) or len(rumpf.elts) < 2:
                # Auch der bedingte Fall aus pacing/pipeline.py: IfExp mit
                # Tupeln in beiden Zweigen.
                if isinstance(rumpf, ast.IfExp) and all(
                    isinstance(z, ast.Tuple) and len(z.elts) >= 2
                    for z in (rumpf.body, rumpf.orelse)
                ):
                    rumpf.body.elts = rumpf.body.elts[:-1]
                    rumpf.orelse.elts = rumpf.orelse.elts[:-1]
                else:
                    continue
            else:
                rumpf.elts = rumpf.elts[:1]

            einzug = " " * (knoten.col_offset)
            neu = einzug + ast.unparse(knoten)
            ende = getattr(knoten, "end_lineno", knoten.lineno)
            zeilenende = "\r\n" if zeilen[knoten.lineno - 1].endswith("\r\n") else "\n"
            ersetzt = (
                "".join(zeilen[: knoten.lineno - 1])
                + neu + zeilenende
                + "".join(zeilen[ende:])
            )
            return ersetzt, "Tie-Break im Sortierschluessel entfernt"

    # ------------------------------------------------------------------
    # Zweiter Durchgang: mehrzeilige Anweisungen generisch neutralisieren.
    #
    # Der erste vollstaendige Lauf am 2026-09-03 meldete fuer den Grossteil
    # der Stellen "keine generische Mutation passt". Die Zeilen waren fast
    # alle mehrzeilige Aufrufe (``analysis_status_service.mark_cancelled(``
    # ueber vier Zeilen) oder Funktionskoepfe. Beides ist per Zeilen-Regex
    # nicht fassbar, ueber den AST schon: Start- und Endzeile stehen im
    # Knoten.
    # ------------------------------------------------------------------
    def _zeilenende(nr: int) -> str:
        return "\r\n" if zeilen[nr - 1].endswith("\r\n") else "\n"

    def _ersetze(knoten, ersatz: str, beschreibung: str) -> tuple[str, str]:
        einzug = " " * knoten.col_offset
        ende = getattr(knoten, "end_lineno", knoten.lineno)
        return (
            "".join(zeilen[: knoten.lineno - 1])
            + einzug + ersatz + _zeilenende(knoten.lineno)
            + "".join(zeilen[ende:])
        ), beschreibung

    for knoten in ast.walk(baum):
        if getattr(knoten, "lineno", None) != zeilennr:
            continue

        # Ein Aufruf als eigene Anweisung: seine Wirkung faellt weg.
        if isinstance(knoten, ast.Expr) and isinstance(knoten.value, ast.Call):
            return _ersetze(knoten, "pass", "Aufruf entfernt (mehrzeilig)")

        # Bedingung erzwingen - auch bei mehrzeiligem Test. Der Koerper bleibt
        # stehen, nur der Test wird unerreichbar.
        if isinstance(knoten, ast.If):
            einzug = " " * knoten.col_offset
            koerper_start = knoten.body[0].lineno
            return (
                "".join(zeilen[: knoten.lineno - 1])
                + einzug + "if False:" + _zeilenende(knoten.lineno)
                + "".join(zeilen[koerper_start - 1:])
            ), "Bedingung auf False (mehrzeilig)"

        # Zuweisung mit sorted(...) -> Eingangsreihenfolge.
        if isinstance(knoten, ast.Assign) and isinstance(knoten.value, ast.Call):
            f = knoten.value.func
            if isinstance(f, ast.Name) and f.id == "sorted" and knoten.value.args:
                kopie = ast.parse(ast.unparse(knoten)).body[0]
                kopie.value = ast.parse(
                    "list(" + ast.unparse(knoten.value.args[0]) + ")").body[0].value
                return _ersetze(knoten, ast.unparse(kopie), "sorted entfernt")

    return None


def _mutiere(zeile: str) -> tuple[str, str] | None:
    """Eine generische Umkehrung fuer ``zeile``, oder ``None``.

    Rueckgabe: (neue Zeile, Kurzbeschreibung der Mutation).
    """
    kern = zeile.strip()
    einzug = zeile[: len(zeile) - len(zeile.lstrip())]

    if not kern or kern.startswith("#"):
        return None

    # Sortierung mit Tie-Break -> nur der erste Schluessel.
    m = re.match(r"(.*\.sort\(key=lambda \w+: )\((-?[^,]+),.*\)(.*)$", kern)
    if m:
        return f"{einzug}{m.group(1)}{m.group(2)}{m.group(3)}", "Tie-Break entfernt"

    # sorted(...) -> Liste in Eingangsreihenfolge.
    if "sorted(" in kern and "=" in kern:
        links, rechts = kern.split("=", 1)
        inner = rechts.strip()
        if inner.startswith("sorted(") and inner.endswith(")"):
            return f"{einzug}{links}= [{inner[7:-1]}]", "sorted entfernt"

    # Bedingung erzwingen: `if <cond>:` -> `if False:`
    if kern.startswith("if ") and kern.endswith(":"):
        return f"{einzug}if False:", "Bedingung auf False"

    # Guard-Rueckgabe: `return X` in einem Guard -> weglassen ist zu riskant;
    # stattdessen einzelne Anweisung neutralisieren.
    if re.match(r"^[\w.\[\]()]+\((.*)\)$", kern) and not kern.startswith("return"):
        return f"{einzug}pass", "Aufruf entfernt"

    # Schluesselwortargument entfernen: kind="stable" u.ae.
    m = re.match(r'^(.*?), *\w+=(?:"[^"]*"|\'[^\']*\'|True|False)(\).*)$', kern)
    if m:
        return f"{einzug}{m.group(1)}{m.group(2)}", "Schluesselwortargument entfernt"

    return None


def _testziele(datei: Path, bug: str | None = None) -> list[str]:
    """Testdateien, die zu ``datei`` gehoeren koennten.

    Zwei Wege: Testdateien, die den Modulnamen nennen, und Testdateien, die ein
    im Modul definiertes oeffentliches Symbol nennen. Beides ist eine Naeherung.
    """
    modul = datei.stem
    treffer: set[str] = set()

    symbole: set[str] = set()
    try:
        baum = ast.parse(_lies(datei))
        for knoten in ast.walk(baum):
            if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not knoten.name.startswith("_") and len(knoten.name) >= 6:
                    symbole.add(knoten.name)
    except (OSError, SyntaxError):
        pass

    for p in sorted((REPO_ROOT / "tests").rglob("test_*.py")):
        if "qa_artifacts" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            quelle = _lies(p)
        except OSError:
            continue
        if modul in quelle or any(s in quelle for s in symbole):
            treffer.add(p.relative_to(REPO_ROOT).as_posix())
        elif bug and (bug in quelle or bug.lower().replace("-", "") in p.name.lower()):
            treffer.add(p.relative_to(REPO_ROOT).as_posix())

    # Tests, die die Bug-ID selbst nennen, zuerst. Ohne diese Reihenfolge
    # schnitt das Ziel-Limit sie ab: scorer.py:67 galt im ersten Lauf als
    # UNGEDECKT, obwohl test_b888_alle_fuenf_tiebreak_stellen.py einen Guard
    # dafuer hat - die Datei stand nur nicht unter den ersten sechs.
    def _rang(pfad: str) -> tuple[int, str]:
        if not bug:
            return (1, pfad)
        knapp = bug.lower().replace("-", "")
        try:
            inhalt = _lies(REPO_ROOT / pfad)
        except OSError:
            inhalt = ""
        if knapp in Path(pfad).name.lower() or bug in inhalt:
            return (0, pfad)
        return (1, pfad)

    return sorted(treffer, key=_rang)


def _stellen_fuer(bug: str) -> list[tuple[Path, int]]:
    """Fundstellen der ID im Produktivcode: die Zeile **nach** dem Marker."""
    ordner = ("services", "ui", "workers", "agents", "database")
    dateien: list[Path] = []
    for o in ordner:
        wurzel = REPO_ROOT / o
        if wurzel.is_dir():
            dateien += [
                p for p in wurzel.rglob("*.py")
                if "__pycache__" not in p.parts and "qa_artifacts" not in p.parts
            ]
    if (REPO_ROOT / "main.py").exists():
        dateien.append(REPO_ROOT / "main.py")

    stellen: list[tuple[Path, int]] = []
    for p in dateien:
        try:
            zeilen = _lies(p).splitlines()
        except OSError:
            continue
        for nr, z in enumerate(zeilen, 1):
            if bug not in z:
                continue
            # Eine ID **in einem Zeichenketten-Literal** ist keine Markierung,
            # sondern Text: `logger.debug("B-797: Banner-Nachzug ... %s", exc)`.
            # Am 2026-09-03 wurde genau diese Zeile mutiert statt der Reparatur
            # ein paar Zeilen darueber - das Ergebnis las sich als "UNGEDECKT",
            # gemessen wurde aber die Logmeldung im except-Zweig.
            ohne_kommentar = z.split("#", 1)[0]
            nur_in_zeichenkette = False
            if bug in ohne_kommentar:
                rest = ohne_kommentar
                for anfuehrung in ('"', "'"):
                    teile = rest.split(anfuehrung)
                    # Ungerade Indizes liegen innerhalb der Anfuehrungszeichen.
                    if len(teile) > 2 and any(
                        bug in teil for i, teil in enumerate(teile) if i % 2 == 1
                    ) and not any(
                        bug in teil for i, teil in enumerate(teile) if i % 2 == 0
                    ):
                        nur_in_zeichenkette = True
                        break
            kommentarteil = z.split("#", 1)[1] if "#" in z else ""
            if nur_in_zeichenkette and bug not in kommentarteil:
                continue

            # Steht der Marker als Randkommentar hinter Code, ist DIESE Zeile
            # die Reparatur - nicht die naechste. In
            # ``services/video_analysis_service.py`` sieht das so aus:
            #     analysis_status_service.mark_cancelled(  # B-147/B-756
            # Ohne diese Unterscheidung zeigte die Fundstelle auf die
            # Argumentzeile darunter, die kein Anweisungsanfang ist - sechs
            # B-756-Stellen blieben deshalb ungemessen.
            vor_dem_kommentar = z.split("#", 1)[0].strip()
            if vor_dem_kommentar:
                stellen.append((p, nr))
                continue

            # Sonst: der Marker steht in einer eigenen Kommentarzeile, die
            # Reparatur folgt darunter. Die Spanne war zuerst 11 Zeilen - zu
            # knapp: der B-797-Block in ui/controllers/media_table.py:285
            # erklaert den Fall ueber 14 Kommentarzeilen, und die Stelle fiel
            # deshalb ganz aus der Messung.
            for versatz in range(1, 30):
                if nr - 1 + versatz >= len(zeilen):
                    break
                kandidat = zeilen[nr - 1 + versatz]
                kern = kandidat.strip()
                if not kern or kern.startswith("#"):
                    continue
                # Strukturschluesselwoerter sind keine Reparatur - hinter
                # ``try:`` steht sie erst eine Zeile weiter. Ohne diesen
                # Schritt zeigte die B-797-Fundstelle auf ``try:``, und dafuer
                # gibt es keine sinnvolle Mutation.
                if kern in ("try:", "else:", "finally:") or kern.startswith(
                    ("with ", "for ", "while ", "elif ", "except")
                ):
                    continue
                stellen.append((p, nr + versatz))
                break
    return stellen


def _pytest(ziele: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *ziele, "-p", "no:randomly", "-q", "-x"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    zeilen = [z for z in r.stdout.splitlines()
              if "passed" in z or "failed" in z or "error" in z]
    return r.returncode, (zeilen[-1] if zeilen else f"exit={r.returncode}")


def probe(bug: str, max_ziele: int = 6) -> list[dict]:
    """Eine Bug-ID durchmessen. Gibt einen Eintrag pro Fundstelle zurueck."""
    ergebnisse: list[dict] = []
    for pfad, zeilennr in _stellen_fuer(bug):
        rel = pfad.relative_to(REPO_ROOT).as_posix()
        original = _lies(pfad)
        zeilen = original.splitlines(keepends=True)
        if zeilennr > len(zeilen):
            continue
        roh = zeilen[zeilennr - 1].rstrip("\r\n")
        ende = zeilen[zeilennr - 1][len(roh):]

        # Erst der AST-Weg (ganze Anweisung), dann der zeilenweise Notbehelf.
        ast_mutation = _mutiere_anweisung(original, zeilennr)
        mutation = None
        if ast_mutation is not None:
            ganzer_text, beschreibung = ast_mutation
            mutation = (None, beschreibung)
        else:
            ganzer_text = None
            mutation = _mutiere(roh)
        if mutation is None:
            ergebnisse.append({
                "bug": bug, "stelle": f"{rel}:{zeilennr}",
                "ergebnis": "uebersprungen",
                "grund": "keine generische Mutation passt",
                "zeile": roh.strip()[:80],
            })
            continue

        _unbenutzt, beschreibung = mutation
        ziele = _testziele(pfad, bug)[:max_ziele]
        if not ziele:
            ergebnisse.append({
                "bug": bug, "stelle": f"{rel}:{zeilennr}",
                "ergebnis": "uebersprungen",
                "grund": "keine zugehoerige Testdatei gefunden",
                "zeile": roh.strip()[:80],
            })
            continue

        try:
            # Erst sichern, dann mutieren. Stirbt der Prozess dazwischen,
            # findet der naechste Start die Sicherung und spielt sie zurueck.
            _sicherung_anlegen(pfad, original)
            if ganzer_text is not None:
                _schreib(pfad, ganzer_text)
            else:
                zeilen[zeilennr - 1] = mutation[0] + ende
                _schreib(pfad, "".join(zeilen))
            # Syntaxfehler durch die Mutation zaehlen nicht als Befund.
            try:
                ast.parse(_lies(pfad))
            except SyntaxError:
                ergebnisse.append({
                    "bug": bug, "stelle": f"{rel}:{zeilennr}",
                    "ergebnis": "uebersprungen",
                    "grund": "Mutation erzeugt Syntaxfehler",
                    "zeile": roh.strip()[:80],
                })
                continue
            code, zusammenfassung = _pytest(ziele)
        finally:
            _schreib(pfad, original)
            _sicherung_loeschen()

        ergebnisse.append({
            "bug": bug, "stelle": f"{rel}:{zeilennr}",
            "ergebnis": "gedeckt" if code != 0 else "UNGEDECKT",
            "mutation": beschreibung,
            "tests": ziele,
            "pytest": zusammenfassung,
            "zeile": roh.strip()[:80],
        })
    return ergebnisse


def _unbeschriftete_ids() -> list[str]:
    """Die IDs, die ``fix_ohne_test`` als 'nur unbeschriftet' fuehrt."""
    r = subprocess.run(
        [sys.executable, "tools/fix_ohne_test.py", "--top", "500"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    ab = r.stdout.find("=== Nur unbeschriftet")
    if ab == -1:
        return []
    ids: list[str] = []
    for zeile in r.stdout[ab:].splitlines():
        m = re.match(r"\s+(B-\d{3,4})\s", zeile)
        if m:
            ids.append(m.group(1))
    return ids


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    zurueckgesetzt = _offene_mutation_zuruecknehmen()
    if zurueckgesetzt:
        print(f"ACHTUNG: offene Mutation aus einem abgebrochenen Lauf "
              f"zurueckgenommen: {zurueckgesetzt}")
        print()

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bug", action="append", default=None,
                   help="Bug-ID, mehrfach angebbar")
    p.add_argument("--alle-unbeschrifteten", action="store_true",
                   help="alle IDs, die fix_ohne_test als 'nur unbeschriftet' fuehrt")
    p.add_argument("--json", default=None)
    args = p.parse_args()

    if args.alle_unbeschrifteten:
        bugs = _unbeschriftete_ids()
        print(f"Von fix_ohne_test uebernommen: {len(bugs)} IDs\n")
    elif args.bug:
        bugs = args.bug
    else:
        p.error("--bug oder --alle-unbeschrifteten angeben")
        return 2

    alle: list[dict] = []
    for bug in bugs:
        eintraege = probe(bug)
        alle += eintraege
        for e in eintraege:
            kennzeichen = {"UNGEDECKT": "UNGEDECKT", "gedeckt": "  gedeckt"}.get(
                e["ergebnis"], "  uebersprungen")
            zusatz = e.get("pytest") or e.get("grund", "")
            print(f"{kennzeichen}  {e['bug']}  {e['stelle']}  [{zusatz}]")
        if not eintraege:
            print(f"  ohne Fundstelle  {bug}")

    ungedeckt = [e for e in alle if e["ergebnis"] == "UNGEDECKT"]
    gedeckt = [e for e in alle if e["ergebnis"] == "gedeckt"]
    offen = [e for e in alle if e["ergebnis"] == "uebersprungen"]

    print()
    print(f"Stellen gemessen : {len(gedeckt) + len(ungedeckt)}")
    print(f"  gedeckt        : {len(gedeckt)}")
    print(f"  UNGEDECKT      : {len(ungedeckt)}")
    print(f"Stellen ungemessen: {len(offen)}")
    print()
    print("Ungemessen heisst NICHT gedeckt. Fuer diese Stellen passte keine")
    print("generische Mutation oder es gab keine zugehoerige Testdatei - sie")
    print("brauchen eine Pruefung von Hand.")

    if args.json:
        Path(args.json).write_text(json.dumps(alle, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"\nJSON: {args.json}")

    return 1 if ungedeckt else 0


if __name__ == "__main__":
    raise SystemExit(main())

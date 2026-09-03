"""Tests für ``tools/mutationsprobe.py``.

Das Werkzeug misst, ob ein Test eine Reparatur wirklich absichert: es kehrt den
Fix im Produktivcode um und prüft, ob die Tests rot werden. Bleiben sie grün,
ist die Deckung Fiktion.

Zwei eigene Messfehler stecken als Testfall darin:

* Die erste Fassung schnitt Sortierschlüssel per regulärem Ausdruck und
  erzeugte an vier von fünf B-888-Stellen einen Syntaxfehler — die Stellen
  blieben ungemessen.
* Die zweite Fassung wählte bis zu sechs Testdateien, ohne die ID-spezifischen
  zu bevorzugen. `scorer.py:67` galt dadurch als UNGEDECKT, obwohl ein Guard
  dafür existiert; die Datei stand nur nicht unter den ersten sechs.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def probe():
    pfad = REPO_ROOT / "tools" / "mutationsprobe.py"
    spec = importlib.util.spec_from_file_location("_mutationsprobe", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# ---------------------------------------------------------------------------
# AST-Mutation
# ---------------------------------------------------------------------------

def test_der_tie_break_wird_gekuerzt_nicht_die_sortierung(probe):
    """Aus ``(-t[0], t[2], t[1])`` wird ``(-t[0],)`` — die Sortierung bleibt.

    Die Sortierung ganz zu entfernen wäre zu grob: ein Test, der nur die
    Score-Reihenfolge prüft, würde dann rot und die Stelle fälschlich als
    gedeckt gelten.
    """
    quelle = textwrap.dedent("""\
        def f(scored):
            scored.sort(key=lambda t: (-t[0], t[2], t[1]))
            return scored
        """)

    ergebnis = probe._mutiere_anweisung(quelle, 2)

    assert ergebnis is not None
    neu, beschreibung = ergebnis
    assert "sort(" in neu, "die Sortierung selbst wurde entfernt"
    assert "t[2]" not in neu and "t[1]" not in neu
    assert "Tie-Break" in beschreibung


def test_die_mutation_bleibt_syntaktisch_gueltig(probe):
    """Der Kern des ersten Messfehlers.

    Der reguläre Ausdruck der ersten Fassung erzeugte hier einen Syntaxfehler.
    """
    import ast

    quelle = textwrap.dedent("""\
        def f(results):
            results.sort(key=lambda r: (-r.final_score, r.clip_id))
        """)

    neu, _ = probe._mutiere_anweisung(quelle, 2)

    ast.parse(neu)  # darf nicht werfen


def test_ein_einelementiger_schluessel_faellt_auf_die_grobe_mutation(probe):
    """Ohne Tie-Break gibt es nichts zu kürzen — dann greift der zweite Durchgang.

    Früher gab die Funktion hier ``None`` zurück und die Stelle blieb
    ungemessen. Seit der Erweiterung um mehrzeilige Anweisungen wird der
    Sortieraufruf als Ganzes entfernt.

    Das ist die grobe Variante: sie misst, ob überhaupt jemand die Reihenfolge
    prüft — nicht, ob der Tie-Break geprüft wird. Für die Deckungsfrage reicht
    das, aber der Unterschied gehört festgehalten: eine so gemessene „Deckung"
    ist schwächer als eine, die den gekürzten Schlüssel überlebt.
    """
    quelle = textwrap.dedent("""\
        def f(xs):
            xs.sort(key=lambda x: -x.score)
        """)

    ergebnis = probe._mutiere_anweisung(quelle, 2)

    assert ergebnis is not None
    neu, beschreibung = ergebnis
    assert "pass" in neu
    assert "mehrzeilig" in beschreibung


def test_der_bedingte_sortierschluessel_wird_erkannt(probe):
    """``services/pacing/pipeline.py`` sortiert mit einem ``IfExp`` als Key."""
    quelle = textwrap.dedent("""\
        def f(scored, tabelle):
            scored.sort(
                key=lambda t: (0, -tabelle[t[0]], int(t[0]))
                if t[0] in tabelle
                else (1, 0.0, int(t[0])),
            )
        """)

    ergebnis = probe._mutiere_anweisung(quelle, 2)

    assert ergebnis is not None
    neu, _ = ergebnis
    import ast
    ast.parse(neu)
    assert "int(t[0])" not in neu


def test_zeilenenden_bleiben_erhalten(probe, tmp_path):
    """Der dritte eigene Fehler: CRLF wurde als LF zurückgeschrieben.

    Sechs Dateien wurden dadurch dirty, ohne eine inhaltliche Änderung.
    """
    p = tmp_path / "datei.py"
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("a = 1\r\nb = 2\r\n")

    inhalt = probe._lies(p)
    probe._schreib(p, inhalt)

    with open(p, "rb") as f:
        assert f.read() == b"a = 1\r\nb = 2\r\n"


# ---------------------------------------------------------------------------
# Zeilenweise Notbehelfs-Mutationen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zeile,erwartet", [
    ("        if x is not None:", "if False:"),
    ("    self.window.keyframe_text.clear()", "pass"),
])
def test_notbehelf_mutationen(probe, zeile, erwartet):
    ergebnis = probe._mutiere(zeile)

    assert ergebnis is not None
    assert erwartet in ergebnis[0]


@pytest.mark.parametrize("zeile", ["", "   ", "# nur ein Kommentar", "return 5"])
def test_leere_und_kommentarzeilen_werden_nicht_mutiert(probe, zeile):
    assert probe._mutiere(zeile) is None


# ---------------------------------------------------------------------------
# Testauswahl
# ---------------------------------------------------------------------------

def test_id_spezifische_tests_stehen_vorn(probe):
    """Der zweite eigene Messfehler.

    Ohne diese Reihenfolge schnitt das Ziel-Limit von sechs Dateien die
    ID-spezifische Testdatei ab, und die Stelle galt fälschlich als ungedeckt.
    """
    ziele = probe._testziele(REPO_ROOT / "services" / "brain" / "scorer.py", "B-888")

    assert ziele, "keine Testziele gefunden"
    assert "b888" in ziele[0].lower() or "B-888" in probe._lies(REPO_ROOT / ziele[0])


def test_ohne_bug_id_bleibt_die_auswahl_alphabetisch(probe):
    ziele = probe._testziele(REPO_ROOT / "services" / "brain" / "scorer.py")

    assert ziele == sorted(ziele)


# ---------------------------------------------------------------------------
# Fundstellen
# ---------------------------------------------------------------------------

def test_die_fundstelle_zeigt_auf_die_zeile_nach_dem_marker(probe):
    """Der Marker steht im Kommentar; mutiert wird die Reparatur darunter."""
    stellen = probe._stellen_fuer("B-888")

    assert stellen, "keine B-888-Fundstelle gefunden"
    for pfad, nr in stellen:
        zeile = probe._lies(pfad).splitlines()[nr - 1]
        assert zeile.strip(), "die Fundstelle zeigt auf eine Leerzeile"
        assert not zeile.strip().startswith("#"), (
            f"die Fundstelle zeigt auf einen Kommentar: {pfad}:{nr}"
        )


def test_eine_unbekannte_id_liefert_keine_stellen(probe):
    assert probe._stellen_fuer("B-9999") == []


def test_ein_randkommentar_markiert_die_eigene_zeile(probe, tmp_path):
    """``mark_cancelled(  # B-147/B-756`` — die Reparatur steht *in* der Zeile.

    Ohne diese Unterscheidung zeigte die Fundstelle auf die Argumentzeile
    darunter, die kein Anweisungsanfang ist. Sechs B-756-Stellen blieben
    deshalb im ersten vollständigen Lauf ungemessen.
    """
    stellen = probe._stellen_fuer("B-756")

    assert stellen, "keine B-756-Fundstelle gefunden"
    for pfad, nr in stellen:
        zeile = probe._lies(pfad).splitlines()[nr - 1]
        vor_dem_kommentar = zeile.split("#", 1)[0].strip()
        assert vor_dem_kommentar, (
            f"die Fundstelle zeigt auf reinen Kommentar: {pfad}:{nr}"
        )


# ---------------------------------------------------------------------------
# Wiederherstellung nach hartem Abbruch
# ---------------------------------------------------------------------------

def test_eine_offene_mutation_wird_beim_naechsten_start_zurueckgenommen(
    probe, tmp_path, monkeypatch
):
    """Der gefährlichste eigene Fund.

    Am 2026-09-03 starb ein Lauf mitten in der Arbeit — der nohup-Wrapper
    meldete exit 0, der Prozess selbst verschwand ohne Bilanz. Das ``finally``
    lief nie, und zwei Produktivdateien blieben mutiert im Arbeitsverzeichnis
    liegen. Aufgefallen ist es nur, weil ``git status`` zufällig geprüft wurde.
    """
    ziel = tmp_path / "produktiv.py"
    original = "x = 1\n"
    probe._schreib(ziel, original)

    monkeypatch.setattr(probe, "_SICHERUNG", tmp_path / "offen.json")
    probe._sicherung_anlegen(ziel, original)
    probe._schreib(ziel, "x = 2  # mutiert\n")

    zurueck = probe._offene_mutation_zuruecknehmen()

    assert zurueck == str(ziel)
    assert probe._lies(ziel) == original
    assert not (tmp_path / "offen.json").exists()


def test_ohne_offene_mutation_passiert_nichts(probe, tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "_SICHERUNG", tmp_path / "offen.json")

    assert probe._offene_mutation_zuruecknehmen() is None


def test_eine_bereits_saubere_datei_wird_nicht_ueberschrieben(
    probe, tmp_path, monkeypatch
):
    """Wurde von Hand zurückgesetzt, darf die Sicherung nichts zerstören."""
    ziel = tmp_path / "produktiv.py"
    original = "x = 1\n"
    probe._schreib(ziel, original)

    monkeypatch.setattr(probe, "_SICHERUNG", tmp_path / "offen.json")
    probe._sicherung_anlegen(ziel, original)

    assert probe._offene_mutation_zuruecknehmen() is None
    assert probe._lies(ziel) == original
    assert not (tmp_path / "offen.json").exists()


def test_die_sicherung_wird_vor_der_mutation_geschrieben(probe):
    """Quellcode-Guard: die Reihenfolge ist der ganze Schutz."""
    quelle = probe._lies(REPO_ROOT / "tools" / "mutationsprobe.py")

    ab = quelle.index("_sicherung_anlegen(pfad, original)")
    danach = quelle[ab:ab + 400]

    assert "_schreib(pfad" in danach, "nach dem Sichern wird nicht mutiert"
    assert quelle.index("_sicherung_anlegen(pfad, original)") < quelle.index(
        "if ganzer_text is not None:"), "gesichert wird erst nach der Mutation"


# ---------------------------------------------------------------------------
# Docstring-Ausschluss (Consulting-Team-Befund vom 2026-09-03)
# ---------------------------------------------------------------------------

def test_eine_id_im_docstring_ist_keine_fundstelle(probe, tmp_path):
    """Dritter Fall derselben Klasse: Kommentar, Log-String, jetzt Docstring.

    Eine AST-Stichprobe an sechs der 29 „ungemessenen" Stellen fand vier
    Docstring-Treffer. Dort gibt es keine Reparatur zu mutieren.
    """
    quelle = (
        'def f():\n'
        '    """B-123: erklaerender Text im Docstring."""\n'
        '    x = 1\n'
        '    return x\n'
    )

    docstrings = probe._docstring_zeilen(quelle)

    assert 2 in docstrings
    assert 3 not in docstrings


def test_ein_mehrzeiliger_docstring_wird_ganz_erfasst(probe):
    quelle = (
        'def f():\n'
        '    """Zeile eins.\n'
        '\n'
        '    B-123: steht hier drin.\n'
        '    """\n'
        '    return 1\n'
    )

    docstrings = probe._docstring_zeilen(quelle)

    assert {2, 3, 4, 5} <= docstrings
    assert 6 not in docstrings


def test_eine_kaputte_datei_liefert_keine_docstringzeilen(probe):
    assert probe._docstring_zeilen("def (:\n") == set()


# ---------------------------------------------------------------------------
# Zuweisungs-Mutation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zuweisung,erwartet", [
    ("x = len(videos)", "0"),
    ("x = sum(w for w in ws)", "0"),
    ("x = self.verticalScrollBar().value()", "0"),
    # `sorted(...)` hat eine eigene, praezisere Regel: Eingangsreihenfolge
    # statt leerer Liste. Die greift vor der generischen Neutralisierung.
    ("x = sorted(ys)", "list(ys)"),
    ("x = []", "[]"),
    ("x = {}", "{}"),
    ("x = [a for a in b]", "[]"),
    ("x = a > b", "False"),
    ("x = a + b", "0"),
    ("x = self.attribut", "None"),
    ("x = True", "False"),
    ("x = 5", "0"),
    ('x = "text"', '""'),
])
def test_die_rechte_seite_wird_passend_neutralisiert(probe, zuweisung, erwartet):
    """Ein pauschales ``None`` erzeugt oft nur einen TypeError weiter unten.

    Das liest sich dann als „gedeckt", obwohl kein Test die eigentliche Logik
    geprüft hat. Deshalb richtet sich der Ersatzwert nach der Form.
    """
    quelle = f"def f(a, b, ws, ys, videos):\n    {zuweisung}\n    return x\n"

    ergebnis = probe._mutiere_anweisung(quelle, 2)

    assert ergebnis is not None, f"keine Mutation fuer {zuweisung}"
    neu, beschreibung = ergebnis
    import ast as _ast
    _ast.parse(neu)
    assert f"= {erwartet}" in neu, f"{zuweisung} -> {neu.splitlines()[1]}"
    assert "Zuweisung neutralisiert" in beschreibung or "sorted" in beschreibung


def test_eine_none_zuweisung_wird_nicht_angefasst(probe):
    """`x = None` zu neutralisieren ändert nichts — das wäre eine Scheinmessung."""
    quelle = "def f():\n    x = None\n    return x\n"

    assert probe._mutiere_anweisung(quelle, 2) is None


def test_der_zuweisungstyp_steht_in_der_beschreibung(probe):
    """Der Bericht muss zeigen, wie grob gemessen wurde."""
    quelle = "def f(videos):\n    total = len(videos)\n    return total\n"

    _neu, beschreibung = probe._mutiere_anweisung(quelle, 2)

    assert "(0)" in beschreibung


# ---------------------------------------------------------------------------
# Trockenlauf
# ---------------------------------------------------------------------------

def test_der_trockenlauf_schreibt_nichts(probe, monkeypatch):
    """`--nur-anzeigen` darf keine Datei anfassen und keine Tests starten."""
    geschrieben: list[str] = []
    gestartet: list[str] = []

    monkeypatch.setattr(probe, "_schreib",
                        lambda p, s: geschrieben.append(str(p)))
    monkeypatch.setattr(probe, "_pytest",
                        lambda ziele: gestartet.append(str(ziele)) or (0, ""))

    eintraege = probe.probe("B-011", nur_anzeigen=True)

    assert eintraege, "keine Fundstelle fuer B-011"
    assert geschrieben == [], f"trotz Trockenlauf geschrieben: {geschrieben}"
    assert gestartet == [], f"trotz Trockenlauf Tests gestartet: {gestartet}"
    assert all(e["ergebnis"] in ("nur angezeigt", "uebersprungen")
               for e in eintraege)

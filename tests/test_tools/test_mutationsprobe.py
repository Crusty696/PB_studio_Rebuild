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


def test_ein_einelementiger_schluessel_wird_nicht_angefasst(probe):
    """Ohne Tie-Break gibt es nichts zu entfernen."""
    quelle = textwrap.dedent("""\
        def f(xs):
            xs.sort(key=lambda x: -x.score)
        """)

    assert probe._mutiere_anweisung(quelle, 2) is None


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

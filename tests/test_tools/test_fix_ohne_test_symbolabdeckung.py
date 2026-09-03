"""``fix_ohne_test`` prüft jetzt zusätzlich das umschließende Symbol.

Die reine ID-Suche war zu grob: am 2026-09-02 standen 89 Bug-IDs in keinem
Test. Ein Test kann eine Reparatur aber sehr wohl absichern, ohne die Nummer zu
nennen — er prüft dann die Funktion, nicht die Beschriftung.

Deshalb die zweite Stufe: pro Fundstelle wird per AST das engste umschließende
Symbol bestimmt und geprüft, ob dessen Name unter ``tests/`` vorkommt.

* Fehlt beides — ID **und** Symbol — ist die Reparatur nachweislich ungedeckt.
* Steht das Symbol in den Tests, fehlt nur die Beschriftung.

Gemessen nach der Änderung: von 89 IDs bleiben 47 als harte Befunde, 42 sind
nur unbeschriftet.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def werkzeug():
    pfad = REPO_ROOT / "tools" / "fix_ohne_test.py"
    spec = importlib.util.spec_from_file_location("_fix_ohne_test", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture()
def quelle(tmp_path: Path) -> Path:
    p = tmp_path / "beispiel.py"
    p.write_text(textwrap.dedent("""\
        class Regler:
            def setze_lautstaerke(self, wert):
                # B-999: hier war der Fehler
                return wert

            def kurz(self):
                # B-998: auch hier
                return 1


        def freie_funktion():
            # B-997
            return 0
        """), encoding="utf-8")
    return p


def test_findet_die_methode_um_die_zeile(werkzeug, quelle):
    assert werkzeug._symbol_an_zeile(quelle, 3) == "setze_lautstaerke"


def test_die_methode_gewinnt_gegen_ihre_klasse(werkzeug, quelle):
    """Das engste umschließende Symbol ist aussagekräftiger."""
    assert werkzeug._symbol_an_zeile(quelle, 3) != "Regler"


def test_findet_auch_eine_freie_funktion(werkzeug, quelle):
    assert werkzeug._symbol_an_zeile(quelle, 12) == "freie_funktion"


def test_ausserhalb_jedes_symbols_kommt_nichts(werkzeug, quelle):
    assert werkzeug._symbol_an_zeile(quelle, 1) == "Regler"


def test_eine_kaputte_datei_wirft_nicht(werkzeug, tmp_path):
    p = tmp_path / "kaputt.py"
    p.write_text("def (:\n", encoding="utf-8")

    assert werkzeug._symbol_an_zeile(p, 1) is None


def test_ein_symbol_in_den_tests_zaehlt_als_abdeckung(werkzeug):
    testquelle = "def test_x():\n    r.setze_lautstaerke(3)\n"

    assert werkzeug._symbol_in_tests("setze_lautstaerke", testquelle) is True


def test_ein_fehlendes_symbol_zaehlt_nicht(werkzeug):
    assert werkzeug._symbol_in_tests("setze_lautstaerke", "nichts") is False


@pytest.mark.parametrize("name", ["run", "main", "kurz", "setUp", "tearDown", ""])
def test_zu_allgemeine_namen_gelten_nie_als_abdeckung(werkzeug, name):
    """Sonst frisst die Trennung genau die Fälle, die zählen.

    ``run`` und ``main`` treffen in jeder Suite — als Abdeckungsbeleg wertlos.
    """
    testquelle = f"def test_x():\n    obj.{name or 'x'}()\n"

    assert werkzeug._symbol_in_tests(name, testquelle) is False


def test_teiltreffer_zaehlen_nicht(werkzeug):
    """``\\b``-Grenze: ``setze_lautstaerke_neu`` deckt nicht ``setze_lautstaerke``."""
    assert werkzeug._symbol_in_tests(
        "setze_lautstaerke", "obj.setze_lautstaerke_neu()") is False


def test_die_id_im_dateinamen_zaehlt_als_abdeckung(werkzeug, tmp_path):
    """Am 2026-09-03 bei der Mutationsprobe gefunden.

    ``fix_ohne_test`` fuehrte B-907 und B-878 als ungedeckt, obwohl
    ``tests/test_ui/test_b907_version_checker_shutdown.py`` und
    ``tests/test_services/test_b878_missing_media_candidates.py`` existieren.
    Beide nennen die ID **nur** im Dateinamen. 345 Testdateien tun das.
    """
    for name in ("test_b907_version_checker_shutdown.py",
                 "test_b878_missing_media_candidates.py",
                 "test_b12_kurze_nummer.py"):
        (tmp_path / name).write_text("def test_x(): pass\n", encoding="utf-8")

    treffer = werkzeug._ids_in_dateinamen(sorted(tmp_path.glob("*.py")))

    assert "B-907" in treffer
    assert "B-878" in treffer


def test_dateien_ohne_id_im_namen_zaehlen_nicht(werkzeug, tmp_path):
    for name in ("test_export_service.py", "conftest.py", "test_bugs.py"):
        (tmp_path / name).write_text("def test_x(): pass\n", encoding="utf-8")

    assert werkzeug._ids_in_dateinamen(sorted(tmp_path.glob("*.py"))) == {}


def test_b907_und_b878_stehen_nicht_mehr_als_ungedeckt(werkzeug):
    """Messbares Ergebnis der Korrektur am echten Repo."""
    quelle = (REPO_ROOT / "tools" / "fix_ohne_test.py").read_text(
        encoding="utf-8", errors="replace")

    assert "_ids_in_dateinamen(testdateien)" in quelle, (
        "die Dateinamen-Auswertung ist nicht verdrahtet"
    )

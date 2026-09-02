"""Der Methoden-Prüfer sortiert Treffer jetzt nach Gewicht.

Am 2026-09-02 meldete ``pruefer_methoden`` vier Methoden ohne Aufrufer
gleichrangig. Nur eine davon war ein Defekt:

* ``StemWorkspace.destroy_workspace`` setzt ein Flag und ruft ``close()`` —
  ohne Aufrufer bleibt der einzige Aufräum-Zweig zu (B-965).
* ``PacingCurveWidget.get_density_at`` und ``StemTrackWidget.stem_name`` sind
  reine Getter. Kein Aufrufer heißt dort: ungenutzte Schnittstelle.
* ``StemWorkspace.current_track_id`` hat sehr wohl einen Aufrufer — in
  ``scripts/diag/``, das der Prüfer nicht mitgelesen hat.

Drei von vier Meldungen waren also Rauschen, das den einen echten Fund
übertönte. Der Prüfer trennt jetzt in vier Töpfe.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def inv():
    pfad = REPO_ROOT / "tools" / "inventory_audit.py"
    spec = importlib.util.spec_from_file_location("_inv_audit_b965", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _funktion(quelle: str) -> ast.AST:
    return ast.parse(quelle).body[0]


def test_zuweisung_an_self_zaehlt_als_nebenwirkung(inv):
    """Der Kern von destroy_workspace."""
    fn = _funktion(
        "def destroy_workspace(self):\n"
        "    self._is_being_destroyed = True\n"
        "    self.close()\n"
    )

    assert inv._hat_nebenwirkung(fn) is True


def test_reiner_getter_hat_keine_nebenwirkung(inv):
    """Der Kern von get_density_at."""
    fn = _funktion(
        "def get_density_at(self, t):\n"
        "    if self._total_duration <= 0:\n"
        "        return 0.5\n"
        "    idx = int(t)\n"
        "    return self._density[idx]\n"
    )

    assert inv._hat_nebenwirkung(fn) is False


def test_ein_verworfener_aufruf_zaehlt_als_nebenwirkung(inv):
    """``self.close()`` als eigene Anweisung — Ergebnis egal, Wirkung zählt."""
    fn = _funktion("def f(self):\n    self.update()\n")

    assert inv._hat_nebenwirkung(fn) is True


def test_lokale_variable_allein_ist_keine_nebenwirkung(inv):
    """Sonst wäre jeder Getter mit Zwischenschritt ein Befund."""
    fn = _funktion("def f(self):\n    x = self._a + 1\n    return x\n")

    assert inv._hat_nebenwirkung(fn) is False


def test_augmented_assign_zaehlt(inv):
    fn = _funktion("def f(self):\n    self._n += 1\n")

    assert inv._hat_nebenwirkung(fn) is True


def test_diagnoseskripte_werden_mitgelesen(inv):
    """``current_track_id`` stand nur als tot da, weil scripts/ fehlte."""
    quelle = inv._diagquelltext()

    assert "current_track_id" in quelle


def test_der_pruefer_liefert_die_vier_toepfe(inv):
    ergebnis = inv.pruefer_methoden()

    for schluessel in (
        "ohne_aufrufer",
        "nur_von_tests_benutzt",
        "nur_von_diagnoseskripten_benutzt",
        "ohne_aufrufer_aber_nur_lesend",
    ):
        assert schluessel in ergebnis


def test_die_drei_harmlosen_stehen_nicht_mehr_unter_ohne_aufrufer(inv):
    """Messbares Ergebnis der Präzisierung."""
    ergebnis = inv.pruefer_methoden()
    harte_befunde = " ".join(ergebnis["details"])

    for name in ("get_density_at", "stem_name", "current_track_id"):
        assert name not in harte_befunde, (
            f"{name} steht weiterhin als harter Befund in der Liste"
        )

"""B-975 — ein abgewiesener SCHNITT-Klick stand nur in der GUI-Konsole.

Am 2026-09-04 meldete der User: „es ist immer seit Wochen die selbe Timeline,
nichts ändert sich". Ein Klick auf „Auto-Edit" erzeugte weder eine sichtbare
Reaktion noch eine Zeile im Logfile.

Die Fehlersuche hing genau daran fest: Im Log war **nicht unterscheidbar**, ob

* der Klick ankam und vom Gate (`_require_schnitt_action`) abgewiesen wurde, oder
* der Klick den Knopf gar nicht erreichte.

Beide Fälle sahen im Logfile identisch aus — nämlich gar nicht. Die Blockade
schrieb ausschließlich nach `console_text`, also in den LOG-Tab der GUI, den
niemand nachträglich auswerten kann.

Der Fix ergänzt eine `logger.warning`-Zeile mit demselben Text. Die
Konsolenmeldung bleibt, sie ist für den Nutzer am Bildschirm.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _quelle(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _methode(rel: str, name: str) -> str:
    """Rumpf einer Methode, per AST abgegrenzt."""
    quelle = _quelle(rel)
    zeilen = quelle.splitlines()
    for knoten in ast.walk(ast.parse(quelle)):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
            ende = getattr(knoten, "end_lineno", knoten.lineno)
            return "\n".join(zeilen[knoten.lineno - 1:ende])
    raise AssertionError(f"{name} nicht gefunden in {rel}")


def _nur_code(text: str) -> str:
    """Kommentare weg — Wächter-Regel aus Loop 6.

    Viermal traf dort ein Guard die gesuchte Zeichenkette im Kommentar statt
    im Code.
    """
    return "\n".join(z.split("#", 1)[0] for z in text.splitlines())


def test_b975_die_blockade_steht_im_logfile():
    """Der Kern des Fixes."""
    rumpf = _nur_code(_methode("ui/controllers/edit_workspace.py",
                               "_require_schnitt_action"))

    assert "logger.warning" in rumpf, (
        "eine abgewiesene SCHNITT-Aktion hinterlaesst keine Spur im Logfile"
    )


def test_b975_die_logzeile_nennt_aktion_und_grund():
    """Ohne beides ist die Zeile für die Fehlersuche wertlos."""
    rumpf = _nur_code(_methode("ui/controllers/edit_workspace.py",
                               "_require_schnitt_action"))
    ab = rumpf.index("logger.warning")
    zeile = rumpf[ab:ab + 200]

    assert "feature" in zeile, "die Logzeile nennt die Aktion nicht"
    assert "reason" in zeile, "die Logzeile nennt den Grund nicht"


def test_b975_die_konsolenmeldung_bleibt():
    """Die GUI-Meldung ist für den Nutzer am Bildschirm — sie wird ergänzt,
    nicht ersetzt."""
    rumpf = _nur_code(_methode("ui/controllers/edit_workspace.py",
                               "_require_schnitt_action"))

    assert "console_text.append" in rumpf


def test_b975_das_log_kommt_vor_der_konsole():
    """Wirft die Konsolenausgabe (fehlendes Widget), steht das Log schon."""
    rumpf = _nur_code(_methode("ui/controllers/edit_workspace.py",
                               "_require_schnitt_action"))

    assert rumpf.index("logger.warning") < rumpf.index("console_text.append")


def test_b975_der_erfolgsfall_loggt_nicht():
    """Sonst stünde bei jedem Klick eine Warnung im Log."""
    rumpf = _nur_code(_methode("ui/controllers/edit_workspace.py",
                               "_require_schnitt_action"))

    vor_dem_log = rumpf[:rumpf.index("logger.warning")]
    assert "return True" in vor_dem_log, (
        "der Erfolgsfall kehrt nicht vor der Warnung zurueck"
    )


@pytest.mark.parametrize("aufrufer", ["Auto-Edit", "Timeline"])
def test_b975_die_gates_uebergeben_einen_aktionsnamen(aufrufer):
    """`feature` landet in der Logzeile — er muss sprechend sein."""
    quelle = _nur_code(_quelle("ui/controllers/edit_workspace.py"))

    assert f'_require_schnitt_action("{aufrufer}' in quelle, (
        f"kein Gate-Aufruf mit Aktionsname {aufrufer!r}"
    )


def test_b975_die_stelle_behaelt_ihren_marker():
    assert "B-975" in _quelle("ui/controllers/edit_workspace.py")

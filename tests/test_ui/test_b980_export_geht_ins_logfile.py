"""B-980: Der Export-Controller schrieb Abschluss und Fehler nur in GUI-Widgets.

Gefunden im Live-Lauf 8.1: das Logfile endete nach `Concat-Export` und
schwieg. Der Lauf sah dadurch aus wie haengengeblieben, obwohl die Vorschau
nach rund 10 Sekunden fertig war — die Erfolgsmeldung stand ausschliesslich
am Bildschirm.

Geprueft wird, dass beide Erfolgs- und beide Fehlerpfade eine Zeile ins
Logfile schreiben und die GUI-Ausgaben dabei erhalten bleiben.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

QUELLE = Path(__file__).resolve().parents[2] / "ui" / "controllers" / "export.py"


def _funktion(name: str) -> ast.FunctionDef:
    baum = ast.parse(io.open(QUELLE, encoding="utf-8").read())
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
            return knoten
    pytest.fail(f"{name} nicht in {QUELLE.name} gefunden")


def _logger_aufrufe(fn: ast.FunctionDef) -> list[str]:
    """Namen der logger.<stufe>-Aufrufe im Rumpf, Kommentare zaehlen nicht."""
    treffer = []
    for knoten in ast.walk(fn):
        if not isinstance(knoten, ast.Call):
            continue
        f = knoten.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            if f.value.id == "logger":
                treffer.append(f.attr)
    return treffer


@pytest.mark.parametrize(
    "handler,erwartete_stufen",
    [
        ("_on_export_finished", {"info", "warning"}),
        ("_on_preview_finished", {"info", "warning"}),
        ("_on_export_error", {"error", "exception"}),
        ("_on_preview_error", {"error", "exception"}),
    ],
)
def test_jeder_abschlusspfad_schreibt_ins_logfile(handler, erwartete_stufen):
    aufrufe = set(_logger_aufrufe(_funktion(handler)))
    assert aufrufe & erwartete_stufen, (
        f"{handler} schreibt nichts ins Logfile — genau daran scheiterte die "
        f"Fehlersuche in Loop 8.1 (gefunden: {sorted(aufrufe) or 'keine'})"
    )


@pytest.mark.parametrize(
    "handler",
    ["_on_export_finished", "_on_preview_finished", "_on_export_error", "_on_preview_error"],
)
def test_die_gui_ausgabe_bleibt_erhalten(handler):
    """Das Logfile kommt hinzu, es ersetzt die Bildschirmausgabe nicht."""
    quelltext = ast.unparse(_funktion(handler))
    assert "export_log.append" in quelltext, (
        f"{handler} schreibt nicht mehr in das Export-Protokoll der GUI — "
        "die Meldung am Bildschirm ist fuer den Nutzer da und bleibt"
    )


def test_der_fehlerfall_nennt_den_grund():
    """Eine Logzeile ohne die Fehlermeldung waere wertlos."""
    for handler in ("_on_export_error", "_on_preview_error"):
        fn = _funktion(handler)
        for knoten in ast.walk(fn):
            if (
                isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Attribute)
                and isinstance(knoten.func.value, ast.Name)
                and knoten.func.value.id == "logger"
            ):
                argumente = ast.unparse(ast.Module(body=[ast.Expr(knoten)], type_ignores=[]))
                assert "error_msg" in argumente, (
                    f"{handler}: die Logzeile nennt den Grund nicht ({argumente})"
                )
                break
        else:
            pytest.fail(f"{handler} hat keinen logger-Aufruf")


def test_der_erfolgsfall_nennt_den_ausgabepfad():
    for handler, variable in (
        ("_on_export_finished", "output_path"),
        ("_on_preview_finished", "preview_path"),
    ):
        fn = _funktion(handler)
        gefunden = False
        for knoten in ast.walk(fn):
            if (
                isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Attribute)
                and isinstance(knoten.func.value, ast.Name)
                and knoten.func.value.id == "logger"
            ):
                if variable in ast.unparse(knoten):
                    gefunden = True
                    break
        assert gefunden, f"{handler}: die Logzeile nennt {variable} nicht"


def test_gegenprobe_der_logger_existiert_ueberhaupt():
    """Schlaegt fehl, wenn der Logger aus dem Modul verschwindet."""
    quelle = io.open(QUELLE, encoding="utf-8").read()
    assert "logger = logging.getLogger(__name__)" in quelle

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

WURZEL = Path(__file__).resolve().parents[2]
QUELLE = WURZEL / "ui" / "controllers" / "export.py"
QUELLE_CONVERT = WURZEL / "ui" / "controllers" / "convert.py"


def _funktion(name: str, quelle: Path = None) -> ast.FunctionDef:
    quelle = quelle or QUELLE
    baum = ast.parse(io.open(quelle, encoding="utf-8").read())
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
            return knoten
    pytest.fail(f"{name} nicht in {quelle.name} gefunden")


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


# --------------------------------------------------------------------------
# B-981 — dieselbe Luecke im Convert-Controller
#
# Belegt im Live-Lauf 8.4: 121 Videos in 3:49 konvertiert, im Logfile standen
# genau zwei Zeilen (der GPU-Lock). Ergebnis und Fehler der Batch-Konvertierung
# gingen nur in ein GUI-Widget.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handler,erwartete_stufen",
    [
        ("_on_batch_convert_finished", {"info", "warning"}),
        ("_on_batch_convert_error", {"error", "exception"}),
    ],
)
def test_b981_convert_schreibt_ins_logfile(handler, erwartete_stufen):
    aufrufe = set(_logger_aufrufe(_funktion(handler, QUELLE_CONVERT)))
    assert aufrufe & erwartete_stufen, (
        f"{handler} schreibt nichts ins Logfile — 121 konvertierte Videos "
        f"hinterliessen so nur zwei GPU-Lock-Zeilen "
        f"(gefunden: {sorted(aufrufe) or 'keine'})"
    )


def test_b981_die_gui_ausgabe_bleibt_erhalten():
    for handler in ("_on_batch_convert_finished", "_on_batch_convert_error"):
        quelltext = ast.unparse(_funktion(handler, QUELLE_CONVERT))
        assert "convert_log.append" in quelltext, (
            f"{handler} schreibt nicht mehr in das Convert-Protokoll der GUI"
        )


def test_b981_der_erfolgsfall_nennt_die_stueckzahl():
    quelltext = ast.unparse(_funktion("_on_batch_convert_finished", QUELLE_CONVERT))
    for knoten in ast.walk(ast.parse(quelltext)):
        if (
            isinstance(knoten, ast.Call)
            and isinstance(knoten.func, ast.Attribute)
            and isinstance(knoten.func.value, ast.Name)
            and knoten.func.value.id == "logger"
        ):
            argumente = ast.unparse(knoten)
            assert "converted" in argumente and "total" in argumente, (
                f"die Logzeile nennt nicht, wie viele von wie vielen fertig "
                f"wurden ({argumente})"
            )
            return
    pytest.fail("kein logger-Aufruf in _on_batch_convert_finished")

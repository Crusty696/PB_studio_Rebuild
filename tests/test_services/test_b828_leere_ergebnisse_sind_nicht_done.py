"""B-828: Analyse-Schritte meldeten `done`, obwohl sie nichts erzeugt hatten.

Der Nutzer sieht im Analyse-Panel ein gruenes Haekchen und hat trotzdem keine
Keyframes, keine Motion-Werte oder keine Captions. ``get_completion_percent``
zaehlt den Clip als fertig analysiert, und nachgelagerte Schritte laufen auf
leeren Daten weiter.

Betroffen waren vier Aufrufstellen in ``services/video_analysis_service.py``:
Keyframes, Motion und zweimal Captioning (einmal im Einzelpfad, einmal in der
Pipeline). Zwei unabhaengige Pruefer fanden dieselben Stellen.

Fuer genau diesen Fall existiert bereits ``mark_degraded`` — SigLIP-Embeddings
nutzen es seit laengerem (``video_analysis_service.py:1899``): der Schritt lief
durch, das Ergebnis ist aber leer, und ``degraded`` zaehlt nicht als ``done``.
Dieses Muster wird hier auf die vier verbliebenen Stellen uebertragen.

Die Tests pruefen den Quelltext strukturell statt die Pipeline auszufuehren:
ein echter Lauf braucht Videodateien, GPU und Modelle. Geprueft wird, dass an
jeder Stelle die Null-Menge abgefangen wird, bevor ``mark_done`` faellt.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

QUELLE = Path(__file__).resolve().parents[2] / "services" / "video_analysis_service.py"

# step_key -> Name der Zaehlvariablen, die vor mark_done geprueft werden muss
SCHRITTE = {
    "keyframe_extraction": "keyframe_count",
    # Der Motion-Schritt meldete nur einen Durchschnitt (``avg_motion``). Ein
    # Durchschnitt von 0.0 ist bei einem statischen Video aber ein voellig
    # gueltiges Ergebnis und taugt deshalb nicht zur Leer-Erkennung — dafuer
    # braucht es die Anzahl der Szenen, die ueberhaupt einen Wert bekommen haben.
    "motion_scores": "motion_count",
    "ai_scene_caption": "captioned_count",
}


@pytest.fixture(scope="module")
def baum() -> ast.Module:
    return ast.parse(QUELLE.read_text(encoding="utf-8"))


def _mark_aufrufe(baum: ast.Module, funktion: str) -> list[ast.Call]:
    """Alle analysis_status_service.<funktion>(...)-Aufrufe im Modul."""
    treffer = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        ziel = knoten.func
        if isinstance(ziel, ast.Attribute) and ziel.attr == funktion:
            treffer.append(knoten)
    return treffer


def _step_key(aufruf: ast.Call) -> str | None:
    """Der dritte Positionsparameter ist der step_key."""
    if len(aufruf.args) >= 3 and isinstance(aufruf.args[2], ast.Constant):
        return aufruf.args[2].value
    return None


@pytest.mark.parametrize("step_key", sorted(SCHRITTE))
def test_jeder_schritt_hat_einen_degraded_pfad(baum, step_key):
    """Fuer jeden betroffenen Schritt muss es mark_degraded geben."""
    keys = {_step_key(a) for a in _mark_aufrufe(baum, "mark_degraded")}
    assert step_key in keys, (
        f"B-828: '{step_key}' meldet nur done/error. Ein leeres Ergebnis "
        "bekommt damit ein gruenes Haekchen."
    )


@pytest.mark.parametrize("step_key", sorted(SCHRITTE))
def test_mark_done_steht_nicht_mehr_unbedingt(baum, step_key):
    """Jedes mark_done fuer diese Schritte muss in einem if/else haengen.

    Ein mark_done ohne umschliessende Bedingung ist der Fehler selbst: es
    faellt dann auch bei einer Null-Menge.
    """
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for aufruf in _mark_aufrufe(ast.Module(body=knoten.body, type_ignores=[]), "mark_done"):
            if _step_key(aufruf) != step_key:
                continue
            # Den umschliessenden if-Zweig suchen
            drin = False
            for kandidat in ast.walk(knoten):
                if isinstance(kandidat, ast.If):
                    for teil in kandidat.body + kandidat.orelse:
                        for unterknoten in ast.walk(teil):
                            if unterknoten is aufruf:
                                drin = True
            assert drin, (
                f"B-828: mark_done fuer '{step_key}' in {knoten.name}() steht "
                "unbedingt — es faellt auch bei 0 Ergebnissen."
            )


@pytest.mark.parametrize("step_key,zaehler", sorted(SCHRITTE.items()))
def test_der_zaehler_wird_gegen_null_geprueft(step_key, zaehler):
    """Die Bedingung muss den tatsaechlichen Zaehler auf 0 pruefen."""
    text = QUELLE.read_text(encoding="utf-8")
    assert f"{zaehler} == 0" in text, (
        f"B-828: '{step_key}' prueft '{zaehler}' nicht auf 0 — dann kann die "
        "Fallunterscheidung nicht greifen."
    )


def test_siglip_muster_bleibt_unveraendert(baum):
    """Gegenprobe: das Vorbild darf durch die Aenderung nicht verlorengehen."""
    keys = {_step_key(a) for a in _mark_aufrufe(baum, "mark_degraded")}
    assert "siglip_embeddings" in keys


def test_mark_degraded_signatur_passt(baum):
    """Der Aufruf braucht eine Begruendung — sonst steht der Nutzer im Dunkeln."""
    from services import analysis_status_service

    parameter = list(inspect.signature(analysis_status_service.mark_degraded).parameters)
    assert parameter[:4] == ["media_type", "media_id", "step_key", "reason"]

    for aufruf in _mark_aufrufe(baum, "mark_degraded"):
        if _step_key(aufruf) in SCHRITTE:
            assert len(aufruf.args) >= 4, (
                f"B-828: mark_degraded fuer '{_step_key(aufruf)}' uebergibt "
                "keine Begruendung."
            )

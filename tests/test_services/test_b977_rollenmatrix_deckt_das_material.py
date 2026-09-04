"""B-977 — die Rollenmatrix sperrte 60 % des Materials aus.

Gefunden am 2026-09-04 über `tools/log_audit.py`: 292 Zeilen an einem Tag über
zu wenige rollenkonforme Kandidaten. Nachgemessen im Projekt
`Erstlauf_Test_2026-08-30` (147 Szenen, 121 Videos):

    Material je Rolle:  establishing 76, hero 36, action 13,
                        filler 12, detail 7, transition 3
    Sektionen im Song:  chorus 10, buildup 7, drop 6, verse 4

`establishing` — mit 52 % die grösste Gruppe — stand nur in den Matrixzeilen
`intro`, `warmup`, `breakdown` und `outro`. Genau diese vier Sektionen kommen
in dem Track **nicht vor**. Damit waren 88 von 147 Szenen gesperrt.

Die Rechnung ging nicht auf: 79 Segmente brauchen bei `max_uses=1` 79
verschiedene Clips, nutzbar waren je Sektion höchstens 52. Folge — in **einem**
Lauf mit 79 Segmenten:

    B-768 Rollenmenge gesoftet :  40
    B-776 Pool geweitet        :  42
    zusammen                   :  82

Der Notfallpfad griff öfter, als es Segmente gab. In 12 von 40 Fällen liess die
Matrix **null** Kandidaten übrig — bei 121 verfügbaren Videos.

Userentscheidung: Matrix erweitern, `establishing` in die vier vorkommenden
Sektionen aufnehmen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGELN = REPO_ROOT / "config" / "pacing_rules.yaml"

# Sektionen, die im Testprojekt tatsächlich vorkommen.
VORKOMMENDE = ("buildup", "chorus", "drop", "verse")


@pytest.fixture(scope="module")
def matrix() -> dict[str, list[str]]:
    daten = yaml.safe_load(REGELN.read_text(encoding="utf-8"))
    return daten["section_role_matrix"]


@pytest.mark.parametrize("sektion", VORKOMMENDE)
def test_b977_establishing_ist_in_den_haeufigen_sektionen_erlaubt(matrix, sektion):
    """Der Kern: die grösste Materialgruppe darf nicht ausgesperrt sein."""
    assert "establishing" in matrix[sektion], (
        f"section={sektion} sperrt establishing aus — 52 % des Materials"
    )


def test_b977_die_uebrigen_sektionen_bleiben_unveraendert(matrix):
    """Nur die vier vorkommenden Sektionen wurden angefasst.

    `intro`, `warmup`, `breakdown` und `outro` hatten `establishing` ohnehin;
    `bridge` und `transition` blieben bewusst unberührt.
    """
    assert matrix["bridge"] == ["transition", "detail"]
    assert matrix["transition"] == ["transition", "action", "hero"]
    assert matrix["intro"] == ["establishing", "ambient", "detail"]
    assert matrix["outro"] == ["establishing", "detail", "ambient"]


def test_b977_filler_bleibt_draussen(matrix):
    """Absicht: B-768 lädt `filler` ohnehin als Notfall nach.

    Es zusätzlich regulär zuzulassen, würde die Notfall-Erkennung entwerten.
    """
    for sektion in VORKOMMENDE:
        assert "filler" not in matrix[sektion]


def test_b977_die_bisherigen_rollen_bleiben_erhalten(matrix):
    """Erweitert, nicht ersetzt — sonst kippt die Bildsprache."""
    assert set(["hero", "action", "transition"]) <= set(matrix["buildup"])
    assert set(["hero", "action"]) <= set(matrix["drop"])
    assert set(["hero", "detail"]) <= set(matrix["verse"])
    assert set(["hero", "action"]) <= set(matrix["chorus"])


def test_b977_establishing_steht_hinten(matrix):
    """Die Reihenfolge ist Rangfolge — establishing ergänzt, führt nicht."""
    for sektion in VORKOMMENDE:
        assert matrix[sektion][-1] == "establishing"


def test_b977_die_begruendung_steht_in_der_datei():
    """Ohne Beleg sieht die Zeile beim nächsten Umbau wie Willkür aus."""
    text = REGELN.read_text(encoding="utf-8")

    assert "B-977" in text
    assert "88 von 147" in text, "die gemessene Sperrquote fehlt"


def test_b977_die_matrix_deckt_das_material_rechnerisch_ab(matrix):
    """Gegenrechnung mit den gemessenen Materialzahlen.

    79 Segmente bei `max_uses=1` brauchen 79 verschiedene Clips. Vor der
    Erweiterung lagen alle vier Sektionen darunter (43 bis 52).
    """
    material = {
        "establishing": 76, "hero": 36, "action": 13,
        "filler": 12, "detail": 7, "transition": 3,
    }
    gebraucht = 79

    for sektion in VORKOMMENDE:
        nutzbar = sum(material.get(rolle, 0) for rolle in matrix[sektion])
        assert nutzbar >= gebraucht, (
            f"section={sektion}: nur {nutzbar} nutzbare Szenen fuer "
            f"{gebraucht} Segmente — der Notfallpfad greift wieder"
        )


def test_b977_ohne_establishing_waere_die_rechnung_nicht_aufgegangen(matrix):
    """Belegt, dass die Erweiterung den Unterschied macht, nicht Zufall."""
    material = {
        "establishing": 76, "hero": 36, "action": 13,
        "filler": 12, "detail": 7, "transition": 3,
    }

    for sektion in VORKOMMENDE:
        ohne = sum(material.get(r, 0) for r in matrix[sektion] if r != "establishing")
        assert ohne < 79, (
            f"section={sektion} käme auch ohne establishing auf {ohne} — dann "
            f"war die Diagnose falsch"
        )


def test_b977_die_datei_bleibt_gueltiges_yaml():
    daten = yaml.safe_load(REGELN.read_text(encoding="utf-8"))

    assert isinstance(daten, dict)
    assert "section_role_matrix" in daten
    assert "key_mood_gate" in daten
    assert daten["stage1_fallback"] == "soften"


def test_b977_die_pipeline_liest_genau_diese_datei():
    """Quellcode-Guard: der Schlüsselname darf nicht auseinanderlaufen."""
    quelle = (REPO_ROOT / "services" / "pacing" / "pipeline.py").read_text(
        encoding="utf-8", errors="replace")

    assert 'self._rules.get("section_role_matrix", {})' in quelle

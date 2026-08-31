"""Die Pruefwerkzeuge selbst pruefen.

Ein Werkzeug, das Fehler finden soll, ist wertlos, solange niemand gezeigt hat,
dass es einen bekannten Fehler auch findet. Diese Tests fuettern jedem Werkzeug
einen Defekt, den es melden MUSS, und einen sauberen Fall, bei dem es schweigen
muss.

Anlass: Selbstpruefung 2026-08-31. Die Werkzeuge entstanden als Antwort auf
Fehler desselben Tages; ohne diese Tests waeren sie nur eine weitere
unbelegte Behauptung.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from tools.pacing_metrics import kennzahlen
from tools.session_learning import THEMEN, relevante_lessons


# ── Werkzeug: pacing_metrics ──────────────────────────────────────────────

@dataclass
class _Segment:
    """Nur die Felder, die kennzahlen() liest (wie TimelineSegment)."""
    video_id: int
    start: float
    end: float
    source_start: float
    source_end: float


def _sauber() -> list[_Segment]:
    """Drei Segmente, lueckenlos, Quelle deckt den Slot vollstaendig."""
    return [
        _Segment(1, 0.0, 4.0, 0.0, 4.0),
        _Segment(2, 4.0, 9.0, 0.0, 5.0),
        _Segment(3, 9.0, 12.0, 0.0, 3.0),
    ]


def test_sauberer_lauf_meldet_keinen_defekt():
    werte = kennzahlen(_sauber(), 1.0, {1: 10.0, 2: 10.0, 3: 10.0})

    assert werte["gekappte_quellen"] == 0
    assert werte["luecken"] == 0
    assert werte["ueberlappungen"] == 0
    assert werte["segmente"] == 3
    assert werte["verschiedene_clips"] == 3
    assert werte["direkte_wiederholungen"] == 0


def test_gekappte_quelle_wird_gefunden():
    """Der Fehler, der am 2026-08-31 38 geschlossene Luecken ausloeste.

    Slot 5.0 s, Quelle nur 4.0 s: beim Anwenden entsteht eine Luecke, die die
    Timeline-Reparatur schliesst und dabei alle Folgesegmente verschiebt.
    """
    segmente = _sauber()
    segmente[1] = _Segment(2, 4.0, 9.0, 0.0, 4.0)  # 5.0s Slot, 4.0s Quelle

    werte = kennzahlen(segmente, 1.0, {1: 10.0, 2: 4.0, 3: 10.0})

    assert werte["gekappte_quellen"] == 1
    detail = werte["gekappt_details"][0]
    assert detail["clip"] == 2
    assert detail["slot"] == 5.0
    assert detail["quelle"] == 4.0
    assert detail["clipdauer"] == 4.0


def test_luecke_zwischen_segmenten_wird_gefunden():
    segmente = _sauber()
    segmente[2] = _Segment(3, 9.5, 12.0, 0.0, 2.5)  # 0.5s Loch vor dem Segment

    werte = kennzahlen(segmente, 1.0, {1: 10.0, 2: 10.0, 3: 10.0})

    assert werte["luecken"] == 1
    assert werte["luecken_summe_s"] == pytest.approx(0.5)


def test_ueberlappung_wird_gefunden():
    segmente = _sauber()
    segmente[2] = _Segment(3, 8.0, 12.0, 0.0, 4.0)  # startet 1.0s zu frueh

    werte = kennzahlen(segmente, 1.0, {1: 10.0, 2: 10.0, 3: 10.0})

    assert werte["ueberlappungen"] == 1


def test_direkte_wiederholung_wird_gezaehlt():
    segmente = _sauber()
    segmente[1] = _Segment(1, 4.0, 9.0, 0.0, 5.0)  # zweimal Clip 1 hintereinander

    werte = kennzahlen(segmente, 1.0, {1: 10.0, 2: 10.0, 3: 10.0})

    assert werte["direkte_wiederholungen"] == 1
    assert werte["verschiedene_clips"] == 2


def test_laengenkennzahlen_stimmen():
    werte = kennzahlen(_sauber(), 2.5, {1: 10.0, 2: 10.0, 3: 10.0})

    assert werte["laenge_min"] == 3.0
    assert werte["laenge_max"] == 5.0
    assert werte["laenge_median"] == 4.0
    assert werte["laufzeit_s"] == 2.5


def test_leere_segmentliste_stuerzt_nicht_ab():
    werte = kennzahlen([], 0.1, {})

    assert werte["segmente"] == 0
    assert werte["laenge_max"] == 0.0
    assert werte["gekappte_quellen"] == 0


# ── Werkzeug: session_learning relevant ───────────────────────────────────

def _lesson(tmp_path, name: str, **felder) -> None:
    daten = {
        "lesson_id": name,
        "recorded_at": felder.pop("recorded_at", "2026-08-01T00:00:00+00:00"),
        "problem": "", "cause": "", "rule": "", "applies_to": "",
    }
    daten.update(felder)
    (tmp_path / f"{name}.json").write_text(
        json.dumps(daten), encoding="utf-8")


def test_findet_die_lehre_zum_thema(tmp_path):
    """Der Fall vom 2026-08-31: die Flag-Lehre lag im Bestand und kam nie hoch."""
    _lesson(tmp_path, "flag", problem="Flag-Zustand aus der Default-Zeile geschlossen",
            rule="settings.json pruefen, nicht nur den Code-Default",
            applies_to="Feature-Flags")
    _lesson(tmp_path, "ffmpeg", problem="ffmpeg-Pfad im Frozen Build falsch",
            rule="Binary-Pfad ueber den Resolver aufloesen", applies_to="FFmpeg")

    treffer = relevante_lessons(lessons_path=tmp_path, stichworte=["flag", "setting"])

    assert [t["lesson_id"] for t in treffer] == ["flag"]


def test_liefert_nichts_bei_fremdem_thema(tmp_path):
    """Kein Rauschen: was nicht passt, darf nicht angezeigt werden."""
    _lesson(tmp_path, "flag", problem="Flag-Zustand falsch gelesen",
            rule="settings.json pruefen", applies_to="Feature-Flags")

    assert relevante_lessons(lessons_path=tmp_path, stichworte=["quantenphysik"]) == []


def test_thema_aus_dateipfaden(tmp_path):
    """Ohne Stichworte: das Thema kommt aus den geaenderten Dateien."""
    _lesson(tmp_path, "qt", problem="QThread ohne sauberes Teardown",
            rule="Worker-Lebenszyklus pro Worker pruefen", applies_to="Qt-Worker")
    _lesson(tmp_path, "db", problem="Alembic-Migration nicht idempotent",
            rule="Migration zweimal laufen lassen", applies_to="Datenbank")

    treffer = relevante_lessons(lessons_path=tmp_path, dateien=["workers/video.py"])

    assert [t["lesson_id"] for t in treffer] == ["qt"]


def test_haeufigere_treffer_stehen_vorn(tmp_path):
    _lesson(tmp_path, "viel", problem="Flag Flag Flag", rule="Flag pruefen",
            applies_to="Feature-Flags")
    _lesson(tmp_path, "wenig", problem="einmal flag erwaehnt", rule="",
            applies_to="Sonstiges")

    treffer = relevante_lessons(lessons_path=tmp_path, stichworte=["flag"], limit=2)

    assert treffer[0]["lesson_id"] == "viel"


def test_fehlendes_verzeichnis_liefert_leere_liste(tmp_path):
    assert relevante_lessons(lessons_path=tmp_path / "gibt-es-nicht",
                             stichworte=["flag"]) == []


@pytest.mark.parametrize("thema", sorted(THEMEN))
def test_jedes_thema_hat_ein_brauchbares_muster(thema):
    """Ein leeres oder immer passendes Muster waere nutzlos."""
    import re

    text_muster, _ = THEMEN[thema]

    assert text_muster, f"{thema} hat kein Textmuster"
    re.compile(text_muster)  # muss uebersetzbar sein
    assert not re.search(text_muster, "voellig unbeteiligter satz ohne bezug"), (
        f"{thema} trifft auf beliebigen Text zu"
    )


# ── Werkzeug: regression_baseline ─────────────────────────────────────────

def test_parametrisierte_testnamen_mit_leerzeichen_gehen_nicht_verloren():
    """Der Defekt im ersten Wurf des Werkzeugs.

    ``\S+?`` verlor jeden Test, dessen Parameter ein Leerzeichen enthaelt.
    Im ersten Baseline-Lauf fehlten dadurch 4 von 20 roten Tests — sie waeren
    beim naechsten Vergleich als NEU ROT gemeldet worden, obwohl sie seit
    Wochen rot sind.
    """
    from tools.regression_baseline import _FAILED, _testname

    ausgabe = (
        "FAILED tests/a.py::test_einfach - AssertionError: nope\n"
        "FAILED tests/b.py::test_frage[Was weisst du ueber Clip X?]\n"
        "FAILED tests/c.py::TestKlasse::test_methode\n"
        "ERROR tests/d.py - collection error\n"
        "1 failed, 2 passed\n"
    )

    gefunden = {_testname(t) for t in _FAILED.findall(ausgabe)}

    assert gefunden == {
        "tests/a.py::test_einfach",
        "tests/b.py::test_frage[Was weisst du ueber Clip X?]",
        "tests/c.py::TestKlasse::test_methode",
        "tests/d.py",
    }


def test_begruendung_wird_vom_testnamen_getrennt():
    from tools.regression_baseline import _testname

    assert _testname("tests/a.py::test_b - ValueError: x - y") == "tests/a.py::test_b"
    assert _testname("tests/a.py::test_b") == "tests/a.py::test_b"


def test_zusammenfassungszeile_wird_nicht_als_test_gelesen():
    from tools.regression_baseline import _FAILED

    assert _FAILED.findall("20 failed, 4696 passed, 56 skipped in 1376s\n") == []

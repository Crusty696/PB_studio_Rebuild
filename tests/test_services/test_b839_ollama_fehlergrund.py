"""B-839: Der Grund einer fehlgeschlagenen Ollama-Antwort wurde weggeworfen.

`services/ollama_service.py` meldete nur `f"Fehler: {response.status_code}"`.
Bei den HTTP-500-Fehlern in der Nacht vom 14.08. war deshalb nicht
feststellbar, WARUM Ollama ablehnte — die Ursache (eine Ollama-Version, die
das Modell auf dieser GPU nicht laden konnte) liess sich erst durch manuelle
Nachstellung finden.
"""

from __future__ import annotations

import logging

from services.ollama_service import _fehlertext


class _Antwort:
    def __init__(self, status, daten=None, text=""):
        self.status_code = status
        self._daten = daten
        self.text = text

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


def test_grund_aus_dem_json_body(caplog):
    antwort = _Antwort(500, {"error": "model requires more system memory"})
    with caplog.at_level(logging.ERROR):
        text = _fehlertext(antwort, "/api/chat", "qwen3-vl:4b")

    assert "500" in text
    assert "more system memory" in text, f"Grund fehlt: {text!r}"
    assert any("more system memory" in r.getMessage() for r in caplog.records), (
        "der Grund muss auch im Log stehen, nicht nur im Rueckgabewert"
    )


def test_grund_aus_dem_message_feld():
    antwort = _Antwort(400, {"message": "unsupported architecture"})
    assert "unsupported architecture" in _fehlertext(antwort, "/api/chat", "m")


def test_ohne_json_wird_der_rohtext_genutzt():
    antwort = _Antwort(502, daten=None, text="upstream connect error")
    assert "upstream connect error" in _fehlertext(antwort, "/api/generate", "m")


def test_ohne_jede_begruendung_bleibt_der_statuscode():
    antwort = _Antwort(503, daten=None, text="")
    text = _fehlertext(antwort, "/api/chat", "m")
    assert "503" in text


def test_langer_body_wird_gekuerzt():
    antwort = _Antwort(500, {"error": "x" * 5000})
    assert len(_fehlertext(antwort, "/api/chat", "m")) < 400


def test_kaputte_antwort_wirft_nicht():
    class Kaputt:
        status_code = 500

        def json(self):
            raise RuntimeError("kaputt")

        @property
        def text(self):
            raise RuntimeError("auch kaputt")

    assert "500" in _fehlertext(Kaputt(), "/api/chat", "m")

"""B-963 — der "Singleton" wurde bei jedem Aufruf neu gebaut.

Im Log der laufenden App stand 1403 Mal ``OllamaClient: Singleton erstellt``,
864 davon an einem einzigen Vormittag. Ursache: Der Konstruktor legt die URL
normalisiert ab (``localhost`` -> ``127.0.0.1``, B-760), ``get_ollama_client``
verglich aber gegen die **rohe** URL. Der Vergleich war damit immer ungleich,
und jeder Aufruf verwarf den bestehenden Client samt Connection-Pool.

Genau das soll der Doppel-Check-Lock in ``local_agent_service._get_ollama_client``
(B-129) verhindern.

Dieser Test kam nach dem Fix dazu: Die Commit-Prueferin
(``tools/commit_audit.py``) meldete am 2026-09-01, dass ``921fb91`` einen
Testlauf zitiert, aber keine Testdatei enthaelt. Formal war das ein
Falschpositiv - der Commit versprach keine neuen Tests. Die Luecke war
trotzdem echt.
"""

from __future__ import annotations

import pytest

from services.ollama_client import (
    DEFAULT_OLLAMA_URL,
    _normalize_ollama_host,
    get_ollama_client,
)


@pytest.fixture(autouse=True)
def _frischer_client(monkeypatch):
    """Jeder Test startet ohne vorher gebauten Modul-Client."""
    import services.ollama_client as mod

    monkeypatch.setattr(mod, "_default_client", None, raising=False)
    yield


def test_wiederholter_aufruf_liefert_dieselbe_instanz():
    """Der Kern des Befunds: 1403 Instanzen statt einer."""
    a = get_ollama_client()
    b = get_ollama_client()

    assert a is b


def test_explizite_default_url_liefert_dieselbe_instanz():
    """`get_ollama_client()` und `get_ollama_client(DEFAULT_OLLAMA_URL)` sind dasselbe."""
    a = get_ollama_client()
    b = get_ollama_client(DEFAULT_OLLAMA_URL)

    assert a is b


def test_schraegstrich_am_ende_aendert_nichts():
    a = get_ollama_client(DEFAULT_OLLAMA_URL)
    b = get_ollama_client(DEFAULT_OLLAMA_URL + "/")

    assert a is b


def test_normalisierte_und_rohe_form_treffen_denselben_client():
    """localhost und 127.0.0.1 sind nach der B-760-Normalisierung dasselbe Ziel."""
    a = get_ollama_client("http://localhost:11434")
    b = get_ollama_client("http://127.0.0.1:11434")

    assert a is b


def test_andere_url_erzeugt_einen_neuen_client():
    """Die Absicht des Dokstrings bleibt erhalten: Settings-Wechsel wirkt."""
    a = get_ollama_client()
    b = get_ollama_client("http://example.invalid:11434")

    assert a is not b


def test_der_vergleich_laeuft_gegen_die_normalisierte_form():
    """Der eigentliche Fehler, direkt geprueft.

    Waere der Vergleich wieder gegen die rohe URL gerichtet, koennte dieser
    Test nicht bestehen: die abgelegte Form ist 127.0.0.1, die uebergebene
    localhost.
    """
    client = get_ollama_client("http://localhost:11434")

    assert client.base_url == _normalize_ollama_host("http://localhost:11434")
    assert client.base_url != "http://localhost:11434"

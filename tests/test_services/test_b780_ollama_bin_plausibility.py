"""B-780: kaputter PB_OLLAMA_BIN-Pin darf nicht als gueltig durchgehen.

Real vorgefunden 2026-08-09: ``PB_OLLAMA_BIN`` zeigte auf
``C:\\Users\\...\\ollama-0.21.2\\ollama.exe`` — eine **1 Byte** grosse
Platzhalterdatei. ``_find_ollama_bin`` prueft nur ``p.exists()``, der
Platzhalter passierte den Check und wurde als
"Ollama-Binary via PB_OLLAMA_BIN" geloggt. Der kaputte Pin maskierte
damit jede funktionierende Alternative; der Start scheiterte erst
spaeter mit unverstaendlichem Fehler.

Vertraege:
1. Plausibel grosses Binary im Pin -> wird genutzt (Bestandsverhalten).
2. Zu kleines Binary (Platzhalter) -> wird verworfen, Suche laeuft
   weiter, Warnung nennt Groesse und Erwartung.
3. Nicht existierender Pin -> wie bisher: Warnung + normale Suche.
4. Kein Pin gesetzt -> normale Suche, keine Warnung ueber den Pin.
"""
from __future__ import annotations

import logging

import pytest

from services import ollama_service
from services.ollama_service import _MIN_OLLAMA_BIN_BYTES, _find_ollama_bin


@pytest.fixture()
def fake_candidate(tmp_path, monkeypatch):
    """Fallback-Kandidat, den die normale Suche findet."""
    fallback = tmp_path / "system" / "ollama.exe"
    fallback.parent.mkdir(parents=True)
    fallback.write_bytes(b"\0" * (_MIN_OLLAMA_BIN_BYTES + 1))
    monkeypatch.setattr(
        ollama_service, "_find_ollama_bin",
        _find_ollama_bin, raising=True,
    )
    return fallback


def test_plausible_pin_is_used(tmp_path, monkeypatch):
    pinned = tmp_path / "ollama.exe"
    pinned.write_bytes(b"\0" * (_MIN_OLLAMA_BIN_BYTES + 10))
    monkeypatch.setenv("PB_OLLAMA_BIN", str(pinned))
    assert _find_ollama_bin() == pinned


def test_one_byte_placeholder_is_rejected(tmp_path, monkeypatch, caplog):
    """Der exakte Realfall: 1-Byte-Datei am Pin."""
    pinned = tmp_path / "ollama.exe"
    pinned.write_bytes(b"\0")
    monkeypatch.setenv("PB_OLLAMA_BIN", str(pinned))
    with caplog.at_level(logging.WARNING):
        result = _find_ollama_bin()
    assert result != pinned, "1-Byte-Platzhalter wurde als Binary akzeptiert"
    assert "1 Byte gross" in caplog.text or "Byte gross" in caplog.text


def test_missing_pin_warns_and_falls_through(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("PB_OLLAMA_BIN", str(tmp_path / "gibtsnicht.exe"))
    with caplog.at_level(logging.WARNING):
        result = _find_ollama_bin()
    assert "existiert nicht" in caplog.text
    assert str(tmp_path) not in str(result)


def test_no_pin_no_pin_warning(monkeypatch, caplog):
    monkeypatch.delenv("PB_OLLAMA_BIN", raising=False)
    with caplog.at_level(logging.WARNING):
        _find_ollama_bin()
    assert "PB_OLLAMA_BIN" not in caplog.text


def test_threshold_is_sane():
    # Reale Binaries: ~30-35 MB. Schwelle muss klar darunter und klar
    # ueber jedem Platzhalter liegen.
    assert 1_000 < _MIN_OLLAMA_BIN_BYTES < 20_000_000

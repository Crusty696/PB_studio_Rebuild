"""B-434: Ein gecachtes _use_ollama=False (Boot-Race) darf den Chat nicht die
ganze Session tot halten — defensiver, throttled Reprobe schaltet zurueck auf
Ollama, sobald es wieder erreichbar ist. Explizit deaktiviertes Ollama wird NICHT
reprobed.
"""

from __future__ import annotations

from unittest.mock import patch


def _svc(use_ollama=None, model="phi3:mini"):
    from services.local_agent_service import LocalAgentService
    return LocalAgentService(ollama_model=model, use_ollama=use_ollama)


def test_b434_reprobe_switches_false_to_true_when_ollama_recovers():
    svc = _svc(use_ollama=None)
    svc._use_ollama = False  # Boot-Detect war faelschlich False
    assert svc._ollama_disabled_explicit is False
    with patch.object(svc, "_auto_detect_ollama", return_value=True) as ad:
        svc._maybe_reprobe_ollama()
    assert svc._use_ollama is True
    ad.assert_called_once()


def test_b434_reprobe_is_throttled():
    svc = _svc(use_ollama=None)
    svc._use_ollama = False
    with patch.object(svc, "_auto_detect_ollama", return_value=False) as ad:
        svc._maybe_reprobe_ollama()  # 1. Mal: probt (bleibt False)
        svc._maybe_reprobe_ollama()  # 2. Mal: innerhalb Intervall -> kein Probe
    assert ad.call_count == 1
    assert svc._use_ollama is False


def test_b434_explicit_disabled_never_reprobes():
    svc = _svc(use_ollama=False)
    assert svc._ollama_disabled_explicit is True
    with patch.object(svc, "_auto_detect_ollama", return_value=True) as ad:
        svc._maybe_reprobe_ollama()
    ad.assert_not_called()
    assert svc._use_ollama is False


def test_b434_true_is_noop():
    svc = _svc(use_ollama=True)
    with patch.object(svc, "_auto_detect_ollama") as ad:
        svc._maybe_reprobe_ollama()
    ad.assert_not_called()


def test_b434_generate_reprobes_cached_false(monkeypatch):
    """_generate ruft den Reprobe bei gecachtem False (nicht nur bei None)."""
    svc = _svc(use_ollama=None)
    svc._use_ollama = False
    calls = {"reprobe": 0}

    def _fake_reprobe():
        calls["reprobe"] += 1
        svc._use_ollama = True  # simuliere Recovery

    monkeypatch.setattr(svc, "_maybe_reprobe_ollama", _fake_reprobe)
    monkeypatch.setattr(svc, "_generate_ollama", lambda *a, **k: "echte Antwort")
    out = svc._generate("hallo")
    assert calls["reprobe"] == 1
    assert out == "echte Antwort"

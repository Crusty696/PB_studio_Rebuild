"""B-770: User-Modellwahl (Settings ``ollama.model``) wird vom Task-Router ignoriert.

Beleg (Trace 2026-08-07): SettingsDialog speichert ``ollama.model`` via
``settings_store.save_ollama_settings`` (services/settings_store.py:196), aber
``services/model_router.py::resolve_model_for_task`` kannte nur env-Overrides —
alle Router-Aufrufer (pacing_strategist.py:354, ai_actions.py:90,
local_agent_service.py:262/367, video_analysis_service.py:797,
model_status_field.py:63) liefen an der User-Wahl vorbei.

Soll (minimal-invasiv):
- User-Modell gesetzt + installiert -> exakt dieses Modell fuer Text-Pfade
  (chat/pacing/action), Vorrang vor der Auto-Wahl.
- Vision-Pfade (caption/vision) nur, wenn das gewaehlte Modell vision-faehig
  ist (``_VISION_FIRST_PATTERNS`` bzw. vision-capability).
- Gesetzt + NICHT installiert -> Fallback auf Auto-Wahl + sichtbares
  ``logger.warning`` mit "B-770".
- Nicht gesetzt -> bisherige Praeferenzlogik unveraendert (Regression:
  tests/services/test_b650_model_router.py).

Reine Unit-Tests, gemockte Modell-Liste, kein Netz.
"""
from __future__ import annotations

import logging

from services import model_router

# Original-Seam VOR jeder Fixture sichern (Modul-Import passiert bei der
# Collection, also bevor eine autouse-Fixture den Seam neutralisiert).
_ORIG_USER_SELECTED_MODEL = getattr(model_router, "_user_selected_model", None)

# (name, size_bytes, capabilities) — reale PB-Studio-Maschine (wie B-650-Tests)
_INSTALLED = [
    ("qwen3-vl:4b",      3_300_000_000, ["completion", "vision"]),
    ("gemma3:4b",        3_300_000_000, ["completion", "vision"]),
    ("phi3:mini",        2_200_000_000, ["completion"]),
    ("moondream:latest", 1_700_000_000, ["completion", "vision"]),
    ("minicpm-v4.6:1b",  1_600_000_000, ["completion", "vision"]),
    ("gemma4:e4b",       9_600_000_000, ["completion"]),
]


class _FakeClient:
    def __init__(self, models=None):
        self._models = models if models is not None else _INSTALLED
        self.installed = {m[0] for m in self._models}

    def model_exists(self, name):
        return name in self.installed

    def _list_models_detailed(self):
        return [{"name": n, "size": s} for (n, s, _c) in self._models]

    def _capabilities(self, name):
        for (n, _s, c) in self._models:
            if n == name:
                return c
        return None

    def select_best_model(self, task="chat", max_size_bytes=None, prefer="quality"):
        return None  # Fallback darf hier nicht gebraucht werden


def _set_user_model(monkeypatch, model):
    monkeypatch.setattr(model_router, "_user_selected_model", lambda: model)


# ---------------------------------------------------------------------------
# (a) User-Modell gesetzt + installiert -> exakt dieses fuer Text-Pfade
# ---------------------------------------------------------------------------

def test_user_model_wins_for_chat_and_pacing(monkeypatch):
    # Explizite User-Wahl schlaegt sogar den Vision-First-Ausschluss:
    # genau DAS war der Bug — User waehlte qwen3-vl:4b, Router lieferte
    # phi3:mini/gemma3:4b.
    _set_user_model(monkeypatch, "qwen3-vl:4b")
    assert model_router.resolve_model_for_task(_FakeClient(), "chat") == "qwen3-vl:4b"
    assert model_router.resolve_model_for_task(_FakeClient(), "pacing") == "qwen3-vl:4b"
    assert model_router.resolve_model_for_task(_FakeClient(), "action") == "qwen3-vl:4b"


def test_user_text_model_wins_for_text_tasks(monkeypatch):
    _set_user_model(monkeypatch, "gemma3:4b")
    assert model_router.resolve_model_for_task(_FakeClient(), "chat") == "gemma3:4b"
    assert model_router.resolve_model_for_task(_FakeClient(), "pacing") == "gemma3:4b"


# ---------------------------------------------------------------------------
# Vision-Pfade: nur wenn das User-Modell vision-faehig ist
# ---------------------------------------------------------------------------

def test_user_vision_model_wins_for_caption(monkeypatch):
    _set_user_model(monkeypatch, "minicpm-v4.6:1b")
    assert model_router.resolve_model_for_task(_FakeClient(), "caption") == "minicpm-v4.6:1b"
    assert model_router.resolve_model_for_task(_FakeClient(), "vision") == "minicpm-v4.6:1b"


def test_user_text_only_model_not_used_for_caption(monkeypatch):
    # phi3:mini hat keine vision-capability -> Caption bleibt Auto-Wahl.
    _set_user_model(monkeypatch, "phi3:mini")
    assert model_router.resolve_model_for_task(_FakeClient(), "caption") == "qwen3-vl:4b"


# ---------------------------------------------------------------------------
# (b) gesetzt + NICHT installiert -> Fallback + WARNING "B-770"
# ---------------------------------------------------------------------------

def test_user_model_missing_falls_back_with_warning(monkeypatch):
    # Eigener Handler direkt am Router-Logger — caplog haengt am Root-Logger
    # und wird von App-Logging-Setups anderer Tests ausgehebelt.
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=logging.WARNING)
    router_logger = logging.getLogger("services.model_router")
    old_level = router_logger.level
    # App-Logging-Config (dictConfig, disable_existing_loggers) setzt im
    # Test-Prozess logger.disabled=True — fuer die Messung aufheben.
    old_disabled = router_logger.disabled
    old_disable = logging.root.manager.disable
    router_logger.addHandler(handler)
    router_logger.setLevel(logging.WARNING)
    router_logger.disabled = False
    logging.disable(logging.NOTSET)
    try:
        _set_user_model(monkeypatch, "nicht-da:7b")
        got = model_router.resolve_model_for_task(_FakeClient(), "chat")
    finally:
        router_logger.removeHandler(handler)
        router_logger.setLevel(old_level)
        router_logger.disabled = old_disabled
        logging.disable(old_disable)

    assert got == "phi3:mini"  # bisherige Auto-Wahl
    warnings = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
    assert any(
        "B-770" in msg and "nicht-da:7b" in msg and "phi3:mini" in msg
        for msg in warnings
    ), f"B-770-Warning fehlt: {warnings}"


# ---------------------------------------------------------------------------
# (c) nicht gesetzt -> bisherige Praeferenzlogik unveraendert
# ---------------------------------------------------------------------------

def test_no_user_model_keeps_auto_choice(monkeypatch):
    _set_user_model(monkeypatch, None)
    assert model_router.resolve_model_for_task(_FakeClient(), "chat") == "phi3:mini"
    assert model_router.resolve_model_for_task(_FakeClient(), "pacing") == "gemma3:4b"
    assert model_router.resolve_model_for_task(_FakeClient(), "caption") == "qwen3-vl:4b"


# ---------------------------------------------------------------------------
# Praezedenz: env-Override (bewusster Power-User-Zwang) bleibt vor Settings
# ---------------------------------------------------------------------------

def test_env_override_beats_user_model(monkeypatch):
    monkeypatch.setenv("PB_STRATEGIST_MODEL", "phi3:mini")
    _set_user_model(monkeypatch, "gemma3:4b")
    assert model_router.resolve_model_for_task(_FakeClient(), "pacing") == "phi3:mini"


# ---------------------------------------------------------------------------
# Seam liest wirklich settings_store.get_ollama_settings
# ---------------------------------------------------------------------------

def test_seam_reads_settings_store(monkeypatch):
    assert _ORIG_USER_SELECTED_MODEL is not None, (
        "model_router._user_selected_model fehlt (B-770-Fix nicht vorhanden)"
    )
    import services.settings_store as ss
    monkeypatch.setattr(
        ss, "get_ollama_settings",
        lambda: {"enabled": True, "url": "http://x", "model": "  qwen3-vl:4b  "},
    )
    assert _ORIG_USER_SELECTED_MODEL() == "qwen3-vl:4b"

    monkeypatch.setattr(
        ss, "get_ollama_settings",
        lambda: {"enabled": True, "url": "http://x", "model": ""},
    )
    assert _ORIG_USER_SELECTED_MODEL() is None

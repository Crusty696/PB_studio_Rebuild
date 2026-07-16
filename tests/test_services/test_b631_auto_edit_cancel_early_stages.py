"""B-631: Auto-Edit "Abbrechen" bricht den Worker nicht wirklich ab.

Root-Cause (verifiziert per Code-Lesung): der bisher EINZIGE
should_stop_cb-Check in ``_auto_edit_phase3_inner`` sass tief im
Segment-Selection-Loop (B-157). Alle vorgelagerten, potenziell lang
laufenden Stufen (Audio-Laden, Beat-/Struktur-Erkennung, Stem-/Motion-
Analyse, optionaler LLM-Strategist — laut B-629-Live-Retest kann allein
"Lade Audio" unter Last >240s dauern) liefen OHNE jeden Check. Ein
Cancel-Klick waehrend dieser Stufen setzte zwar den Flag, aber die
Pipeline pruefte ihn erst (viel) spaeter. Der Worker lief nachweislich
weiter, obwohl SchnittController._on_cancel das Overlay bereits sofort
geschlossen hatte — UND ``btn_auto_edit`` blieb "laeuft..." haengen,
weil dieser Button ausschliesslich ueber ``worker.finished`` (also erst
beim TATSAECHLICHEN Pipeline-Ende) zurueckgesetzt wird
(``edit_workspace.py:_on_auto_edit_finished``).

Fix: should_stop_cb wird jetzt an 4 zusaetzlichen fruehen Stage-Grenzen
geprueft (vor Audio-Load, nach Audio-Load, vor Stem-/Motion-Analyse, vor
LLM-Strategist) — gleiches Rueckgabe-Idiom wie der bestehende Check
(frueher Return mit leeren Listen, keine Exception).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.pacing_service import AdvancedPacingSettings, _auto_edit_phase3_inner


def _cancelled_cb():
    return True


def _not_cancelled_cb():
    return False


@pytest.fixture
def fake_engine():
    return MagicMock(name="fake_engine")


def test_cancel_before_audio_load_returns_immediately(fake_engine, monkeypatch):
    """should_stop_cb=True VOR dem ersten DB-Zugriff -> sofortiger Return,
    _get_audio_duration wird NIE aufgerufen."""
    from services import pacing_service

    called = []
    monkeypatch.setattr(
        pacing_service, "_get_audio_duration",
        lambda *a, **kw: called.append("audio_duration") or 100.0,
    )

    segments, cuts = _auto_edit_phase3_inner(
        fake_engine, audio_id=1, video_clip_ids=[1, 2],
        settings=AdvancedPacingSettings(),
        should_stop_cb=_cancelled_cb,
    )

    assert (segments, cuts) == ([], [])
    assert called == [], "_get_audio_duration darf bei sofortigem Cancel nicht aufgerufen werden"


def test_cancel_after_audio_load_skips_beat_data(fake_engine, monkeypatch):
    """should_stop_cb wird erst NACH dem ersten Check True -> Audio-Load
    laeuft noch, aber _get_beat_data_combined (naechste teure Stufe) wird
    uebersprungen."""
    from services import pacing_service

    calls = []
    monkeypatch.setattr(
        pacing_service, "_get_audio_duration",
        lambda *a, **kw: calls.append("audio_duration") or 100.0,
    )
    monkeypatch.setattr(
        pacing_service, "_get_beat_data_combined",
        lambda *a, **kw: calls.append("beat_data") or (None, None, None, None),
    )

    # Erster Check (vor Audio-Load) liefert False, ALLE weiteren True —
    # simuliert einen Cancel-Klick waehrend/kurz nach dem Audio-Load.
    call_count = {"n": 0}

    def _cb():
        call_count["n"] += 1
        return call_count["n"] > 1

    segments, cuts = _auto_edit_phase3_inner(
        fake_engine, audio_id=1, video_clip_ids=[1, 2],
        settings=AdvancedPacingSettings(),
        should_stop_cb=_cb,
    )

    assert (segments, cuts) == ([], [])
    assert "audio_duration" in calls
    assert "beat_data" not in calls, (
        "_get_beat_data_combined haette nach dem 2. Cancel-Check nicht mehr "
        "laufen duerfen"
    )


def test_no_cancel_runs_past_early_checks(fake_engine, monkeypatch):
    """Gegenprobe: should_stop_cb liefert immer False -> Audio-Load UND
    Beat-Data-Load laufen normal weiter (keine falsch-positiven Aborts)."""
    from services import pacing_service

    calls = []
    monkeypatch.setattr(
        pacing_service, "_get_audio_duration",
        lambda *a, **kw: calls.append("audio_duration") or 100.0,
    )
    monkeypatch.setattr(
        pacing_service, "_get_beat_data_combined",
        lambda *a, **kw: calls.append("beat_data") or ([], [], [], False),
    )

    # Keine Beats + kein BPM -> Funktion returnt frueh mit ([], []) ueber
    # den BESTEHENDEN "keine Beat-Daten"-Pfad (nicht ueber Cancel) — das
    # ist hier gewollt, um ohne volle Pipeline-Mocks zu testen, dass die
    # frueheren Stufen bei should_stop_cb=False tatsaechlich laufen.
    monkeypatch.setattr(pacing_service, "_get_bpm", lambda *a, **kw: None)

    segments, cuts = _auto_edit_phase3_inner(
        fake_engine, audio_id=1, video_clip_ids=[1, 2],
        settings=AdvancedPacingSettings(),
        should_stop_cb=_not_cancelled_cb,
    )

    assert (segments, cuts) == ([], [])
    assert calls == ["audio_duration", "beat_data"]


def test_should_stop_cb_none_does_not_crash(fake_engine, monkeypatch):
    """Rueckwaertskompat: should_stop_cb=None (Default) darf die neuen
    Checks nicht crashen lassen — bestehende Aufrufer ohne Cancel-Support
    (z.B. direkte Tests) muessen weiter funktionieren."""
    from services import pacing_service

    monkeypatch.setattr(pacing_service, "_get_audio_duration", lambda *a, **kw: 100.0)
    monkeypatch.setattr(
        pacing_service, "_get_beat_data_combined",
        lambda *a, **kw: ([], [], [], False),
    )
    monkeypatch.setattr(pacing_service, "_get_bpm", lambda *a, **kw: None)

    segments, cuts = _auto_edit_phase3_inner(
        fake_engine, audio_id=1, video_clip_ids=[1, 2],
        settings=AdvancedPacingSettings(),
        should_stop_cb=None,
    )
    assert (segments, cuts) == ([], [])

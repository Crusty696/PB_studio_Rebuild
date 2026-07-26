"""B-066/V2: Fallback-Ergebnisse werden nicht persistiert, brechen die
Pipeline aber auch nicht ab — sie landen als `degraded` im Status.

Statusaufnahme 2026-07-26: die V2-Pipeline (Default) schrieb Rate-Werte als
echte Messwerte in `audio_tracks` — Key `Am`/`8A` mit confidence 0.0,
Spektral-Baender mit lauter 0.0, LUFS -14.0. V1 hat dagegen den B-066-Schutz.

Der erste Fix-Ansatz warf eine RuntimeError wie V1. Das ist in V2 falsch:
V1 hat pro Schritt einen eigenen Worker, V2 ist eine strikt sequentielle
Pipeline mit fail-fast — ein LUFS-Fallback in Stage 6 haette Classify,
Waveform und AV-Pacing mitgerissen. Diese Tests sichern das korrigierte
Verhalten ab: nicht persistieren, weiterlaufen, als geraten markieren.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.audio_pipeline import stages as stages_mod
from services.audio_pipeline.context import PipelineContext


@dataclass
class _FallbackKey:
    key = "Am"
    camelot = "8A"
    confidence = 0.0
    method = "fallback"


@dataclass
class _GoodKey:
    key = "F#m"
    camelot = "11A"
    confidence = 0.87
    method = "krumhansl"


def _ctx() -> PipelineContext:
    return PipelineContext(track_id=1, original_path="/x.wav")


def test_fallback_result_is_not_persisted_and_marked_degraded():
    ctx = _ctx()
    may_persist = stages_mod._guard_no_fallback_persist(_FallbackKey(), "key", ctx)

    assert may_persist is False, "Rate-Ergebnis darf nicht persistiert werden"
    assert ctx.is_degraded("key")
    assert "fallback" in ctx.degraded["key"].lower()


def test_good_result_is_persisted_and_not_degraded():
    ctx = _ctx()
    may_persist = stages_mod._guard_no_fallback_persist(_GoodKey(), "key", ctx)

    assert may_persist is True
    assert not ctx.is_degraded("key")
    assert ctx.degraded == {}


def test_guard_does_not_raise_so_pipeline_continues():
    """Der eigentliche Regressionsschutz: kein Abbruch der Restpipeline."""
    ctx = _ctx()
    try:
        stages_mod._guard_no_fallback_persist(_FallbackKey(), "lufs", ctx)
    except Exception as exc:  # pragma: no cover - genau das darf nicht passieren
        pytest.fail(
            "Guard hat geworfen und haette in der fail-fast-Pipeline alle "
            f"folgenden Stages mitgerissen: {exc!r}"
        )


def test_key_stage_skips_persist_on_fallback(monkeypatch):
    """Ende-zu-Ende auf Stage-Ebene: KeyStage schreibt nichts in die DB."""
    persisted: list[dict] = []
    monkeypatch.setattr(
        stages_mod, "_persist_to_track",
        lambda track_id, fields: persisted.append(fields),
    )

    class _Svc:
        def detect_key(self, *a, **kw):
            return _FallbackKey()

    ctx = _ctx()
    ctx.stem_paths = {"bass": "/b.wav", "other": "/o.wav"}
    stages_mod.KeyStage(service_cls=_Svc).run(ctx)

    assert persisted == [], "Fallback-Key darf nicht in audio_tracks landen"
    assert ctx.is_degraded("key")
    # Das Stage-Result selbst wird weiterhin gesetzt, damit Folge-Stages und
    # der Worker den Lauf normal abschliessen koennen.
    assert ctx.results["key"]["key"] == "Am"


def test_key_stage_persists_good_result(monkeypatch):
    persisted: list[dict] = []
    monkeypatch.setattr(
        stages_mod, "_persist_to_track",
        lambda track_id, fields: persisted.append(fields),
    )

    class _Svc:
        def detect_key(self, *a, **kw):
            return _GoodKey()

    ctx = _ctx()
    ctx.stem_paths = {"bass": "/b.wav", "other": "/o.wav"}
    stages_mod.KeyStage(service_cls=_Svc).run(ctx)

    assert len(persisted) == 1
    assert persisted[0]["key"] == "F#m"
    assert not ctx.is_degraded("key")

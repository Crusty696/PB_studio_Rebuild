"""Regressionstests fuer zwei bestaetigte Befunde aus dem Audio-Video-Sweep
(Workflow wf_7c300576-f08, Suchagent-Label ``suche:audio-video``):

- Befund services/audio_pipeline/stages.py:796 (Skeptiker: echt, Schwere
  "mittel") — ``AVPacingStage`` reicht ``context.should_stop`` nicht an
  ``AVPacingService.analyze`` durch; der Abbruch wirkt erst nach der
  kompletten Analyse (bis ~20 min HPSS-Last, Batch-Stall).
- Befund services/audio_pipeline/stages.py:592 (Skeptiker: echt, Schwere
  von "hoch" auf "niedrig" korrigiert) — ``StemGenStage.rehydrate``
  schreibt DB-Stem-Pfade ohne Existenzpruefung in den Context. Die Pfade
  MUESSEN weiterhin gesetzt werden (OTK-018, sonst fail-fast der
  Folge-Stages), aber der stem-lose Fallback darf nicht als "gruen"
  gemeldet werden -> ``mark_degraded``.

Keine DB-Writes, keine GPU, keine App.
"""
from __future__ import annotations

from types import SimpleNamespace


# --------------------------------------------------------------------------
# Befund stages.py:796 — AVPacingStage reicht should_stop nicht durch
# --------------------------------------------------------------------------
def test_avpacing_stage_reicht_should_stop_an_service_durch(monkeypatch):
    """RED ohne Fix: ``svc.analyze(context.original_path)`` ohne should_stop."""
    from services.audio_pipeline import stages as stages_mod
    from services.audio_pipeline.context import PipelineContext

    captured: dict = {}

    class _FakeAVPacingService:
        def analyze(self, file_path, **kwargs):
            captured["file_path"] = file_path
            captured["kwargs"] = kwargs
            return SimpleNamespace(times_sec=[], hop_sec=0.1)

    # Kein DB-Zugriff aus dieser Stage.
    monkeypatch.setattr(stages_mod, "nullpool_session", None)

    stage = stages_mod.AVPacingStage(service_cls=_FakeAVPacingService)
    ctx = PipelineContext(
        track_id=4242,
        original_path="/tmp/mix.wav",
        should_stop=lambda: False,
    )
    stage.run(ctx)

    assert captured["file_path"] == "/tmp/mix.wav"
    assert "should_stop" in captured["kwargs"], (
        "AVPacingStage muss should_stop an AVPacingService.analyze durchreichen "
        "(sonst wirkt Abbrechen erst nach der kompletten Analyse)"
    )
    assert captured["kwargs"]["should_stop"] is ctx.should_stop


def test_avpacing_stage_should_stop_erreicht_den_chunk_loop(monkeypatch):
    """Der durchgereichte Callback muss der echte Cancel-Callback sein:
    der Service bricht damit im Chunk-Loop ab statt bis zum Ende zu rechnen."""
    from services.audio_pipeline import stages as stages_mod
    from services.audio_pipeline.context import PipelineContext

    stop_flag = {"v": False}
    chunks_processed = {"n": 0}

    class _ChunkedFakeService:
        """Minimal-Nachbau des Chunk-Loops aus av_pacing_service.analyze:120."""

        def analyze(self, file_path, should_stop=None, **kwargs):
            for _ in range(100):
                if should_stop is not None and should_stop():
                    break
                chunks_processed["n"] += 1
                if chunks_processed["n"] == 3:
                    stop_flag["v"] = True  # User drueckt Abbrechen
            return SimpleNamespace(times_sec=[], hop_sec=0.1)

    monkeypatch.setattr(stages_mod, "nullpool_session", None)

    stage = stages_mod.AVPacingStage(service_cls=_ChunkedFakeService)
    ctx = PipelineContext(
        track_id=4243,
        original_path="/tmp/mix.wav",
        should_stop=lambda: stop_flag["v"],
    )
    try:
        stage.run(ctx)
    except RuntimeError:
        # _raise_if_cancelled nach analyze() — erwartet, sobald der Cancel greift.
        pass

    assert chunks_processed["n"] == 3, (
        "Abbruch muss im Chunk-Loop wirken; ohne durchgereichtes should_stop "
        f"laufen alle 100 Chunks weiter (gemessen: {chunks_processed['n']})"
    )


# --------------------------------------------------------------------------
# Befund stages.py:592 — rehydrate schreibt tote DB-Stem-Pfade ohne Vermerk
# --------------------------------------------------------------------------
def _patch_db_track(monkeypatch, stages_mod, drums, bass, vocals, other):
    class _Track:
        id = 7
        stem_drums_path = drums
        stem_bass_path = bass
        stem_vocals_path = vocals
        stem_other_path = other

    class _Sess:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def first(self):
            return _Track()

    monkeypatch.setattr(stages_mod, "nullpool_session", lambda: _Sess())
    monkeypatch.setattr("database.AudioTrack", _Track, raising=False)


def test_rehydrate_markiert_degraded_wenn_db_stems_nicht_existieren(monkeypatch):
    """RED ohne Fix: context.degraded bleibt leer, die UI meldet
    stem_separation gruen obwohl keine Stem-Datei existiert."""
    from services.audio_pipeline import stages as stages_mod
    from services.audio_pipeline.context import PipelineContext

    stage = stages_mod.StemGenStage()
    monkeypatch.setattr(stage, "_try_reuse", lambda ctx: None)  # Cache-Miss
    _patch_db_track(
        monkeypatch, stages_mod,
        drums="/db/drums.wav", bass="/db/bass.wav",
        vocals=None, other="/db/other.wav",
    )

    ctx = PipelineContext(track_id=7, original_path="/x.wav")
    stage.rehydrate(ctx)

    # OTK-018 bleibt: Pfade werden weiterhin gesetzt (sonst fail-fast der
    # Folge-Stages ueber _require_stems).
    assert ctx.stem_paths.get("drums") == "/db/drums.wav"
    assert ctx.stem_paths.get("bass") == "/db/bass.wav"
    assert ctx.stem_paths.get("other") == "/db/other.wav"
    assert "vocals" not in ctx.stem_paths

    assert ctx.is_degraded("stem_gen") is True, (
        "Fehlende Stem-Dateien beim DB-Rehydrate muessen als degraded "
        "vermerkt werden (sonst meldet das Analyse-Panel gruen)"
    )
    reason = ctx.degraded["stem_gen"]
    assert "drums" in reason and "bass" in reason and "other" in reason


def test_rehydrate_ohne_degraded_wenn_stems_existieren(tmp_path, monkeypatch):
    """Gegenprobe: existierende Stem-Dateien duerfen NICHT degraded sein."""
    from services.audio_pipeline import stages as stages_mod
    from services.audio_pipeline.context import PipelineContext

    paths = {}
    for name in ("drums", "bass", "vocals", "other"):
        p = tmp_path / f"{name}.wav"
        p.write_bytes(b"RIFF")
        paths[name] = str(p)

    stage = stages_mod.StemGenStage()
    monkeypatch.setattr(stage, "_try_reuse", lambda ctx: None)
    _patch_db_track(
        monkeypatch, stages_mod,
        drums=paths["drums"], bass=paths["bass"],
        vocals=paths["vocals"], other=paths["other"],
    )

    ctx = PipelineContext(track_id=7, original_path="/x.wav")
    stage.rehydrate(ctx)

    assert ctx.stem_paths.get("drums") == paths["drums"]
    assert ctx.is_degraded("stem_gen") is False
    assert ctx.degraded == {}

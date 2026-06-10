"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T1.3: Stages - StemGen, BeatGrid, Onset, Key, Structure, LUFS, Spectral, AVPacing.

Service-Mapping (siehe A-8 + RED-Pre-Check-Update aus T1.0-Migration-Doc):
- StemGenStage -> services.ai_audio_service.StemSeparator (separate_to in T2.1)
- BeatGridStage -> BeatAnalysisService.analyze_and_store(track_id, trigger_onset=False)
- OnsetStage -> OnsetRhythmService.analyze_and_store(track_id) (drums-path aus DB)
- KeyStage -> KeyDetectionService.detect_key(original, bass_path=..., other_path=...)
- StructureStage -> StructureDetectionService.detect(original, stem_paths={bass,drums,vocals})
- LUFSStage -> LUFSService.analyze(original)
- SpectralStage -> SpectralAnalysisService.analyze(original)
- AVPacingStage -> AVPacingService.analyze(original)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def ctx():
    from services.audio_pipeline.context import PipelineContext
    c = PipelineContext(track_id=42, original_path="/tmp/orig.wav")
    c.stem_paths = {
        "drums": "/tmp/drums.wav",
        "bass": "/tmp/bass.wav",
        "vocals": "/tmp/vocals.wav",
        "other": "/tmp/other.wav",
    }
    return c


def test_stage_base_abstract_run_raises():
    from services.audio_pipeline.stages import Stage
    s = Stage()
    with pytest.raises(NotImplementedError):
        s.run(None)


def test_stage_base_has_name_attr():
    from services.audio_pipeline.stages import Stage
    assert hasattr(Stage, "name")


def test_stem_gen_stage_calls_separator(ctx):
    from services.audio_pipeline.stages import StemGenStage

    mock_sep_cls = MagicMock()
    mock_sep = mock_sep_cls.return_value
    mock_sep.separate_to.return_value = {
        "drums": "/storage/stems/42/drums.wav",
        "bass": "/storage/stems/42/bass.wav",
        "vocals": "/storage/stems/42/vocals.wav",
        "other": "/storage/stems/42/other.wav",
    }
    s = StemGenStage(separator_cls=mock_sep_cls)
    s.run(ctx)
    mock_sep.separate_to.assert_called_once()
    # Stem-Pfade in Context geschrieben
    assert ctx.stem_paths["drums"].endswith("drums.wav")


def test_beat_grid_stage_calls_beat_analysis_with_trigger_onset_false(ctx):
    """A-7 / T1.6: Orchestrator passt trigger_onset=False."""
    from services.audio_pipeline.stages import BeatGridStage

    mock_bs_cls = MagicMock()
    mock_bs = mock_bs_cls.return_value
    mock_bs.analyze_and_store.return_value = {"bpm": 128.0, "beats": [], "downbeats": []}

    s = BeatGridStage(service_cls=mock_bs_cls)
    s.run(ctx)
    mock_bs.analyze_and_store.assert_called_once()
    _, kwargs = mock_bs.analyze_and_store.call_args
    assert kwargs.get("trigger_onset") is False


def test_onset_stage_calls_onset_rhythm_with_track_id(ctx):
    """C-01: Service zieht drums-Pfad aus DB-Field track.stem_drums_path."""
    from services.audio_pipeline.stages import OnsetStage

    mock_ors_cls = MagicMock()
    mock_ors = mock_ors_cls.return_value
    mock_ors.analyze_and_store.return_value = MagicMock()

    s = OnsetStage(service_cls=mock_ors_cls)
    s.run(ctx)
    mock_ors.analyze_and_store.assert_called_once_with(42)


def test_onset_stage_raises_when_drums_stem_missing(ctx):
    """Pipeline-Pre-Condition: T2.1 muss stem_paths.drums setzen."""
    from services.audio_pipeline.stages import OnsetStage, StageInputMissingError
    ctx.stem_paths.pop("drums")
    s = OnsetStage(service_cls=MagicMock())
    with pytest.raises(StageInputMissingError):
        s.run(ctx)


def test_key_stage_calls_detect_key_with_bass_other_kwargs(ctx):
    """C-02: detect_key(file_path, bass_path=..., other_path=...) - Sandbox-MOD."""
    from services.audio_pipeline.stages import KeyStage

    mock_kd_cls = MagicMock()
    mock_kd = mock_kd_cls.return_value
    mock_kd.detect_key.return_value = MagicMock(key="Am", camelot="8A", confidence=0.9)

    s = KeyStage(service_cls=mock_kd_cls)
    s.run(ctx)
    mock_kd.detect_key.assert_called_once()
    args, kwargs = mock_kd.detect_key.call_args
    # Erstes arg = original_path
    assert args[0] == "/tmp/orig.wav"
    assert kwargs.get("bass_path") == "/tmp/bass.wav"
    assert kwargs.get("other_path") == "/tmp/other.wav"


def test_key_stage_raises_when_bass_or_other_missing(ctx):
    from services.audio_pipeline.stages import KeyStage, StageInputMissingError
    ctx.stem_paths.pop("bass")
    s = KeyStage(service_cls=MagicMock())
    with pytest.raises(StageInputMissingError):
        s.run(ctx)


def test_structure_stage_calls_detect_with_filtered_stem_paths(ctx):
    """C-03 fuer Structure: dict-arg ohne 'other'-Stem."""
    from services.audio_pipeline.stages import StructureStage

    mock_sd_cls = MagicMock()
    mock_sd = mock_sd_cls.return_value
    mock_sd.detect.return_value = MagicMock()

    s = StructureStage(service_cls=mock_sd_cls)
    s.run(ctx)
    mock_sd.detect.assert_called_once()
    _, kwargs = mock_sd.detect.call_args
    sp = kwargs.get("stem_paths")
    assert sp is not None
    # 'other' MUSS gefiltert sein (nur bass, drums, vocals)
    assert set(sp.keys()) == {"bass", "drums", "vocals"}


def test_structure_stage_raises_when_required_stem_missing(ctx):
    from services.audio_pipeline.stages import StructureStage, StageInputMissingError
    ctx.stem_paths.pop("vocals")
    s = StructureStage(service_cls=MagicMock())
    with pytest.raises(StageInputMissingError):
        s.run(ctx)


def test_lufs_stage_uses_original(ctx):
    from services.audio_pipeline.stages import LUFSStage

    mock_ls_cls = MagicMock()
    mock_ls = mock_ls_cls.return_value
    mock_ls.analyze.return_value = MagicMock()

    s = LUFSStage(service_cls=mock_ls_cls)
    s.run(ctx)
    mock_ls.analyze.assert_called_once_with("/tmp/orig.wav")


def test_spectral_stage_uses_original(ctx):
    from services.audio_pipeline.stages import SpectralStage

    mock_ss_cls = MagicMock()
    mock_ss = mock_ss_cls.return_value
    mock_ss.analyze.return_value = MagicMock()

    s = SpectralStage(service_cls=mock_ss_cls)
    s.run(ctx)
    mock_ss.analyze.assert_called_once()
    args, _ = mock_ss.analyze.call_args
    assert args[0] == "/tmp/orig.wav"


def test_av_pacing_stage_uses_original(ctx):
    from services.audio_pipeline.stages import AVPacingStage

    mock_av_cls = MagicMock()
    mock_av = mock_av_cls.return_value
    mock_av.analyze.return_value = MagicMock()

    s = AVPacingStage(service_cls=mock_av_cls)
    s.run(ctx)
    mock_av.analyze.assert_called_once_with("/tmp/orig.wav")


def test_stage_routing_matches_service_routing_constant():
    """T1.0-Migration aus test_stem_router: SERVICE_ROUTING-Konstanten-Check."""
    from services.stem_router import SERVICE_ROUTING

    assert SERVICE_ROUTING["onset_rhythm"] == ("drums",)
    assert SERVICE_ROUTING["key_detection"] == ("bass", "other")
    assert SERVICE_ROUTING["drop_detection"] == ("bass", "drums", "vocals")
    assert SERVICE_ROUTING["lufs"] is None
    assert SERVICE_ROUTING["beat_this"] is None
    assert SERVICE_ROUTING["av_pacing"] is None


def test_stage_has_default_service_cls():
    """Stages haben Default-Service-Klasse fuer real-use."""
    from services.audio_pipeline.stages import LUFSStage, AVPacingStage
    # default ohne ctor-arg sollte gehen
    assert LUFSStage() is not None
    assert AVPacingStage() is not None

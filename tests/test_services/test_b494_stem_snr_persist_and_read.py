"""B-494: SNR (acoustic_metadata) End-to-End — Persistierung nach StemGen
+ Read-Through im Stems-Workspace.

Der Bug-Report (2026-06-11) beklagte eine fehlende Datenquelle fuer den
SNR-Subtab (Spalte existierte nicht, keine Analyse-Pipeline). Code-Pruefung
2026-07-16 zeigt: bereits vollstaendig geloest (Migration
``2026_07_15_c9d0e1f2a3b4``, `AudioTrack.acoustic_metadata`,
``services/ai_audio_service.py:StemSeparator.separate_and_store`` persistiert
``compute_stem_snr()``-Ergebnisse, ``ui/controllers/stems.py`` reicht sie
durch). Dieser Test schliesst die einzige noch fehlende Luecke: es gab
bisher KEINEN Test, der den vollen Kreis (echte Stem-WAVs -> SNR-Berechnung
-> DB-Persistierung -> UI-Read-Through-Format) end-to-end beweist.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

_GPU_STUBS = [
    "torch", "torch.cuda", "torch.nn", "torch.utils", "torch.utils.data",
    "torch.device", "torchaudio", "torchaudio.functional",
    "demucs", "demucs.pretrained", "demucs.apply",
]
for _mod_name in _GPU_STUBS:
    if _mod_name not in sys.modules:
        try:
            __import__(_mod_name)
        except ImportError:
            sys.modules[_mod_name] = MagicMock()

import numpy as np
import soundfile as sf
from sqlalchemy.orm import Session
from unittest.mock import patch

from database import AudioTrack, Project


def _setup_track_with_stems(test_engine, tmp_path) -> int:
    """Legt einen Track an UND schreibt echte (kurze, verrauschte) Stem-WAVs
    auf die Platte — compute_stem_snr prueft Path.exists() und laedt sie via
    librosa."""
    sr = 22050
    rng = np.random.default_rng(42)
    stem_paths = {}
    for name, amp in [("vocals", 0.3), ("drums", 0.5), ("bass", 0.2), ("other", 0.1)]:
        audio = rng.standard_normal(sr * 2).astype(np.float32) * amp
        p = tmp_path / f"{name}.wav"
        sf.write(str(p), audio, sr)
        stem_paths[name] = str(p)

    with Session(test_engine) as s:
        proj = Project(name="P", path=".")
        s.add(proj)
        s.commit()
        s.refresh(proj)
        track = AudioTrack(
            project_id=proj.id, file_path="/fake/audio.mp3", title="Test",
            stem_vocals_path=stem_paths["vocals"],
            stem_drums_path=stem_paths["drums"],
            stem_bass_path=stem_paths["bass"],
            stem_other_path=stem_paths["other"],
        )
        s.add(track)
        s.commit()
        s.refresh(track)
        return track.id


def test_b494_separate_and_store_persists_real_snr_into_acoustic_metadata(
    test_engine, monkeypatch, tmp_path,
):
    """Kernfall: separate_and_store() -> compute_stem_snr() -> echte SNR-
    Werte landen in AudioTrack.acoustic_metadata['stem_snr']."""
    import services.ai_audio_service as svc
    import services.pacing_beat_grid as pbg_mod
    from contextlib import contextmanager as _cm

    svc.engine = test_engine
    monkeypatch.setattr(pbg_mod, "engine", test_engine)

    @_cm
    def _test_nullpool():
        with Session(test_engine) as s:
            yield s

    svc.nullpool_session = _test_nullpool

    track_id = _setup_track_with_stems(test_engine, tmp_path)

    fake_stems = {}
    with Session(test_engine) as s:
        t = s.get(AudioTrack, track_id)
        fake_stems = {
            "vocals": t.stem_vocals_path, "drums": t.stem_drums_path,
            "bass": t.stem_bass_path, "other": t.stem_other_path,
        }

    with patch.object(svc.StemSeparator, "separate", return_value=fake_stems):
        svc.StemSeparator().separate_and_store(track_id)

    with Session(test_engine) as s:
        track = s.get(AudioTrack, track_id)
        meta = track.acoustic_metadata

    assert meta is not None, "B-494: acoustic_metadata blieb None trotz echter Stem-Dateien"
    assert "stem_snr" in meta
    snr = meta["stem_snr"]
    for stem in ("drums", "bass", "vocals", "other"):
        assert stem in snr
        assert isinstance(snr[stem], (int, float))


def test_b494_persisted_format_matches_ui_extract_snr_reader(
    test_engine, monkeypatch, tmp_path,
):
    """Bruecken-Test: das von ai_audio_service.py geschriebene Format
    (``{"stem_snr": {...}}``) muss exakt dem entsprechen, was
    ``ui/workspaces/stems_workspace.py:_extract_snr`` liest — sonst zeigt
    der Subtab trotz persistierter Daten weiterhin 'nicht verfuegbar'."""
    import services.ai_audio_service as svc
    import services.pacing_beat_grid as pbg_mod
    from ui.workspaces.stems_workspace import _extract_snr
    from contextlib import contextmanager as _cm

    svc.engine = test_engine
    monkeypatch.setattr(pbg_mod, "engine", test_engine)

    @_cm
    def _test_nullpool():
        with Session(test_engine) as s:
            yield s

    svc.nullpool_session = _test_nullpool

    track_id = _setup_track_with_stems(test_engine, tmp_path)
    with Session(test_engine) as s:
        t = s.get(AudioTrack, track_id)
        fake_stems = {
            "vocals": t.stem_vocals_path, "drums": t.stem_drums_path,
            "bass": t.stem_bass_path, "other": t.stem_other_path,
        }

    with patch.object(svc.StemSeparator, "separate", return_value=fake_stems):
        svc.StemSeparator().separate_and_store(track_id)

    with Session(test_engine) as s:
        track = s.get(AudioTrack, track_id)
        meta = track.acoustic_metadata

    snr_map = _extract_snr(meta)
    assert snr_map, "B-494: _extract_snr() liest das persistierte Format nicht — UI bleibt leer"
    for stem in ("drums", "bass", "vocals", "other"):
        assert stem in snr_map
        assert isinstance(snr_map[stem], float)


def test_b494_missing_stems_leaves_acoustic_metadata_untouched(test_engine, monkeypatch):
    """Gegenprobe: ohne Stem-Dateien auf der Platte (Alt-Track, keine
    Separation) bleibt acoustic_metadata None — kein Fake-SNR, ehrliches
    'nicht verfuegbar' im UI (Bug-Note: kein Crash, keine Falschanzeige)."""
    import services.ai_audio_service as svc
    import services.pacing_beat_grid as pbg_mod
    from contextlib import contextmanager as _cm

    svc.engine = test_engine
    monkeypatch.setattr(pbg_mod, "engine", test_engine)

    @_cm
    def _test_nullpool():
        with Session(test_engine) as s:
            yield s

    svc.nullpool_session = _test_nullpool

    with Session(test_engine) as s:
        proj = Project(name="P", path=".")
        s.add(proj)
        s.commit()
        s.refresh(proj)
        track = AudioTrack(project_id=proj.id, file_path="/fake/audio.mp3", title="Test")
        s.add(track)
        s.commit()
        s.refresh(track)
        track_id = track.id

    fake_stems = {
        "vocals": "/nonexistent/vocals.wav", "drums": "/nonexistent/drums.wav",
        "bass": "/nonexistent/bass.wav", "other": "/nonexistent/other.wav",
    }
    with patch.object(svc.StemSeparator, "separate", return_value=fake_stems):
        svc.StemSeparator().separate_and_store(track_id)

    with Session(test_engine) as s:
        track = s.get(AudioTrack, track_id)
        assert track.acoustic_metadata is None

"""
Tests fuer services/ai_audio_service.py

Getestet: StemSeparator.separate_and_store(), FrequencyAnalyzer.analyze_and_store()
Keine echten GPU-Ops, keine echten Modelle – alles gemockt.

WICHTIG: ai_audio_service.py importiert torch/torchaudio/librosa/scipy auf
Modul-Ebene. Diese Pakete sind in der reinen Python-3.11-Testumgebung NICHT
installiert. Daher werden sie hier per sys.modules BEVOR dem ersten Import
der Service-Datei als MagicMock-Stubs registriert.
"""

# ---------------------------------------------------------------------------
# GPU/ML-Paket-Stubs – muss VOR allen anderen Imports stehen!
# ---------------------------------------------------------------------------
import sys
from unittest.mock import MagicMock

_GPU_STUBS = [
    "torch", "torch.cuda", "torch.nn", "torch.utils", "torch.utils.data",
    "torch.device",
    "torchaudio", "torchaudio.functional",
    "librosa", "librosa.beat", "librosa.onset", "librosa.feature",
    # scipy und scipy.io NICHT mocken — sie sind installiert und werden von
    # test_new_features.py mit echten Daten benötigt. Das Mocken über setdefault()
    # würde den globalen sys.modules-State verschmutzen und nachfolgende Tests
    # mit echtem scipy brechen (Bug #42 Fix).
    "demucs", "demucs.pretrained", "demucs.apply",
]
for _mod_name in _GPU_STUBS:
    # Nur mocken wenn das Modul WIRKLICH nicht verfügbar ist —
    # kein Überschreiben bereits vorhandener (echter) Module
    if _mod_name not in sys.modules:
        try:
            __import__(_mod_name)
        except ImportError:
            sys.modules[_mod_name] = MagicMock()

# ---------------------------------------------------------------------------
# Normale Imports
# ---------------------------------------------------------------------------
import json
import pytest
from unittest.mock import patch, PropertyMock

from sqlalchemy.orm import Session

import database
from database import AudioTrack, Project, WaveformData


# ---------------------------------------------------------------------------
# StemSeparator.separate_and_store() Tests
# ---------------------------------------------------------------------------

class TestStemSeparatorAndStore:
    def _setup_track(self, test_engine, file_path="/fake/audio.mp3") -> int:
        with Session(test_engine) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            track = AudioTrack(project_id=proj.id, file_path=file_path, title="Test")
            s.add(track)
            s.commit()
            s.refresh(track)
            return track.id

    def test_separate_and_store_raises_for_missing_track(self, test_engine):
        """separate_and_store() loest ValueError aus wenn Track nicht existiert."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        with pytest.raises(ValueError, match="AudioTrack 9999 nicht gefunden"):
            svc.StemSeparator().separate_and_store(track_id=9999)

    def test_separate_and_store_saves_stem_paths(self, test_engine):
        """separate_and_store() speichert Stem-Pfade in der DB."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)
        fake_stems = {
            "vocals": "/stems/vocals.wav",
            "drums":  "/stems/drums.wav",
            "bass":   "/stems/bass.wav",
            "other":  "/stems/other.wav",
        }

        with patch.object(svc.StemSeparator, "separate", return_value=fake_stems):
            result = svc.StemSeparator().separate_and_store(track_id)

        assert result == fake_stems

        with Session(test_engine) as s:
            track = s.get(AudioTrack, track_id)
            assert track.stem_vocals_path == "/stems/vocals.wav"
            assert track.stem_drums_path  == "/stems/drums.wav"
            assert track.stem_bass_path   == "/stems/bass.wav"
            assert track.stem_other_path  == "/stems/other.wav"

    def test_separate_and_store_raises_if_track_gone_after_separation(self, test_engine):
        """separate_and_store() loest ValueError wenn Track nach Separation fehlt."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)
        fake_stems = {
            "vocals": "/stems/v.wav", "drums": "/stems/d.wav",
            "bass": "/stems/b.wav",   "other": "/stems/o.wav",
        }

        original_get = Session.get
        call_count = {"n": 0}

        def patched_get(self_s, model, pk):
            call_count["n"] += 1
            if call_count["n"] >= 2 and model is AudioTrack:
                return None
            return original_get(self_s, model, pk)

        with patch.object(svc.StemSeparator, "separate", return_value=fake_stems):
            with patch.object(Session, "get", patched_get):
                with pytest.raises(ValueError, match="nicht mehr gefunden"):
                    svc.StemSeparator().separate_and_store(track_id)

    def test_separate_and_store_wraps_separation_error(self, test_engine):
        """separate_and_store() wraps Separation-Fehler in RuntimeError."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)

        with patch.object(svc.StemSeparator, "separate",
                          side_effect=RuntimeError("CUDA OOM")):
            with pytest.raises(RuntimeError, match="Stem-Separation fehlgeschlagen"):
                svc.StemSeparator().separate_and_store(track_id)


# ---------------------------------------------------------------------------
# FrequencyAnalyzer.analyze_and_store() Tests
# ---------------------------------------------------------------------------

class TestFrequencyAnalyzerAndStore:
    def _setup_track(self, test_engine) -> int:
        with Session(test_engine) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            track = AudioTrack(project_id=proj.id, file_path="/fake/audio.wav", title="Test")
            s.add(track)
            s.commit()
            s.refresh(track)
            return track.id

    def _fake_analysis_result(self):
        return {
            "band_low":  [0.1, 0.2, 0.3],
            "band_mid":  [0.4, 0.5, 0.6],
            "band_high": [0.7, 0.8, 0.9],
            "num_samples": 3,
            "duration": 60.0,
            "bpm": 128.0,
            "beat_positions": [0.0, 0.47, 0.94],
        }

    def test_analyze_and_store_raises_for_missing_track(self, test_engine):
        """analyze_and_store() loest ValueError aus wenn Track nicht existiert."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        with pytest.raises(ValueError, match="AudioTrack 9999 nicht gefunden"):
            svc.FrequencyAnalyzer().analyze_and_store(track_id=9999)

    def test_analyze_and_store_creates_waveform_data(self, test_engine):
        """analyze_and_store() legt WaveformData in der DB an."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)
        fake_result = self._fake_analysis_result()

        with patch.object(svc.FrequencyAnalyzer, "analyze", return_value=fake_result):
            result = svc.FrequencyAnalyzer().analyze_and_store(track_id)

        assert result["bpm"] == 128.0
        assert result["duration"] == 60.0

        with Session(test_engine) as s:
            track = s.get(AudioTrack, track_id)
            assert track.bpm == 128.0
            assert track.duration == 60.0
            assert track.waveform_data is not None
            assert track.waveform_data.num_samples == 3
            assert json.loads(track.waveform_data.band_low) == [0.1, 0.2, 0.3]

    def test_analyze_and_store_updates_existing_waveform_data(self, test_engine):
        """analyze_and_store() aktualisiert vorhandene WaveformData (kein Duplikat)."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)

        # Erste Analyse
        with patch.object(svc.FrequencyAnalyzer, "analyze",
                          return_value=self._fake_analysis_result()):
            svc.FrequencyAnalyzer().analyze_and_store(track_id)

        # Zweite Analyse mit neuen Werten
        v2 = self._fake_analysis_result()
        v2["bpm"] = 140.0
        v2["num_samples"] = 5
        v2["band_low"]  = [0.9, 0.8, 0.7, 0.6, 0.5]
        v2["band_mid"]  = [0.1, 0.2, 0.3, 0.4, 0.5]
        v2["band_high"] = [0.5, 0.4, 0.3, 0.2, 0.1]

        with patch.object(svc.FrequencyAnalyzer, "analyze", return_value=v2):
            svc.FrequencyAnalyzer().analyze_and_store(track_id)

        # Nur eine WaveformData-Zeile darf existieren
        with Session(test_engine) as s:
            count = s.query(WaveformData).filter_by(audio_track_id=track_id).count()
            assert count == 1, f"Erwartet 1 WaveformData, gefunden: {count}"
            track = s.get(AudioTrack, track_id)
            # J-01 Fix: BPM wird NICHT ueberschrieben wenn bereits gesetzt (128.0 aus erster Analyse)
            # FrequencyAnalyzer soll den praeziseren BPM-Wert von BeatAnalysisService nicht ueberschreiben
            assert track.bpm == 128.0
            assert track.waveform_data.num_samples == 5

    def test_analyze_and_store_raises_if_track_gone_after_analysis(self, test_engine):
        """analyze_and_store() loest ValueError wenn Track nach Analyse fehlt."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)
        fake_result = self._fake_analysis_result()

        original_get = Session.get
        call_count = {"n": 0}

        def patched_get(self_s, model, pk):
            call_count["n"] += 1
            if call_count["n"] >= 2 and model is AudioTrack:
                return None
            return original_get(self_s, model, pk)

        with patch.object(svc.FrequencyAnalyzer, "analyze", return_value=fake_result):
            with patch.object(Session, "get", patched_get):
                with pytest.raises(ValueError, match="nicht mehr gefunden"):
                    svc.FrequencyAnalyzer().analyze_and_store(track_id)


# ---------------------------------------------------------------------------
# FrequencyAnalyzer Konstanten (ohne echte librosa-Ops)
# ---------------------------------------------------------------------------

class TestFrequencyAnalyzerConstants:
    def test_frequency_bands_are_correctly_defined(self):
        """Frequenzband-Grenzen entsprechen Rekordbox-Spec."""
        from services.ai_audio_service import FrequencyAnalyzer

        fa = FrequencyAnalyzer()
        assert fa.LOW_MAX == 250
        assert fa.MID_MAX == 4000
        assert fa.SR == 22050
        assert fa.HOP_LENGTH == 512

    def test_stem_separator_chunk_constants(self):
        """CHUNK_SECONDS und OVERLAP_SECONDS sind sinnvolle positive Werte."""
        import services.ai_audio_service as svc

        assert svc.CHUNK_SECONDS > 0
        assert svc.OVERLAP_SECONDS > 0
        assert svc.OVERLAP_SECONDS < svc.CHUNK_SECONDS

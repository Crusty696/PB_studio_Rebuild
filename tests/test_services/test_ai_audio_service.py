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
from pathlib import Path
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
        # Fix: nullpool_session Alias im Modul patchen (Import-Aliasing)
        from contextlib import contextmanager as _cm

        @_cm
        def _test_nullpool():
            with Session(test_engine) as s:
                yield s

        svc.nullpool_session = _test_nullpool

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

    def test_separate_and_store_passes_should_stop_to_separator(self, test_engine):
        """B-327: UI-Cancel muss bis in den Demucs-Chunk-Loop gelangen."""
        import services.ai_audio_service as svc
        svc.engine = test_engine
        from contextlib import contextmanager as _cm

        @_cm
        def _test_nullpool():
            with Session(test_engine) as s:
                yield s

        svc.nullpool_session = _test_nullpool
        track_id = self._setup_track(test_engine)
        cancel_cb = lambda: False
        seen = {}

        def fake_separate(self, file_path, progress_cb=None, should_stop=None):
            seen["file_path"] = file_path
            seen["should_stop"] = should_stop
            return {
                "vocals": "/stems/vocals.wav",
                "drums": "/stems/drums.wav",
                "bass": "/stems/bass.wav",
                "other": "/stems/other.wav",
            }

        with patch.object(svc.StemSeparator, "separate", fake_separate):
            svc.StemSeparator().separate_and_store(track_id, should_stop=cancel_cb)

        assert seen["should_stop"] is cancel_cb

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

    def test_b565_separate_to_writes_directly_to_short_output_dir(
        self, monkeypatch, tmp_path
    ):
        """B-565: Pipeline darf nicht erst ins dateiname-basierte Alt-Layout schreiben."""
        import services.ai_audio_service as svc

        seen = {}

        def fake_separate(
            self,
            file_path,
            model="htdemucs_ft",
            progress_cb=None,
            should_stop=None,
            output_dir=None,
        ):
            seen["file_path"] = file_path
            seen["output_dir"] = output_dir
            return {}

        monkeypatch.setattr(svc.StemSeparator, "separate", fake_separate)
        out_dir = tmp_path / "storage" / "stems" / "42"

        result = svc.StemSeparator().separate_to(
            file_path="Z" * 180 + ".mp3",
            out_dir=str(out_dir),
        )

        assert result == {}
        assert Path(seen["output_dir"]) == out_dir


# ---------------------------------------------------------------------------
# B-356: StemSeparator.separate() darf nicht-OOM RuntimeErrors nicht als
# CUDAOutOfMemoryError maskieren.
# ---------------------------------------------------------------------------

# Echtes torch wird benoetigt damit isinstance() / hasattr() korrekt
# auswerten. torch 1.12 hat KEIN torch.cuda.OutOfMemoryError -> Erkennung
# faellt auf den String-Match "out of memory" zurueck.
_real_torch = pytest.importorskip("torch")


class TestSeparateRuntimeErrorNotMaskedAsOOM:
    """B-356 Regressionstest: Shape-/Model-RuntimeErrors bleiben erhalten."""

    def _run_separate_with_apply_error(self, exc, monkeypatch, tmp_path):
        import services.ai_audio_service as svc

        sep = svc.StemSeparator()

        # CPU-Pfad erzwingen (kein GPU-Lauf, kein VRAM-Verbrauch).
        monkeypatch.setattr(_real_torch.cuda, "is_available", lambda: False)

        # Demucs-Modell + apply_model stubben.
        fake_model = MagicMock()
        fake_model.samplerate = 44100
        fake_model.sources = ["drums", "bass", "other", "vocals"]
        fake_model.to.return_value = fake_model
        fake_model.eval.return_value = None

        import sys as _sys
        demucs_pretrained = MagicMock()
        demucs_pretrained.get_model.return_value = fake_model
        demucs_apply = MagicMock()
        demucs_apply.apply_model = MagicMock()
        monkeypatch.setitem(_sys.modules, "demucs.pretrained", demucs_pretrained)
        monkeypatch.setitem(_sys.modules, "demucs.apply", demucs_apply)

        # ModelManager.unload() darf no-op sein.
        import services.model_manager as mm
        monkeypatch.setattr(mm.ModelManager, "unload", lambda self: None)

        # torchaudio.load liefert ein kleines Stereo-Signal.
        import torchaudio as _ta
        waveform = _real_torch.zeros(2, 44100)
        monkeypatch.setattr(_ta, "load", lambda *_a, **_k: (waveform, 44100))

        # Der eigentliche Knackpunkt: apply_model (ueber den Locked-Wrapper)
        # wirft die uebergebene Exception.
        def _raise(*_a, **_k):
            raise exc

        monkeypatch.setattr(
            svc.StemSeparator, "_apply_demucs_model_locked",
            staticmethod(lambda *_a, **_k: _raise()),
        )

        return sep.separate(str(tmp_path / "fake.wav"))

    def test_non_oom_runtimeerror_propagates(self, monkeypatch, tmp_path):
        """Ein Shape-RuntimeError wird NICHT als CUDAOutOfMemoryError gemeldet."""
        from services.errors import CUDAOutOfMemoryError

        original = RuntimeError("shape mismatch: expected 2 channels, got 1")
        with pytest.raises(RuntimeError) as ei:
            self._run_separate_with_apply_error(original, monkeypatch, tmp_path)

        assert not isinstance(ei.value, CUDAOutOfMemoryError), (
            "Nicht-OOM RuntimeError wurde faelschlich als OOM maskiert"
        )
        assert "shape mismatch" in str(ei.value)

    def test_oom_runtimeerror_triggers_oom_path(self, monkeypatch, tmp_path):
        """Echte 'out of memory'-RuntimeError landen im OOM-Pfad (Halbierung
        scheitert hier ebenfalls -> CUDAOutOfMemoryError)."""
        from services.errors import CUDAOutOfMemoryError

        oom = RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        with pytest.raises(CUDAOutOfMemoryError):
            self._run_separate_with_apply_error(oom, monkeypatch, tmp_path)


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
        # B-501: analyze() liefert keine "bpm"/"beat_positions"-Keys mehr —
        # BPM/Beatgrid kommt ausschliesslich von BeatAnalysisService.
        return {
            "band_low":  [0.1, 0.2, 0.3],
            "band_mid":  [0.4, 0.5, 0.6],
            "band_high": [0.7, 0.8, 0.9],
            "num_samples": 3,
            "duration": 60.0,
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

        # B-501: FrequencyAnalyzer schreibt kein BPM mehr — Track ohne BPM
        # bleibt ohne BPM, "bpm"-Key fehlt im Ergebnis.
        assert "bpm" not in result
        assert result["duration"] == 60.0

        with Session(test_engine) as s:
            track = s.get(AudioTrack, track_id)
            assert track.bpm is None
            assert track.duration == 60.0
            assert track.waveform_data is not None
            assert track.waveform_data.num_samples == 3
            # H7-FIX: Column(JSON) deserialisiert automatisch — kein json.loads() noetig.
            band_low = track.waveform_data.band_low
            if isinstance(band_low, str):
                band_low = json.loads(band_low)
            assert band_low == [0.1, 0.2, 0.3]

    def test_analyze_and_store_updates_existing_waveform_data(self, test_engine):
        """analyze_and_store() aktualisiert vorhandene WaveformData (kein Duplikat)."""
        import services.ai_audio_service as svc
        svc.engine = test_engine

        track_id = self._setup_track(test_engine)

        # B-501: BPM in DB simuliert BeatAnalysisService-Schreibvorgang
        with Session(test_engine) as s:
            track = s.get(AudioTrack, track_id)
            track.bpm = 128.0
            s.commit()

        # Erste Analyse
        with patch.object(svc.FrequencyAnalyzer, "analyze",
                          return_value=self._fake_analysis_result()):
            r1 = svc.FrequencyAnalyzer().analyze_and_store(track_id)

        # B-501: vorhandener DB-BPM wird nur durchgereicht (UI-Anzeige)
        assert r1.get("bpm") == 128.0

        # Zweite Analyse mit neuen Werten
        v2 = self._fake_analysis_result()
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
            # B-501 (ersetzt J-01): FrequencyAnalyzer fasst track.bpm gar nicht
            # mehr an — der BeatAnalysisService-Wert bleibt unveraendert.
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

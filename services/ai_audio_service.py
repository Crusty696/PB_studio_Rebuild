"""AI Audio Service: Demucs Stem Separation + Auto-Ducking + Rekordbox Frequency Analysis."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import librosa
from scipy.io import wavfile
from sqlalchemy.orm import Session

from database import engine, AudioTrack, Beatgrid, WaveformData

STEMS_DIR = Path("storage/stems")


class StemSeparator:
    """Trennt Audio via Demucs in Vocals, Drums, Bass, Other."""

    def separate(self, file_path: str, model: str = "htdemucs",
                 progress_cb=None) -> dict[str, str]:
        """Fuehrt Demucs Stem Separation aus.

        Returns: dict mit Keys 'vocals', 'drums', 'bass', 'other' -> Pfade.
        """
        STEMS_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(file_path)

        # Demucs als CLI-Tool ausfuehren
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems=vocals",  # Schnell: nur vocals + accompaniment
            "-n", model,
            "-o", str(STEMS_DIR),
            str(src),
        ]

        # Fuer volle 4-Stem-Separation (--mp3 vermeidet torchcodec DLL-Problem):
        cmd_full = [
            sys.executable, "-m", "demucs",
            "--mp3",
            "-n", model,
            "-o", str(STEMS_DIR),
            str(src),
        ]

        if progress_cb:
            progress_cb(1, 4, "Starte Demucs KI-Analyse...")

        result = subprocess.run(
            cmd_full,
            capture_output=True, text=True, timeout=1800,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Demucs fehlgeschlagen:\n{result.stderr[-1000:]}")

        if progress_cb:
            progress_cb(3, 4, "Stems extrahiert, sammle Pfade...")

        # Demucs Output-Struktur: stems_dir/model/track_name/vocals.mp3 (oder .wav)
        stem_dir = STEMS_DIR / model / src.stem
        stems = {}
        for stem_name in ["vocals", "drums", "bass", "other"]:
            # Suche mp3 oder wav
            for ext in [".mp3", ".wav"]:
                stem_path = stem_dir / f"{stem_name}{ext}"
                if stem_path.exists():
                    stems[stem_name] = str(stem_path.resolve())
                    break
            else:
                stems[stem_name] = None

        if progress_cb:
            progress_cb(4, 4, "Stem Separation abgeschlossen")

        return stems

    def separate_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Separiert Stems und speichert Pfade in der DB."""
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        stems = self.separate(file_path, progress_cb=progress_cb)

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            track.stem_vocals_path = stems.get("vocals")
            track.stem_drums_path = stems.get("drums")
            track.stem_bass_path = stems.get("bass")
            track.stem_other_path = stems.get("other")
            session.commit()

        return stems


class AutoDucker:
    """Senkt Musik automatisch ab wenn Sprache erkannt wird."""

    def __init__(self, duck_db: float = -12.0, attack_ms: float = 200.0,
                 release_ms: float = 500.0, threshold_rms: float = 0.02):
        self.duck_db = duck_db
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.threshold_rms = threshold_rms

    def create_ducked_audio(self, music_path: str, voice_path: str,
                            output_path: str, progress_cb=None) -> str:
        """Erstellt eine geduckte Version: Musik wird leiser wenn Voice aktiv.

        Versucht FFmpeg, faellt auf Scipy zurueck bei Fehler.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(1, 3, "Berechne Auto-Ducking...")

        # Erst: Konvertiere Inputs zu WAV falls noetig
        tmp_music = out.parent / "_tmp_music.wav"
        tmp_voice = out.parent / "_tmp_voice.wav"
        try:
            for src, dst in [(music_path, str(tmp_music)), (voice_path, str(tmp_voice))]:
                cmd = ["ffmpeg", "-y", "-i", src, "-ar", "44100", "-ac", "1",
                       "-c:a", "pcm_s16le", str(dst)]
                subprocess.run(
                    cmd, capture_output=True, timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )

            if progress_cb:
                progress_cb(2, 3, "Scipy Ducking laeuft...")

            result = self.create_ducked_audio_scipy(
                str(tmp_music), str(tmp_voice), output_path, progress_cb=None
            )

            if progress_cb:
                progress_cb(3, 3, "Auto-Ducking fertig")

            return result
        finally:
            tmp_music.unlink(missing_ok=True)
            tmp_voice.unlink(missing_ok=True)

    def create_ducked_audio_scipy(self, music_path: str, voice_path: str,
                                   output_path: str, progress_cb=None) -> str:
        """Fallback: Scipy-basiertes Ducking wenn FFmpeg sidechaincompress fehlt."""
        if progress_cb:
            progress_cb(1, 4, "Lade Audio-Dateien...")

        # WAV einlesen (fuer Stems die bereits WAV sind)
        music_sr, music_data = wavfile.read(music_path)
        voice_sr, voice_data = wavfile.read(voice_path)

        # Zu float32 normalisieren
        if music_data.dtype == np.int16:
            music_data = music_data.astype(np.float32) / 32768.0
        if voice_data.dtype == np.int16:
            voice_data = voice_data.astype(np.float32) / 32768.0

        # Mono sicherstellen
        if music_data.ndim > 1:
            music_data = music_data.mean(axis=1)
        if voice_data.ndim > 1:
            voice_data = voice_data.mean(axis=1)

        if progress_cb:
            progress_cb(2, 4, "Berechne Voice-Envelope...")

        # Laengen anpassen
        min_len = min(len(music_data), len(voice_data))
        music_data = music_data[:min_len]
        voice_data = voice_data[:min_len]

        # Voice RMS Envelope berechnen (Fenster: 50ms)
        window_size = int(music_sr * 0.05)
        envelope = np.zeros_like(voice_data)
        for i in range(0, len(voice_data), window_size):
            chunk = voice_data[i:i + window_size]
            rms = np.sqrt(np.mean(chunk ** 2))
            envelope[i:i + window_size] = rms

        if progress_cb:
            progress_cb(3, 4, "Wende Ducking an...")

        # Ducking: Wo Voice laut ist, Musik leiser
        duck_factor = 10 ** (self.duck_db / 20.0)  # z.B. -12dB -> 0.25
        gain = np.where(envelope > self.threshold_rms, duck_factor, 1.0)

        # Smooth (Attack/Release)
        from scipy.ndimage import uniform_filter1d
        smooth_window = int(music_sr * max(self.attack_ms, self.release_ms) / 1000.0)
        gain = uniform_filter1d(gain, size=max(1, smooth_window))

        # Anwenden
        ducked_music = music_data * gain
        mixed = ducked_music + voice_data

        # Clipping vermeiden
        peak = np.abs(mixed).max()
        if peak > 0.95:
            mixed = mixed * (0.95 / peak)

        # Speichern
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        wavfile.write(str(out), music_sr, (mixed * 32767).astype(np.int16))

        if progress_cb:
            progress_cb(4, 4, "Ducking abgeschlossen")

        return str(out.resolve())


class FrequencyAnalyzer:
    """Rekordbox-Style Frequenzband-Analyse: Zerlegt Audio in Low/Mid/High Bänder.

    Frequenzbereiche (wie Rekordbox/CDJ):
        Low  (Bass/Kicks):   20 - 250 Hz   → Blau
        Mid  (Vocals/Snare): 250 - 4000 Hz → Rosa/Rot
        High (HiHats/Air):   4000 - 20000 Hz → Weiß/Gelb
    """

    # Grenzfrequenzen in Hz
    LOW_MAX = 250
    MID_MAX = 4000
    SR = 22050
    HOP_LENGTH = 512      # ~23ms pro Frame → hochauflösend
    N_FFT = 2048          # Frequenzauflösung: ~10.7 Hz pro Bin

    def analyze(self, file_path: str, progress_cb=None) -> dict:
        """Berechnet Frequenzband-Amplituden + präzises Beatgrid.

        Returns dict mit:
            band_low:  list[float]   Normalisierte Bass-Amplituden [0..1]
            band_mid:  list[float]   Normalisierte Mitten-Amplituden [0..1]
            band_high: list[float]   Normalisierte Höhen-Amplituden [0..1]
            num_samples: int         Anzahl der Zeitschritte
            duration: float          Track-Dauer in Sekunden
            bpm: float               Erkannte BPM
            beat_positions: list[float]  Beat-Zeitstempel in Sekunden
        """
        if progress_cb:
            progress_cb(1, 5, "Lade Audio...")

        y, sr = librosa.load(file_path, sr=self.SR, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        if progress_cb:
            progress_cb(2, 5, "STFT Frequenzanalyse...")

        # Short-Time Fourier Transform → Magnitude-Spektrogramm
        S = np.abs(librosa.stft(y, n_fft=self.N_FFT, hop_length=self.HOP_LENGTH))

        # Frequenz-Bins zu Hz mappen
        freqs = librosa.fft_frequencies(sr=sr, n_fft=self.N_FFT)

        # Frequenzband-Masken
        low_mask = freqs <= self.LOW_MAX
        mid_mask = (freqs > self.LOW_MAX) & (freqs <= self.MID_MAX)
        high_mask = freqs > self.MID_MAX

        # Mittlere Energie pro Band über alle Frequenz-Bins im Band
        band_low = np.mean(S[low_mask, :], axis=0)
        band_mid = np.mean(S[mid_mask, :], axis=0)
        band_high = np.mean(S[high_mask, :], axis=0)

        # Normalisierung: Jedes Band auf [0..1] skalieren (Peak = 1.0)
        def _normalize(arr):
            peak = arr.max()
            if peak > 0:
                return arr / peak
            return arr

        band_low = _normalize(band_low)
        band_mid = _normalize(band_mid)
        band_high = _normalize(band_high)

        if progress_cb:
            progress_cb(3, 5, "Beatgrid-Erkennung...")

        # Präzises Beatgrid via librosa
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=self.HOP_LENGTH)
        if isinstance(tempo, np.ndarray):
            bpm = float(tempo.flat[0])
        else:
            bpm = float(tempo)
        bpm = round(bpm, 1)

        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=self.HOP_LENGTH)
        beat_positions = [round(float(t), 4) for t in beat_times]

        if progress_cb:
            progress_cb(4, 5, "Daten komprimieren...")

        # Downsampling für Speichereffizienz: max ~2000 Samples für DB
        num_samples = len(band_low)
        max_db_samples = 4000
        if num_samples > max_db_samples:
            factor = num_samples / max_db_samples
            indices = np.round(np.arange(0, num_samples, factor)).astype(int)
            indices = indices[indices < num_samples]
            band_low_store = band_low[indices]
            band_mid_store = band_mid[indices]
            band_high_store = band_high[indices]
            store_samples = len(indices)
        else:
            band_low_store = band_low
            band_mid_store = band_mid
            band_high_store = band_high
            store_samples = num_samples

        # Auf 4 Dezimalstellen runden für kompakte JSON-Speicherung
        result = {
            "band_low": [round(float(v), 4) for v in band_low_store],
            "band_mid": [round(float(v), 4) for v in band_mid_store],
            "band_high": [round(float(v), 4) for v in band_high_store],
            "num_samples": store_samples,
            "duration": round(duration, 3),
            "bpm": bpm,
            "beat_positions": beat_positions,
        }

        if progress_cb:
            progress_cb(5, 5, "Frequenzanalyse abgeschlossen")

        return result

    def analyze_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Analysiert einen AudioTrack und speichert Waveform + Beatgrid in der DB."""
        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        result = self.analyze(file_path, progress_cb=progress_cb)

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)

            # BPM + Duration updaten
            track.bpm = result["bpm"]
            track.duration = result["duration"]

            # Beatgrid speichern/aktualisieren
            if track.beatgrid:
                track.beatgrid.bpm = result["bpm"]
                track.beatgrid.beat_positions = json.dumps(result["beat_positions"])
                track.beatgrid.offset = result["beat_positions"][0] if result["beat_positions"] else 0.0
            else:
                bg = Beatgrid(
                    audio_track_id=track_id,
                    bpm=result["bpm"],
                    offset=result["beat_positions"][0] if result["beat_positions"] else 0.0,
                    beat_positions=json.dumps(result["beat_positions"]),
                )
                session.add(bg)

            # WaveformData speichern/aktualisieren
            if track.waveform_data:
                track.waveform_data.num_samples = result["num_samples"]
                track.waveform_data.duration = result["duration"]
                track.waveform_data.band_low = json.dumps(result["band_low"])
                track.waveform_data.band_mid = json.dumps(result["band_mid"])
                track.waveform_data.band_high = json.dumps(result["band_high"])
            else:
                wd = WaveformData(
                    audio_track_id=track_id,
                    num_samples=result["num_samples"],
                    duration=result["duration"],
                    band_low=json.dumps(result["band_low"]),
                    band_mid=json.dumps(result["band_mid"]),
                    band_high=json.dumps(result["band_high"]),
                )
                session.add(wd)

            session.commit()

        return result

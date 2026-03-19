"""Erstellt eine synthetische Test-Audio-Datei (120 BPM) und testet die Analyse."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.io import wavfile

# Test-Audio erstellen
sr = 22050
duration = 10.0
t = np.linspace(0, duration, int(sr * duration), endpoint=False)
signal = np.zeros_like(t)
for bt in np.arange(0, duration, 0.5):  # 120 BPM
    idx = int(bt * sr)
    n = min(2000, len(t) - idx)
    decay = np.exp(-np.linspace(0, 10, n))
    kick = np.sin(2 * np.pi * 60 * np.linspace(0, n / sr, n)) * decay
    signal[idx:idx + n] += kick
signal = (signal / np.max(np.abs(signal)) * 0.8 * 32767).astype(np.int16)

os.makedirs("storage/test", exist_ok=True)
wav_path = os.path.join("storage", "test", "test_beat_120bpm.wav")
wavfile.write(wav_path, sr, signal)
print(f"[OK] Test-Audio erstellt: {wav_path}")

# In DB importieren und analysieren
from database import init_db, engine, AudioTrack
from sqlalchemy.orm import Session
from services.ingest_service import ingest_audio
from services.audio_service import AudioAnalyzer

init_db()
abs_path = os.path.abspath(wav_path)
track = ingest_audio(abs_path)
if track is None:
    # Bereits importiert, ID holen
    with Session(engine) as s:
        track = s.query(AudioTrack).filter_by(file_path=abs_path).first()
    print(f"[Info] Track bereits in DB: ID={track.id}")
else:
    print(f"[OK] Track importiert: ID={track.id}")

# Analyse testen
analyzer = AudioAnalyzer()
try:
    result = analyzer.analyze_and_store(track.id)
    print(f"[OK] Analyse erfolgreich!")
    print(f"     BPM:    {result['bpm']}")
    print(f"     Dauer:  {result['duration']}s")
    print(f"     Energie: {len(result['energy_curve'])} Punkte")

    # Verifiziere DB
    with Session(engine) as s:
        db_track = s.get(AudioTrack, track.id)
        print(f"[OK] DB-Check: bpm={db_track.bpm}, duration={db_track.duration}")
        assert db_track.bpm is not None, "BPM ist None in DB!"
        assert db_track.bpm > 0, f"BPM ungueltig: {db_track.bpm}"
    print("[OK] ALLE TESTS BESTANDEN")
except Exception as e:
    print(f"[FEHLER] Analyse fehlgeschlagen: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

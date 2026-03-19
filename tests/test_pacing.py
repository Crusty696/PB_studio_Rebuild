"""Test für Pacing-Service."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db
from services.pacing_service import PacingSettings, calculate_cut_points

init_db()

# Test 1: Mit Audio-ID 2 (117.5 BPM Track)
settings = PacingSettings(tempo=50, energy=60, cut_density=50)
cuts = calculate_cut_points(audio_id=2, video_id=None, settings=settings, total_duration=10.0)
print(f"Test 1 - Mit BPM aus DB: {len(cuts)} Cuts")
for c in cuts[:5]:
    print(f"  t={c.time}s src={c.source} str={c.strength}")

# Test 2: Ohne Audio (Fallback)
settings2 = PacingSettings(tempo=75, energy=80, cut_density=30)
cuts2 = calculate_cut_points(audio_id=None, video_id=None, settings=settings2)
print(f"Test 2 - Fallback: {len(cuts2)} Cuts")

# Test 3: Hohe Dichte
settings3 = PacingSettings(tempo=90, energy=90, cut_density=90)
cuts3 = calculate_cut_points(audio_id=2, video_id=None, settings=settings3)
print(f"Test 3 - High energy: {len(cuts3)} Cuts")

print("PACING SERVICE OK")

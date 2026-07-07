"""Pacing-Qualitaets-Report: wie gut passt der Schnitt zur Musik?

Misst gegen die Projekt-DB (kein Video-Decode noetig — die Timeline IST der
Schnitt):
  1. Beat-Sync: Anteil der Cuts auf Beat / Downbeat (Toleranzfenster)
  2. Section-Pacing: mittlere Segment-Laenge pro Section-Typ
     (Erwartung: DROP deutlich schneller geschnitten als BREAKDOWN/INTRO)
  3. Energie-Korrelation: Segment-Laenge vs. Energie am Segment-Start
     (hohe Energie -> kurze Segmente erwartet, negative Korrelation gut)
  4. Mood-Passung: gewaehlter Clip-Mood vs. Section (SECTION_MOOD_AFFINITY)
  5. Section-Grenzen: liegt an jeder Struktur-Grenze ein Cut?
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(r"C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild")
sys.path.insert(0, str(REPO))

from services.pacing_edit_helpers import SECTION_MOOD_AFFINITY  # noqa: E402

BEAT_TOL = 0.070   # 70 ms
DOWNBEAT_TOL = 0.070


def main(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    segs = c.execute(
        "SELECT media_id, start_time, end_time FROM timeline_entries "
        "WHERE track='video' ORDER BY start_time").fetchall()
    if not segs:
        print("Keine Video-Segmente."); return
    cuts = [s[1] for s in segs][1:]  # erster Start (0.0) ist kein Cut

    bg = c.execute(
        "SELECT bpm, beat_positions, downbeat_positions, energy_per_beat, "
        "stem_weighted_energy FROM beatgrids LIMIT 1").fetchone()
    bpm = bg[0]
    beats = np.array(json.loads(bg[1]) or [])
    downbeats = np.array(json.loads(bg[2]) or []) if bg[2] else np.array([])
    energy = json.loads(bg[4] or bg[3] or "[]")

    sections = c.execute(
        "SELECT start_time, end_time, label, energy FROM structure_segments "
        "ORDER BY start_time").fetchall()

    def near(arr, t, tol):
        if arr.size == 0:
            return False
        return bool(np.min(np.abs(arr - t)) <= tol)

    # 1. Beat-Sync
    on_beat = sum(near(beats, t, BEAT_TOL) for t in cuts)
    on_down = sum(near(downbeats, t, DOWNBEAT_TOL) for t in cuts)
    print(f"== 1. Beat-Sync ==  (BPM {bpm:.1f}, {len(cuts)} Cuts)")
    print(f"  Cuts auf Beat (+-70ms):     {on_beat}/{len(cuts)} = {100*on_beat/len(cuts):.0f}%")
    print(f"  Cuts auf Downbeat (+-70ms): {on_down}/{len(cuts)} = {100*on_down/len(cuts):.0f}%")

    # 2. Section-Pacing
    def section_at(t):
        for s0, s1, label, en in sections:
            if s0 <= t < s1:
                return label, en
        return "?", 0.5

    lens = defaultdict(list)
    for _mid, s0, s1 in segs:
        label, _ = section_at(s0 + 0.01)
        lens[label].append(s1 - s0)
    print("\n== 2. Segment-Laenge pro Section ==")
    order = sorted(lens, key=lambda k: -np.mean(lens[k]))
    for label in order:
        v = lens[label]
        print(f"  {label:12s} n={len(v):3d}  mean={np.mean(v):5.2f}s  "
              f"min={min(v):4.2f}  max={max(v):5.2f}")

    # 3. Energie-Korrelation
    if energy and beats.size:
        seg_en, seg_len = [], []
        for _mid, s0, s1 in segs:
            bi = int(np.searchsorted(beats, s0))
            bi = min(bi, len(energy) - 1)
            seg_en.append(energy[bi]); seg_len.append(s1 - s0)
        r = float(np.corrcoef(seg_en, seg_len)[0, 1])
        print(f"\n== 3. Energie vs. Segment-Laenge ==")
        print(f"  Korrelation r = {r:+.2f}  "
              f"({'gut: hohe Energie -> kurze Clips' if r < -0.2 else 'schwach/kein Zusammenhang' if r < 0.1 else 'VERKEHRT: hohe Energie -> lange Clips'})")

    # 4. Mood-Passung
    moods = {}
    for vc_id, mood in c.execute(
            "SELECT video_clip_id, ai_mood FROM scenes WHERE ai_mood IS NOT NULL"):
        moods.setdefault(vc_id, mood)
    scored, per_sec = [], defaultdict(list)
    for mid, s0, _s1 in segs:
        label, _ = section_at(s0 + 0.01)
        mood = moods.get(mid)
        aff = SECTION_MOOD_AFFINITY.get(label, {})
        if mood and aff:
            v = aff.get(mood, 0.5)
            scored.append(v); per_sec[label].append(v)
    if scored:
        print(f"\n== 4. Mood-Passung (Affinitaet 0..1) ==")
        print(f"  Gesamt: mean={np.mean(scored):.2f} ueber {len(scored)} Segmente")
        for label, v in sorted(per_sec.items()):
            print(f"  {label:12s} mean={np.mean(v):.2f} (n={len(v)})")

    # 5. Cuts an Section-Grenzen
    bounds = [s0 for s0, _s1, _l, _e in sections[1:]]
    cut_arr = np.array(cuts)
    hit = sum(near(cut_arr, b, 0.15) for b in bounds)
    print(f"\n== 5. Section-Grenzen mit Cut (+-150ms): {hit}/{len(bounds)} ==")

    # Kontext
    print(f"\nSegmente gesamt: {len(segs)}, Timeline-Ende: {segs[-1][2]:.1f}s")
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         str(REPO / "outputs/6262626/pb_studio.db"))

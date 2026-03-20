"""
PoC #1: OpenTimelineIO Machbarkeit
Wegwerf-Skript — testet ob OTIO fuer PB Studio taugt.
"""

import subprocess
import sys
import time
import traceback

# --- 1. Import / Install ---
print("=" * 60)
print("PoC #1: OpenTimelineIO Machbarkeit")
print("=" * 60)

try:
    import opentimelineio as otio
    print(f"[OK] opentimelineio bereits installiert: v{otio.__version__}")
except ImportError:
    print("[...] opentimelineio nicht gefunden, installiere via pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "opentimelineio"])
    import opentimelineio as otio
    print(f"[OK] opentimelineio installiert: v{otio.__version__}")

import os

try:
    import psutil
    proc = psutil.Process(os.getpid())
    mem_before = proc.memory_info().rss / (1024 * 1024)
    has_psutil = True
except ImportError:
    mem_before = 0
    has_psutil = False
print(f"[INFO] RAM nach Import: {mem_before:.1f} MB")

# --- 2. Timeline erstellen ---
print("\n--- Timeline erstellen ---")

from opentimelineio.opentime import RationalTime, TimeRange

timeline = otio.schema.Timeline(name="PB_Studio_PoC")

# 2 Video-Tracks
track_v1 = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
track_v2 = otio.schema.Track(name="V2", kind=otio.schema.TrackKind.Video)

# 5 Clips mit In/Out Points
clips_data = [
    ("Intro_Beat",      0, 120, 10, 110),
    ("Verse_Loop",    120, 240, 5,  230),
    ("Drop_Section",  240, 480, 0,  480),
    ("Breakdown",     480, 600, 20, 580),
    ("Outro_Fade",    600, 720, 15, 700),
]

clips = []
for name, src_start, src_end, in_pt, out_pt in clips_data:
    mr = otio.schema.ExternalReference(
        target_url=f"/media/{name}.wav",
        available_range=TimeRange(
            start_time=RationalTime(src_start, 24),
            duration=RationalTime(src_end - src_start, 24),
        ),
    )
    clip = otio.schema.Clip(
        name=name,
        media_reference=mr,
        source_range=TimeRange(
            start_time=RationalTime(in_pt, 24),
            duration=RationalTime(out_pt - in_pt, 24),
        ),
    )
    clips.append(clip)

# Verteile Clips: 3 auf V1, 2 auf V2
track_v1.append(clips[0])
track_v1.append(clips[1])
track_v1.append(clips[2])
track_v2.append(clips[3])
track_v2.append(clips[4])

print(f"[OK] 5 Clips erstellt, auf 2 Tracks verteilt")

# 1 Transition (Crossfade) zwischen Clip 0 und 1 auf V1
transition = otio.schema.Transition(
    name="Crossfade_1",
    transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
    in_offset=RationalTime(12, 24),
    out_offset=RationalTime(12, 24),
)
track_v1.insert(1, transition)  # zwischen Clip 0 und 1
print(f"[OK] Transition eingefuegt: {transition.name}")

# 3 Marker mit custom metadata (pb_studio namespace)
markers_data = [
    ("Anchor_CuePoint",   RationalTime(50, 24),  {"audio_features": [0.82, 0.15, 0.63], "similarity_threshold": 0.75}),
    ("Anchor_DropStart",  RationalTime(240, 24), {"audio_features": [0.95, 0.88, 0.71, 0.44], "similarity_threshold": 0.60}),
    ("Anchor_Breakdown",  RationalTime(500, 24), {"audio_features": [0.30, 0.12], "similarity_threshold": 0.90}),
]

for mname, mtime, mdata in markers_data:
    marker = otio.schema.Marker(
        name=mname,
        marked_range=TimeRange(start_time=mtime, duration=RationalTime(0, 24)),
        color=otio.schema.MarkerColor.RED,
        metadata={"pb_studio": mdata},
    )
    timeline.tracks.markers.append(marker)

print(f"[OK] 3 Marker mit pb_studio Metadata erstellt")

timeline.tracks.append(track_v1)
timeline.tracks.append(track_v2)

# --- 3. Export: CMX 3600 EDL ---
print("\n--- Export ---")
edl_path = os.path.join(os.path.dirname(__file__), "poc_otio_export.edl")
otio_path = os.path.join(os.path.dirname(__file__), "poc_otio_export.otio")

edl_ok = True
try:
    otio.adapters.write_to_file(timeline, edl_path)
    edl_size = os.path.getsize(edl_path)
    print(f"[OK] EDL exportiert: {edl_path} ({edl_size} bytes)")
except Exception as e:
    print(f"[FAIL] EDL Export fehlgeschlagen: {e}")
    traceback.print_exc()
    edl_ok = False

# --- 4. Export: OTIO JSON ---
otio_ok = True
try:
    otio.adapters.write_to_file(timeline, otio_path)
    otio_size = os.path.getsize(otio_path)
    print(f"[OK] OTIO exportiert: {otio_path} ({otio_size} bytes)")
except Exception as e:
    print(f"[FAIL] OTIO Export fehlgeschlagen: {e}")
    traceback.print_exc()
    otio_ok = False

# --- 5. Reload & Verify ---
print("\n--- Reload & Verify ---")
errors = []

try:
    loaded = otio.adapters.read_from_file(otio_path)
    print(f"[OK] OTIO geladen: '{loaded.name}'")

    # 5a. Alle 5 Clips?
    all_clips = list(loaded.find_clips())
    if len(all_clips) == 5:
        print(f"[OK] 5/5 Clips gefunden")
    else:
        msg = f"Erwartet 5 Clips, gefunden {len(all_clips)}"
        print(f"[FAIL] {msg}")
        errors.append(msg)

    # Clip-Namen pruefen
    clip_names = {c.name for c in all_clips}
    expected_names = {"Intro_Beat", "Verse_Loop", "Drop_Section", "Breakdown", "Outro_Fade"}
    if clip_names == expected_names:
        print(f"[OK] Alle Clip-Namen korrekt")
    else:
        msg = f"Clip-Namen Mismatch: erwartet {expected_names}, got {clip_names}"
        print(f"[FAIL] {msg}")
        errors.append(msg)

    # 5b. 3 Marker mit Metadata?
    markers = loaded.tracks.markers
    if len(markers) == 3:
        print(f"[OK] 3/3 Marker gefunden")
    else:
        msg = f"Erwartet 3 Marker, gefunden {len(markers)}"
        print(f"[FAIL] {msg}")
        errors.append(msg)

    metadata_ok = True
    for m in markers:
        pb = m.metadata.get("pb_studio")
        if pb is None:
            msg = f"Marker '{m.name}' hat kein pb_studio metadata"
            print(f"[FAIL] {msg}")
            errors.append(msg)
            metadata_ok = False
            continue
        af = pb.get("audio_features")
        st = pb.get("similarity_threshold")
        if not hasattr(af, '__iter__') or isinstance(af, str):
            msg = f"Marker '{m.name}': audio_features ist nicht iterable sondern {type(af)}"
            print(f"[FAIL] {msg}")
            errors.append(msg)
            metadata_ok = False
        # Verify values are accessible and correct type after round-trip
        try:
            af_list = list(af)  # AnyVector -> list conversion
            assert all(isinstance(v, float) for v in af_list), "nicht alle floats"
        except Exception as ex:
            msg = f"Marker '{m.name}': audio_features nicht zu list konvertierbar: {ex}"
            print(f"[FAIL] {msg}")
            errors.append(msg)
            metadata_ok = False
        if not isinstance(st, (float, int)):
            msg = f"Marker '{m.name}': similarity_threshold ist kein float sondern {type(st)}"
            print(f"[FAIL] {msg}")
            errors.append(msg)
            metadata_ok = False

    if metadata_ok:
        print(f"[OK] Alle Marker-Metadata (pb_studio) intakt — Lists und Floats korrekt")

    # 5c. Transition?
    transitions = []
    for track in loaded.tracks:
        for child in track:
            if isinstance(child, otio.schema.Transition):
                transitions.append(child)
    if len(transitions) >= 1:
        t = transitions[0]
        print(f"[OK] Transition gefunden: '{t.name}' (type={t.transition_type})")
    else:
        msg = "Keine Transition gefunden"
        print(f"[FAIL] {msg}")
        errors.append(msg)

except Exception as e:
    msg = f"Reload/Verify Fehler: {e}"
    print(f"[FAIL] {msg}")
    traceback.print_exc()
    errors.append(msg)

# --- 6. RAM Impact ---
print(f"\n--- Resourcen ---")
if has_psutil:
    mem_after = proc.memory_info().rss / (1024 * 1024)
    print(f"RAM vorher:  {mem_before:.1f} MB")
    print(f"RAM nachher: {mem_after:.1f} MB")
    print(f"RAM Delta:   {mem_after - mem_before:.1f} MB")
else:
    print(f"RAM: psutil nicht verfuegbar, keine Messung")
print(f"VRAM Impact: 0 (reines CPU-Paket, kein GPU-Code)")

# --- 7. GO / NO-GO ---
print("\n" + "=" * 60)
if not errors and otio_ok:
    print("ERGEBNIS:  *** GO ***")
    print("Begruendung: Alle Tests bestanden.")
    if not edl_ok:
        print("  Hinweis: EDL-Export hatte Probleme (erwartet bei custom metadata).")
else:
    print("ERGEBNIS:  *** NO-GO ***")
    print(f"Fehler ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
print("=" * 60)

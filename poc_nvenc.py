"""
PoC #4: FFmpeg NVENC Machbarkeit
Wegwerf-Skript — testet NVENC/NVDEC Verfügbarkeit und Performance-Profile.
"""

import subprocess
import sys
import os
import time
import re
import shutil
from pathlib import Path

FFMPEG = r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe"
if not os.path.isfile(FFMPEG):
    found = shutil.which("ffmpeg")
    if found:
        FFMPEG = found
    else:
        print("FATAL: ffmpeg nicht gefunden")
        sys.exit(1)

WORKDIR = Path(__file__).parent / "_poc_nvenc_tmp"
WORKDIR.mkdir(exist_ok=True)

RESULTS = {}


def run(cmd, capture_stderr=False, timeout=120):
    """Run a command, return (returncode, stdout, stderr)."""
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    return p.returncode, p.stdout, p.stderr


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 1. FFmpeg Version ─────────────────────────────────────────
section("1. FFmpeg Version")
rc, out, err = run([FFMPEG, "-version"])
version_line = out.strip().split("\n")[0] if out else "unbekannt"
print(version_line)
RESULTS["ffmpeg_version"] = version_line

# ── 2. NVENC Encoder ──────────────────────────────────────────
section("2. NVENC Encoder verfügbar?")
rc, out, err = run([FFMPEG, "-hide_banner", "-encoders"])
nvenc_encoders = [l.strip() for l in out.split("\n") if "nvenc" in l.lower()]
for e in nvenc_encoders:
    print(f"  {e}")
RESULTS["nvenc_encoders"] = nvenc_encoders
has_h264_nvenc = any("h264_nvenc" in e for e in nvenc_encoders)
has_hevc_nvenc = any("hevc_nvenc" in e for e in nvenc_encoders)
print(f"  h264_nvenc: {'JA' if has_h264_nvenc else 'NEIN'}")
print(f"  hevc_nvenc: {'JA' if has_hevc_nvenc else 'NEIN'}")

# ── 3. NVDEC / CUDA hwaccel ──────────────────────────────────
section("3. NVDEC / CUDA Hardware-Acceleration?")
rc, out, err = run([FFMPEG, "-hide_banner", "-hwaccels"])
hwaccels = out.strip().split("\n")
print("  Verfügbare hwaccels:")
for h in hwaccels:
    print(f"    {h.strip()}")
has_cuda = any("cuda" in h.lower() for h in hwaccels)
has_d3d11va = any("d3d11va" in h.lower() for h in hwaccels)
print(f"  CUDA: {'JA' if has_cuda else 'NEIN'}")
print(f"  D3D11VA: {'JA' if has_d3d11va else 'NEIN'}")
RESULTS["has_cuda"] = has_cuda
RESULTS["has_d3d11va"] = has_d3d11va

# ── 4. NVENC Encoder-Details ──────────────────────────────────
section("4. NVENC Encoder-Details")
for enc in ["h264_nvenc", "hevc_nvenc"]:
    rc, out, err = run([FFMPEG, "-hide_banner", "-h", f"encoder={enc}"])
    if rc == 0 and out:
        # Show first 5 lines + preset line
        lines = out.strip().split("\n")
        print(f"\n  --- {enc} ---")
        for l in lines[:5]:
            print(f"    {l}")
        preset_lines = [l for l in lines if "preset" in l.lower() or "-p " in l.lower()]
        if preset_lines:
            print(f"    ...presets found: {len(preset_lines)} lines")
    else:
        print(f"  {enc}: nicht verfügbar")

# ── 5. Synthetisches Testvideo erstellen ──────────────────────
section("5. Synthetisches 10s Testvideo (1080p)")
src_file = WORKDIR / "testsrc_1080p.mp4"
cmd_src = [
    FFMPEG, "-y", "-hide_banner",
    "-f", "lavfi", "-i", "testsrc2=duration=10:size=1920x1080:rate=30",
    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
    str(src_file),
]
t0 = time.perf_counter()
rc, out, err = run(cmd_src, timeout=60)
dt = time.perf_counter() - t0
if rc == 0 and src_file.exists():
    sz = src_file.stat().st_size / (1024 * 1024)
    print(f"  OK — {sz:.1f} MB in {dt:.1f}s")
else:
    print(f"  FEHLER: rc={rc}")
    print(err[-500:] if err else "kein stderr")
    sys.exit(1)

# ── 6. Preset-Profile testen ─────────────────────────────────
section("6. Preset-Profile (NVENC)")

profiles = {
    "Edit-Proxy (540p, p1, cq28)": [
        FFMPEG, "-y", "-hide_banner",
        "-i", str(src_file),
        "-vf", "scale=960:540",
        "-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr", "-cq", "28",
        "-b:v", "0",
        str(WORKDIR / "proxy_540p.mp4"),
    ],
    "Master-Export (1080p, p4, cq18)": [
        FFMPEG, "-y", "-hide_banner",
        "-i", str(src_file),
        "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18",
        "-b:v", "0",
        str(WORKDIR / "master_1080p.mp4"),
    ],
    "DaVinci-Proxy (720p, DNxHR LB)": [
        FFMPEG, "-y", "-hide_banner",
        "-i", str(src_file),
        "-vf", "scale=1280:720",
        "-c:v", "dnxhd", "-profile:v", "dnxhr_lb",
        str(WORKDIR / "davinci_720p.mxf"),
    ],
}

profile_results = {}
for name, cmd in profiles.items():
    print(f"\n  --- {name} ---")
    t0 = time.perf_counter()
    rc, out, err = run(cmd, timeout=120)
    dt = time.perf_counter() - t0

    outfile = Path(cmd[-1])
    if rc == 0 and outfile.exists():
        sz = outfile.stat().st_size / (1024 * 1024)
        # Parse fps from stderr
        fps_match = re.search(r"frame=\s*(\d+)", err)
        frames = int(fps_match.group(1)) if fps_match else 300  # 10s * 30fps
        fps = frames / dt if dt > 0 else 0
        realtime_x = fps / 30.0
        print(f"    OK — {sz:.2f} MB, {dt:.2f}s, ~{fps:.0f} fps, {realtime_x:.1f}x Realtime")
        profile_results[name] = {
            "size_mb": sz, "time_s": dt, "fps": fps, "realtime_x": realtime_x, "ok": True
        }
    else:
        print(f"    FEHLER: rc={rc}")
        if err:
            # Show last few lines of error
            err_lines = err.strip().split("\n")
            for l in err_lines[-5:]:
                print(f"      {l}")
        profile_results[name] = {"ok": False, "error": err[-200:] if err else "unknown"}

RESULTS["profiles"] = profile_results

# ── 7. Hardware-Decode + Encode Pipeline ──────────────────────
section("7. Hardware-Pipeline (CUDA decode + NVENC encode)")
hw_out = WORKDIR / "hw_pipeline.mp4"
cmd_hw = [
    FFMPEG, "-y", "-hide_banner",
    "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
    "-i", str(src_file),
    "-c:v", "h264_nvenc", "-preset", "p4",
    str(hw_out),
]
t0 = time.perf_counter()
rc, out, err = run(cmd_hw, timeout=60)
dt = time.perf_counter() - t0
if rc == 0 and hw_out.exists():
    sz = hw_out.stat().st_size / (1024 * 1024)
    print(f"  OK — {sz:.2f} MB in {dt:.2f}s (full HW pipeline)")
    RESULTS["hw_pipeline"] = True
else:
    print(f"  FEHLER: rc={rc}")
    if err:
        for l in err.strip().split("\n")[-5:]:
            print(f"    {l}")
    RESULTS["hw_pipeline"] = False

# ── 8. Progress-Parsing Test ──────────────────────────────────
section("8. Fortschritts-Parsing (stderr)")
progress_out = WORKDIR / "progress_test.mp4"
cmd_prog = [
    FFMPEG, "-y", "-hide_banner", "-progress", "pipe:1",
    "-i", str(src_file),
    "-c:v", "h264_nvenc", "-preset", "p1",
    str(progress_out),
]
rc, out, err = run(cmd_prog, timeout=60)

# Parse progress from stdout (because -progress pipe:1)
frame_matches = re.findall(r"frame=(\d+)", out)
time_matches = re.findall(r"out_time=(\S+)", out)
speed_matches = re.findall(r"speed=(\S+)", out)

print(f"  frame= Einträge gefunden: {len(frame_matches)}")
print(f"  out_time= Einträge gefunden: {len(time_matches)}")
print(f"  speed= Einträge gefunden: {len(speed_matches)}")
if frame_matches:
    print(f"    Letzter frame: {frame_matches[-1]}")
if time_matches:
    print(f"    Letzter out_time: {time_matches[-1]}")
if speed_matches:
    print(f"    Letzter speed: {speed_matches[-1]}")

progress_ok = len(frame_matches) > 0 and len(time_matches) > 0
RESULTS["progress_parsing"] = progress_ok
print(f"  Progress-Parsing: {'OK' if progress_ok else 'FEHLER'}")

# Also test stderr parsing (classic method)
frame_stderr = re.findall(r"frame=\s*(\d+)", err)
time_stderr = re.findall(r"time=(\d+:\d+:\d+\.\d+)", err)
print(f"  stderr frame= : {len(frame_stderr)} Einträge")
print(f"  stderr time=  : {len(time_stderr)} Einträge")

# ── 9. Aufräumen ──────────────────────────────────────────────
section("9. Aufräumen")
import shutil as _shutil
_shutil.rmtree(WORKDIR, ignore_errors=True)
print(f"  {WORKDIR} gelöscht")

# ── ZUSAMMENFASSUNG ───────────────────────────────────────────
section("ZUSAMMENFASSUNG")
print(f"  FFmpeg:          {RESULTS['ffmpeg_version']}")
print(f"  NVENC:           {'JA' if nvenc_encoders else 'NEIN'}")
print(f"  h264_nvenc:      {'JA' if has_h264_nvenc else 'NEIN'}")
print(f"  hevc_nvenc:      {'JA' if has_hevc_nvenc else 'NEIN'}")
print(f"  CUDA hwaccel:    {'JA' if has_cuda else 'NEIN'}")
print(f"  HW-Pipeline:     {'OK' if RESULTS.get('hw_pipeline') else 'FEHLER'}")
print(f"  Progress-Parsing:{'OK' if RESULTS.get('progress_parsing') else 'FEHLER'}")

print(f"\n  Preset-Ergebnisse:")
for name, r in profile_results.items():
    if r.get("ok"):
        print(f"    {name}: {r['size_mb']:.2f} MB, {r['fps']:.0f} fps, {r['realtime_x']:.1f}x RT, {r['time_s']:.2f}s")
    else:
        print(f"    {name}: FEHLER")

# Verdict
all_profiles_ok = all(r.get("ok") for r in profile_results.values())
go = has_h264_nvenc and has_cuda and RESULTS.get("hw_pipeline") and progress_ok and all_profiles_ok

print(f"\n  {'='*40}")
if go:
    print(f"  VERDICT: GO — NVENC voll einsatzbereit")
else:
    reasons = []
    if not has_h264_nvenc:
        reasons.append("h264_nvenc fehlt")
    if not has_cuda:
        reasons.append("CUDA hwaccel fehlt")
    if not RESULTS.get("hw_pipeline"):
        reasons.append("HW-Pipeline fehlgeschlagen")
    if not progress_ok:
        reasons.append("Progress-Parsing fehlgeschlagen")
    if not all_profiles_ok:
        failed = [n for n, r in profile_results.items() if not r.get("ok")]
        reasons.append(f"Profile fehlgeschlagen: {', '.join(failed)}")
    print(f"  VERDICT: NO-GO — {'; '.join(reasons)}")
print(f"  {'='*40}")

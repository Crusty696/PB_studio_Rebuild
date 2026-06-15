# DG-001 H1.3 4h Preparation Runbook

Purpose: prepare DG-001 H1.3 without starting the 4h model-pipeline run.

## Current Gate

Source: `docs/superpowers/DG-001_LIVE_VERIFY.md`.

Open release blockers:

- H1.3: full 4h model-pipeline run on GTX 1060.
- H2.2: human QMediaPlayer/PB playback verdict.

## User Sources

Video source root:

```text
C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur
```

Audio source:

```text
C:\Users\David Lochmann\Music\Audio\Psy-Set\Podcast-04.m4a
```

Verified facts from `ffprobe` before this runbook:

- `Podcast-04.m4a`: AAC stereo, 44.1 kHz, `11258.659s` (~3h 07m 39s), no video stream.
- Largest checked `Solo_Natur` clips are short (`8-10s`), H.264, mostly 720p/480p; some contain AAC audio.

## Prepared Output Area

```text
test-report\dg001-h1-4h-20260615
```

Expected prepared files:

- `source_candidates.json`: probed usable video files.
- `video_loop.ffconcat`: concat plan rotating real Solo_Natur clips until >=4h.
- `commands.ps1`: explicit build command for the 4h input.
- `README.md`: generated local preparation summary.

Future 4h input name if intentionally built:

```text
test-report\dg001-h1-4h-20260615\input_4h_real_video_real_audio.mp4
```

## Prepare Only

This writes manifests only. It does not build the 4h MP4 and does not start PB Studio pipeline.

```powershell
powershell -ExecutionPolicy Bypass -File tools\prepare_dg001_h1_4h.ps1 -WritePlan
```

## Build Input Later

Only run when the machine is scheduled for a long encode. This creates the 4h MP4, but still does not start model analysis.

```powershell
powershell -ExecutionPolicy Bypass -File tools\prepare_dg001_h1_4h.ps1 -BuildInput
```

## Pipeline Later

After the 4h MP4 exists, H1.3 still requires a full model-pipeline run on GTX 1060, log capture, and post-run verdict:

- no OOM/crash
- no VRAM/RAM leak over full duration
- coverage >=99.5%
- pipeline result `failed=False`
- release gate checked with `python tools\release_gate.py`

No `fixed` or `release` marker is allowed from preparation alone.

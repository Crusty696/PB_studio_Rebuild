# B-471 Rekordbox Waveform Follow-up - 2026-06-07

Status: code-fix-pending-live-verification

## User Live Result

User tested commit `1966e94` and reported the timeline still looked the same as before. No `fixed` marker.

## External Reference Checked

- rekordbox manual 6.7.0: waveform color can be set to `Blue`, `RGB`, or `3Band`; higher waveform drawing quality can increase CPU load.
- AlphaTheta support: old analysis data can prevent 3Band waveform display; 3Band depends on suitable analysis data.
- AlphaTheta support: supported hardware distinguishes `BLUE/RGB/3Band`.

## Root Cause Found

Two root causes were found.

First, the previous tests only checked that a `WaveformGraphicsItem` exists. They did not prove visibility.

In `ui/timeline.py`, waveform items were painted behind the audio clip:

- scene waveform z was `1`, while audio clip z was `2`;
- async child waveform used `ItemStacksBehindParent`, so the clip fill could still cover it.

Second, the real `test55655` project DB had waveform and beatgrid rows, but the timeline build still ended with `waveform_items=0`. The DB worker emitted SQLAlchemy object maps through `Signal(list, dict, dict, dict, dict)`. PySide queued delivery preserved the entries list but delivered `audio_map` and `video_map` as empty dicts. That made audio clips fall back to `?`/flat clip behavior and prevented thumbnail paths from reaching the UI.

## Code Changes

- Increased timeline lane height from 50 px to 80 px for readable waveform/beatgrid.
- Moved waveform items above audio clip fill, below labels/handles.
- Removed `ItemStacksBehindParent` from styled waveform items.
- Changed the timeline DB worker signal to `Signal(object, object, object, object, object)` so SQLAlchemy media maps survive the thread boundary.
- Draws waveform immediately from the already loaded audio map instead of depending on a late async worker.
- Added visible video thumbnail state text: `Thumbnail laedt` or `Thumbnail fehlt - Datei fehlt`.
- Enlarged timeline zoom toolbar buttons to at least 48 x 36 px.
- Reduced button zoom step from 25% to 15% for touchpad usability.
- Kept scope inside B-471 visible timeline usability; no pacing algorithm or dependency change.

## Verification

- New RED tests first failed: waveform z-order, async child waveform stacking, lane height, touchpad button size, thumbnail status.
- New DB worker regression test first reproduced empty media maps; current focused tests passed: `27 passed`.
- `run_pytest_schnitt.bat`: `25 passed`.
- Affected-file py_compile passed.
- `from main import PBWindow`: `OK`, with GPU readiness warning.
- Offscreen visual smoke image: `test_reports/b471_professional_timeline_surface_2026-06-07.png`.
- DB-backed headless build on `C:\Users\David Lochmann\Downloads\video\test55655`: `clip_items=768`, `waveform_items=1`, `waveform_z=4.0`, `audio_clip_z=2.0`, vertical fit scale `m22_after_fit=1.0`.
- DB-backed screenshot: `test_reports/b471_db_timeline_build_after_waveform_fix.png`.

## Open

Real app workflow still needs user/live verification on an active project with analyzed audio waveform data and video paths. The offscreen screenshot shows waveform/beatgrid, but many text labels render as square glyphs in the headless image; that is not proof of real-app readability. Status remains `code-fix-pending-live-verification`.

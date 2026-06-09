# B-471 Timeline Gap Repair 2026-06-09

## Scope

User reported that video clips are not correctly divided/placed and that there are gaps where none are allowed.

## Root Cause Evidence

Project DB checked:

```text
C:\Users\David Lochmann\Downloads\video\test55655\pb_studio.db
```

Before repair:

- video entries: 767
- gaps: 7
- max gap: 5.0s
- overlaps: 1
- locked video entries: 0

The issue was not only a rendering problem. The DB contained real video-track timing gaps/overlap. `services.timeline_service.repair_timeline_integrity()` clamped overlong durations and shifted overlaps, but did not close positive gaps between unlocked video entries.

## Code Fix

- `services/timeline_service.py`
  - `repair_timeline_integrity()` now tracks `video_gaps_closed`.
  - Positive gaps before unlocked video entries are closed by shifting the entry to the current video cursor while preserving duration/source span.
- `tests/test_services/test_apply_auto_edit_locked.py`
  - Added B-471 regression test for closing unlocked video gaps.
  - Updated old B-319 expectations that preserved a small gap after source-span clamping.

## Project DB Repair

Backup created before mutation:

```text
C:\Users\David Lochmann\Downloads\video\test55655\pb_studio.db.b471-gapfix-20260609.bak
```

Repair command used the app service after `database.set_project(test55655)`:

```text
repair_timeline_integrity(1)
```

Repair result:

```text
{'video_duration_clamped': 0, 'video_overlaps_shifted': 0, 'video_gaps_closed': 765, 'video_source_span_rebuilt': 0, 'audio_duplicates_removed': 0, 'audio_duration_synced': 0}
```

After repair:

- video entries: 767
- gaps: 0
- overlaps: 0
- first three video rows: `[0.0-5.74]`, `[5.74-15.74]`, `[15.74-23.78]`
- last video row ends at `3731.46`

## Verification

- RED test before fix: failed with missing `video_gaps_closed`.
- Focused repaired tests: `3 passed`.
- Full `tests/test_services/test_apply_auto_edit_locked.py`: `16 passed`.
- `run_pytest_schnitt.bat`: `27 passed`.
- `py_compile services/timeline_service.py ui/timeline.py`: passed.
- `git diff --check`: passed.

## Honest Status

Code fix and project DB repair are in place. Real GUI/user review is still required. No `fixed` marker set.

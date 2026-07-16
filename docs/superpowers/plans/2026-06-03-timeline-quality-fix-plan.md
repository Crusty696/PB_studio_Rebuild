# Timeline Quality Fix Plan (user feedback 2026-06-03)

> **⛔ SUPERSEDED 2026-07-16 — PLAN GESCHLOSSEN + KOMPLETT ERLEDIGT.** Bucket-7-Aufloesung:
> alle referenzierten Bugs erledigt (B-471/472/473/475 `fixed`, B-474 `cannot-reproduce`) —
> keine offene Task. Konsolidiert unter `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16` (D-071).
> Nicht mehr als aktiver Plan nutzen.

status: in-progress (autonomous, user authorized "mach alles autonom bis alles fertig ist")
plan_id: TIMELINE-QUALITY-FIX-2026-06-03
parent_plan: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
created: 2026-06-03
owner: agent (David confirms each `status: fixed`)

## Origin

During the B-470 Stack A live-verify the user saw the real timeline (1132 entries,
110 visible cuts) and reported 5 defects: gaps, no thumbnails, poor optics, bad
zoom, constant freezing. This plan triages + fixes them. B-470 Stack A (project-
switch teardown freeze) is already fixed/verified (`c634b39`); the B-470 110s
/alembic sub-item is paused in favour of this.

## Verified roots (read-only, ui/timeline.py + edit_actions.py)

1. **Gaps (B-471):** `add_to_timeline` (edit_actions.py:651-657) appends video
   clips contiguously at `last_entry.end_time` — no data gap. The visual "gap" is
   the **thumbnail width cap**: `TimelineClipItem.__init__` caps the thumbnail at
   `min(int(width), 220)` px (timeline.py:200); a clip wider than 220px shows the
   thumbnail on the left and a bare gold rect after → reads as a gap.
2. **No thumbnails (B-472):** `_timeline_video_thumbnail` (timeline.py:132) loads
   a pre-generated hashed JPG from the media-grid thumb cache (`_thumb_path`); if
   missing it returns a `#id` placeholder. Also opacity is **0.58** and the tile
   is small → even present thumbs are barely visible. The disk load is
   **synchronous inside the item build** (main thread).
3. **Optics (B-473-opt):** capped/faint thumbnails, flat gold rect, label/handle
   styling.
4. **Zoom (B-474):** `wheelEvent` uses `self.scale(factor, 1.0)` — a horizontal-
   only QGraphicsView transform. It stretches text + thumbnails (distortion) and
   repaints every item on each wheel step.
5. **Freezing (B-475):** zoom repaints all items; synchronous thumbnail disk I/O
   per item during the (batched) build; large item counts.

## Constraints (binding)

- Autonomous, but: TDD per fix, full default gate green before each commit, live
  verify in the real app, vault per sub-step, `status: fixed` set by USER only.
- Do not break working timeline behavior (drag/trim/anchors/waveform/beatgrid).
- One fix at a time; commit each separately; honest about residual risk.
- GPU rule untouched (no model/device work here).

## Staged plan (value/risk ordered)

- **T1 — Thumbnail rendering (fixes #2 + #1-visual + part of #3).** Make the
  thumbnail cover the clip width (tile/repeat or a filmstrip strip instead of a
  single 220px tile), raise visibility (opacity), and load thumbs OFF the main
  thread (async, like waveforms) with a placeholder until ready. Removes the
  "gap" look and the build-time disk I/O.
- **T2 — Thumbnail generation coverage.** Ensure imported clips actually have
  cached thumbs (verify `_thumb_path` resolution + that import generates them);
  generate missing ones lazily/async. (Depends on T1 finding whether thumbs
  exist.)
- **T3 — Zoom rework (#4 + part #5).** Stop distorting items: zoom by rescaling
  the time→x mapping (pixels-per-second) and item widths/positions instead of a
  view transform that stretches text/thumbnails; or counter-scale text/thumbnail
  items. Throttle/repaint efficiently so zoom is smooth on large timelines.
- **T4 — Paint/perf hardening (#5).** Reduce per-zoom/scroll repaint cost
  (viewport update mode, item caching, cull offscreen items / LOD), building on
  the B-470 Stack A teardown fix.
- **T5 — Optics polish (#3).** Clip styling, label legibility, selected/locked
  states, track backgrounds — only after correctness/perf are solid.

Each stage: failing test/observation → minimal change → targeted tests → full
gate → live verify in app → propose `fixed` to user.

## Acceptance (per stage)

Targeted tests green + full default gate green + live app verification of the
specific defect (e.g. thumbnails visible across clip width; zoom smooth + no text
distortion; no multi-second freeze on zoom/scroll). `status: fixed` user only.

## Honest scope note

This is a multi-stage rendering rework, not a single fix. Progress is committed
and live-verified per stage; the user sees each stage land rather than one big
unverifiable change.

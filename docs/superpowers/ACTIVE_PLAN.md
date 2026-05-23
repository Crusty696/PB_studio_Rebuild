# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-BUGFIX-2026-05-23
next_allowed_task: Phase 1 — tote UI-Features erreichbar machen (F-5/F-6/F-9 = B-337/B-338/B-341)
updated: 2026-05-23

## Meaning

Der User hat am 2026-05-23 per `/goal` den Bugfix-Plan `PB-STUDIO-BUGFIX-2026-05-23` freigegeben und beauftragt, ihn abzuarbeiten. Quelle: Bug-Hunt-Bericht `wiki/synthesis/bug-hunt-2026-05-23.md` (30 Findings F-1..F-30 → B-333..B-362). Decision: D-051.

Vorher aktiver `COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22` und `PB-STUDIO-OFFENE-BUGS-TASKS-MASTERPLAN-2026-05-20` sind pausiert, nicht geloescht.

## Agent Behavior

- Nur `PB-STUDIO-BUGFIX-2026-05-23` ausfuehren.
- Phasen-Reihenfolge: Phase 1 (UI erreichbar) → Phase 2 (GPU/VRAM) → Phase 3 (NVENC) → Phase 4 (Correctness) → Phase 5 (Robustheit) → Phase 6 (Low).
- Phase-1-Strategie: tote Features erreichbar machen statt loeschen.
- Autonomer Background-Run im Worktree: keine GUI-Klicks → GUI-Fixes `code-fix-pending-live-verification`, NICHT `fixed`.
- `status: fixed` setzt nur der User nach Live-Test.
- Audio-V2 nicht aendern/portieren. GPU-Hartregel (GTX 1060 / cuda:0 / NVENC) gilt.
- Eine Task zur Zeit, Vault pro Sub-Schritt.

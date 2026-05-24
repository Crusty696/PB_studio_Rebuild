---
title: PB Studio Area Audit Plan
date: 2026-05-24
status: active
plan_id: PB-STUDIO-AREA-AUDIT-2026-05-24
vault_mirror: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-pb-studio-area-audit-2026-05-24.md
decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-052-pb-studio-area-audit.md
tags: [area-audit, qa, pb-studio, governance]
---

# PB Studio Area Audit Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or equivalent task-by-task execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit PB Studio area by area and produce evidence-backed findings plus a prioritized fix plan without silently fixing app code.

**Architecture:** This plan is a QA/governance plan, not a feature plan. It gates each app area through static inspection, test mapping, safe smoke checks, optional live GUI checks, Vault findings, and final synthesis before any fix work starts.

**Tech Stack:** Python 3.10, PySide6, SQLite/SQLAlchemy, pytest, FFmpeg/ffprobe, CUDA on NVIDIA GTX 1060 only.

---

## Scope

This plan authorizes auditing and documentation only. It does not authorize app-code refactors, feature work, library swaps, model changes, Audio-V2 porting, or bug fixes.

All discovered bugs must be recorded as Vault bug files with severity, evidence, reproduction path, and test plan. Status `fixed` is forbidden unless a real live user workflow has been verified.

## Preconditions

- [x] Registry contains `PB-STUDIO-AREA-AUDIT-2026-05-24`.
- [x] `docs/superpowers/ACTIVE_PLAN.md` selects `PB-STUDIO-AREA-AUDIT-2026-05-24`.
- [x] Vault Decision `D-052-pb-studio-area-audit.md` exists.
- [x] Vault Mirror `plan-pb-studio-area-audit-2026-05-24.md` exists.
- [x] Dirty worktree is preserved; unrelated existing changes are not reverted.

## Audit Method

For every area:

1. Quote current area task from this plan.
2. Run or record `python -m pytest --collect-only`.
3. Inventory relevant files with `rg --files` and targeted `rg`.
4. Read entrypoints, data flow, worker/thread path, DB writes, IO paths, and error handling.
5. Map existing tests and GUI tools.
6. Run safe tests/smokes that do not require unsupported GPU backend or destructive data changes.
7. If technically possible, run app start or GUI path; otherwise mark live verification open.
8. Write area synthesis to Vault.
9. Create Vault bug files for concrete findings only.
10. Update this plan's Audit Log and continue to next area only after the area status is clear.

## Area Order

### Area 1: Governance, Start, Setup, Runtime Paths

- [x] Read `AGENTS.md`, `PLAN_REGISTRY.md`, `ACTIVE_PLAN.md`, `pyproject.toml`, `main.py`, `start_pb_studio.py`, `STARTUP.md`, setup scripts, startup checks.
- [x] Check CUDA/GTX-1060 assumptions, Python runtime pins, PATH/DLL handling, FFmpeg/ffprobe discovery, setup wizard wiring.
- [x] Map tests for startup/setup/runtime.
- [x] Run safe import/syntax/tests for startup/setup/runtime.
- [x] Create Vault synthesis `wiki/synthesis/area-audit-01-governance-start-runtime-2026-05-24.md`.

### Area 2: Database, Migrations, Storage, Soft-Delete

- [ ] Read `database/`, migrations, session setup, storage path services, DB tests.
- [ ] Check schema drift, destructive defaults, migration order, backup/recovery assumptions.
- [ ] Run targeted DB tests.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-02-database-storage-2026-05-24.md`.

### Area 3: Project, Import, Media Ingest

- [ ] Read project management, ingest service, media table model, import controllers, GUI import tools.
- [ ] Check duplicate handling, file type validation, project path safety, worker dispatch.
- [ ] Run targeted ingest/project tests and safe GUI navigation if possible.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-03-project-ingest-2026-05-24.md`.

### Area 4: Audio Pipeline

- [ ] Read audio services, Demucs/stems, Beatgrid, key/structure/onset/LUFS services, audio controllers.
- [ ] Check GPU/CPU boundaries, long-track chunking, cache paths, failure recovery.
- [ ] Run non-live-GPU tests first; live GPU tests only if explicitly safe on GTX 1060.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-04-audio-pipeline-2026-05-24.md`.

### Area 5: Video Pipeline

- [ ] Read proxy, scene detect, RAFT/SigLIP, vector DB, video pipeline stages, video controllers.
- [ ] Check VRAM locking, batch size, proxy lifecycle, embedding dimensions, failure cleanup.
- [ ] Run safe video pipeline tests; no unsupported GPU backend.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-05-video-pipeline-2026-05-24.md`.

### Area 6: Brain, Pacing, Auto-Edit, Memory/RL

- [ ] Read Brain V2/V3, pacing services, auto-edit worker, memory/RL modules, structure services.
- [ ] Check data contracts between audio/video analysis and timeline generation.
- [ ] Run pacing/brain tests and safe smoke scripts.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-06-brain-pacing-memory-2026-05-24.md`.

### Area 7: Schnitt UI, Timeline, Waveform, Thumbnails, Anchors

- [ ] Read Schnitt workspace, timeline widgets, waveform item, thumbnails, anchors, related controllers.
- [ ] Check signal/slot wiring, QThread lifecycle, layout/visibility states, missing media fallback.
- [ ] Run UI tests, Qt offscreen smoke, and available GUI tools if app starts.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-07-schnitt-ui-2026-05-24.md`.

### Area 8: Export/Delivery

- [ ] Read export service, convert service, delivery workspace, FFmpeg/NVENC handling, LUFS paths.
- [ ] Check encoder selection, fallback, timeout/cancel, temp files, output path safety.
- [ ] Run export/convert tests and safe dry-run/smoke only.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-08-export-delivery-2026-05-24.md`.

### Area 9: Chat, Actions, Agents, Ollama

- [ ] Read chat dock, action registry, action modules, local agent service, Ollama service/client, agents.
- [ ] Check command routing, side effects, error reporting, forbidden direct callers from other plans.
- [ ] Run targeted action/chat/agent tests.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-09-chat-actions-agents-2026-05-24.md`.

### Area 10: Packaging, Installer, Docs, Launch Scripts

- [ ] Read PyInstaller spec, installer scripts/hooks, setup docs, launch scripts, user docs.
- [ ] Check runtime dependency packaging, CUDA/FFmpeg/model cache assumptions, stale docs.
- [ ] Run packaging smoke where safe; no release build unless explicitly approved.
- [ ] Create Vault synthesis `wiki/synthesis/area-audit-10-packaging-docs-2026-05-24.md`.

## Final Deliverables

- [ ] Vault synthesis `wiki/synthesis/pb-studio-area-audit-final-2026-05-24.md`.
- [ ] Prioritized fix plan grouped by Critical, High, Medium, Low.
- [ ] Repo summary in `docs/superpowers/synthesis/pb-studio-area-audit-final-2026-05-24.md`.
- [ ] No app-code changes unless user explicitly approves a later fix plan.

## Audit Log

- 2026-05-24: Plan created from user-approved implementation plan.
- 2026-05-24: Area 1 audited. Startup/setup targeted tests passed, py_compile passed, default pytest collect blocked by B-348, live UI path open. Next allowed task: Area 2 Database, Migrations, Storage, Soft-Delete.

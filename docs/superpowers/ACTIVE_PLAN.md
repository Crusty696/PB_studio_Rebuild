# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07
next_allowed_task: Task 1 Regression Tests
updated: 2026-06-07

## Meaning

Der User hat am 2026-06-07 entschieden, den Fix mit groesserem direktem App-Mehrwert zuerst zu machen: FFmpeg/FFprobe-Resolver-Fixes fuer Thumbnail- und Ingest-Pfade aus dem Audit `PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07`.

Aktiver Plan:

```text
PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07
```

Repo-Plan:

```text
docs/superpowers/plans/2026-06-07-ffmpeg-resolver-fix.md
```

Vault-Mirror:

```text
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-ffmpeg-resolver-fix-2026-06-07.md
```

Decision:

```text
C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-058-ffmpeg-resolver-fix.md
```

## Agent Behavior

- Nur `PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07` bearbeiten.
- Modus: `fix-plan`.
- Nur CQ-004/CQ-005 Resolver-Call-Sites bearbeiten.
- Keine Dependency-Swaps, keine UI-Optik, kein Poetry-Lock-Cleanup.
- `verified` / `fixed` nur nach realem App-Workflow plus Log-/UI-Beleg. Focused pytest/import-smoke ist keine Live-Verifikation.

## Current Status

- Branch erstellt: `codex/PB-STUDIO-FFMPEG-RESOLVER-FIX-2026-06-07`.
- Repo-Plan, Vault-Decision und Vault-Mirror wurden erstellt.
- Task 0 Governance Activation abgeschlossen: Registry, Active Plan, Handoff, Vault-Decision und Vault-Mirror gesetzt.
- Vorherige Plaene bleiben in Registry erhalten; offene Live-/Fixpunkte wurden nicht geloescht.

## Current Next Task

```text
Task 1 Regression Tests
```

# PB Studio Plan Registry

Diese Datei ist die kanonische Repo-Quelle fuer autorisierte PB-Studio-Plaene. `AGENTS.md`, `CLAUDE.md` und `GEMINI.md` verweisen auf diese Registry statt feste Planlisten zu duplizieren.

## Status Values

| Status | Meaning |
|---|---|
| `draft` | Plan existiert, aber keine Implementierung erlaubt. |
| `approved-for-planning` | Planung/Drift-Pruefung erlaubt, Code-Arbeit noch nicht automatisch erlaubt. |
| `approved-for-implementation` | User/Decision erlaubt Implementierung, sofern `ACTIVE_PLAN.md` genau diesen Plan als Fokus setzt. |
| `in_progress` | Aktiver Plan mit laufender Task. |
| `blocked` | Nicht starten; Blocker lesen und User fragen. |
| `code-complete-live-pending` | Code/Test-Arbeit abgeschlossen, Live-Verifikation offen. |
| `fixed` | User hat Live-Verifikation bestaetigt. |
| `superseded` | Durch neueren Plan ersetzt. |

## Registry

| plan_id | repo_path | vault_mirror | decision | status | next_allowed_task | blocker |
|---|---|---|---|---|---|---|
| `BRAIN-V3-NVIDIA-2026-05-04` | `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\brain-v3-plan-audit-2026-05-05.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-033-brain-v3-plan-adoption.md` | `code-complete-live-pending` | When selected: first do Phase 1-3 App-Sync, then Pre-Phase-4 PacingConfig spike. See `docs/superpowers/synthesis/brain-v3-open-items-2026-05-20.md`. | Phase 1-3 are code-complete but App-Sync/live pending; Phase 4 blocked by PacingConfig/use_brain_v3 decision; NVENC parallel and real DJ-mix validation remain open. |
| `SCHNITT-WORKSPACE-REDESIGN-2026-05-09` | `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-041-only-user-authorized-changes.md` | `code-complete-live-pending` | Phase 12 live verification / user confirmation path. | `status: fixed` remains user-only after full live workflow. |
| `SCHNITT-USABILITY-WIRING-REBUILD-2026-05-13` | `docs/superpowers/plans/2026-05-13-schnitt-usability-wiring-rebuild/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-schnitt-b310-2026-05-13.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-041-only-user-authorized-changes.md` | `code-complete-live-pending` | Task 8 live verification, then open B-316..B-320 in bug order if user selects this plan. | B-310 not fixed until complete live workflow is confirmed. |
| `AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17` | `docs/superpowers/plans/2026-05-20-audio-v2-reconcile/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-audio-v2-reconcile-2026-05-20.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-048-audio-v2-reconcile-before-port.md` | `approved-for-planning` | `P0 - Freeze And Snapshot` from the reconcile plan. | Do not port app code until P0 is complete; sandbox branch is dirty and old, direct merge is forbidden. |
| `PB-STUDIO-OFFENE-BUGS-TASKS-MASTERPLAN-2026-05-20` | `docs/superpowers/plans/2026-05-07-bug-und-task-liste-abwicklung.md` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\bug-und-task-liste-2026-05-20.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-049-offene-bugs-tasks-masterplan.md` | `approved-for-implementation` | Governance Gate + SCHNITT B-310/B-316..B-320 Reihenfolge pruefen. | Audio-V2-Reconcile ist pausiert, nicht geloescht; keine Audio-V2-Portierung in diesem Plan. |
| `COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22` | `docs/superpowers/plans/2026-05-22-comfyui-reference-audit/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-comfyui-reference-audit-2026-05-22.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-050-comfyui-reference-audit-integration.md` | `approved-for-implementation` | Phase 1 workflow-first reference audit from `30_Workflows\Brücke_ComfyUI_API.md`. | User set `workflows` as highest-priority folder on 2026-05-22; read-only parallel support is allowed for app-side lookup and independent inventory checks; reference traversal inside `30_Workflows` and code integration remain sequential and documented per file. |
| `VIDEO-PIPELINE-ENGINE-2026-05-19` | `docs/superpowers/plans/2026-05-19-video-pipeline-engine/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-video-pipeline-engine-2026-05-19.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-045-video-pipeline-engine.md` | `approved-for-implementation` | Continue from first unchecked/unfinished phase in plan README and phase docs. | Must not modify Audio-V2; VLM hooks depend on Plan B readiness. |
| `LLM-BACKEND-PLATFORM-2026-05-19` | `docs/superpowers/plans/2026-05-19-llm-backend-platform/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-llm-backend-platform-2026-05-19.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-044-llm-backend-platform-ollama-embed.md` | `approved-for-planning` | Planning/review only until user selects it in `ACTIVE_PLAN.md`. | New direct callers to `ollama_service.py` / `ollama_client.py` are forbidden before migration phases 41/42. |
| `GLOBAL-STORAGE-PROVENANCE-2026-05-19` | `docs/superpowers/plans/2026-05-19-global-storage-provenance/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-global-storage-provenance-2026-05-19.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-046-global-storage-provenance.md` | `approved-for-planning` | Planning/review only until prerequisites and `ACTIVE_PLAN.md` select it. | Wait for V2 stable and/or Plan A/B prerequisite readiness. |
| `PB-STUDIO-BUGFIX-2026-05-23` | `docs/superpowers/synthesis/bug-hunt-2026-05-23.md` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-bugfix-2026-05-23.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-051-bugfix-plan-2026-05-23.md` | `approved-for-implementation` | Phase 0 done; work F-1..F-30 (B-333..B-362) in plan phase order, one task at a time. | Autonomous run cannot click GUI: GUI fixes stay `code-fix-pending-live-verification`. Audio-V2 must not be modified. |
| `PB-STUDIO-INTEGRATION-SIDE-EFFECTS-2026-05-23` | `C:\Users\David Lochmann\.gemini\antigravity-cli\brain\a60377cf-6e1e-49a6-84f9-ee4b2feac695\implementation_plan.md` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-integration-sideeffects-2026-05-23.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-051-bugfix-plan-2026-05-23.md` | `approved-for-implementation` | Task 2: Export-NVENC absichern (Befund 1) | None |

## Agent Rule

Ein Agent darf nur an einem Plan arbeiten, wenn:

1. Der Plan in dieser Registry steht.
2. `docs/superpowers/ACTIVE_PLAN.md` genau diesen Plan als aktiven Fokus nennt oder explizit `blocked-needs-user-selection` meldet und der User gerade diesen Governance-/Auswahl-Fix beauftragt hat.
3. Der Registry-Status Implementierung erlaubt (`approved-for-implementation`, `in_progress`, `code-complete-live-pending` fuer Verifikation/Fix-Folge).
4. Der Vault-Mirror und die Decision existieren, ausser der Registry-Status ist `draft`.
5. Die naechste Task aus dem Plan selbst oder aus dem Vault-Living-Plan eindeutig bestimmbar ist.

Wenn eine Bedingung fehlt: stoppen, Befund melden, User-Entscheidung abwarten.

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
| `BRAIN-V3-NVIDIA-2026-05-04` | `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\brain-v3-plan-audit-2026-05-05.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-033-brain-v3-plan-adoption.md` | `code-complete-live-pending` | Read `06_PHASES.md`; continue only from first phase/task not live-verified in vault. | Phase/status drift exists between code-complete and live-verified state. |
| `SCHNITT-WORKSPACE-REDESIGN-2026-05-09` | `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-041-only-user-authorized-changes.md` | `code-complete-live-pending` | Phase 12 live verification / user confirmation path. | `status: fixed` remains user-only after full live workflow. |
| `SCHNITT-USABILITY-WIRING-REBUILD-2026-05-13` | `docs/superpowers/plans/2026-05-13-schnitt-usability-wiring-rebuild/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\functional-test-schnitt-b310-2026-05-13.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-041-only-user-authorized-changes.md` | `code-complete-live-pending` | Task 8 live verification, then open B-316..B-320 in bug order if user selects this plan. | B-310 not fixed until complete live workflow is confirmed. |
| `AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17` | `_sandbox_meta/plan.md` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-audio-analysis-v2-strict-sequential-2026-05-17.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-042-vault-per-substep-strict.md` | `blocked` | Reconcile `feat/audio-analysis-v2` against current branch before implementation. | Branch is 141 commits behind current and 5 commits ahead; contains `_sandbox_meta`, audio service, worker, and test changes. Do not merge blindly. |
| `VIDEO-PIPELINE-ENGINE-2026-05-19` | `docs/superpowers/plans/2026-05-19-video-pipeline-engine/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-video-pipeline-engine-2026-05-19.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-045-video-pipeline-engine.md` | `approved-for-implementation` | Continue from first unchecked/unfinished phase in plan README and phase docs. | Must not modify Audio-V2; VLM hooks depend on Plan B readiness. |
| `LLM-BACKEND-PLATFORM-2026-05-19` | `docs/superpowers/plans/2026-05-19-llm-backend-platform/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-llm-backend-platform-2026-05-19.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-044-llm-backend-platform-ollama-embed.md` | `approved-for-planning` | Planning/review only until user selects it in `ACTIVE_PLAN.md`. | New direct callers to `ollama_service.py` / `ollama_client.py` are forbidden before migration phases 41/42. |
| `GLOBAL-STORAGE-PROVENANCE-2026-05-19` | `docs/superpowers/plans/2026-05-19-global-storage-provenance/` | `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-global-storage-provenance-2026-05-19.md` | `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-046-global-storage-provenance.md` | `approved-for-planning` | Planning/review only until prerequisites and `ACTIVE_PLAN.md` select it. | Wait for V2 stable and/or Plan A/B prerequisite readiness. |

## Agent Rule

Ein Agent darf nur an einem Plan arbeiten, wenn:

1. Der Plan in dieser Registry steht.
2. `docs/superpowers/ACTIVE_PLAN.md` genau diesen Plan als aktiven Fokus nennt oder explizit `blocked-needs-user-selection` meldet und der User gerade diesen Governance-/Auswahl-Fix beauftragt hat.
3. Der Registry-Status Implementierung erlaubt (`approved-for-implementation`, `in_progress`, `code-complete-live-pending` fuer Verifikation/Fix-Folge).
4. Der Vault-Mirror und die Decision existieren, ausser der Registry-Status ist `draft`.
5. Die naechste Task aus dem Plan selbst oder aus dem Vault-Living-Plan eindeutig bestimmbar ist.

Wenn eine Bedingung fehlt: stoppen, Befund melden, User-Entscheidung abwarten.

# PB Studio — Gemini CLI Instructions

> **MANDATORY:** Read [`AGENTS.md`](./AGENTS.md) **completely** before any
> action. That file is the single source of truth for all agent behavior
> in this repository. The rules below are a safety-net excerpt — full
> rules in `AGENTS.md` always apply.

---

## ⛔ TOP RULE — 100 % HONESTY, ALWAYS, NO EXCEPTIONS

- Don't guess. Unclear = read / grep / test / ask.
- Smoke test green ≠ verified.
- Code edit ≠ bug fixed. Live verification first, then `fixed`.
- "Verified" / "fixed" / "works" are reserved words. Real live test only.
- On uncertainty, say it: "I don't know that for sure."
- No sugarcoating. Better briefly painful and honest than misleading.

---

## Hard requirements

- **Language of responses to the user: German only.**
- **Plan root:**
  `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/`
  Files `01_ARCHITECTURE.md` … `07_RISKS.md`. Execute strictly. No
  invention. Phase blueprints (e.g. `phase_3_brain_core.md`) under the
  same root are subordinate — if a blueprint contradicts `06_PHASES.md`,
  stop and ask.
- **Hardware: GTX 1060 6 GB, CUDA only (cuda:0).** Library without CUDA backend → CPU. Never install a different GPU backend.
- **Vault path: `C:\Brain-Bug\projects\pb-studio\`.** Every non-trivial
  action requires a vault entry — **per sub-task**, not bundled at
  phase end.
- **Predecessor phase / task `status: fixed`** is set by the **user**,
  not the agent. The agent may propose; the user confirms.
- **Repo synthesis ≠ vault synthesis.** Files under
  `docs/superpowers/synthesis/` must be mirrored to the vault before
  the next phase may begin.
- **One task at a time.** No parallel half-finished work, no commit spam.
- **Plan contradiction or unclarity: stop + ask.** Never decide alone.

---

## Before doing anything

1. Open `AGENTS.md` and read it fully.
2. Open
   `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md`
   and identify the current task. Cross-check against the phase
   blueprint (`phase_X_*.md`) under the same plan root if it exists.
3. Verify the predecessor task has `status: fixed` in the vault
   (`C:\Brain-Bug\projects\pb-studio\wiki\`). If only present in
   `docs/superpowers/synthesis/` of the repo, **stop and ask the user**
   to confirm verification status before mirroring to vault.
4. Only then: act.

If `AGENTS.md` is missing, stop and tell the user. Do not proceed.

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
- **Plan-Governance:** `AGENTS.md` is source of truth. Current plan
  authority comes from `docs/superpowers/PLAN_REGISTRY.md` plus
  `docs/superpowers/ACTIVE_PLAN.md`, not from a hardcoded plan list.
  Execute strictly, one task at a time, from one selected plan at a time.
  No invention.
- **Hardware: GTX 1060 6 GB, CUDA only (cuda:0).** Library without CUDA backend → CPU. Never install a different GPU backend.
- **Vault path: `C:\Brain-Bug\projects\pb-studio\`.** Every non-trivial
  action requires a vault entry — **per sub-task**, not bundled at
  phase end.
- **Obsidian Vault Brain tooling:** use
  `C:\Users\David Lochmann\plugins\obsidian-vault-brain\skills\obsidian-vault-brain\SKILL.md`
  and `C:\Users\David Lochmann\plugins\obsidian-vault-brain\scripts\vault_brain.py`
  for vault refresh/search/get/append. Refresh index before vault-state
  answers; read only directly relevant notes.
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
2. Open `docs/superpowers/PLAN_REGISTRY.md` and
   `docs/superpowers/ACTIVE_PLAN.md`.
3. Identify the one selected active plan. If `ACTIVE_PLAN.md` says
   `blocked-needs-user-selection`, do not start app-code work; ask the
   user to choose one plan unless the current request is explicitly
   governance/plan-selection work.
4. Cross-check the current task against the selected plan, its Registry
   row, its Decision file, and its Vault living-plan mirror.
5. Verify the predecessor task has `status: fixed` in the vault
   (`C:\Brain-Bug\projects\pb-studio\wiki\`). If only present in
   `docs/superpowers/synthesis/` of the repo, **stop and ask the user**
   to confirm verification status before mirroring to vault.
6. Only then: act.

If `AGENTS.md` is missing, stop and tell the user. Do not proceed.

## How to choose current task

Use the same sequence as `AGENTS.md`: Registry -> Active Plan -> selected
repo plan -> Vault mirror -> Decision file -> next unambiguous task. If
`ACTIVE_PLAN.md` is `blocked-needs-user-selection`, ask for one plan before
product/app-code work.

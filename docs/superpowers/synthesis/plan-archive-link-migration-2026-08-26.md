# Superseded Plan Archive and Link Migration — 2026-08-26

Status: complete

## Scope

- 12 Registry-`superseded` files moved from `docs/superpowers/plans/` to
  `docs/superpowers/archive/superseded-plans/`.
- One external Gemini source copied byte-identically into same archive.
- Registry and exact incoming Repo/Vault path references migrated.
- Historical plans received no artificial new semantic links.

## Preserved authority

- Active Masterplan stayed under `docs/superpowers/plans/`.
- Paused exhaustive audit plan stayed under `docs/superpowers/plans/`.
- Six files not registered as `superseded` were not moved.

## Verification

- Old migrated plan-path hits: 0.
- Superseded Registry entries still under `plans/`: 0.
- All 34 Registry rows: `repo_path`, `vault_mirror`, `decision` exist.
- Gemini source/archive SHA-256 identical:
  `DEAFECFFF784D6523894DB1DF01FE54729DFBB4343F9289525B0D490F29AB0DC`.
- No product code changed; no app test required.

# B-910 — Default-Pacingprofil synchron

Status: `code-fix-pending-full-suite-and-live`

## Root Cause

B-842 registrierte `w_roter_faden: 1.0` nur in `DEFAULT_WEIGHTS`. Vollabgleich
zeigte zwei weitere stale YAML-Werte: `w_style: 0.15` und `w_collision: 0.10`
ueberschrieben `4403ccd`-Code-Defaults `0.30`/`0.20`. Default-Profil machte
weiche-Uebergang-Fixes teilweise unwirksam.

## Fix

- `w_style: 0.30`
- `w_collision: 0.20`
- `w_roter_faden: 1.0`
- Golden-Baseline per geschuetztem Generator aktualisiert.

## Verifikation

- Config-RED nach erstem Keyfix legte Wertedrift offen.
- Config+Golden: `23 passed in 1.10s`.
- Golden chosen Clip-/Scene-IDs unveraendert; nur beabsichtigte Contributions
  und daraus folgende Scores geaendert.
- Vollsuite und echter Auto-Edit-Livepfad pending.

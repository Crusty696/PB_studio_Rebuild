# B-913 — Brain-Gateway Vision-Learn-Bypass behoben (2026-08-28)

status: code-verified-no-gui-live

## Root Cause (verifiziert)

Commit `50ce61d fix(B-897)` fuehrte `normalize_brain_learn_params()` ein und
routete in `execute_gateway_response()` JEDE `brain_learn_note`-Anfrage durch
diese Funktion. `normalize_brain_learn_params` validiert hart mit
`_validate_params("brain_learn_note", params, "chat")` — der uebergebene
`mode` (z. B. `"vision"`) wurde nie mehr gegen die Mode-Allowlist geprueft.
Folge: `mode="vision"` + `allow_learn=True` fuehrte einen Schreibvorgang aus,
obwohl `_VISION_ACTION_PARAMS` kein `brain_learn_note` enthaelt (B-738/D-083:
Vision strikt read-only).

Beweis: identische 6 Failures auf Basis `55565d1` (vor Brain-Cleanup);
`git log -S normalize_brain_learn_params` zeigt Einfuehrung exakt in `50ce61d`.

## Fix

`services/brain_gateway.py`, `execute_gateway_response()`:
`normalize_brain_learn_params` nur noch bei `mode == "chat"`; jeder andere
Modus laeuft durch `_validate_params(action, params, mode)` und wird fuer
`brain_learn_note` mit `Aktion 'brain_learn_note' ist im vision-Gateway nicht
erlaubt` abgelehnt (sichtbares `brain_gateway_rejected`).

## Zweite Ursache der roten Tests (Test-Staleness, kein Produktbug)

`50ce61d` band zusaetzlich `_ollama_model` als Instanzattribut des
`OrchestratorAgent` (`__init__` setzt es). 5 Tests in
`tests/test_services/test_b738_brain_gateway.py` bauen den Orchestrator via
`OrchestratorAgent.__new__` ohne `__init__` und setzten das Attribut nicht →
`AttributeError: '_ollama_model'`. Fix: `orch._ollama_model = None` an den 3
Konstruktionsstellen ergaenzt (eine Stelle hatte es bereits).

## Verifikation

- Vorher: `6 failed, 29 passed` (Repro exakt wie B-913-Bugfile).
- Nachher: `35 passed in 1.63s` (`tests/test_services/test_b738_brain_gateway.py`).
- `py_compile` beider Dateien PASS.
- Kein Live-ChatDock-/Vision-Lauf in dieser Task → kein `fixed`-Claim.

## Grenzen

Echter Vision-/ChatDock-Livepfad mit Ollama bleibt offen (spaetes Endgate
gemaess Uservorgabe 2026-08-26/27).

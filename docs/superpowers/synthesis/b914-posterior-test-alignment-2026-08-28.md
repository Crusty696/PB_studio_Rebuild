# B-914 — Posterior-Integrationstest an B-895-Vertrag angeglichen (2026-08-28)

status: agent-fixed-await-user

## Root Cause (verifiziert)

`test_integration_clicks_change_posterior` erwartete die alte
WeightStore-Semantik von vor B-895: nackter Beta-Posterior auf 0..1-Skala
(`(α+1)/(α+β+2) = 0.96875`). Seit `f4fb1a0 fix(B-895)` liefert
`get_posterior_mean` das effektive Gewicht als Multiplikator um den
Cold-Start-Wert (`posterior 0.5 = 1x`, `1.0 = 2x`). Beobachteter Ist-Wert
`2.3249999999999997` ist exakt `1.2 (kick_weight-Cold-Start) × 2 × 31/32`
— das Produkt verhaelt sich vertragskonform, nur der Test war stale.
Die uebrigen Tests derselben Datei (Zeilen 177/192/209) waren bereits auf
den neuen Vertrag nachgezogen; nur der Integrationstest fehlte.

## Fix

Nur Testdatei `tests/test_services/test_brain_v3_brain_core.py`:
Erwartungen auf `cold × 2 × posterior` umgestellt, Docstring korrigiert,
Neutral-Erwartung auf `≈ 1x Cold-Start` statt `≈ 0.5`. Kein Produktcodeedit.

## Verifikation

- Vorher: `1 failed` (`assert 1.3562… < 1e-09`).
- Nachher: `tests/test_services/test_brain_v3_brain_core.py` +
  `tests/test_services/test_b895_weightstore_transition.py` zusammen
  `44 passed in 3.92s`.

## Grenzen

Test-only-Fix; es gibt keinen separaten Live-App-Pfad fuer diesen
Testvertrag. `fixed`-Marker bleibt Userrecht.

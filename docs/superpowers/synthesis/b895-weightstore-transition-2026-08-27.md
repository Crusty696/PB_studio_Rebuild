# B-895 WeightStore-Uebergang — 2026-08-27

Status: `code-fix-pending-live-verification`

## Root Cause

Bis n=9 kam achsenspezifischer Cold-Start-Wert auf heterogener
TriggerSettings-Skala zurueck. Ab n=10 ersetzte ihn harter Beta-Posterior auf
0..1-Skala. Scorer verwendete beide als relative Achsengewichte.

## Codefix

Posterior wirkt als 0x..2x-Multiplikator um Cold-Start-Gewicht. Vorhandene
Buckets werden Level 0 bis spezifisch mit `min(n/10,1)` ineinander geblendet.
DB, Schema und Schreibpfad bleiben unveraendert.

## Direkte Verifikation

- `py_compile`: PASS.
- Schwellen-, Posterior- und Backoff-Vertraege: `6 passed`.
- Kein breiter Testlauf, kein echter App-/Auto-Edit-Livepfad; gesammelt am
  Ende der userautorisierten Fixwelle.

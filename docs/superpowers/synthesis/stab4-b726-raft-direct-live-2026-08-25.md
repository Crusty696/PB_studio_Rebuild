# STAB-4 / B-726 RAFT-Direktpfad unter Execution-Lease

Datum: 2026-08-25
Status: agent-complete; kein neuer Codefix

## Echter Direktpfad

- Oeffentliche Service-API `compute_motion_scores()` mit realem lokalem
  HEVC-10-Bit-Video und einer 8-Sekunden-Szene ausgefuehrt.
- RAFT Small aus lokalem Torch-Cache real auf NVIDIA GeForce GTX 1060 / `cuda:0`
  geladen. Ergebnis `motion=0.8859`, `motion_is_fallback=false`.
- Instrumentierter Produktions-Lease `motion_scores` hielt Load, drei
  RAFT-Inferenzen, Cleanup und `ModelManager.unload_raft()` zusammen fuer
  7034.5 ms.
- Zweiter Thread versuchte waehrenddessen `GPU_EXECUTION_LOCK` non-blocking:
  220 Versuche blockiert, 0 Erwerbungen waehrend Lauf. Nach Rueckkehr war
  Lock sofort wieder erwerbbar.

## Kleinste Regression

`tests/test_services/test_b726_motion_execution_lock.py`:
`2 passed in 0.81s`.

## Ehrliche Grenze

B-726-Direktpfad ist real auf CUDA und unter Konkurrenz belegt. Er besitzt
selbst keinen Cancel-Parameter. Im Bugfile genannter kombinierter
RAFT-/GPU-/Cancel-Lauf gehoert zum separaten D-078/STAB-4-Endgate; ebenso
bleibt Kalt-VRAM-Gesamtgate aus B-723 rot (+813 statt maximal +512 MiB).
Vault-Userstatus `fixed` blieb unangetastet.

Naechster Task:
`STAB-4 / Ollama-Prozessbesitz und Shutdown-/Cancel-/Projektwechsel-Races live verifizieren`.

# Verify log: b686-vram-coordination (Variant C, iteriert)

Phase 5. conda-Python C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe,
alle Laeufe `-p no:cacheprovider`. Vom Hauptagenten geschrieben (Verifier-Subagent
hing an Redirect-Pufferung; die Laeufe wurden selbst ausgefuehrt).

## Baseline (main) vs. Worktree — betroffene Bereiche
Filter: `-k "embedding_scheduler or brain_v3 or thread_safety or b627 or b684 or b679 or b686 or video"`

| Branch | Ergebnis |
|---|---|
| main (Baseline) | 401 passed, 5 skipped (443 s) |
| sandbox/b686-vram-coordination | **411 passed, 5 skipped** (593 s) |

Delta = **+10** — exakt die neuen B-686-Tests. **Keine Regression**, gleiche Skip-Zahl.
(Bestehende embedding_scheduler/brain_v3/thread_safety/b627/b684/b679/video-Tests
weiterhin gruen -> Bestandsfixes intakt.)

## Deadlock-Nachweis (scharf)
- `test_control_bad_ordering_deadlocks`: Kontroll-Lauf (Free INNERHALB Load-Lease,
  Mid-Barrier erzwingt Interleaving) **deadlockt** wie erwartet (Threads bleiben
  alive nach 6 s) -> der Test ist scharf.
- `test_safe_ordering_does_not_deadlock`: sicheres Ordering (Free VOR Lease)
  laeuft 40 Iterationen durch. PASS.
- `test_worker_pause_is_before_any_gpu_lease`: Source-Anker — in BEIDEN Worker-run()
  steht der Pause-Aufruf vor jeder gpu_resource_lease/gpu_execution_lease/acquire. PASS.

## P1-Fix verifiziert
- `test_nested_pause_gate_stays_closed_until_all_resume`: 2x pause -> 1x resume ->
  Gate BLEIBT zu; erst nach dem 2. resume offen. PASS (Refcount).
- `test_resume_underflow_is_safe`: resume ohne pause -> Zaehler bleibt 0. PASS.

## Verdikt pro Akzeptanzkriterium
| # | Kriterium | Verdikt |
|---|---|---|
| 1 | Keine Embedder-Residenz waehrend Analyse | **deferred-to-live** — Design (Free+Gate+Refcount) belegt; reale VRAM-Nicht-Residenz braucht nvidia-smi unter echtem Parallel-Import auf der GTX 1060 (User-Live-Verify) |
| 2 | Keine neue Lock-Inversion LOAD->EXECUTION | **PASS** — statischer Beweis (Skeptic bestaetigt P0=keine) + Deadlock-Stress + Source-Anker |
| 3 | Bestandsfixes intakt (B-684/B-679/B-554/AUD-35/H-25) | **PASS** — 401 Baseline-Tests weiter gruen, model_manager.py unberuehrt |
| 4 | GPU-Hartregel (cuda:0, kein Backend-Wechsel) | **PASS** — nur Free/Reload auf cuda:0 |
| 5 | Concurrency-Stress ohne Deadlock | **PASS** — safe-ordering-Stress + nested-pause-Test |

## Offen fuer User-Live-Verify (Pflicht, ersetzt keinen statischen Beweis)
Realer Import (Solo_Natur-Video + Crusty-Mix) parallel zu Pipeline-Analyse,
nvidia-smi mitloggen: waehrend Analyse KEINE Embedder-Residenz, kein CUDA OOM,
Embeddings laufen nach Analyse weiter.

## Noch nicht gelaufen
Volle Suite (3000+ Tests) im Worktree — empfohlen beim Apply (Phase 7) im Haupt-Repo
nach Merge, da ~30 min unter aktueller Maschinen-Last.

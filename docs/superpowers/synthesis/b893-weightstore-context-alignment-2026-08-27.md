# B-893 WeightStore-Context-Angleichung — 2026-08-27

status: code-fix-pending-live-verification
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
task: PACING-PRIORITAET / B-893 WeightStore Motion-/Pace-Kontext an produktiven Reranker angleichen

## Root Cause

Produktiver Brain-V3-Reranker baute einen gemeinsamen CutContext vor dem
Kandidaten-Loop: Motion war konstant `medium`, Default-Pace kam aus
`recent_cuts`. Feedback rekonstruierte dagegen Motion des gewaehlten Clips und
Pace aus dem gespeicherten BPM. Spezifische WeightStore-Buckets wurden somit
beschrieben, spaeter aber nicht mit denselben Schluesseln gelesen.

## Aenderung

- Reranker-Produktdefault nutzt BPM-Pace wie Feedback.
- Jeder Kandidat erhaelt unmittelbar vor Scoring sein Motion-Quartil.
- Fehlender Motionwert bleibt neutral `medium` wie Feedback-Fallback.

## Verifikation

- RED vor Fix: Context-Key-Level 3 wich ab (`motion=medium` gegen `motion=low`).
- `py_compile` PASS.
- `pytest tests/test_services/test_b893_weightstore_context.py -q`:
  `1 passed in 0.93s`.
- Test vergleicht alle sechs Context-Keys fuer zwei Kandidaten und BPM 140
  direkt mit `build_cut_context_from_decision()`.

## Offene Grenze

Kein echter Auto-Edit-UI-Lauf nach Patch. Lokale STAB-3-Artefakte enthalten
keine wiederverwendbare Automation; aktive Tools koennen fremde Windows-App
nicht klicken. Code fix in place, live test missing. B-893 bleibt unfixed.

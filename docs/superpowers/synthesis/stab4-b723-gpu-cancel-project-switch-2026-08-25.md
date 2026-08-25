# STAB-4 / B-723 GPU-, Cancel- und Projektwechsel-Livepfad

Datum: 2026-08-25
Status: agent-complete; STAB-4-Gesamtgate VRAM offen

## Codefix

`StemSeparationWorker` leert bei einer Exception die abgewickelten Traceback-
Frames noch innerhalb `GPU_EXECUTION_LOCK`, fuehrt dort `gc.collect()` aus und
leert danach den CUDA-Cache. Damit koennen CUDA-Tensorreferenzen aus dem
Service-Frame nicht erst nach Lock-Freigabe zerstoert werden.

## Deterministischer Beleg

- RED vor Fix: Modellattrappe wurde bei `lock.held == False` zerstoert.
- GREEN nach Fix: Modellattrappe wurde bei `lock.held == True` zerstoert.
- B-723-Fokus: `3 passed in 2.65s`.
- PyCompile und Ruff auf beiden betroffenen Dateien gruen.

## Echter Produktpfad

- GTX 1060 / `cuda:0`; htdemucs; reale 337.1-s-Audiodatei.
- Projekt-Open waehrend laufendem Task korrekt blockiert.
- TASKS-Cancel waehrend Chunk 1/12: kooperativer Abbruch; Worker und
  Analysis-Status auf kanonischem Cancel-Pfad; App responsiv.
- Nach Taskende Projektordner-Dialog wieder erreichbar; ohne Wechsel beendet.
- DB `quick_check=ok`; Baseline-Zaehler unveraendert; Stem-Status
  `error` plus `error_message='cancelled'` entspricht B-820-Vertrag.

## Offene Grenze

Kalte GPU-Baseline 338 MiB. 81 Sekunden nach Cancel: 1151 MiB/0 %, Ollama
leer. Damit +813 MiB und STAB-4-Gesamtgrenze `Baseline +512 MiB` rot. Ein
isolierter Torch-Prozess belegte selbst bei `allocated=0/reserved=0` nach
erstem CUDA-Tensor dauerhaft rund 371 MiB bis Prozessende. B-723-Lockordnung
ist belegt; die kalte Gesamtgrenze ist fuer In-Process-CUDA nicht bestanden
und bleibt fuer STAB-4 offen. Kein `fixed`-Marker durch Agent gesetzt.

## Naechster sequenzieller Task

`STAB-4 / B-725 CPU-/Copy-Konvertierung ausserhalb GPU-Lease live verifizieren`.

# STAB-1 DB-Baseline — 2026-07-27

Status: `pass` für Baseline-/Backup-Teilgate. B-727-Negativkontrollen und
STAB-1-Gesamtgate bleiben offen.

## Bindung

- Commit: `d60c3e15885d91e6aa01ae3e425f87e07f31df91`
- Canonical Python: 3.10.20
- Run: `20260727T234100+0200-stab1-baseline-d60c3e1-full`
- Manifest:
  `C:\Users\David_Lochmann\AppData\Local\PBStudioStability\20260727T234100+0200-stab1-baseline-d60c3e1-full\manifest.json`

## Ergebnis

- 13 aktive geschützte SQLite-DBs erfasst.
- DB/WAL/SHM zuerst als RAW-Bundle extern kopiert.
- Originale nie per SQLite geöffnet.
- Quellen innerhalb Capture vor/nach byte-identisch.
- Erster und zweiter Capture byte- und logisch identisch.
- 13/13 Analysen der WAL-konsolidierten Kopien: `quick_check=ok`.
- Schema-/Migration-/Tabellenzählungs-/logische Inhalts-Hashes im Manifest.
- 38 Backup-/Analyseartefakte im kanonischen Run.

## Prozessgrenze

AirLLM lief parallel aus `C:\Users\David_Lochmann\airllm`; `psutil` zeigte
keine PB-Studio-/DB-Datei offen. Prozess wurde nicht beendet. Ein fremder
Base-Python-Prozess installierte kurzzeitig Torch cu124 per `pip
--force-reinstall`; er war beim kanonischen Capture beendet. PB-Studio-Env
blieb bei Torch 1.12.1+cu113. Falls fremde Installation für PB Studio gedacht
war, verletzt sie die Hardwarevorgabe und muss außerhalb dieses Root-Cause-
Pakets geklärt werden.

## Ehrliche Grenzen

- Nur Baseline-/Backup-Teilgate bestanden.
- B-727 acht Negativkontrollen noch nicht vollständig implementiert.
- Keine Import-/Ruff-/Bandit-/Alembic-/Vollsuite durchgeführt.
- Keine Live-App-Verifikation.
- Kein Status `fixed`.

Nächster Schritt: B-727 acht Negativkontrollen als RED-Beweis ergänzen.

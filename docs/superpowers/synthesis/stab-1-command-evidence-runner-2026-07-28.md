# STAB-1 Command-Evidenzrunner — 2026-07-28

Status: code-complete, Current-Gate-Einsatz offen.

## Umfang

- `run_evidenced_command`: geschützte DBs vor/nach Befehl roh sichern.
- DB/WAL/SHM byteweise und konsolidierten logischen Inhalt vergleichen.
- Befehl, Zeiten, Exitcode, Prozesse, Logs, Artefakte und Grenzen als JSON.
- `tools/stability_run.py`: reproduzierbare CLI für folgende Pflichtgates.

## Beweise

- RED: fehlende Funktion, danach fehlende CLI.
- Fokus: `6 passed`.
- `py_compile`: Exit 0.
- fokussiertes Ruff: `All checks passed`.
- Mutationstest: Command-Exit 0, Manifest trotzdem `fail`.

## Grenzen

- Noch kein Current-Gate über Runner ausgeführt.
- Kein Current-Vollsuitenlauf.
- Keine App-/GUI-Liveverifikation.
- Keine Produkt-API, Library oder Produktlogik geändert.

Nächste einzige Task nach Commit:
`STAB-1 Import-/Syntax-Smokes` über Current-Commit und Evidenzrunner.

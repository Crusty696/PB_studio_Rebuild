# STAB-1 Command-Evidenzrunner — 2026-07-28

Status: B-739 `code-fix-pending-live-verification`; Runnervertrag belegt,
Current-App-Gates offen.

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

- Syntax und Import wurden über Runner ausgeführt, gelten wegen B-739 nicht als
  abschließende Gatebelege.
- Kein Current-Vollsuitenlauf.
- Keine App-/GUI-Liveverifikation.
- Keine Produkt-API, Library oder Produktlogik geändert.

Nächste einzige Task:
`STAB-1 / B-739 Evidenzrunner-False-Pass`.

## B-739 Code-Follow-up — 2026-07-28

- Fail-closed Git-Preflight bindet tatsächlichen sauberen HEAD.
- Manifest/Logs entstehen vor Command; Capture-/Spawnfehler bleiben sichtbar.
- Initial-/Post-Discovery bildet Union inklusive Missing-/neuer DB-Pfade.
- Fehlende/gelöschte DB erzeugt keine `None`-/`consolidated.db`-Nebenfiles.
- Pre-/Post-Prozesssnapshot inklusive Ollama; Command-Descendants blockieren.
- Fokus: `19 passed`; echter detached Python-Child erkannt und kooperativ beendet.
- Syntax und fokussiertes Ruff: grün.
- Frühes Manifest-Skeleton, Source-Status und Post-CIM-Exception zusätzlich
  abgesichert.
- Historischer Runde-1-Stand; durch Runde 2, Commit und Finalreview superseded.

Genau nächste Task: B-739 committen, adversarial re-reviewen, Findings einzeln
schließen. Danach Syntax-/Import-Gates neu starten.

## B-739 Runde 2 / Finalreview — 2026-07-28

- Post-Command-Gitvalidierung.
- Vollständige Prozessinventur ohne Executable-Allowlist.
- Command-/Vanished-Parent-Prozessbesitz statt globalem Umgebungsrauschen.
- Probe- und Parent-PID-Reuse per CreationDate abgesichert.
- DB-`quick_check` verdictwirksam.
- Initial-Discovery schreibt blocked Manifest.
- Evidenzroot exakt extern; LOCALAPPDATA innerhalb Repo schreibt nichts.
- Fokus: `30 passed in 36.38s`.
- D-077 reduziert weitere Wiederholung: kein zweites Review.

Syntax/Ruff grün. Commit `c068169`.
Post-Commit-Evidenz `20260728T0214-b739-postcommit-0968eed`: pass,
Source vor/nach sauber, 13/13 existierende DBs byte-/logisch identisch,
13× quick_check ok, 0 Descendants, 0 neue command-owned Prozesse.

B-739: `code-fix-pending-live-verification`, kein `fixed`.
Nächste einzige Task: `STAB-1 / Import-/Syntax-Smokes`.

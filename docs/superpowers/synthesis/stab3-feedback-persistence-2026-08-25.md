# STAB-3 Feedback und Persistenz — 2026-08-25

status: agent-complete-await-user-marker
plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
task: STAB-3 / Gezieltes positives/negatives Feedback, Flush, kompletter App-Neustart

## Live-Beleg

- Isoliertes Stability-Projekt mit final gebundenem `mem_pacing_run #9`.
- Negatives Feedback: Decision 795, Scene 127, gespeicherte Bewertung 1,
  Pattern `accept=0`, `reject=1`.
- Positives Feedback an anderem Clip: Decision 821, Scene 32, gespeicherte
  Bewertung 5, Pattern `accept=1`, `reject=0`.
- Nach Debounce, sauberem Shutdown und komplettem App-Neustart: 2
  Feedbackevents, 2 bewertete Decisions, 2 `mem_learned_pattern`, Summen
  `accept=1`/`reject=1`, 138 globale Achsengewichte.
- Projekt-DB und Weight-DB jeweils `quick_check=ok`; exakte Persistenz-
  Assertions nach Neustart gruen.

## Direkt gefundene und korrigierte Defekte

- B-889: parentloses Marker-Overlay verdeckte Clip beim Kontext-Hit-Test.
- B-890: parentlose QMenu/QDialog-Lebensdauer plus synchrone Referenzfreigabe
  im Qt-Signaldispatch korrelierte mit Windows Heap-Korruption `0xc0000374`.
- B-891: aktiver Pacing-Run wurde nach Projekt-/Audio-Rehydration nicht
  restauriert; globale Gewichte lernten, projektgebundene Patterns nicht.
- Produktcommits: B-889/B-890 `ed13280`; B-891 `2ed783f`.

Alle drei stehen `agent-fixed-await-user`; User-`fixed`-Marker unberuehrt.

## Gezielte Verifikation

- B-889 Fokus: Overlay-Hit-Test plus bestehender Child-Item-Vertrag gruen.
- B-890 Fokus: Timeline-Ownership und verzögerte Freigabe gruen.
- B-891 Fokus: Async-Combo, manueller Audio-Wechsel und None-Clear gruen.
- Geaenderte Produkt-/Testdateien: `py_compile`, fokussiertes Ruff und
  `git diff --check` gruen.
- Kein breiter Testsweep; gemaess Userentscheidung bis spaetes Finalgate
  verschoben.

## Beleggrenze

- Exakte native Instruktion fuer B-890 nicht bewiesen: Windows lieferte
  WER-Bericht, aber keinen Dump. Root-Cause-Kandidat ist durch Lifecycle-
  Vertrag, RED/GREEN und stabilen Livepfad stark belegt.
- Beim Combo-Aufbau erscheinen kurz Bindungen fuer Zwischen-Audios; finale
  sichtbare Auswahl bindet korrekt Audio 1 an Run 9. Kein Zusatzfix ohne
  eigenen Planauftrag.
- Kein STAB-3-Phasenmarker gesetzt. User entscheidet `fixed`.

## Naechste einzige Task

`STAB-3 / Auto-Edit B mit identischen Eingaben; erklaerbare Aenderung nur
adressierter Beitraege und Kandidatenrangfolge beweisen`.

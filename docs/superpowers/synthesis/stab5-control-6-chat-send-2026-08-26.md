# STAB-5 Control #6 — Chat-Senden

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

`ChatDock.btn_send` → echter Qt-Click → `ChatDock._on_send()` →
Userzeile sichtbar + Input geleert → ohne Agent sichtbarer Fehler.

## Evidence-Abgleich

- Frühere Candidate-Refs waren falsch zugeordnet:
  - B-417 prüft späte Workerresultate mit Fake-Button.
  - B-020 prüft PBWindow-/ChatDock-Lifetime.
- Auch ältere als E2E bezeichnete Dateien enthalten keinen belastbaren
  Send-Click-/Ergebnisbeleg.

## Ergebnis

- Neuer fokussierter Qt-Test nutzt echten ChatDock und echten Send-Button.
- Nichtleerer Text erscheint als Usernachricht; Input wird geleert.
- Ohne Agent erscheint sichtbar `Kein Agent konfiguriert.`; Button bleibt aktiv.
- Bekannter AiStatusDot-Teardown wurde nur im Test durch stoppbaren QLabel
  isoliert; Send-Control und Handler bleiben real.
- Erster Lauf: Assertions passierten, Prozess-Teardown Exit 1.
- Nach Harness-Isolation: `1 passed in 0.69s`, Prozess Exit 0.
- Drei geführte Read-only-Prüfer fanden keinen Produktdefekt.
- Kein Produktcode geändert.

## Offen

- Agent-/TaskManager-/LLM-Workerpfad nicht ausgeführt.
- Kein echter PBWindow-App-Livepfad; daher nicht `fixed`.

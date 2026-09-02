---
title: Waechter - Bilanz Loop 4 und Konfiguration Loop 5
status: laufend
created: 2026-09-02 17:40
---

# Waechter - Loop 5

## 1. Bilanz Loop 4

| Kennzahl | Loop 1 | Loop 2 | Loop 3 | Loop 4 |
|---|---|---|---|---|
| Neue Funde | 4 | 2 | 2 | 2 (B-1001-Verweis, `.gitignore`-Luecke) |
| Reparierte Bugs | 1 | 2 | 2 | **8** |
| Neue Pruefwerkzeuge | 0 | 2 | 0 | 2 |
| Neue Tests | 4 | 4 | 5 | 14 |
| Eigene Verfahrensfehler | 6 | 3 | 2 | 5 |

**Reparierte Bugs in Loop 4:** B-861, B-862, B-863, B-864 (Audit-Haertung), B-918, B-925,
B-839-Restluecke, B-958. Dazu der Harness-Defekt (`tasklist` ohne encoding) und die
`.gitignore`-Luecke.

**Die zehn "bestehenden" Bugs aus Loop 3:**

| Bug | Stand |
|---|---|
| B-861, B-862, B-863, B-864 | behoben, Commit `c47df36` / `036e914` |
| B-918, B-925, B-839-Rest | behoben, Commit `e8147da` |
| B-958 | behoben, Commit `1a362ce` (Schaden; Ursache offen) |
| **B-923** | offen - Produktentscheidung, eine Timeline-Vorschau existiert nicht |
| **B-870** | offen - Crash ohne Repro, nicht auf Kommando herstellbar |

## 2. Was Loop 4 ueber das Vorgehen gelernt hat

**Der wichtigste Satz:** Bei B-958 habe ich zwei Stunden in die Ursache gesteckt und dabei
uebersehen, dass sich der Schaden unabhaengig davon beheben laesst. Erst die Userfrage
"warum offen lassen?" hat das sichtbar gemacht.

**Regel fuer Loop 5 und danach:** Bei jedem Bug zuerst fragen, ob sich der **Schaden** beheben
laesst, auch wenn die **Ursache** unklar bleibt. Beides ist wertvoll, aber die Reihenfolge ist
nicht beliebig - ein behobener Schaden blockiert die Ursachensuche nicht, umgekehrt schon.

**Zweite Lehre, teuer bezahlt:** Zwei Eingrenzungslaeufe waren wertlos, weil `--ignore` auf ein
Verzeichnis die explizite Dateiangabe sticht und der Zieltest nie gesammelt wurde. Aufgefallen
nur, weil die Messdatei leer blieb. Seitdem vor jedem Lauf:
`--collect-only | grep -c <ziel>`.

**Dritte Lehre:** Ein gueltiges Einzelexperiment ist noch keine Ursache. `app.exit(0)` erzeugt
nachweislich `rc=-1` - im Testlauf ruft aber niemand `exit()`. Ich habe vom moeglichen Weg auf
den tatsaechlichen geschlossen.

## 3. Blindstellen nach Loop 4

- **B-958-Mechanismus unerklaert.** Zwei weitere Testdateien nutzen `QEventLoop.exec()` und
  koennen still nichts pruefen: `test_ollama_chat_dock_e2e.py`,
  `test_b321_completion_refresh_debounce.py`.
- **B-1001 steht zweimal im Code**, ohne dass es diese Bug-ID gibt. Nicht korrigiert - welche
  Nummer richtig waere, ist unbekannt.
- **Die 53 Bugs mit `agent-fixed-await-user`** und `agent-live-verified-await-user-marker` warten
  weiterhin auf die Userfreigabe. Dort ist die Arbeit getan.
- **B-923** braucht eine Produktentscheidung, keine weitere Messung.

## 4. Konfiguration Loop 5

**Werkzeuge:** `pruefstand` (jetzt neun Pruefer), `consulting-team`, `caveman ultra`, dazu
Pruef-Agenten parallel.

| Schritt | Inhalt |
|---|---|
| 5.1 | Voller Pruefstand-Lauf mit Projekt - Gesamtbeleg nach allen Fixes. Laeuft. |
| 5.2 | Baseline neu aufnehmen: b353 ist gruen, die alte Baseline von 19 roten Tests stimmt nicht mehr. |
| 5.3 | `fix_ohne_test` auf die sechs verbleibenden IDs anwenden (B-1001, B-922, B-913, B-907, B-959, B-961) und je entscheiden: Test nachliefern oder Kommentar korrigieren. |
| 5.4 | `commit_audit` ueber die gesamte Historie laufen lassen, nicht nur 60 Commits. |
| 5.5 | Die zwei uebrigen `QEventLoop.exec()`-Tests auf `processEvents()` umstellen - dieselbe Immunitaet wie b353. |

**Bewusst ausgelassen:** B-870 (nicht herstellbar), B-923 (Produktentscheidung), B-960/B-961
(Routing/Registry - Userentscheidung steht aus).

## 5. Abbruchkriterium

Loop 5 ist erledigt, wenn der Pruefstand-Bericht vorliegt, die Baseline den aktuellen Stand
abbildet und die sechs Bug-IDs ohne Test einzeln entschieden sind.

## 6. Wie der Waechter praeziser geworden ist

| Beobachtung | Konsequenz |
|---|---|
| 8 Reparaturen in Loop 4 gegen 1-2 in den Loops davor | Der Wechsel von "suchen" zu "abarbeiten" hat sich gelohnt; Loop 5 bleibt dabei |
| Zwei wertlose Laeufe durch `--ignore` | Sammel-Check ist ab jetzt Teil jedes Laufbefehls, nicht Kuer |
| Schaden vs. Ursache bei B-958 | Neue erste Frage bei jedem Bug: laesst sich der Schaden isoliert beheben? |
| Zwei Tests deckten mehr auf als ihren Anlass (B-964, B-861) | Quellcode-Guards lohnen sich - sie finden die zweite Fundstelle, die im Bugfile fehlt |

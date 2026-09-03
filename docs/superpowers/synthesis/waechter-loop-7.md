---
title: Waechter - Bilanz Loop 6 (gemessen) und Konfiguration Loop 7
status: laufend
created: 2026-09-03 10:30
updated: 2026-09-03 17:45
---

# Waechter - Loop 7

## 1. Bilanz Loop 6 — gemessen, nicht geschaetzt

| Kennzahl | Loop 4 | Loop 5 | Loop 6 |
|---|---|---|---|
| Neue Funde | 2 | 4 | **8** (B-965 bis B-972) |
| Reparierte Bugs | 8 | 4 | 5 |
| Neue Pruefwerkzeuge | 2 | 2 | 1 (`mutationsprobe`) |
| Werkzeug-Praezisierungen | 1 | 1 | **11** |
| Neue Tests | 14 | 27 | **~140** |
| **Eigene Messfehler im Werkzeug** | 0 | 0 | **7** |

### Reparierte Bugs mit Beleg

| Bug | Was | Beleg |
|---|---|---|
| B-965 | `StemWorkspace.destroy_workspace()` ohne Aufrufer — PeakWorker-Threads liefen beim App-Ende weiter | Live-Log `18:51:53 closeEvent: StemWorkspace endgueltig geschlossen` |
| B-967 | EDL-Reasoning fragte Ollama mit leerem Modellnamen | End-zu-End: `''` → `gemma3:4b`, 28 EDL-Eintraege in 107.4 s |
| B-968 | Kommentar behauptete das Gegenteil des Codes | `git log -S` |
| B-969 | Testdatei konnte strukturell nicht rot werden — 10 dauergruene Tests, 4 echte Abweichungen verdeckt | Gegenprobe: absichtlich falsche Behauptung → exit 1 |
| B-970 | Dauerfehler beim Sammeln + zwei verwaiste Aufrufe | `1 error` → `1 skipped`, Skript laeuft durch (98 Pruefungen) |

**Dokumentiert ohne Aenderung:** B-966 (vier DB-Spalten ohne Produktivnutzung) — Userentscheidung.

### Abgesicherte, aber ungedeckte Reparaturen (per Mutationsprobe gefunden)

B-971 (B-888, fuenffach), B-680, B-800, B-656, B-821 (dreifach), B-797, B-972 (zwoelf Stellen),
B-633, B-604, B-005. Jede Abnahme durch dieselbe Probe belegt: unter Mutation rot, ohne gruen.

### Regressionslauf, sauber

`17 failed, 4910 passed, 57 skipped in 1746.88s (29:06)` — keine neuen roten Tests, kein `error`.

## 2. Die harte Lehre aus Loop 6: das Werkzeug frass den Loop

**Sieben Messfehler in `tools/mutationsprobe.py`**, jeder erst nach einem Lauf sichtbar:

| Nr | Messfehler | Folge |
|---|---|---|
| 1 | Sortierschluessel per Regex geschnitten | Syntaxfehler, 4 von 5 B-888-Stellen ungemessen |
| 2 | Zielauswahl bevorzugte ID-spezifische Tests nicht | `scorer.py:67` faelschlich UNGEDECKT |
| 3 | CRLF als LF zurueckgeschrieben | sechs Dateien dirty ohne Inhaltsaenderung |
| 4 | Guards trafen Kommentar / Log-String / Docstring | **viermal dieselbe Klasse**, jeweils falsches Ergebnis |
| 5 | Nativer Crash `0xC0000409` als Testfehler gewertet | B-891 faelschlich "gedeckt" |
| 6 | Lauf starb hart | zwei Produktivdateien blieben mutiert liegen |
| 7 | Baseline-Fehlschlaege als Deckung gewertet | `15 failed` waren die bekannten roten Tests |

**Das Missverhaeltnis in Zahlen:** `fix_ohne_test` kennt **589 Bug-IDs** im Produktivcode.
Gemessen wurden **19**. Die letzten drei Runden brachten **3 abgesicherte Stellen** gegen rund
**15 Werkzeugkorrekturen**.

*Ursache, offen benannt:* Aus "alles beweisen" habe ich abgeleitet, erst ein fehlerfreies
Messwerkzeug zu brauchen. Diese Ableitung war **meine eigene Entscheidung**, keine Anweisung des
Users — und sie hat den Loop in die Werkzeugpflege gezogen.

*Was dagegen getragen hat:* Die belastbarsten Funde des Loops (B-965, B-967) kamen aus
**Live-Laeufen der App**, nicht aus statischer Analyse. Genau das Vorgehen der Loops 1 bis 5.

## 3. Konfiguration Loop 7 — Werkzeug einfrieren, Live-Laeufe fahren

**Werkzeuge:** `pruefstand`, `mutationsprobe` (**eingefroren** — bleibt im Bestand, wird nicht
weiter ausgebaut), `consulting-team`, `caveman ultra`.

| Schritt | Inhalt | Abbruchkriterium |
|---|---|---|
| 7.1 | Live-GUI-Lauf mit `Erstlauf_Test_2026-08-30` ueber **alle** Workspaces, Aufzeichnung als Logdatei | Jeder Workspace einmal geoeffnet, jede ERROR-Zeile im Log einer Ursache zugeordnet |
| 7.2 | Jede unerklaerte ERROR-Zeile aus 7.1 wird ein Bugfile mit Reproduktionsweg | Keine ERROR-Zeile ohne Zuordnung |
| 7.3 | `log_audit` nach jedem Live-Lauf: Wiederholungen ueber der Schwelle, neue Takte unter 60 s | Keine neue Wiederholungsgruppe unerklaert |
| 7.4 | Die 42 IDs ohne jeden Testbezug (ID **und** Symbol fehlen in `tests/`) nach Schadensbild sortieren: ist es heute noch herstellbar? | Jede der 42 hat eine Entscheidung |
| 7.5 | `set_project()` in alle Mess-Skripte, die Projektdaten lesen | Kein Messlauf mehr gegen die leere Repo-DB |

**Bewusst ausgelassen:** weiterer Ausbau der Mutationsprobe (siehe Lehre oben), B-870 (ohne
Repro nicht herstellbar), B-923, B-960, B-961, B-966 (Userentscheidung steht aus), B-603
(Ursachenanalyse vor Test — ein Test wuerde sonst den Hard-Cut-Fallback als Sollverhalten
zementieren).

**Ungemessen und ausdruecklich nicht als gedeckt gezaehlt:** B-891
(`edit_workspace.py:943`), B-335 (`brain/scorer.py:52`, per Handprobe **ungedeckt**), B-371
(`pacing_service.py:1621`, `= None` nicht sinnvoll mutierbar).

## 3b. Bilanz Loop 7.1 — Live-GUI-Rundgang, gemessen

Aufzeichnung: `test-report/loop7/gui_rundgang.log`, Screenshots unter
`tests/qa_artifacts/loop7_*`.

| Geprueft | Log-Zeilen | ERROR | WARNING |
|---|---|---|---|
| 5 Workspaces (PROJEKT/MATERIAL ANALYSE/CONVERT/SCHNITT/EXPORT) | 84 | 0 | 0 |
| 4 SCHNITT-Sub-Tabs (Schnitt/Pacing Anker/Audio/Notizen) | 0 (loggt nicht) | 0 | 0 |
| 4 Panel-Tabs (CHAT/TASKS/LOG/Brain V3) | 3 | 0 | 0 |
| Einstellungen-Dialog + 3 Tabs + Verbindungstest 2x | 2 | 0 | 0 |
| 6 Studio-Brain-Tabs | 21 | 0 | 0 |
| Timeline generieren | 5 | 0 | 0 |

**Timeline-Lauf:** 161 Eintraege (160 Video + 1 Audio), 185 Beat-Marker,
185 Cut-Points, 337 s, Thumbnails geladen. Graph-Cockpit: 147 Knoten,
4402 Kanten.

### Zwei echte Funde

| Bug | Was | Stand |
|---|---|---|
| B-973 | `member_count` der Stil-Cluster um 46 zu hoch (105/66, 11/11, 29/22) | repariert, 12 Tests, Commit `e11fe45` |
| B-974 | 48 von 147 Szenen zeigen auf abgeschaltete Cluster | dokumentiert, Userentscheidung |

### Vier Kandidaten geprueft und aufgeloest — keine Bugs

| Kandidat | Aufloesung |
|---|---|
| `registered_paths=0` bei 161 Records | Lazy-Thumbnails vor der Anforderung; Screenshot zeigt geladene Thumbnails |
| Drei Zahlen fuer "Cuts": 185 / 161 / 160 | 185 Cut-Points, 161 Eintraege inkl. Audio, 160 Video-Clips. Zwei Schreiber des Labels (`edit_workspace.py:434` und `:836`) |
| `5x get_active_project_id(): Kein aktives Projekt` | kam VOR dem Auto-Resume, App lief noch auf der leeren Boot-DB. Danach keine mehr |
| B-053-Fallback auf `project_id=1` | Boot-DB nachgemessen: 0 Projekte, 0 Tracks, 0 Clips, 0 Timeline-Eintraege. Nichts geschrieben |

### Eine Beobachtung ohne Reparatur

Das Wort "Cuts" bezeichnet in zwei Labels zwei verschiedene Dinge: 185
Schnittkandidaten gegen 160 Clips. Fuer den Nutzer irreführend. Umbenennen ist
per Userauftrag untersagt, deshalb nur notiert.

### Eigene Fehlschluesse in diesem Lauf, korrigiert

1. "0 neue Zeilen" nach den Sub-Tab-Klicks als "keine Wirkung" gelesen — ein
   Sub-Tab-Wechsel loggt einfach nichts, der Screenshot belegt den Wechsel.
2. Im verkleinerten Screenshot dreimal "Fertig" im Notizen-Bereich vermutet.
   Der Regionsausschnitt zeigt dort nichts; die Labels stehen im rechten
   TASKS-Panel, ich hatte die x-Positionen falsch zugeordnet.
3. "Verbindung testen" fuer ungeschuetzt gehalten. Der Handler sperrt den Knopf
   sofort (`setEnabled(False)`); die zwei Log-Zeilen kamen aus zwei
   nacheinander fertigen Tests.

*Konsequenz:* Bei jeder Auffaelligkeit aus einem verkleinerten Screenshot erst
einen Regionsausschnitt oder die UIA-Koordinaten pruefen, bevor sie als Fund
benannt wird.

## 4. Wie der Waechter praeziser geworden ist

| Beobachtung aus Loop 6 | Konsequenz fuer Loop 7 |
|---|---|
| Sieben Messfehler in einem Werkzeug, jeder erst nach einem Lauf sichtbar | Werkzeug einfrieren. Ein Messwerkzeug, das siebenmal falsch gemessen hat, verdient keine achte Runde vor dem naechsten echten Fund |
| Viermal dieselbe Fehlerklasse (ID in Kommentar / Log-String / Docstring / Kommentar ueber der Reparatur) | Jeder Quellcode-Guard prueft ab jetzt **nur Code** — Kommentare und Docstrings werden vorher entfernt |
| Live-Laeufe fanden die schwersten Bugs (B-965, B-967) | bestaetigt in 7.1: B-973 und B-974 kamen aus einem Widerspruch im Screenshot, nicht aus dem Log |
| Vier von sechs Auffaelligkeiten in 7.1 loesten sich als Fehlschluss auf | Erst Regionsausschnitt oder UIA-Koordinaten, dann Fund benennen |
| "Gedeckt" per grober Mutation ist schwaecher als per feiner | Im Bericht steht die Mutationsart; im Wächter wird zwischen stark und schwach gedeckt getrennt |
| Baseline-Fehlschlaege verfaelschten die Messung | Jede Messung, die Testfehler zaehlt, gleicht gegen `tests/known_failures.json` ab |
| Eine eigene Ableitung ("erst fehlerfreies Werkzeug") lenkte den Loop | Ableitungen aus dem Auftrag gehoeren offengelegt und vom User bestaetigt, nicht stillschweigend umgesetzt |

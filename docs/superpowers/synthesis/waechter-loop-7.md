---
title: Waechter - Bilanz Loop 6 und Konfiguration Loop 7
status: laufend
created: 2026-09-03 10:30
---

# Waechter - Loop 7

## 1. Bilanz Loop 6

| Kennzahl | Loop 3 | Loop 4 | Loop 5 | Loop 6 |
|---|---|---|---|---|
| Neue Funde | 2 | 2 | 4 | **7** (B-965 bis B-971) |
| Reparierte Bugs | 2 | 8 | 4 | 5 |
| Neue Pruefwerkzeuge | 0 | 2 | 2 | **1** (`mutationsprobe`) |
| Werkzeug-Praezisierungen | 1 | 1 | 1 | **4** |
| Neue Tests | 5 | 14 | 27 | **70** |
| Eigene Verfahrensfehler | 2 | 5 | 3 | **3** |

**Reparierte Bugs:**

| Bug | Was | Beleg |
|---|---|---|
| B-965 | `StemWorkspace.destroy_workspace()` ohne Aufrufer — Peak-Threads liefen beim Beenden weiter | Live-Log `18:51:53 closeEvent: StemWorkspace endgueltig geschlossen` |
| B-967 | EDL-Reasoning fragte Ollama mit leerem Modellnamen | End-zu-End: `''` → `gemma3:4b`, 28 EDL-Eintraege in 107.4 s |
| B-968 | Kommentar behauptete eine Entfernung, die `8a5c6a4` rueckgaengig machte | `git log -S` |
| B-969 | `test_deep_functional.py` konnte unter pytest nicht rot werden — 4 echte Abweichungen verdeckt | Gegenprobe: absichtlich falsche Behauptung → exit 1 |
| B-970 | Skriptdatei im `tests/`-Ordner erzeugte einen Dauerfehler beim Sammeln; zwei verwaiste Aufrufe | `1 error` → `1 skipped`, Skript laeuft durch (98 Pruefungen) |
| B-971 | Der B-888-Test deckte keine der fuenf markierten Stellen ab | Mutationsprobe: 5× GRUEN vor dem Fix, 5× ROT danach |
| B-680, B-800 | zwei weitere ungedeckte Reparaturen | Mutationsprobe |

**Dokumentiert ohne Aenderung:** B-966 (vier DB-Spalten ohne Produktivnutzung) — Loeschen waere
Migration, Leser bauen waere Feature. Userentscheidung.

**Regressionslauf, sauber (ohne parallele Aenderungen):**
`17 failed, 4910 passed, 57 skipped in 1746.88s (29:06)` — **keine neuen roten Tests**, und
**kein `error`** mehr.

## 2. Die eine Lehre, die Loop 6 traegt

**Ein Werkzeug, das Namen zaehlt, misst keine Deckung.**

`fix_ohne_test` prueft, ob eine Bug-ID oder ein Symbolname unter `tests/` vorkommt. Dreimal in
Loop 6 stellte sich heraus, dass das nichts ueber die Absicherung sagt:

* B-969: zehn Tests, die strukturell nicht fehlschlagen konnten, haetten als Deckung gezaehlt.
* B-971: B-888 galt als gedeckt und war an allen fuenf markierten Stellen ungedeckt.
* B-680/B-800: dasselbe.

*Konsequenz:* Die Frage „gibt es einen Test?" wird ersetzt durch „wird der Test rot, wenn ich
den Fix umkehre?". Dafuer gibt es jetzt `tools/mutationsprobe.py`.

**Was daraus NICHT folgt:** Drei von drei geprueften IDs waren ungedeckt — das ist keine Aussage
ueber die restlichen. Die Stichprobe war klein und nicht zufaellig gezogen (ich habe gut
mutierbare Faelle gewaehlt). Die Gesamtzahl steht erst nach dem vollstaendigen Lauf fest.

## 3. Die drei eigenen Verfahrensfehler aus Loop 6

| Fehler | Folge | Regel daraus |
|---|---|---|
| `tools/inventory_audit.py` **waehrend** eines 39-min-Testlaufs geaendert | ein Befund („neu rot") war unbrauchbar, einzeln gruen | Waehrend eines Laufs keine Datei anfassen, die der Lauf liest |
| Mutationsskript schrieb CRLF als LF zurueck | sechs Dateien dirty ohne Inhaltsaenderung | Jedes Skript, das Quelldateien schreibt, nutzt `newline=""` |
| Vier generische Agenten gestartet statt des Consulting-Teams | Werkzeugvorgabe des Users verletzt | Nur `pruefstand`, `consulting-team`, `caveman ultra` |

Dazu eine Formulierung, die korrigiert wurde: „die 33 nur unbeschrifteten sind mehrheitlich
ebenfalls ungedeckt" war eine Hochrechnung aus drei Messungen, kein Beleg. Im Bugfile B-971
richtiggestellt.

## 4. Blindstellen nach Loop 6

- **Die vollstaendige Mutationsprobe laeuft**, Ergebnis steht aus. Erst danach ist die Zahl der
  wirklich ungedeckten Reparaturen bekannt.
- **42 IDs** gelten bei `fix_ohne_test` als nachweislich ungedeckt (ID *und* Symbol fehlen in
  `tests/`). Fuer sie ist die Mutationsprobe gar nicht noetig — dort gibt es nichts zu messen.
- **B-961 / B-960** — 23 von 62 Aktionen scheitern mit `TypeError ... missing required
  positional argument`. Userentscheidung steht aus.
- **B-966** — Userentscheidung steht aus.
- **B-958-Mechanismus** unerklaert (Schaden behoben), **B-923** Produktentscheidung,
  **B-870** ohne Repro nicht herstellbar.
- **`tests/test_core_services_deep.py`**: sechs Fehlschlaege im Skript-Modus, alle mit derselben
  Ursache — das Skript setzt kein Projekt. Aufbaumangel, bewusst nicht repariert.

## 5. Konfiguration Loop 7

**Werkzeuge:** `pruefstand` (neun Pruefer), `mutationsprobe` (neu), `consulting-team`,
`caveman ultra`. **Keine generischen Agenten.**

| Schritt | Inhalt | Abbruchkriterium |
|---|---|---|
| 7.1 | Vollstaendige Mutationsprobe auswerten. Jede UNGEDECKT-Meldung bekommt einen Test, jede ungemessene Stelle eine Pruefung von Hand. | Keine Stelle mehr in der Spalte „UNGEDECKT", und keine ungemessene ohne Notiz |
| 7.2 | Die 42 nachweislich ungedeckten IDs durchgehen — je Bug: ist das Schadensbild heute noch herstellbar? Nur dann Test. | Jede der 42 hat eine Entscheidung |
| 7.3 | `mutationsprobe` in den `pruefstand` aufnehmen als zehnter Pruefer | Ein Pruefstand-Lauf misst Deckung, nicht nur Namensvorkommen |
| 7.4 | `set_project()` in alle Mess-Skripte, die Projektdaten lesen | Kein Messlauf mehr gegen die leere Repo-DB |
| 7.5 | Live-GUI-Lauf mit `Erstlauf_Test_2026-08-30` ueber alle Workspaces, Aufzeichnung als Logdatei | Jeder Workspace einmal geoeffnet, Log ohne unerklaerte ERROR-Zeile |

**Bewusst ausgelassen:** B-870 (nicht herstellbar), B-923, B-960, B-961, B-966
(alle: Userentscheidung steht aus), B-603 (Ursachenanalyse vor Test — ein Test wuerde sonst den
Hard-Cut-Fallback als Sollverhalten zementieren).

## 6. Wie der Waechter praeziser geworden ist

| Beobachtung aus Loop 6 | Konsequenz fuer Loop 7 |
|---|---|
| Namenszaehlung misst keine Deckung (3 Faelle) | `mutationsprobe` ersetzt die Leitfrage; wird zehnter Pruefer (7.3) |
| `fix_ohne_test` las die ID nur im Inhalt, 345 Testdateien tragen sie im Namen | behoben; 89 → 75 IDs, 47 → 42 harte Befunde |
| Der Methoden-Pruefer meldete 3 harmlose neben 1 echten Befund | behoben; vier Toepfe statt einer Liste |
| Eine Testdatei kann strukturell nicht rot werden | Beim naechsten neuen Test immer die Gegenprobe fahren: absichtlich falsch behaupten, rot sehen |
| Aenderung waehrend eines Laufs machte den Befund unbrauchbar | Waehrend eines Laufs keine gelesene Datei anfassen |
| Hochrechnung aus drei Messungen als Aussage formuliert | Zahlen nur nach vollstaendiger Messung nennen; sonst „gemessen: n von m" |

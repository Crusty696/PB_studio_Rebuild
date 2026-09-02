---
title: Waechter - Bilanz Loop 5 und Konfiguration Loop 6
status: laufend
created: 2026-09-02 19:45
---

# Waechter - Loop 6

## 1. Bilanz Loop 5

| Kennzahl | Loop 1 | Loop 2 | Loop 3 | Loop 4 | Loop 5 |
|---|---|---|---|---|---|
| Neue Funde | 4 | 2 | 2 | 2 | 4 (B-963, B-964, B-959, B-1001-Verweis) |
| Reparierte Bugs | 1 | 2 | 2 | 8 | 4 |
| Neue Pruefwerkzeuge | 0 | 2 | 0 | 2 | 2 (`commit_audit`, `fix_ohne_test`) |
| Neue Tests | 4 | 4 | 5 | 14 | 27 |
| Eigene Verfahrensfehler | 6 | 3 | 2 | 5 | 3 |

**Erledigt aus der Loop-5-Konfiguration:**

| Schritt | Stand |
|---|---|
| 5.1 Voller Pruefstand-Lauf | laeuft erneut in Loop 6 (nach den neuen Fixes) |
| 5.2 Baseline neu aufnehmen | erledigt - 17 statt 19 rote Tests, keine neuen |
| 5.3 `fix_ohne_test` auf die sechs IDs | erledigt - B-959, B-963, B-964, B-908 haben jetzt Tests; B-1001-Verweis entfernt |
| 5.4 `commit_audit` ueber die volle Historie | **erledigt in Loop 6** - 89 von 2000 Commits mit Befund, 167 mit Hinweis |
| 5.5 `QEventLoop.exec()` aus den Tests | erledigt - kein aktiver Aufruf mehr in `tests/`, nur noch zwei erklaerende Kommentare |

## 2. Bilanz Loop 6 (Stand 19:45)

**Reparierte Bugs:** 2

| Bug | Was | Beleg | Commit |
|---|---|---|---|
| B-965 | `StemWorkspace.destroy_workspace()` ohne Aufrufer - der einzige closeEvent-Zweig, der Signale trennt und PeakWorker-Threads beendet, lief nie | Live-Log `18:51:53 closeEvent: StemWorkspace endgueltig geschlossen`, 7 Tests | `cd206bc` |
| B-967 | Direktes EDL-Reasoning fragte Ollama mit leerem Modellnamen (`HTTP 400: model is required`) | End-zu-End: `''` -> `gemma3:4b`, 28 EDL-Eintraege in 107.4 s, 7 Tests | `724f36c` |

**Dokumentiert ohne Aenderung:** B-966 (vier DB-Spalten ohne Produktivnutzung). Loeschen waere
Migration, Leser bauen waere Feature - beides faellt nicht unter "reparieren".

**Werkzeug praeziser gemacht:** `pruefer_methoden` in `tools/inventory_audit.py` sortiert
Treffer jetzt nach Gewicht statt sie gleichrangig zu melden. Commit `6472d79`.

## 3. Was Loop 6 ueber das Vorgehen gelernt hat

**Erste Lehre - Rauschen uebertoent den einen echten Fund.** Der Methoden-Pruefer meldete vier
Methoden ohne Aufrufer. Genau eine war ein Defekt. Die anderen drei: zwei reine Getter (ein
fehlender Aufrufer heisst dort nur "ungenutzte Schnittstelle") und eine Methode, die sehr wohl
einen Aufrufer hat - in `scripts/diag/`, das der Pruefer nicht mitgelesen hat.

*Konsequenz:* Ein Pruefer, der drei harmlose neben einen echten Befund stellt, ist kein
strengerer Pruefer, sondern ein schlechterer. Ab Loop 6 gilt fuer jede neue Pruefung: **welche
Kategorien von Treffern sind strukturell harmlos, und wie trenne ich sie maschinell?** Der
Methoden-Pruefer hat jetzt vier Toepfe; danach: 76 geprueft, 0 harte Befunde.

**Zweite Lehre - die falsche Datenbank gelesen.** Ich habe im Bugfile zu B-967 geschrieben, ein
End-zu-End-Lauf sei unmoeglich, "die DB hat keine Tracks". Falsch. Ein nacktes Skript liest die
Repo-Standard-DB (`pb_studio.db`, leer); die App wechselt beim Projektoeffnen per
`database.session.set_project()` auf die Projekt-DB. Mit gesetztem Projekt lagen 1 Track mit 27
Strukturabschnitten und 5 Clips bereit, und der Lauf ging durch.

*Konsequenz:* **Vor jeder Aussage "Daten fehlen" pruefen, ob der Messaufbau ueberhaupt dort
hinschaut, wo die App hinschaut.** Konkret: `set_project(...)` gehoert in jedes Skript, das
Projektdaten liest. Diese Lehre haette Loop 5 schon lernen koennen - der Log-Eintrag
"Projekt gewechselt: ..." steht seit Monaten in jedem Lauf.

**Dritte Lehre - eine Zwischenbehauptung zu frueh ausgesprochen.** Beim B-965-Fix schrieb ich
"mein Einbau greift nicht", weil ich keine Setzstelle fuer `window.stem_workspace` fand. Das
Live-Log von 18:47:20 zeigte, dass der Zweig sehr wohl lief. Der praezisere Zugriffspfad ist
trotzdem der richtige, aber die Aussage war voreilig.

*Konsequenz:* **Erst messen, dann bewerten** - auch wenn die Quelltextlage eindeutig aussieht.

## 4. Blindstellen nach Loop 6

- **89 Commits** ueber die volle Historie versprechen Tests, die ihr Diff nicht enthaelt. Fuer
  einen Teil kamen die Tests spaeter nach (B-963, B-964 nachweislich). Fuer welche **bis heute**
  kein Test existiert, sagt `fix_ohne_test`: **89 Bug-IDs**, davon **47 nachweislich ungedeckt** (auch das
  umschliessende Symbol kommt in keinem Test vor) und 42 nur unbeschriftet. Das ist der
  groesste offene Posten.
- **B-961 / B-960** - 23 von 62 Aktionen scheitern mit `TypeError ... missing required
  positional argument`, weil die Registry Pflichtparameter nicht prueft. Alle 42 verbleibenden
  ERROR-Zeilen im Live-Log gehen darauf zurueck. Userentscheidung steht aus.
- **B-958-Mechanismus** weiterhin unerklaert (Schaden behoben).
- **B-923** braucht eine Produktentscheidung, **B-870** ist ohne Repro nicht herstellbar.
- **53+ Bugs** mit `agent-fixed-await-user` / `agent-live-verified-await-user-marker` warten auf
  die Userfreigabe. `status: fixed` setzt nur der User.

## 5. Konfiguration Loop 7

**Werkzeuge:** `pruefstand` (neun Pruefer), `consulting-team`, `caveman ultra`.

| Schritt | Inhalt | Abbruchkriterium |
|---|---|---|
| 7.1 | Die 47 nachweislich ungedeckten Bug-IDs aus `fix_ohne_test` durchgehen - je Bug: existiert der Test unter anderem Namen, oder fehlt er wirklich? | Jede der 47 IDs hat eine Entscheidung: Test vorhanden / Test nachgeliefert / begruendet ohne Test |
| 7.2 | `set_project()` in alle Mess-Skripte aufnehmen, die Projektdaten lesen | Kein Messlauf mehr gegen die leere Repo-DB |
| 7.3 | Jeden verbleibenden Pruefer nach derselben Frage durchsehen wie den Methoden-Pruefer: welche Trefferkategorie ist strukturell harmlos? | Jeder Pruefer trennt harte Befunde von Hinweisen |
| 7.4 | Live-GUI-Lauf mit dem Projekt `Erstlauf_Test_2026-08-30` ueber alle Workspaces, Aufzeichnung als Logdatei | Jeder Workspace einmal geoeffnet, Log ohne unerklaerte ERROR-Zeile |

**Bewusst ausgelassen:** B-870 (nicht herstellbar), B-923 (Produktentscheidung), B-960/B-961
(Userentscheidung steht aus), B-966 (Userentscheidung steht aus).

## 6. Wie der Waechter praeziser geworden ist

| Beobachtung aus Loop 6 | Konsequenz fuer Loop 7 |
|---|---|
| 3 von 4 Meldungen des Methoden-Pruefers waren harmlos | Jeder Pruefer muss harte Befunde von Hinweisen trennen (7.3) |
| Messlauf las die leere Repo-DB statt der Projekt-DB | `set_project()` gehoert in jedes Mess-Skript (7.2) |
| "Greift nicht" behauptet, bevor das Log vorlag | Erst messen, dann bewerten - gilt auch bei eindeutiger Quelltextlage |
| `commit_audit` ueber 2000 Commits: 89 Befunde | Nicht die Commits nacharbeiten, sondern die 47 nachweislich ungedeckten IDs (7.1) |
| Der Live-Shutdown liess sich nur per `taskkill` ohne `/F` ausloesen (`focus` scheiterte am Titel) | WM_CLOSE per `taskkill` ist ab jetzt der Standardweg fuer Shutdown-Tests |

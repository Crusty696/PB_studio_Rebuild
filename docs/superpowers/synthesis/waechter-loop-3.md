---
title: Waechter - Bilanz Loop 2 und Konfiguration Loop 3
status: laufend
created: 2026-09-01 10:35
---

# Waechter - Loop 3

## 1. Bilanz Loop 2

| Kennzahl | Loop 1 | Loop 2 |
|---|---|---|
| Neue Funde | 4 | 2 (B-963, B-964) |
| Davon repariert | 1 | 2 |
| Funde aus dem Pruefstand | 0 | 0 |
| Funde aus dem Live-Test | 4 | 2 |
| Reproduktionen gefahren | 0 | 5 |
| Eigene Verfahrensfehler | 6 | 3 |

**Reproduktionsstand aller sechs Funde:**

| Fund | Belege | Ergebnis |
|---|---|---|
| B-959 | 57 vs 62, Fix-Gegenprobe | deterministisch reproduziert |
| B-963 | 1403 Logzeilen, Codebeleg, Instanz-Gegenprobe | deterministisch reproduziert |
| B-961 | zwei App-Sitzungen (08:28, 09:44) | reproduziert, identische Meldungen und Zeiten |
| B-964 | zwei App-Sitzungen (09:20, 10:18) | reproduziert, danach behoben und live gegengeprueft |
| B-960 | vier Messungen mit **unterschiedlichen** Ergebnissen | als nichtdeterministisch belegt - das ist der Fund |
| B-962 | zweiter Durchgang widerlegte den Kernvorwurf | herabgestuft high -> low |

**Pacing:** zwei Laeufe (2026-08-31 23:46, 2026-09-01 10:16), Kennzahlen identisch bis auf die
Rechenzeit (41,1 s / 33,6 s). Der bisher einzige Prozess mit hartem Reproduzierbarkeitsnachweis.

## 2. Blindstellen nach Loop 2

- **Der Pruefstand hat in zwei vollen Laeufen null Funde geliefert.** Belegt: B-963 stand
  1403x im App-Log (Pruefstand liest keine Logs), B-960/B-961 brauchen eine ausgeloeste
  Chat-Aktion (loest keine aus), B-964 ist ein UI-Zustand (startet keine GUI).
- **36 aeltere Bug-Dateien** sind weiterhin unangetastet.
- **B-958 ist offen**, und der Detektor-Ansatz hat zweimal den Testlauf blockiert. Der globale
  conftest-Haken ist verworfen.
- **Zweimal wurde die App waehrend laufender Messungen beendet** (09:34:03, 10:06:06), jeweils
  sauberer `closeEvent` mit `spontaneous=True`. Ursache unbekannt, nicht von mir ausgeloest.

## 3. Konfiguration Loop 3

**Werkzeuge unveraendert:** `pruefstand`, `consulting-team`, `caveman ultra`.

**Userfreigaben vom 2026-09-01 10:22:**
- Beide vorgeschlagenen Pruefer ergaenzen.
- Von den drei offenen Funden nur B-964 beheben (erledigt, Commit `884b0a1`).
  B-960 und B-961 bleiben unangetastet.

| Schritt | Inhalt |
|---|---|
| 3.1 | **Log-Pruefer** `tools/log_audit.py`: durchsucht `logs/pb_studio.log` nach Wiederholungsmustern (gleiche Meldung > 50x pro Sitzung), ERROR/Traceback-Haeufungen und Meldungen, die einem Zustand widersprechen. Zielmarke: B-963 muss damit ohne Live-Test findbar sein. |
| 3.2 | **Aktions-Rauchtest** `tools/action_smoke.py`: ruft alle 62 Registry-Aktionen ohne Parameter auf und meldet rohe `TypeError` statt verstaendlicher Meldung. Zielmarke: die 25 Aktionen aus B-961 muessen erscheinen. |
| 3.3 | Beide in `tools/pruefstand.py` einhaengen, Bericht erweitern. |
| 3.4 | Gegenprobe: Pruefstand-Lauf muss B-963 (an einem alten Log) und B-961 finden. Findet er sie nicht, taugen die Pruefer nichts und werden nachgebessert. |
| 3.5 | Die 36 offenen Bug-Dateien einzeln durchgehen: Live-Beleg oder schriftliche Begruendung, warum in dieser Umgebung nicht ausloesbar. |

**Bewusst ausgelassen:** B-960 und B-961 (keine Freigabe), B-958 (Ansatz verworfen, neuer Weg
gehoert in einen eigenen Loop).

## 4. Zielliste Loop 3

- Zwei neue Pruefer, jeder mit einer Zielmarke, die er nachweislich trifft.
- Der Pruefstand findet nach 3.4 mindestens zwei der heutigen sechs Funde selbst.
- Alle 36 offenen Bugs eingeordnet.

## 5. Abbruchkriterium

Loop 3 ist erledigt, wenn die Gegenprobe aus 3.4 belegt ist und die 36 Bugs eine Einordnung haben.

## 6. Wie der Waechter praeziser geworden ist

| Kennzahl | Beobachtung | Konsequenz |
|---|---|---|
| Funde pro Werkzeug | Pruefstand 0 in zwei Loops | Loop 3 repariert nicht die App, sondern das Werkzeug - erstmals ist der Pruefstand selbst der Gegenstand |
| Reproduktionsquote | 5 von 6, davon eine Widerlegung | Die Regel "kein Befund vor der zweiten Sitzung" hat einen Fehlalarm verhindert und bleibt |
| Eigene Fehler | 6 in Loop 1, 3 in Loop 2 | Sinkt, aber zu langsam. Neu ab Loop 3: kein Klick ohne vorherige Fensterpruefung (bereits eingebaut, hat um 10:18 gegriffen) |

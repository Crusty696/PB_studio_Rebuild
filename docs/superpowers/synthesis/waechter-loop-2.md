---
title: Waechter - Bilanz Loop 1 und Konfiguration Loop 2
status: laufend
created: 2026-09-01 09:16
---

# Waechter - Loop 2

## 1. Bilanz Loop 1

Gemessen, nicht geschaetzt. Alle Belege in `test-report/live/loop-1.log` und `logs/pb_studio.log`.

| Kennzahl | Wert |
|---|---|
| Laufzeit GUI-Block | 07:53:17 - 09:15 (1 h 22 min) |
| Aktionen live gemessen | 62 von 62 (100 %) |
| davon funktionieren | 32 |
| davon rohe Fehlermeldung bei nacktem Namen | 25 |
| davon durch Bestaetigungssperre geschuetzt (korrekt) | 4 |
| davon ohne Worker | 1 |
| neue Funde | 4 (B-959, B-960, B-961, B-962) |
| davon repariert | 1 (B-959) |
| Datenverlust | keiner, Timeline durchgehend 161 Eintraege |

### Funde

| ID | Schwere | Kern | Stand |
|---|---|---|---|
| B-959 | medium | `inventory_audit` zaehlte 57 statt 62 Aktionen | **behoben**, Commit `6facc9e` |
| B-960 | high | Exakter Aktionsname geht durchs LLM, verliert Parameter, nicht reproduzierbar | offen |
| B-961 | medium | Fehlender Pflichtparameter schlaegt als roher `TypeError` bis zum Nutzer durch | offen |
| B-962 | high | Natuerliche Sprache landet bei der falschen Aktion | offen |

### Was Loop 1 ueber die Werkzeuge gelernt hat

- **Der GUI-Live-Test hat alle vier Funde geliefert. Die fuenf Pruefwerkzeuge keinen einzigen.**
  B-959 wurde sogar *am Werkzeug selbst* gefunden - und zwar durch die App, nicht durch das
  Werkzeug.
- Das bestaetigt die Blindstelle, die schon in Loop 1 vorab notiert war, jetzt mit Zahlen:
  Werkzeuge finden Struktur, der Live-Test findet Verhalten.

### Eigene Fehler in Loop 1 (sechs, alle im log.md mit Zeitstempel)

1. Erster `pruefstand`-Lauf mit `--schnell` ohne Projektpfad - das einzige inhaltliche Werkzeug
   fehlte. Vom User beanstandet.
2. Glob `tests/*.py` umging die `--ignore`-Liste, Testlauf starb mit `INTERNALERROR`.
3. Geschaetzter Vault-Zeitstempel (04:12 statt gemessener 06:18) - daraus entstand ein falscher
   Alarm ueber einen angeblich haengenden Lauf.
4. Eigener B-958-Detektor brachte den Testlauf zum Stillstand (`probe.exec()` ohne Wachtimer).
5. Dreimal in dieselbe Heredoc-Escape-Falle gelaufen, Datei mit `SyntaxError` zerlegt.
6. Zwischenbilanz "25 Aktionen defekt" war ueberzeichnet - die Gegenprobe mit natuerlicher
   Sprache widerlegte sie teilweise.

## 2. Blindstellen nach Loop 1

- **Nur der Chat-Weg wurde geprueft.** Dieselben Funktionen ueber Knoepfe und Menues sind
  ungeprueft. B-950/B-955 vom 2026-08-31 zeigen, dass genau dort Fehler sitzen, die der Chat
  nicht sieht.
- **Die langen Prozesse laufen noch.** `create_proxy` (121 Videos) und zwei Audio-Analysen wurden
  in Loop 1 gestartet, ihr Ergebnis ist nicht geprueft.
- **B-958 ist unerledigt.** Der volle Testlauf prueft die Dispatcher-Aufraeumung nicht; die
  Ursache der Null-Wartezeit ist offen.
- **36 aeltere Bugs** aus dem Vault sind in Loop 1 nicht angefasst worden.

## 3. Konfiguration Loop 2

**Werkzeuge unveraendert:** `pruefstand`, `consulting-team`, `caveman ultra`.

| Schritt | Befehl / Vorgehen |
|---|---|
| 2.1 | Ergebnis der laufenden Prozesse pruefen: Proxies, Audio-Analyse Track 1, Video-Analyse Clip 5 |
| 2.2 | `python tools/pruefstand.py --projekt <Erstlauf_Test_2026-08-30> --preset Standard`, Ausgabe live in Datei, **nicht** `--schnell` |
| 2.3 | `consulting-team` bewertet den Bericht **und** die vier Funde aus Loop 1 |
| 2.4 | GUI-Block 2: dieselben Funktionen ueber **Knoepfe statt Chat** - die fuenf Workspaces der Reihe nach |
| 2.5 | Die 36 offenen Bug-Dateien durchgehen: welche sind mit den Loop-1-Belegen entscheidbar |

**Bewusst ausgelassen:** Reparatur von B-960/B-961/B-962. Alle drei aendern zentrales
Routing- oder Registry-Verhalten; das ist eine Produktentscheidung des Users, keine Reparatur.

## 4. Zielliste Loop 2

- Alle in Loop 1 gestarteten Prozesse mit Ergebnis belegen.
- Jede der fuenf Workspaces mindestens einmal ueber die Oberflaeche bedient.
- Fuer jeden der 36 offenen Bugs: entweder ein Live-Beleg oder die schriftliche Begruendung,
  warum er in dieser Umgebung nicht ausloesbar ist.

## 5. Abbruchkriterium

Loop 2 ist erledigt, wenn der Pruefstand-Bericht vorliegt, das consulting-team ihn bewertet hat,
jede Workspace einen Log-Beleg hat und die 36 Bugs einzeln eingeordnet sind.

## 6. Wie der Waechter praeziser geworden ist

| Kennzahl | Loop 1 | Konsequenz fuer Loop 2 |
|---|---|---|
| Funde pro Werkzeug | Pruefstand 0, Live-Test 4 | Gewicht verschiebt sich auf den Live-Test; der Pruefstand laeuft weiter, aber nicht mehr als Hauptquelle |
| Anteil Live-Funde | 100 % | Loop 2 nimmt den zweiten Live-Weg dazu (Knoepfe statt Chat) |
| Zeilen mit `live` in `abdeckung.md` | 6 -> 62 | Register um Knoepfe und Prozesse erweitern, sonst steht der Zaehler still |

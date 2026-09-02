---
title: Waechter - Bilanz Loop 3 und Konfiguration Loop 4
status: laufend
created: 2026-09-01 12:20
---

# Waechter - Loop 4

## 1. Bilanz Loop 3

| Kennzahl | Loop 1 | Loop 2 | Loop 3 |
|---|---|---|---|
| Neue Funde | 4 | 2 | 2 (B-949-Nachtrag, B-964-Testluecke) |
| Davon repariert | 1 | 2 | 2 |
| Funde aus dem Pruefstand | 0 | 0 | 0 |
| Funde aus dem Live-Test | 4 | 2 | 0 |
| **Funde aus Pruef-Agenten** | - | - | **2** |
| Bugs eingeordnet | 0 | 0 | **88** |
| Eigene Verfahrensfehler | 6 | 3 | 2 |

### Ergebnis der Einordnung aller 88

| Ergebnis | Anzahl |
|---|---|
| behoben (Codemuster weg bzw. Test gruen) | 62 |
| besteht unveraendert | 10 |
| teilweise behoben | 7 |
| nicht entscheidbar / halb belegt | 9 |

**Der wichtigste Satz dieser Bilanz:** 62 von 88 waren bereits behoben, ohne dass die Bug-Dateien
das festhielten. Der Vault hinkte dem Code um Monate hinterher. Die Zahl "88 offene Bugs" hat den
tatsaechlichen Rueckstand um mehr als das Doppelte ueberzeichnet.

### Was die Werkzeuge geleistet haben - und was nicht

- **Pruefstand: 0 Funde in drei Loops.** Auch mit den zwei neuen Pruefern (Log-Audit,
  Aktions-Rauchtest) lieferte er in Loop 3 keinen neuen Fund. Seine Leistung liegt woanders und
  ist belegt: ein neu roter Test nach vier Code-Eingriffen, und Pacing-Kennzahlen, die ueber drei
  Laeufe identisch reproduzieren.
- **Live-Test: 6 Funde in zwei Loops**, in Loop 3 keiner - dort wurde nicht live getestet,
  sondern eingeordnet.
- **Pruef-Agenten: 2 Funde, beide gegen die eigene Arbeit.** Das ist neu und war mit keinem
  bisherigen Verfahren erreichbar.

## 2. Die zwei Fehlermuster aus Loop 3

Beide fand ein Agent, beide betrafen meine Arbeit vom selben Tag:

1. **Commit-Nachricht verspricht mehr als der Diff enthaelt** (B-949). `bc19d9b` beschrieb eine
   h265-NVENC-Pruefung und vier Tests; eingecheckt waren vier geloeschte Importzeilen.
   Kein Werkzeug haette das gefunden: die Nachricht war plausibel, der Bug-Eintrag stand auf
   behoben, und der Code funktionierte auf dieser Maschine, weil sie NVENC hat.
2. **Fix ohne absichernden Test** (B-964). Live belegt, aber kein Test - ein Grep nach der
   Bug-ID und dem Funktionsnamen lieferte nichts.

## 3. Blindstellen nach Loop 3

- **10 Bugs bestehen unveraendert**, davon vier in den Audit-Werkzeugen (B-861, B-862, B-863,
  B-864) und drei in der Oberflaeche (B-918, B-923, B-925).
- **B-870 bleibt nicht entscheidbar** - ein Crash ohne Repro, der sich nicht auf Kommando
  herstellen laesst.
- **12 der 62 "behoben" sind ausdruecklich nicht live gegengeprueft.** Das steht in jeder
  betroffenen Datei.
- **Ein Test-Harness-Defekt** wurde nebenbei gefunden: `tests/audit/test_audit_runtime_evidence.py:1114`
  liest `tasklist` mit `text=True` und scheitert auf deutschem Windows an
  `UnicodeDecodeError`. Kein Produktfehler, aber zwei Tests sind dadurch dauerhaft rot.

## 4. Konfiguration Loop 4

**Werkzeuge unveraendert:** `pruefstand`, `consulting-team`, `caveman ultra`. Dazu ab jetzt
Pruef-Agenten parallel (Userauftrag 2026-09-01 11:40).

| Schritt | Inhalt |
|---|---|
| 4.1 | **Neuer Pruefer `tools/commit_audit.py`**: haelt Commit-Nachrichten gegen ihre Diffs. Meldet, wenn eine Nachricht Dateien, Tests oder Funktionen nennt, die der Commit nicht anfasst. Zielmarke: `bc19d9b` muss damit auffallen. |
| 4.2 | **Neuer Pruefer `tools/fix_ohne_test.py`**: sucht Bug-IDs, die im Produktivcode als Kommentar auftauchen, aber in `tests/` nicht vorkommen. Zielmarke: B-964 vor Commit `2eb88a8` muss auffallen. |
| 4.3 | Beide in den Pruefstand einhaengen, Gegenprobe fahren. |
| 4.4 | Die 10 bestehenden Bugs dem User zur Entscheidung vorlegen - sie sind alle belegt und brauchen eine Reparaturfreigabe, keine weitere Messung. |
| 4.5 | Den Test-Harness-Defekt (`tasklist` unter cp1252) melden. |

**Bewusst ausgelassen:** B-960 und B-961 (keine Freigabe), B-870 (nicht herstellbar).

## 5. Abbruchkriterium

Loop 4 ist erledigt, wenn beide neuen Pruefer ihre Zielmarke nachweislich treffen und die
10 bestehenden Bugs dem User als Entscheidungsliste vorliegen.

## 6. Wie der Waechter praeziser geworden ist

| Beobachtung | Konsequenz |
|---|---|
| Pruefstand 0 Funde in drei Loops, Agenten 2 in einem | Loop 4 baut Pruefer fuer genau die Fehlerklasse, die Agenten gefunden haben - nicht fuer die, die schon abgedeckt ist |
| Beide Agenten-Funde betrafen die eigene Arbeit desselben Tages | Selbstpruefung wird eigener Schritt, nicht Nebenprodukt |
| 62 von 88 waren laengst behoben | Der Vault-Rueckstand ist selbst ein Befund. Kuenftig gehoert die Statusdatei zum Fix, nicht danach |
| Zwei Agenten fuhren denselben 9-Minuten-Test, einer brach ab | Lange Testlaeufe gehoeren in genau eine Gruppe, nicht in mehrere |

---
title: Waechter - Plan und Arbeitsanweisung
status: aktiv
created: 2026-09-01
author: claude (Userauftrag "erstelle zuvor einen genauen Plan was er alles machen muss und wie er es machen muss")
---

# Waechter - Plan und Arbeitsanweisung

Der Waechter ist kein Programm, das Fehler sucht. Er ist die Instanz, die **jeden Loop neu
konfiguriert**, damit der naechste Loop mehr findet als der letzte. Er misst nicht die App - er
misst, **wie gut der letzte Loop gemessen hat**, und zieht daraus die Einstellungen fuer den
naechsten.

Ziel des Users: 100 % des Codes und der App abgedeckt, jede Funktion und jeder Prozess mit
reproduzierbarem, sauber gemessenem Beleg.

## Was der Waechter NICHT darf

- Keinen Code aendern. Er konfiguriert, er repariert nicht.
- Keine Funde erfinden, um Fortschritt zu zeigen.
- Kein Werkzeug als "ohne Befund" werten, das nicht gelaufen ist.
- Keine Funktion als geprueft eintragen, die nur ein gruener Unit-Test beruehrt hat.
- Nicht behaupten, etwas sei abgedeckt, wenn nur die schnelle Variante lief.

## Eingaben (alle Pflicht, fehlende werden als fehlend gemeldet)

| Quelle | Wofuer |
|---|---|
| `test-report/pruefstand.md` des letzten Loops | Was die fuenf Werkzeuge gemessen haben |
| `test-report/live/loop-<N>.log` | Was der GUI-Live-Test gesehen hat |
| `wiki/synthesis/abdeckung.md` | Welche Funktion/Prozess welchen Belegstand hat |
| `wiki/synthesis/waechter-loop-<N>.md` | Womit der letzte Loop konfiguriert war |
| `log.md` seit dem letzten Loop | Was tatsaechlich passiert ist, mit Zeitstempeln |
| `wiki/bugs/*.md` | Offene Funde, Status, was ohne Live-Beleg blieb |

## Ausgabe: `wiki/synthesis/waechter-loop-<N+1>.md`

Feste Gliederung, jeder Punkt belegpflichtig:

1. **Bilanz des letzten Loops** - Zahlen, keine Adjektive: Werkzeuge gelaufen/nicht gelaufen,
   Laufzeit gemessen, Funde neu/bestaetigt/verworfen, Live-Belege dazugekommen.
2. **Blindstellen** - was der letzte Loop nachweislich nicht sehen konnte, mit Begruendung.
   Beispiel aus dem 2026-08-31: B-939, B-942, B-934 kamen aus Live-Tests, kein Werkzeug sah sie.
3. **Konfiguration fuer diesen Loop** - konkrete Befehlszeilen, nicht Absichten:
   - Pruefstand: `--projekt`, `--preset`, voll oder `--schnell` (mit Begruendung, falls schnell)
   - GUI-Live-Test: welche Bereiche, welche Klickfolge, welche Belege erwartet
   - Was bewusst ausgelassen wird und warum
4. **Zielliste** - welche Eintraege aus `abdeckung.md` dieser Loop von "ungeprueft" oder
   "nur Werkzeug" auf "live belegt" heben soll.
5. **Abbruchkriterium** - woran dieser Loop als erledigt gilt.

## Abdeckungsregister `wiki/synthesis/abdeckung.md`

Der 100-%-Zaehler. Eine Zeile pro Funktion/Prozess der App:

| Spalte | Werte |
|---|---|
| Funktion/Prozess | z. B. "Auto-Ducking ueber Oberflaeche ausloesen" |
| Ort | Datei:Zeile oder Workspace |
| Belegstand | `ungeprueft` / `werkzeug` / `unit` / `live` |
| Beleg | Pfad + Zeile im Log, Messwert |
| Datum | gemessen, nicht geschaetzt |

Nur `live` mit Beleg zaehlt fuer den 100-%-Stand. Das Register wird nach jedem Loop
fortgeschrieben, nie zurueckgesetzt.

## Ablauf eines Loops

1. **Waechter konfiguriert** - liest die Eingaben, schreibt `waechter-loop-<N>.md`.
2. **Messen** - `python tools/pruefstand.py --projekt <pfad> --preset <preset>`,
   Ausgabe live in eine Datei (nie durch `tail` gepuffert), START-/ENDE-Zeit gemessen.
3. **GUI-Live-Test** - App starten, die im Loop-Plan genannte Klickfolge fahren. Der User
   schaut zu. Aufgezeichnet wird **als Log-Datei**: `test-report/live/loop-<N>.log`.
   Kein Screen-Recorder, keine Videoaufnahme (Useranweisung 2026-09-01).
4. **Bewerten** - `consulting-team` bekommt Bericht und Live-Log. Auftrag: die Zahlen einordnen,
   nicht neue suchen.
5. **Belegen** - jeder Fund bekommt Datei:Zeile, Messwert und einen Befehl, mit dem er sich
   reproduzieren laesst. Ohne diese drei Dinge ist es kein Fund, sondern eine Vermutung.
6. **Reparieren** - Reparatur im Rahmen des Auftrags ist erlaubt. Nicht erlaubt: umbenennen,
   Farben aendern, neue Funktionen erfinden, Dinge einbauen, die die App nicht braucht.
   Im Zweifel: fragen. (Userklarstellung 2026-09-01: reparieren ja, alles Uebrige nein.)
7. **Live nachweisen** - jeder Fix wird am laufenden Programm gezeigt, nicht am Test.
8. **Vault schreiben** - pro Sub-Schritt, mit gemessenem Zeitstempel.
9. **Waechter bilanziert** - schreibt die Bilanz in `waechter-loop-<N>.md` und daraus die
   Konfiguration fuer `<N+1>`.

## Wie der Waechter praeziser wird

Nach jedem Loop misst er drei Kennzahlen und passt daran die naechste Konfiguration an:

| Kennzahl | Konsequenz |
|---|---|
| Funde pro Werkzeug | Werkzeug ohne Fund ueber drei Loops: Parameter aendern oder Bereich wechseln, nicht einfach weiterlaufen lassen |
| Anteil Funde aus Live-Test vs. Werkzeug | Ueberwiegt Live deutlich, ist die Werkzeugseite blind - Randfaelle nachziehen |
| Zeilen in `abdeckung.md` mit `live` | Steigt der Wert nicht, war der Loop wirkungslos - das gehoert in die Bilanz, nicht unter den Tisch |

## Ehrlichkeitsregeln (nicht verhandelbar)

- Kein Fund ohne Beleg. Kein "verified" ohne Live-Test.
- Was nicht gelaufen ist, wird als "nicht gelaufen" gemeldet, nicht weggelassen.
- Eigene Fehler werden benannt, nicht relativiert.
- Zeitstempel werden gemessen (`Get-Date`, Prozess-StartTime), nie geschaetzt.
  Am 2026-09-01 fuehrte ein geschaetzter Zeitstempel zu einem falschen Alarm.
- Widerlegte eigene Hypothesen werden als widerlegt aufgeschrieben.

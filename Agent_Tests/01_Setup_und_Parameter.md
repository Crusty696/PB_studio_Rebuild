# SETUP & PARAMETER (BEI JEDEM TEST ZUERST AUSFÜHREN)

Beachte die Datei `00_Basis_Regeln.md` (besonders die EISERNE REGEL:
Test immer über die sichtbare GUI im Vordergrund).

Dieses Skript bereitet jeden Test vor. Jedes Stufen-Skript (`02`–`07`)
verweist auf diese Datei und wiederholt den Frage-Block am Anfang.

---

## ZIEL

Die drei Test-Parameter abfragen, prüfen und die App sichtbar starten.
**Niemals raten oder alte Pfade wiederverwenden** — immer frisch fragen.

---

## SCHRITT A: DIE DREI FRAGEN STELLEN (PFLICHT, BEI JEDEM LAUF)

Frage den Nutzer **wörtlich** und warte auf jede Antwort, bevor du weitermachst:

1. **„Wie lautet der vollständige Pfad zur Audio-Datei (MP3/WAV/FLAC)?"**
   → speichern als `AUDIO_PFAD`.
2. **„Wie lautet der Pfad zum Ordner mit den Video-Clips (MP4/MOV)?"**
   → speichern als `VIDEO_ORDNER`.
3. **„Wie soll das Test-Projekt heißen?"**
   → speichern als `PROJEKT_NAME`.

Diese Fragen stellst du **jedes Mal neu**, auch wenn der Test schon einmal lief.
Die Werte können sich ändern.

---

## SCHRITT B: PARAMETER PRÜFEN (KEINE ANNAHMEN)

1. Prüfe, dass `AUDIO_PFAD` existiert und eine Audio-Datei ist.
   - Erwartet: Datei vorhanden, Endung `.mp3`/`.wav`/`.flac`.
   - Prüfe die **Länge**: Sie soll **zwischen 1 und 10 Minuten** liegen.
     Bei langem DJ-Mix (>10 min) den Nutzer warnen, dass dies außerhalb des
     Test-Korridors liegt, aber für den Stress-/Hang-Check (B-331) zulässig ist.
2. Prüfe, dass `VIDEO_ORDNER` existiert und Video-Dateien enthält.
   - Erwartet: Ordner vorhanden, enthält MP4/MOV-Dateien.
   - Zähle die Clips. **Ziel: ca. 150 Clips.** Melde die genaue Zahl
     (z. B. „148 Clips gefunden").
3. Prüfe, dass `PROJEKT_NAME` ein gültiger, eindeutiger Name ist (noch nicht
   vergeben). Bei Konflikt den Nutzer fragen, ob überschrieben werden soll.

> Wenn eine Prüfung fehlschlägt: **STOPP**, Fehler melden, nicht weitermachen.

---

## SCHRITT C: APP SICHTBAR STARTEN

1. Starte PB Studio über `start_pb_studio.bat` (Doppelklick im Explorer oder
   im Terminal). **Nicht** headless, **nicht** offscreen.
2. Beobachte das Konsolenfenster und warte, bis die GUI vollständig erscheint.
   - Erwartet (Konsole): Meldung „conda-env pb-studio (Python 3.10 + CUDA 11.3)".
   - Erwartet (GUI): Hauptfenster mit den 4 Tabs
     **PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT** ist sichtbar.
   - Erwartet: **kein** Versions-Fehlerdialog, **kein** Crash beim Start.
3. Notiere den Pfad des Start-Logs: `outputs/app_run_<zeitstempel>.log`.
   Das laufende Log liegt unter `logs/pb_studio.log`. Beide nutzt du als Beweis.
4. Lege den Ergebnis-Ordner an:
   `Test-ergebniss/<JJJJ-MM-TT>_<kurzname>/` (siehe `00_Basis_Regeln.md`, §3).

---

## SCHRITT D: PARAMETER-PROTOKOLL

Halte zu Beginn jedes Reports fest:

```
Audio:        <AUDIO_PFAD>   (Länge: <mm:ss>)
Video-Ordner: <VIDEO_ORDNER> (<Anzahl> Clips)
Test-Projekt: <PROJEKT_NAME>
App-Start:    start_pb_studio.bat — GUI sichtbar im Vordergrund
Datum:        <JJJJ-MM-TT HH:MM>
```

---

## ABSCHLUSS

Wenn alle drei Parameter abgefragt, geprüft und die GUI sichtbar gestartet ist,
gib aus:

„Setup abgeschlossen. Parameter geprüft, GUI sichtbar im Vordergrund. Bereit für
den nächsten Test-Schritt."

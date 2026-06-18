# TEST-SKRIPT: TEIL 1 — PROJEKT & IMPORT

Beachte die Dateien `00_Basis_Regeln.md` und `01_Setup_und_Parameter.md`.
**EISERNE REGEL:** Alles über die sichtbare GUI im Vordergrund. Kein Headless.

---

## ZUERST: DIE DREI FRAGEN (siehe 01)

1. „Wie lautet der vollständige Pfad zur Audio-Datei (MP3/WAV/FLAC)?" → `AUDIO_PFAD`
2. „Wie lautet der Pfad zum Ordner mit den Video-Clips (MP4/MOV)?" → `VIDEO_ORDNER`
3. „Wie soll das Test-Projekt heißen?" → `PROJEKT_NAME`

Danach Parameter prüfen und App sichtbar starten (Schritte B + C aus `01`).

---

## ZIEL

Test-Projekt anlegen und das gesamte Material importieren: 1 Audio-Datei
(1–10 min) + ca. 150 Video-Clips. Es geht NUR um Projekt-Anlage und Import —
keine Analyse-Inhalte, kein Schnitt.

---

## VORBEREITUNG

1. PB Studio ist sichtbar gestartet (4 Tabs sichtbar).
2. Notiere den Inhalt von `storage/backups` VOR dem Test (für Bug-Check B-498).

---

## TEST-SCHRITTE (Der Reihe nach, alles per Maus/Tastatur in der GUI)

1. Öffne den Tab **PROJEKT** und lege ein neues Projekt mit Namen
   `PROJEKT_NAME` an.
   - Erwartet: Projekt wird erstellt und ist aktiv; kein Fehlerdialog.
   - Screenshot: `02_projekt-angelegt.png`.

2. Wechsle zum Tab **MATERIAL & ANALYSE**. Importiere die Audio-Datei
   `AUDIO_PFAD` über den echten Datei-Dialog.
   - Erwartet: Audio erscheint in der Material-Liste mit korrektem Dateinamen.
   - Erwartet: Statuszeile/Waveform-Analyse startet ohne Crash.
   - Screenshot: `02_audio-importiert.png`.

3. Importiere die Video-Clips aus `VIDEO_ORDNER` (alle ~150 auf einmal über den
   Datei-/Ordner-Dialog).
   - Erwartet: Die **Anzahl der importierten Clips stimmt** mit der Zählung aus
     `01` überein (z. B. 148 von 148).
   - Erwartet: Automatische **Proxy-Tasks** starten (NVENC 540/720p) und laufen
     der Reihe nach ab — kein „OpenEncodeSessionEx failed".
   - Erwartet: GUI bleibt bedienbar, kein Freeze, kein Absturz beim Massen-Import.
   - Screenshot: `02_clips-importiert.png` (Liste/Grid mit Clip-Zahl sichtbar).

4. Prüfe in der Material-Ansicht, dass jeder Clip einen Eintrag hat und die
   Gesamtzahl korrekt angezeigt wird (Listen-Ansicht).
   - Erwartet: Keine fehlenden/doppelten Einträge.

---

## BEKANNTE SCHWACHSTELLEN PRÜFEN (PFLICHT)

- **B-498 (kein Daily-Backup):** Prüfe nach Projekt-Anlage den Ordner
  `storage/backups`.
  - Erwartet (Soll): Beim ersten Start des Tages liegt ein
    `pb_studio_<JJJJ-MM-TT>-*_daily.db`-Backup vor.
  - Bekannt fehlerhaft: In früheren Tests wurde KEIN `_daily`-Backup erzeugt.
    Melde genau, ob ein Daily-Backup existiert oder nicht. Beweis: Datei-Liste
    in `02_backups-status.txt`.

---

## ABSCHLUSS

Wenn Projekt angelegt, Audio + alle ~150 Clips importiert wurden und der
B-498-Check dokumentiert ist, gib aus:

„Teil 1 (Projekt & Import) erfolgreich getestet. Keine weiteren Aktionen nötig."

Bei Fehler stattdessen: „FEHLER in Teil 1: [Schritt + Beobachtung]" und STOPP.

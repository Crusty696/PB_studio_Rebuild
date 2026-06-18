# TEST-SKRIPT: TEIL 5 — EXPORT (RENDER)

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

Teste ausschließlich den **EXPORT-Tab**: Render des fertigen Videos per FFmpeg
(Concat, LUFS-Normalisierung, NVENC `h264_nvenc`). Voraussetzung: ein fertiger
Auto-Edit liegt auf der Timeline (Teil 4).

---

## VORBEREITUNG

1. PB Studio ist sichtbar gestartet, Projekt `PROJEKT_NAME` geöffnet, Timeline
   enthält einen fertigen Auto-Edit.
2. Notiere den Inhalt von `exports/` VOR dem Test.

---

## TEST-SCHRITTE (Der Reihe nach, alles in der GUI)

1. Öffne den Tab **EXPORT**.
   - Erwartet: Export-Optionen sichtbar (Container/Codec, LUFS-Normalisierung).
   - Screenshot: `06_export-tab.png`.

2. Starte den Export („Video exportieren").
   - Erwartet: Fortschrittsanzeige läuft; Konsole/Log nennt NVENC `h264_nvenc`
     (oder dokumentierten Fallback `libx264`).
   - Erwartet: GUI bleibt bedienbar, kein Crash.
   - Screenshot bei laufendem Export: `06_export-laeuft.png`.

3. Warte, bis der Export fertig ist.
   - Erwartet: Datei erscheint in `exports/` (z. B. `output.mp4`).
   - Screenshot: `06_export-fertig.png`.

4. Prüfe das Ergebnis mit `ffprobe` (nur als ZUSATZ-Beweis, nicht als Ersatz für
   den GUI-Test).
   - Erwartet: Datei spielbar; Video- + Audio-Spur vorhanden; Gesamtdauer passt
     zur Timeline-Länge.
   - Beweis: `06_ffprobe.txt`.

---

## BEKANNTE SCHWACHSTELLEN PRÜFEN (PFLICHT)

- **B-504 (Umlaut-Concat + Outpoint-Trim):** Stelle sicher, dass mindestens ein
  Clip mit **Umlaut im Dateinamen** (z. B. `schoene_gruene_wiese.mp4` →
  „schöne grüne wiese") auf der Timeline liegt und ein Clip per Inspector
  **getrimmt** wurde (z. B. von 10 s auf 5 s).
  - Erwartet (Soll): Export läuft fehlerfrei — **keine UTF-8-Fehler** trotz
    Umlauten; das **Outpoint-Trimming** wirkt (die gemessene Gesamtdauer
    entspricht der Summe der getrimmten Clip-Längen).
  - Beweis: `ffprobe`-Dauer in `06_ffprobe.txt` mit Rechnung
    (z. B. „95.000 s = 9×10 s + 1×5 s") + Screenshot der Export-Meldung.

---

## ABSCHLUSS

Wenn der Export ein abspielbares Video in `exports/` erzeugt hat und der
B-504-Check (Umlaut + Trim) dokumentiert ist, gib aus:

„Teil 5 (Export) erfolgreich getestet. Keine weiteren Aktionen nötig."

Bei Fehler stattdessen: „FEHLER in Teil 5: [Schritt + Beobachtung]" und STOPP.

# TEST-SKRIPT: KOMPLETT-TEST (END-TO-END)

Beachte die Dateien `00_Basis_Regeln.md` und `01_Setup_und_Parameter.md`.
**EISERNE REGEL:** Alles über die sichtbare GUI im Vordergrund. Kein Headless.
Der Nutzer muss den **gesamten** Durchlauf live mitsehen können.

---

## ZUERST: DIE DREI FRAGEN (siehe 01)

1. „Wie lautet der vollständige Pfad zur Audio-Datei (MP3/WAV/FLAC)?" → `AUDIO_PFAD`
2. „Wie lautet der Pfad zum Ordner mit den Video-Clips (MP4/MOV)?" → `VIDEO_ORDNER`
3. „Wie soll das Test-Projekt heißen?" → `PROJEKT_NAME`

Danach Parameter prüfen und App sichtbar starten (Schritte B + C aus `01`).

---

## ZIEL

Teste das **Zusammenspiel der gesamten Pipeline** in einem durchgehenden Lauf:
Projekt → Import (1 Audio 1–10 min + ~150 Clips) → Audio-Analyse → Video-Analyse
→ Auto-Edit → Export. Ein einziges frisches Test-Projekt, kein Springen, kein
Neustart von vorn ohne Grund.

---

## VORBEREITUNG

1. PB Studio ist sichtbar gestartet (4 Tabs sichtbar).
2. Frisches Projekt `PROJEKT_NAME` (noch nicht vorhanden).
3. Ergebnis-Ordner anlegen: `Test-ergebniss/<JJJJ-MM-TT>_e2e_<PROJEKT_NAME>/`.

---

## TEST-SCHRITTE (Der Reihe nach, ohne Auslassen)

1. **PROJEKT:** Neues Projekt `PROJEKT_NAME` anlegen.
   - Erwartet: Projekt aktiv, kein Fehler. Screenshot `07_01_projekt.png`.

2. **MATERIAL & ANALYSE — Import:** Audio `AUDIO_PFAD` + alle ~150 Clips aus
   `VIDEO_ORDNER` importieren.
   - Erwartet: Korrekte Audio- + Clip-Zahl; Proxies starten; kein Crash.
   - Screenshot `07_02_import.png`.

3. **Audio-Analyse:** Waveform + Beat-Detection + Stem-Separation laufen lassen.
   - Erwartet: Beatgrid + Struktur-Marker; 4 Stems erzeugt.
   - Screenshot `07_03_audio.png`.

4. **Video-Analyse:** Szenen + Motion + SigLIP + Keyframes für alle Clips.
   - Erwartet: Analyse für alle ~150 Clips abgeschlossen; Thumbnails sichtbar.
   - Screenshot `07_04_video.png`.

5. **SCHNITT — Auto-Edit:** Preset wählen (z. B. Techno) → Auto-Edit ausführen.
   - Erwartet: Timeline beat-synchron gefüllt; Preview/Transport funktioniert.
   - Setze 1 Lock; führe einmal **Re-Generate** aus (Confirm bestätigen).
   - Erwartet: Gelockter Clip bleibt erhalten.
   - Screenshot `07_05_schnitt.png`.

6. **EXPORT:** Fertiges Video rendern (NVENC, LUFS).
   - Erwartet: abspielbare Datei in `exports/`; Dauer passt zur Timeline.
   - Beweis: `07_ffprobe.txt`. Screenshot `07_06_export.png`.

7. **Gesamt-Konsistenz prüfen:** Das exportierte Video entspricht dem, was in der
   Timeline zu sehen war (Reihenfolge, Länge, Audio synchron).

---

## BEKANNTE SCHWACHSTELLEN IM E2E-LAUF BEOBACHTEN

Notiere, falls eines dieser bekannten Probleme im Durchlauf auftritt
(Detail-Checks stehen in den Einzel-Skripten):

- B-498 (kein Daily-Backup nach Projekt-Anlage)
- B-507 / B-510 / B-524 (Stem-Abbruch hängt, GPU-Lock) — nur falls abgebrochen
- B-505 (Proxy-Parallelität), B-508 / B-NEU-4 (Grid/Thumbnails)
- B-NEU-1 (Inspector-Trim), B-NEU-7 (Undo bei Drags)
- B-504 (Umlaut-/Trim-Export)

---

## ABSCHLUSS

Wenn der komplette Durchlauf von Projekt-Anlage bis abspielbarem Export-Video
ohne Abbruch funktioniert hat und der Report (mit PASS/TEIL-PASS/FAIL-Tabelle)
unter `Test-ergebniss/` liegt, gib aus:

„Komplett-Test erfolgreich. Das System ist stabil."

Bei Fehler an irgendeiner Stelle stattdessen sofort STOPP und:
„FEHLER im E2E-Test bei Schritt [N]: [Beobachtung]". Beschönige nichts.

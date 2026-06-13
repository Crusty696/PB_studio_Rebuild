# Test-Report: Live-Verifikation CRF Waves 1-4 (GUI, echte Daten)

**Datum:** 2026-06-13 02:03 - 02:48
**Projekt:** PB Studio Rebuild v0.5.0 (Branch: code-fix-pending-live-verification)
**App:** start_pb_studio.bat (conda-env pb-studio, Python 3.10 + CUDA 11.3, GTX 1060 6GB)
**Test-Projekt:** C:\Users\David Lochmann\Downloads\video\LiveVerify_2026-06-13 (+ test55655 fuer 4.2)
**Test-Daten:** Crusty_Progressive Psy Set2.mp3 (143 MB DJ-Mix), 7 Videos Solo_Natur (1 Umlaut-Kopie)
**Methode:** Echte Maus-/Tastatur-Bedienung im Vordergrund (Computer-Use), Messung via PowerShell-Polling

## Zusammenfassung

| Status | Anzahl |
|--------|--------|
| PASS | 8 |
| TEIL-PASS (mit Befund) | 2 |
| FAIL | 2 |
| BLOCKIERT (GUI-Luecke) | 1 |

## Ergebnis: TEILWEISE BESTANDEN - 7 neue Befunde

---

## Testschritte

### 1.1 Python-Interpreter-Check (B-499) - PASS
- **Aktion:** App 2x ueber start_pb_studio.bat gestartet (Doppelklick Explorer).
- **Ergebnis:** Konsole meldet "conda-env pb-studio (Python 3.10 + CUDA 11.3)", GUI startet ohne Versions-Fehlerdialog.

### 1.2 Automatisches Datenbank-Backup (B-498) - FAIL
- **Aktion:** storage\backups vor Start, nach 1. Start, nach Projekt-Anlage und nach 2. Start geprueft.
- **Erwartet:** pb_studio_2026-06-13-*_daily.db beim ersten Start des Tages.
- **Tatsaechlich:** KEIN _daily-Backup erzeugt. Nur pb_studio_2026-06-13-000755_pre-migration.db (Trigger: Projekt-Anlage 02:07). Auch im Projekt-Ordner storage\backups: leer. Keine Log-Eintraege zu "backup".
- **Positiv:** Kein Backup-Spam beim 2. Start.

### 1.3 Konsolenfenster-Flackern (B-520) - PASS
- **Aktion:** Beide App-Starts per Screenshot-Serie beobachtet.
- **Ergebnis:** Kein aufblitzendes cmd-Fenster (nur das reguläre bat-Konsolenfenster).

### 2.1 Zerstoerung aktiver Threads (B-500) - PASS
- **Aktion:** Stems-Task gestartet, Abbrechen geklickt, SOFORT "Fertige loeschen" geklickt.
- **Ergebnis:** Kein Crash, App lief stabil weiter, Task-Liste konsistent ("Keine laufenden Tasks").

### 2.2 Task-Abbruch & GPU-Sperre (B-507) - TEIL-PASS
- **PASS-Teil:** Video-Pipeline (Clip 1) abgebrochen -> neuer Task "Pipeline: 2 Videos" startete SOFORT und lief (Gemma Vision Captioning 42%).
- **FAIL-Teil:** Nach Demucs-Stems-Abbruch lief der Worker ~7 Min. weiter (python CPU-Delta 7-8s/5s). 6 Proxy-Tasks standen ~3 Min. auf "Running"/0% mit 0 ffmpeg-Prozessen, bis der Stems-Worker endete -> GPU-Sperre wird bei Stems NICHT zeitnah freigegeben.

### 2.3 Projektwechsel-Guard (B-490) - PASS
- **Aktion:** Waehrend laufender Video-Pipeline "Projekt oeffnen" geklickt.
- **Ergebnis:** Warn-Dialog "Projekt oeffnen ist nicht moeglich, solange Hintergrund-Tasks laufen." Wechsel blockiert.

### 3.1 Speicher-schonende Waveform (B-501) - PASS
- **Aktion:** 143-MB-DJ-Mix importiert, Wellenform-Analyse, python-RAM alle 2s geloggt (ram_poll_3_1.csv).
- **Ergebnis:** Fertig in <45s. RAM-Peak 2621 MB bei Baseline 2299 MB = +322 MB (Limit 1-2 GB). Waveform in Timeline sichtbar (4000 Samples, Statuszeile "Rekordbox-Analyse fertig").

### 3.2 Demucs-Skalierung & Cancel (B-510) - TEIL-PASS
- **PASS-Teil:** Separation startete ohne MemoryError, RAM stabil (~2.3 GB, ram_poll_3_2.csv).
- **FAIL-Teil:** Nach Abbrechen (Log: "Task abgebrochen: task_46c3fe694fbf") stoppte der Prozess NICHT in Sekunden: Button blieb >4 Min. auf "Stems laeuft...", Statuszeile auf "KI-Stems: 0% - Initialisierung...", CPU-Last ~150% fuer ~7 Min.

### 4.1 Parallel-Schutz Proxy-Generierung (B-505) - PASS
- **Aktion:** 6 Videos importiert -> 6 automatische Proxy-Tasks; ffmpeg-Anzahl pro 2s geloggt (ffmpeg_count_4_1.csv).
- **Ergebnis:** Alle 6 Proxies fehlerfrei erzeugt (storage\proxies, je 2.3-2.9 MB). KEIN "OpenEncodeSessionEx failed". Start war durch haengenden Stems-Abbruch verzoegert (siehe 2.2).

### 4.2 Thumbnail-Thread-Limitierung (B-508) - TEIL-VERIFIZIERT
- **Aktion:** Projekt test55655 (124 Videos, 13 Seiten) geoeffnet, Grid-Modus, 8 Seiten schnell durchgeblaettert, ffmpeg pro 1s geloggt (ffmpeg_count_4_2.csv).
- **Ergebnis:** Max. 0 ffmpeg-Prozesse gemessen -> Limit nie verletzt, aber Live-Beweis nicht moeglich: Grid-Ansicht blieb komplett LEER (eigener Befund B-NEU-4); Thumbnails vermutlich gecacht. Statisch verifiziert: ui/widgets/media_grid.py: _THUMB_POOL_MAX_THREADS = 4.

### 5.1 Concat-Export mit Umlauten & Trimming (B-504) - PASS
- **Aktion:** schoene_gruene_wiese.mp4 (Umlaut-Kopie) importiert, in Timeline, Clip via Inspector von 10s auf 5s getrimmt (50.000 -> 45.000), "Video exportieren".
- **Ergebnis:** Export fehlerfrei -> exports\output.mp4 (187 MB). ffprobe-Dauer exakt 95.000s = 9x10s + 1x5s -> outpoint-Trimming wirksam, keine UTF-8-Fehler.
- **ABER:** Inspector-Trim zerstoerte 2x reproduzierbar die Timeline-Ansicht (B-NEU-1).

### 5.2 Batch-Convert mit Video-Copy (B-517) - BLOCKIERT
- **Aktion:** Tools-Menue durchsucht, Material-Tab-Convert-Panel geprueft, Code gegengeprueft.
- **Ergebnis:** "Stapelkonvertierung" existiert nicht im Menue. Convert-Funktion = "Alle Videos standardisieren" mit Container-Optionen mp4(H.264), mp4(HEVC), mov(ProRes), mkv(H.264) - KEINE Option "Kopieren (Copy)". B-517 ist per GUI nicht verifizierbar (nur Worker-Unit-Test tests\test_workers\test_b517_convert_copy.py). Zusatzbefund: Panel wird ueberlappend gerendert (B-NEU-3).

### 6.1 Kein GUI-Freeze bei Timeline-Operationen (B-512) - PASS
- **Aktion:** Clips gedraggt + Strg+Z mehrfach schnell hintereinander.
- **Ergebnis:** GUI reagierte durchgehend sofort, kein Freeze (PerfWatchdog: max. 252ms-Events, kein Block). Befund: Drags landen nicht im Undo-Stack - Strg+Z entfernt stattdessen Clip-Hinzufuegungen (B-NEU-7).

### 6.2 Ollama Settings Dialog (B-518) - PASS
- **Aktion:** Einstellungen -> LLM Backend, Modell geaendert, OK.
- **Ergebnis:** Nicht-installiertes Modell -> sauberer Warn-Dialog (404-Hinweis + Liste installierter Modelle, Save/Cancel). Installiertes Modell (gemma3:4b) -> gespeichert, Statuszeile aktualisiert, kein Absturz. Originalwert danach wiederhergestellt.

---

## Neue Befunde (Bugs)

### B-NEU-1 (KRITISCH): Inspector-Trim leert gesamte Timeline
- **Repro (2x):** Clip in Timeline waehlen -> Clip Inspector -> Ende(s)-Feld editieren -> Enter ODER Tab.
- **Effekt:** A1- UND V1-Spur verschwinden komplett, Inspector leer, Strg+Z stellt nichts wieder her. Spur-Anzeige bleibt fuer Rest der Session kaputt (auch nach erneutem Hinzufuegen nur teilweise). App-Neustart behebt die Anzeige.
- **Daten-Ebene OK:** Trim-Wert landet in DB (Export exakt 95s). Reiner View-State-Bug, aber fuer User Datenverlust-Anmutung.
- **Zusatz:** Spinner-Buttons (+/-) am Ende(s)-Feld ohne Funktion.

### B-NEU-2: Stems-Cancel haengt (betrifft B-507/B-510)
- Worker laeuft nach Task-Abbruch ~7 Min. weiter (CPU ~150%), Button "Stems laeuft..." + Statuszeile bleiben haengen, GPU-/Pipeline-Folge-Tasks warten blockiert (~3 Min. 6x Proxy "Running"/0%).

### B-NEU-3: Convert-Panel Layout kaputt + Copy-Option fehlt
- "Ziel-Format"-GroupBox im Material-Tab wird ueberlappend/uebereinander gerendert (Dropdowns/Buttons verdeckt). Keine Codec-Option "Kopieren" -> Checklisten-Test 5.2 via GUI unmoeglich.

### B-NEU-4: Grid-Ansicht (Kachelmodus) leer
- Umschalten auf Grid-Icon zeigt auf allen 13 Seiten (124 Videos, test55655) keinerlei Kacheln/Thumbnails. Listenansicht OK.

### B-NEU-5: Kein taegliches DB-Backup (B-498 nicht wirksam)
- Siehe Test 1.2. Nur pre-migration-Backups, kein *_daily.db, keine Backup-Logzeilen.

### B-NEU-6 (klein): Strg+S speichert nicht (Schnitt-Tab)
- Nach Strg+S blieb Titel "ungespeichert"; beim Beenden kam "Ungespeicherte Aenderungen"-Dialog.

### B-NEU-7 (klein): Undo-Stack erfasst Clip-Moves nicht
- 3x Drag + 3x Strg+Z entfernte die 3 Clip-Hinzufuegungen statt der Moves. Redo (Strg+Y) stellt Clips wieder her.

---

## Mess-Artefakte
- ram_poll_3_1.csv / ram_poll_3_2.csv (python-RAM waehrend Waveform/Stems)
- ffmpeg_count_4_1.csv / ffmpeg_count_4_2.csv (ffmpeg-Prozesszaehlung)
(Quelle: C:\Users\David Lochmann\Downloads\video\)

## Hinweis Status-Vergabe
Gemaess Projekt-Regel setzt nur der User "status: fixed". Dieser Report dokumentiert Live-Beobachtungen; PASS = im Test beobachtet, ersetzt keine User-Abnahme.

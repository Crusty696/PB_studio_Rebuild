# PB Studio — GUI-Navigations-Playbook

> **Zweck:** Wiederverwendbare, präzise Klick-Anleitung für GUI-Live-Tests.
> Jeder GUI-Tester (Mensch oder Agent) folgt diesem Dokument, statt jedes Mal
> die App neu zu erkunden → spart pro Test viel Zeit. **Erweitern statt
> wegwerfen:** wer eine neue Funktion testet, trägt den Klick-Pfad hier ein.
>
> **Regel (User 2026-07-14):** Dieses Playbook wird bei jedem GUI-Test
> genutzt UND fortgeschrieben (neue/geänderte Flows ergänzen). Es ist von
> allen Agenten teilbar.

---

## 0. Setup (einmalig pro Testlauf)

- **Python (Pflicht):** `C:/Users/David_Lochmann/miniconda3/envs/pb-studio/python.exe`
  (`.venv310` fehlt → PB_PYTHON-Env-Override auf conda-Python setzen).
- **App-Start:** `<conda-python> main.py` aus Repo-Root
  `C:/Users/David_Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild`.
- **HiDPI/Surface Book 2:** Klicks via **pywinauto `click_input()`** (nicht
  pyautogui — Koordinaten-Skalierung falsch). Widget-Namen bevorzugen.
- **Log-Tail:** `logs/pb_studio.log` (Crashes/Traceback), `freeze_stacks.log`
  (Main-Thread-Freeze-Stacks; aktiviert via `PB_STUDIO_FREEZE_PROBE=1`).
- **Perf-Freeze-Probe:** Env `PB_STUDIO_FREEZE_PROBE=1`, `PB_TIMELINE_PERF=1`
  vor App-Start setzen → Watchdog schreibt Freeze-Stacks + Dauer.
- **Test-Datensatz (Standard):**
  - Video-Ordner `Solo_Natur` (~103 MP4) — Import-/Analyse-Tests.
  - Audio `Crusty Progressive Psy Set2.mp3` (~149 MB DJ-Mix) — Audio/Beat/Stems.
  - (Pfade siehe Vault `reference_test_dataset`; falls verschoben, hier aktualisieren.)

## 1. Konventionen für Einträge

Jeder Flow-Eintrag hat:
- **Ziel:** was wird getestet (Funktion + ggf. Bug-ID).
- **Vorbedingung:** Projektzustand, geladene Medien.
- **Schritte:** nummeriert, je `Widget-Name/Label → Aktion`. Wo kein
  stabiler Name: Koordinaten-Region + Screenshot-Referenz.
- **Erwartet:** sichtbares Ergebnis.
- **Freeze-Beobachtung:** wo Main-Thread-Freeze auftreten kann (mit alter
  Baseline in Sekunden, falls bekannt).

> **STATUS DER FLOWS UNTEN:** Gerüst — Widget-Namen/Koordinaten werden vom
> ersten GUI-Test befüllt (TODO-Marker ersetzen).

---

## 2. Flow-Katalog

### 2.1 App-Boot
- **Ziel:** sauberer Start ohne Boot-Freeze (B-627: EmbeddingScheduler-Boot).
- **Schritte:**
  1. `PB_STUDIO_FREEZE_PROBE=1 PB_TIMELINE_PERF=1` setzen, dann Harness `start --freeze-probe`.
  2. `wait-window --title "PB_studio"` (matcht zunächst evtl. den Datei-Explorer-Titel
     der Working-Dir, das Hauptfenster hat erst nach dem Splash-Screen den echten
     Titel `PB_studio v0.5.0 — Director's Cockpit`; per `list-windows` verifizieren).
  3. Alle ~2s `screenshot` bis Splash weg ist und Tabs (PROJEKT/MATERIAL
     ANALYSE/SCHNITT/EXPORT) sichtbar + klickbar sind (Media-Tabelle gefüllt =
     interaktiv).
  4. Boot-Ende per Log bestimmen: `[FREEZE-PROBE] Heartbeat-Watchdog aktiv` (Start)
     bis erste `[SLOW EVENT] ... Resize/Paint -> PBWindow` Zeilen (App reagiert).
- **Erwartet:** Hauptfenster < ~3s interaktiv, kein 5s-Hang beim Brain-V3-Boot.
- **Freeze-Beobachtung:** früher bis 5s (`embedding_scheduler.start/wait_ready`).
  **Live-Befund 2026-07-14:** `embedding_scheduler` blockiert nicht mehr direkt,
  ABER Boot zeigt weiterhin ~8–10s Main-Thread-Freeze
  (`services/startup_checks.py:762 check_nvidia_gpu_state`, PowerShell-Subprocess
  synchron im Main-Thread mit hartem 5s-Timeout + serielle Imports). Vorbestehend,
  identisch in `freeze_stacks_BEFORE_FIX.log`, nicht Teil des B-627-Fixes.

### 2.2 Projekt öffnen / Projekt-Switch
- **Ziel:** Projekt-Load ohne Freeze (B-620, B-622, B-623).
- **Schritte:**
  1. Klick auf Tab-Button `auto_id="workspace_nav.workspace_btn"`, `name="Projekt Workflow"`
     (Koordinate bei 3240x2160: ca. x=942, y=154) → PROJEKT-Tab.
  2. Klick Button `name="Projekt oeffnen"` (kein auto_id, `control_type=Button`,
     rechts oben, ca. x=2504, y=253) → öffnet Qt-Dialog "Projekt oeffnen"
     (grüner Titlebar, eigenes Fenster).
  3. Ins Textfeld `Projektordner waehlen...` klicken (ca. x=1553, y=1005 relativ zum
     Dialog-Zustand) und Vollpfad tippen, z. B.
     `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\projects\test33`.
  4. Klick Button `Oeffnen` (rechts unten im Dialog).
  5. Fenstertitel wechselt auf `PB_studio v0.5.0 — test33`; Cockpit zeigt
     „Schnitt oeffnen (Review)“ + Audio/Video „Bereit“.
- **Erwartet:** Timeline lädt, kein mehrsekündiger UI-Freeze.
- **Freeze-Beobachtung:** früher 2–14s (Blob-ORM-Loads); B-622 einmalig 42s.
  **Live-Befund 2026-07-14:** Projekt-Load selbst < 8s, 0 neue
  `freeze_stacks.log`-Einträge → PASS für B-620/622/623. CAVEAT: perf_watchdog
  loggte einmalig `[SLOW EVENT] 42047ms MouseRelease -> QPushButton` exakt beim
  Öffnen des modalen Dialogs — sehr wahrscheinlich Messartefakt durch
  `QDialog.exec()` reentrant in `notify()`, kein echter Freeze (kein
  `freeze_stacks.log`-Hang in diesem Fenster). Bei künftigen Retests nicht
  vorschnell als B-622-Regression werten, sondern Root-Cause-Stack prüfen.

### 2.3 Audio-/Video-Combo-Wechsel
- **Ziel:** B-625 (edit_workspace combo). Kein Freeze beim Umschalten.
- **Schritte:**
  1. SCHNITT-Tab öffnen (Tab-Button `name="Schnitt Workflow"`, x≈1470, y≈154).
  2. QComboBox `name="Video-Clip Auswahl"` (kein auto_id, oben rechts neben
     „Audio-Track Auswahl“, ca. x=1404, y=224) anklicken → Dropdown öffnet mit
     Liste `[ID] Dateiname`.
  3. Eintrag anklicken (Liste beginnt bei y≈184 unter dem Combo, erster Eintrag
     `-- kein Video --`, danach Video-IDs).
- **Erwartet:** Vorschau/Pacing-Kurve aktualisiert, kein Stall.
  **Live-Befund 2026-07-14:** max. 254ms Slow-Event, PASS.

### 2.4 Audio analysieren
- **Ziel:** Audio-V2-Analyse-Route, kein Freeze.
- **Schritte:** _TODO: Button „Audio analysieren" (audio_analysis)._ 
- **Erwartet:** Analyse läuft im Worker, UI responsiv.

### 2.5 Auto-Ducking (Stems)
- **Ziel:** B-625 (stems `_start_auto_ducking`).
- **Vorbedingung:** Stems separiert.
- **Schritte:** _TODO: Auto-Ducking-Button._
- **Erwartet:** kein Klick-Lag durch Blob-Load.

### 2.6 A/B-Compare
- **Ziel:** B-625 (ab_compare_dialog). ACHTUNG: AudioTrack-Rest-Freeze bekannt.
- **Schritte:** _TODO: A/B-Compare öffnen → „Run"._
- **Erwartet:** Kandidaten laden; Rest-Freeze aus AudioTrack-Teil möglich (dokumentiert).

### 2.7 Auto-Edit
- **Ziel:** B-624 (pacing_beat_grid), B-622 (OTIO-Timeline-Build nach Finish).
- **Schritte:**
  1. SCHNITT-Tab, Button `auto_id="schnitt_editor.btn_accent"`, `name="Auto-Edit starten"`
     (oben rechts neben "Timeline generieren", ca. x=2558, y=224).
  2. Es öffnet ein Overlay „Auto-Edit läuft…“ mit Progress-Bar + Status-Text
     (z. B. „Lade Audio…“) + Button `name="Auto-Edit abbrechen"` (ca. x=1316, y=1008).
  3. Poll per Screenshot alle ~10s bis Overlay verschwindet ODER Fehlermeldung
     im Status-Bar unten erscheint (`⚠ Fehler in 'Auto-Edit (Phase 3)': ...`).
- **Erwartet:** Cuts erzeugt, kein wiederkehrender ~3s-Freeze, kein 42s-Hang beim Finish.
  **Live-Befund 2026-07-14 (FAIL):** unter Last von 269 parallel importierten
  Clips (Proxy+Embedding-Pipeline lief noch) hing der Prozess >3 Minuten in
  „Lade Audio…“, Einzelfreezes bis 17.9s (`pacing_beat_grid.py:232/694`, JSON-Blob
  ORM-Load-Muster wie B-620, hier nicht gefixt), Windows-Titel zeigte „Keine
  Rückmeldung“. Ergebnis am Ende: Fehlermeldung „Keine Segmente“. Der
  „Abbrechen“-Button schließt nur das Dialog-Overlay, der Hintergrund-Task
  (`workers/edit.py`) läuft nachweislich weiter (siehe freeze_stacks.log nach
  Cancel-Klick). Für sauberen Reproduktionstest: Auto-Edit NICHT parallel zu
  einem großen Ordner-Import (>50 Dateien) ausführen, sondern isoliert.

### 2.8 Undo Clip entfernen
- **Ziel:** B-625 (undo_commands RemoveClipCommand.undo).
- **Schritte:** _TODO: Clip entfernen → Strg+Z._ (2026-07-14 nicht erreicht,
  Zeitbudget durch Freeze/Crash-Kaskade bei 2.7/2.10 aufgebraucht.)
- **Erwartet:** kein Freeze beim Undo.

### 2.9 Media-Import
- **Ziel:** B-627 (submit_task fire-and-forget beim Import).
- **Schritte:**
  1. MATERIAL ANALYSE-Tab (Tab-Button `name="Material und Analyse Workflow"`,
     x≈1206, y≈154), Sub-Tab „VIDEO“ ist Default.
  2. Button `auto_id="btn_secondary"`, `name="Ordner importieren"` (ca. x=212,
     y=384) → öffnet nativen Qt-Dateidialog „Ordner importieren“.
  3. Ins Feld `Directory:` (unten im Dialog) klicken und Vollpfad tippen, z. B.
     `C:\Users\David_Lochmann\Videos\Solo_Natur-20260406T220640Z-3-001\Solo_Natur`.
  4. Button `name="Choose"` klicken (per `find-element --name-re Choose` sicher
     zu treffen, Koordinaten der nativen Qt-Filedialog-Buttons verschieben sich
     je nach Pfadlänge).
  5. Dialog schließt sofort; rechtes Kontext-Panel (TASKS) zeigt neuen Eintrag
     `FolderImport: Running`, Status-Bar unten zeigt `[Import] NN% — Importiere
     X/Y`.
- **Erwartet:** Import-Dialog blockiert nicht 5s beim Einreihen.
  **Live-Befund 2026-07-14 (PASS):** 0s Main-Thread-Freeze beim Submit, Dialog
  schloss sofort, Import lief komplett als Hintergrund-TaskEngine-Task. Klarer
  B-627-Fixerfolg. ACHTUNG: der danach folgende automatische Proxy-Generierungs-
  Sturm (1 Task pro importierter Datei, hier 269) verursacht SEPARATE, schwere
  Freezes/Crashes in nachfolgenden Flows (siehe 2.7, 2.10) — bei kleineren
  Testläufen ggf. bewusst kleine Ordner (5–10 Dateien) importieren.

### 2.10 Anker-Sync (Dialog → Timeline-Marker) — NEU B-619
- **Ziel:** Dialog-Anker persistieren + als Cyan-Marker auf Timeline sehen.
- **Schritte:**
  1. SCHNITT-Tab, Sub-Tab `name="Pacing  Anker"` (Doppelleerzeichen im Label!,
     ca. x=283, y=287 bei 3240x2160 — Tab-Leiste liegt bei y≈177 im 2000er
     Vorschaubild, ×1.62 skalieren).
  2. Rechtes Panel „ANKER (feste Audio-Video-Sync-Punkte)“ mit leerer Tabelle
     (Spalten Zeit/Video/Label/Gewicht).
  3. Button `+ Anker` (unten links im Anker-Panel, ca. x=1395, y=1925) → Dialog
     „Anker hinzufügen“ (grüner Titlebar) mit Feldern `Zeitpunkt (Sek)` (QSpinBox)
     und `Video/Szene` (QComboBox, Liste aller Szenen `Dateiname | Szene N
     (start-end)`).
  4. Szene per Klick auf Combo (ca. x=1669, y=1037 im Dialog) + Listeneintrag
     wählen, dann Button `Hinzufügen` (ca. x=1447, y=1140) klicken.
  5. Vorgang für 2. Anker wiederholen (Dialog öffnet sich erneut über denselben
     `+ Anker`-Button).
  6. Button `Sync` (rechts neben `+ Anker`/`- Anker`, ca. x=1639, y=1925) klicken.
  7. Erwartete Erfolgsmeldung im Log: `"N Dialog-Anker synchronisiert"` — falls
     NICHT im Log, per `log-since` auf `_sync_anchors` / `anchor_sync_service`
     Traceback prüfen (siehe Live-Befund).
  8. Cyan/türkise Marker sollten auf der Audio-Zeitachse im „Schnitt“-Sub-Tab
     erscheinen (Timeline-Waveform-Bereich, getrennt von den goldenen
     Beat-Gitterlinien) — per Screenshot-Crop `--region` auf den
     Timeline-Waveform-Bereich prüfen (`y≈930-1230` bei 3240x2160).
- **Erwartet:** Meldung „N Dialog-Anker synchronisiert"; **cyan-türkise vertikale
  Marker** erscheinen auf der Audio-Zeitachse der Timeline (getrennt von goldenen Beats).
  **Live-Befund 2026-07-14 (FAIL/CRASH):** `+ Anker` funktioniert (2 Anker
  erfolgreich in der Anker-Tabelle sichtbar), aber `Sync` crasht mit
  `sqlite3.OperationalError: database is locked` in
  `services/anchor_sync_service.py:58 _resolve_scene_id`, ausgelöst durch
  `session._autoflush()` während massiver paralleler Hintergrundlast (Proxy-
  Generierung + Embeddings für 269 Clips liefen noch). `select count(*) from
  audio_video_anchors` ergab 0 Zeilen nach dem Sync-Versuch — nichts persistiert,
  keine Timeline-Marker, keine Erfolgsmeldung. Für sauberen Reproduktionstest:
  Sync NICHT parallel zu großer Hintergrundlast testen, sondern nach
  vollständigem Abschluss aller Proxy/Embedding-Tasks (TASKS-Panel rechts prüfen:
  alle Einträge müssen „Fertig“ statt „Running“ zeigen).

### 2.11 Schnitt Sub-Tab-Leiste (Schnitt / Pacing Anker / Audio / RL Notes) — NEU 2026-07-15
- **Ziel:** Sub-Tabs unterhalb der Audio/Video-Combo-Zeile im SCHNITT-Workspace anwaehlen.
- **Koordinaten (3240x2160, reale Screen-Coords fuer Harness-`click`):**
  - `Schnitt`: x=84, y=287
  - `Pacing Anker`: x=280, y=287
  - `Audio` (Stem-Mixer): x=470, y=287
  - `RL Notes`: weiter rechts, ca. x=650, y=287 (nicht exakt vermessen)
- **FALLE (2026-07-15 verifiziert):** Wenn Koordinaten aus einem Screenshot
  abgelesen werden, das per `Read`-Tool angezeigt wird, gibt der Read-Tool-
  Footer einen Skalierungsfaktor an (z. B. "displayed at 2000x1333, original
  3240x2160 → Multiply coordinates by 1.62"). **Diesen Faktor IMMER auf die
  abgelesenen Koordinaten anwenden**, bevor sie an `gui_harness click`
  gehen — sonst landen Klicks (v. a. in QMenu-Kontextmenues) auf der
  falschen Stelle und die Aktion feuert nicht (kein Fehler im Log, einfach
  keine Wirkung). Genau das ist beim ersten B-077-Testversuch passiert:
  Klick auf "Anker setzen" bei den *unskalierten* Read-Tool-Koordinaten traf
  daneben, kein DB-Insert, kein Log-Eintrag. Nach Korrektur (×1.62) hat der
  Klick sofort funktioniert.

### 2.12 Clip-Kontextmenue (Rechtsklick auf Timeline-Clip) — NEU B-077, 2026-07-15
- **Ziel:** Anker setzen/entfernen ueber das Clip-Kontextmenue (ClipAnchor,
  NICHT zu verwechseln mit den Dialog-Ankern aus 2.10/AudioVideoAnchor).
- **Schritte:**
  1. SCHNITT-Tab, Sub-Tab `Schnitt`, Rechtsklick auf einen Video-Thumbnail
     in der Video-Spur (unterhalb der Audio-Waveform, ca. y=1360 bei
     Zoom 100%).
  2. Kontextmenue (dunkel, `#1A1A1A`) mit 3 Eintraegen: `Anker setzen
     (X.XXs)`, `Clip: video | ID: <n>`, `Brain V3: Cut bewerten`. Falls
     bereits ein Anker auf dem Clip existiert, zusaetzlich `Alle Anker
     entfernen` (2. Eintrag).
  3. Menue-Item-Position relativ zum Rechtsklick-Punkt: erstes Item
     (`Anker setzen`) ca. 15-30px unterhalb + rechts vom Klick-Y (Menue
     oeffnet mit Top-Left nahe am Cursor).
- **Erwartet:** Ankermarker (rotes Dreieck + gestrichelte rote Linie) an der
  Klickposition erscheint SOFORT synchron (optimistic UI, B-077). ClipAnchor
  wird asynchron in Pool-Thread in die DB geschrieben (Tabelle
  `clip_anchors`).
- **Live-Befund 2026-07-15 (PASS, nach Koordinaten-Fix):** Marker erscheint
  augenblicklich, kein Freeze, kein Crash. `clip_anchors`-Zeile nach ca. 1s
  Wartezeit verifiziert. "Alle Anker entfernen" entfernt Marker sofort
  synchron, DB-Zeile async geloescht — verifiziert per DB-Query. Kein
  `freeze_stacks.log`-Eintrag waehrend beider Aktionen.

---

### 2.13 Erststart / SetupWizard-Falle bei conda-Python (PB_PYTHON-Override) — NEU 2026-07-15
- **Ziel:** App-Start via `PB_PYTHON=<conda-python>` dokumentieren — abweichend
  von `.venv310`-Start kann ein First-Run-Marker fehlen, wodurch der
  `SetupWizard` (Fenstertitel `"PB Studio — Ersteinrichtung"`, NICHT
  `"PB_studio"`) statt des Hauptfensters erscheint.
- **Erkennung:** `wait-window --title "PB_studio"` läuft in 60s Timeout,
  `list-windows` zeigt `"PB Studio — Ersteinrichtung"`.
- **Fix:** `screenshot --window-title "Ersteinrichtung"` (harness filtert
  Screenshots sonst auf Fenster mit `"PB_studio"`-Fragment), dann Button
  „Überspringen" klicken (bei 3240×2160 ca. x=1139, y=1513). Danach
  erscheint das reguläre Hauptfenster `"PB_studio v0.5.0 — Director's
  Cockpit"`.

### 2.14 Schnitt/Audio-Subtab ENERGIE/ONSETS/SNR-Leiste — NEU B-494 GUI-Verify 2026-07-15
- **Ziel:** Verifikation, dass die drei Analyse-Subtabs unterhalb des
  Stem-Mixers sichtbar/klickbar sind (Fix aus Commit c9786d3, vorher laut
  Playbook-Eintrag 2026-07-15 oben nie gemountet).
- **Koordinaten (3240×2160):** Tab-Leiste liegt bei y≈1756 (unterhalb
  Play/Stop-Reihe des Stem-Mixers). `ENERGIE` x≈89, `ONSETS` x≈228, `SNR`
  x≈351 (aus Read-Tool-Displaykoordinaten × 1.62 skaliert — Playbook-Falle
  aus 2.11 gilt auch hier, beim ersten Versuch unskaliert geklickt →
  Klick ging ins Leere/auf falsches Widget).
- **Play/Stop-Buttons Stem-Mixer:** Play ca. x=164, y=1680; Stop ca. x=76,
  y=1680 (3240×2160).
- **Live-Befund 2026-07-15 (PASS):** Alle 3 Tabs sichtbar + klickbar.
  ONSETS zeigt bei geladenem, analysiertem Track echte Daten (`Kick 20371 /
  Snare 25900 / Hihat 23933` + Marker-Streifen). ENERGIE/SNR zeigen für den
  getesteten Track (`02 Mai19 - Kopie`) sauberen Leer-Zustand
  („nicht berechnet" / „nicht verfuegbar") statt Crash — Feature ist
  jetzt real erreichbar (vorher laut Code-Trace nie gemountet).
- **Play/Stop-Regressionstest (8 doppelte Connects entfernt, Commit
  c9786d3):** Play → Position lief einmalig hoch (0:05 → 0:20 in ~15s,
  keine 2×-Geschwindigkeit als Indiz für Doppel-Trigger). Stop → Position
  zurück auf 0:00, Icon zurück auf ▶. Keine doppelten Log-Einträge, kein
  Crash. PASS.

### 2.15 Material & Analyse Toolbar — Papierkorb + Sammlung bereinigen — NEU F-02 GUI-Verify 2026-07-15
- **Ziel:** `btn_clear_all` ("Sammlung bereinigen") nach F-02-Fix (Commit
  c9786d3) in der sichtbaren Toolbar statt im nie gemounteten FILTER-Subtab.
- **Koordinaten/Elemente (3240×2160, via `find-element`):** Toolbar-Reihe
  MATERIAL & ANALYSE → VIDEO-Subtab, y≈354-414. Button-Reihe: `+ Video`,
  `+ Ordner`, `Loeschen` (danger), `Papierkorb` (auto_id btn_secondary,
  center≈494,384), `Sammlung bereinigen` (auto_id **btn_danger**,
  center≈696,384, `enabled: true`, `visible: true`).
  `find-element --name-re "Sammlung bereinigen"` matcht NICHT (Name-Property
  ist der Tooltip-Text, nicht der Label-Text!) — stattdessen
  `--name-re "Alle Medien aus DB"` verwenden.
- **BEOBACHTUNG (kein Bug aus dieser Session, aber real):** Trotz
  `objectName="btn_danger"` und `danger=True`-Flag rendert der Button
  NICHT rot. `resources/styles.qss` definiert `QPushButton#btn_danger`
  (roter Text/Rand `#CC4444`), aber die App laedt diese Datei nicht — sie
  nutzt `ui/theme.py::get_stylesheet()` (programmatisch, `app.setStyleSheet(...)`
  in `main.py:1907`), und **dort existiert keine `btn_danger`-Regel**
  (nur `btn_accent`/`btn_secondary`). `resources/styles.qss` ist toter Code
  (nur `dist/`-Kopie + Quelle, kein `main.py`-Import). Betrifft auch
  `btn_delete_selected_video` ("Loeschen", ebenfalls `danger=True`) —
  gleiches Bild, gleiche Ursache, vorbestehend, NICHT durch c9786d3
  eingefuehrt (Diff zeigt nur Verschieben des Buttons, kein Styling-Touch).
- **Trash-Dialog (QThreadPool-Migration):** Klick auf "Papierkorb" öffnet
  Dialog `"Papierkorb — soft-geloeschte Medien"` (grüner Titlebar) ohne
  Main-Thread-Freeze (0 neue `freeze_stacks.log`-Einträge seit Boot-Ende).
  Bei leerem Papierkorb erscheint Liste direkt mit "Papierkorb ist leer."
  (Ladezustand ggf. zu kurz für Screenshot-Erfassung bei leerem Bestand).
  Log zeigt `ImportMedia._open_trash: Klick angekommen, oeffne Papierkorb`.
  Schliessen-Button ca. x=2067, y=1359 (3240×2160).

### 2.16 Boot-Watchdog-Fehlalarm bei conda-Python + First-Run-SetupWizard
- **Beobachtung 2026-07-15:** `freeze_stacks.log` zeigte beim Boot mit
  aktivem SetupWizard (modaler `QDialog.exec()`) eine WATCHDOG-Kaskade
  „Main-Thread blockiert seit 1.9s" hochzählend bis „90.3s", Stack zeigt
  Haupt-Thread in `main.py:2063 main()` (App-Event-Loop) — kein echter
  Hang, sondern bekanntes Watchdog-Fehlalarm-Muster bei offenen modalen
  Dialogen (siehe bereits dokumentiert in 2.2 „QDialog.exec() reentrant").
  Nach Wizard-Skip keine weiteren WATCHDOG-Einträge während des gesamten
  Testlaufs (Projekt-Load, Tab-Switches, Play/Stop, Trash-Dialog) → alle
  echten App-Interaktionen freeze-frei.

## 3. Änderungslog
- 2026-07-14: Gerüst angelegt (Freeze-Sanierung B-619/622/623/624/625/626/627).
  Flow-Details TODO — erster GUI-Test befüllt Widget-Namen/Koordinaten.
- 2026-07-14 (Freeze-Retest): Flows 2.1, 2.2, 2.3, 2.7, 2.9, 2.10 mit echten
  Widget-Namen/Koordinaten/Klick-Pfaden befüllt + Live-Befunde eingetragen
  (PASS: 2.2, 2.3, 2.9; FAIL: 2.7, 2.10; TEILWEISE FAIL: 2.1). Neuer Befund:
  Masse-Import (>200 Dateien) erzeugt Hintergrundlast, die B-624/B-619 in
  nachfolgenden Flows verschärft/reproduziert — Warnhinweis in 2.7/2.9/2.10
  ergänzt. Report: `test_reports/freeze-retest-2026-07-14/report.md`.
  Flows 2.4, 2.5, 2.6, 2.8 weiterhin TODO (nicht erreicht, Zeitbudget).
- 2026-07-15 (B-617/B-077/B-494-Regressionstest, HEAD 3b32180): Flows 2.11
  (neu, Sub-Tab-Leiste + Koordinaten-Skalierungsfalle dokumentiert), 2.12
  (neu, Clip-Kontextmenue/Anker) ergaenzt. Beat-Grid+Sections (B-617) per
  Pixel-zu-Zeit-Kalibrierung gegen `structure_segments`-DB exakt verifiziert
  (PASS, auch nach Projekt-Reload). B-077 Anchor-Optimistic-UI PASS (nach
  Koordinaten-Fix). B-494 SNR-Anzeige: Code-Trace ergab, dass
  `ui/workspaces/stems_workspace.py` (`StemsWorkspace` mit ENERGIE/ONSETS/
  SNR-Subtabs) im Fenster NIE eingehaengt wird — `ui/workspaces/schnitt/
  tab_audio.py` instanziiert stattdessen eine eigene, separate
  `StemWorkspace`-Mixer-Instanz ohne SNR-Subtab. `_stems_ws.update_analysis()`
  wird zwar befuellt (B-494-Fix korrekt), aber niemand sieht das Ergebnis in
  der laufenden App. Kein Crash (sauberer Silent-Fail), aber Feature real
  nicht erreichbar. Report: siehe Task-Output pb-gui-tester 2026-07-15.
- 2026-07-15 (E1/E3/Play-Stop/Trash-Regressionstest, Commit c9786d3): Flows
  2.13 (SetupWizard-Falle bei conda-Python-Start, neu), 2.14 (Stems-Subtabs
  ENERGIE/ONSETS/SNR jetzt real sichtbar+mit Daten, PASS; Play/Stop-Single-Fire
  nach 8-fachem Doppel-Connect-Fix verifiziert, PASS), 2.15 (btn_clear_all in
  sichtbarer Toolbar erreichbar+enabled PASS, ABER Danger-Styling fehlt real
  — `btn_danger`-QSS-Regel existiert nur in ungeladener `resources/styles.qss`,
  nicht in der tatsächlich geladenen `ui/theme.py::get_stylesheet()`,
  vorbestehend nicht durch diese Session eingeführt; Trash-Dialog PASS ohne
  Freeze), 2.16 (Boot-Watchdog-Fehlalarm bei offenem SetupWizard-Modal,
  dokumentiert) ergaenzt. 0 neue Tracebacks/Crashes im gesamten Testlauf.

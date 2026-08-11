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

### 2.21 Agent-Livetest-Erkenntnisse (Fix-Verify B-759/760/761/762) — NEU 2026-08-06
- **Autoload + Auto-Resume:** App laedt beim Start das letzte Projekt
  automatisch (Titel wechselt ohne Klick auf `— <projektname>`) und startet
  selbststaendig eine Batch-Analyse fuer alle unfertigen Clips
  (`[Pipeline] Starte Batch-Analyse fuer N Video(s)` direkt nach
  `[Projekt] Geoeffnet`). Fuer isolierte Tests: Pipeline zuerst abbrechen.
- **Workspace-Tabs sind `control_type=CheckBox`**, nicht Button —
  `click-element --name-re "^Schnitt Workflow$"` OHNE `--control-type`.
- **Pipeline-Abbruch:** TASKS-Panel rechts, Button `name="Abbrechen"`
  (rot, ca. x=3142, y=186). Log-Beleg: `[TaskEngine] Kooperativer Abbruch`
  + `Analysis cancelled: video/<id>/<step>`; GPU_EXECUTION_LOCK released
  folgt einige Sekunden spaeter.
- **Auto-Edit Empty-State:** vier Preset-Karten
  (`auto_id="schnitt_empty.preset_button"`, Namen `Auto-Edit Preset
  Techno|Cinematic|House|Festival`). Klick startet direkt. Dauer bei 251
  Clips / 5531s Audio / Studio-Brain+Reranker: ca. 19 Minuten bis
  `ApplyAutoEditCommand.redo`.
- **App-Schliessen mit laufenden Tasks (automatisiert):** `gui_harness kill`
  braucht `.app_pid` (nur nach `start` vorhanden); bei Direktstart
  stattdessen `(Get-Process ...).CloseMainWindow()`. Danach erscheint
  Dialog-Fenster `"Laufende Tasks"` mit Buttons `Yes`/`No` —
  `click-element --window-title "Laufende Tasks" --name-re "^Yes$"`.
- **LOG-Panel** (Kontext rechts, TabItem `LOG`, center 2934,132) zeigt die
  `console_text`-Zeilen (`[StemPlayer] ...`), die NICHT in stdout/Logfile
  landen — fuer B-761-artige Verifikationen Panel-Screenshot noetig.

### 2.22 B-643 Live-Verify — SCHNITT/Audio-Thumbnail-Sturm mit 1415-Segmente-Projekt — NEU 2026-08-09
- **Ziel:** Live-Verify des Fix-Commits `ba12528` (Timeline-Thumbnails ueber
  geteilten QThreadPool statt QThread-pro-Thumbnail) gegen Original-Repro
  aus B-643 (32+ sichtbare Clips, AppHang > 6 Min, Windows-Kill AppHangB1).
- **Vorbedingung:** Testprojekt `new_test_august` (1415 Timeline-Segmente
  Video + 1 Audio) — deutlich mehr Last als das urspruengliche `test33`
  (32 Clips).
- **Falle:** `gui_harness start --stability-project <pfad>` laedt das
  Projekt NICHT automatisch (anders als beim normalen App-Autoload-Verhalten
  aus 2.21) — Cockpit zeigt "Kein Projekt aktiv". Projekt danach ganz normal
  ueber PROJEKT-Tab -> "Projekt oeffnen" -> Pfad tippen -> "Oeffnen" laden
  (Flow 2.2).
- **Schritte:** SCHNITT-Tab (x=1470,y=154) -> Sub-Tab `Audio` (x=470,y=287,
  3240x2160) -> optional Sub-Sub-Tab `ONSETS` (x=228,y=1756) -> zurueck zu
  `Schnitt` (x=84,y=287) -> wieder `Audio`. 6x wiederholt, davon 3x ohne
  Pause direkt hintereinander (aggressivste Provokation).
- **Live-Befund 2026-08-09 (PASS):** Thumbnail-Sturm eindeutig ausgeloest
  (32 `[T1] thumb worker start`-Zeilen in ~3s beim ersten Audio-Klick,
  identisches Muster wie im Bugfile). App blieb in JEDEM der 6 Zyklen
  durchgehend responsiv: kein `(Keine Rueckmeldung)` im Fenstertitel (per
  `list-windows` gepollt), `logs/freeze_stacks.log`-mtime blieb unveraendert
  seit App-Boot (kein einziger neuer Freeze-Stack-Dump), 0 Crash-Marker
  (`CRITICAL`/`Traceback`/`AppHang`) im gesamten Testfenster (279 Log-Zeilen
  geprueft). Max. Slow-Event 529ms (weit unter 3s-Watchdog-Schwelle,
  frueher waren es bis 130ms Paint/MetaCall-Events beim urspruenglichen
  Sturm). `request_visible`-Log zeigt am Ende `inflight=0` — kein
  Thumbnail-Leak im `ThumbnailLoadManager`. Fix-Commit `ba12528` haelt der
  Live-Probe stand — B-643 mit dieser Methodik NICHT reproduzierbar,
  ABER: B-643 war laut Bugfile selbst intermittierend (Boot 1 hing, Boot 2
  lief durch) — ein einzelner sauberer Testlauf mit 6 Zyklen beweist keine
  vollstaendige Absenz des Restrisikos, macht es aber sehr unwahrscheinlich
  angesichts des strukturellen Fixes (QThreadPool statt Thread-Churn).

### 2.23 Zwei parallele App-Instanzen + Tastatur-Eingabe — NEU 2026-08-09
- **Falle (real passiert, zweimal):** Laufen zwei PB_studio-Fenster
  gleichzeitig (identischer Titel `Director's Cockpit`, identische
  Vollbild-Geometrie), liefert `pygetwindow` bzw.
  `gui_harness list-windows` **non-deterministisch nur eines** der beiden.
  Koordinaten-Klicks landen dann im falschen Prozess. Am 2026-08-09
  loeste ein Isolations-Test dadurch im Fenster eines anderen Testlaufs
  ein `Projekt geoeffnet: new_test_august` aus, und ein zweiter Vorfall
  (04:57) erzeugte Fremd-Klicks samt `SettingsDialog` in einer fremden
  Instanz.
- **Regel:** **Nie zwei GUI-Testlaeufe parallel.** Wenn es unvermeidbar
  ist, das fremde Fenster per `ShowWindow(SW_MINIMIZE)` minimieren und
  das eigene per `pywinauto Application(process=<PID>).top_window()
  .set_focus()` gezielt fokussieren — rohes `SetForegroundWindow` wird
  von Windows blockiert. Immer gegen die **eigene PID** targeten, nie
  blind auf Bildschirmkoordinaten.
- **Tastatur-Falle:** `gui_harness type` / `pyautogui.typewrite` in ein
  bereits befuelltes `QLineEdit` erzeugt verschachtelten, verstuemmelten
  Text (Fokus-Race + Layout). Robust ist stattdessen `pywinauto` UIA
  `edit.set_edit_text(...)` — setzt den Wert direkt, umgeht Tastatur-
  Layout und Fokus komplett.
- **Kontaminations-Check nach jedem Lauf:** Log-Offset vor dem Test
  merken und hinterher pruefen, ob im Testfenster Events auftauchen, die
  man nicht selbst gesendet hat (`MousePress`, `SLOW EVENT ... QMenu`).
  Betroffene Zeitspannen keinem Ticket zurechnen, sondern den Schritt in
  einer sauberen Session wiederholen.

### 2.24 `click-element --name-re` ohne Window-Scope trifft System-Fenster — NEU 2026-08-09
- **Falle:** `click-element --name-re "Einstellungen"` traf die **Windows-
  Settings-App** statt den PB-Studio-Button — beide Fenster hiessen zu
  dem Zeitpunkt "Einstellungen".
- **Regel:** Bei Namen, die mit System-Fenstern kollidieren koennen, nie
  `click-element` mit blossem `--name-re` verwenden. Stattdessen
  `find-element --window-title "PB_studio" --name-re "..."` und den
  gefundenen Treffer per Koordinate klicken.
- **Shutdown-Dialogkette (Klarstellung, kein Bug):** Bei dirty Projekt
  fragt `main.py::closeEvent` zuerst "Es gibt ungespeicherte
  Aenderungen. **Trotzdem beenden?**". "No" bedeutet hier *nicht
  beenden* -> `event.ignore()`, die App bleibt offen und die
  "Laufende Tasks"-Prompt erscheint bewusst nicht mehr. Wer die
  Tasks-Prompt testen will, muss vorher speichern (oder mit "Yes"
  antworten). Am 2026-08-09 wurde das einmal faelschlich als Bug
  gemeldet.

### 2.25 Task-Running-Guard blockiert JEDEN Projektwechsel — NEU 2026-08-10/11 (Live-Verify B-035/B-077/B-657/B-717/B-714/B-795/B-794)
- **Beobachtung:** Solange irgendein Hintergrund-Task laeuft (TASKS-Panel zeigt "Running"),
  egal ob Proxy-Generierung, Audio-V2-Analyse oder Auto-Edit selbst, blockieren SOWOHL
  "Projekt oeffnen" ALS AUCH "+ Neues Projekt" mit dem Dialog "... ist nicht moeglich,
  solange Hintergrund-Tasks laufen. Bitte warte, bis alle Tasks im TASKS-Panel beendet
  sind, und versuche es erneut." Dieser generelle Guard greift VOR jeder
  B-714/B-795/B-794-spezifischen Discard-Logik.
- **Konsequenz fuer Tests:** Die klassischen "waehrend X laeuft Projekt wechseln"-Szenarien
  (Cuts-Berechnung, Auto-Edit, Keyframe-Strings) sind ueber die normale GUI aktuell NICHT
  reproduzierbar, solange dieser Guard aktiv ist — weder ueber den Dialog-Pfad noch ueber
  Neues-Projekt. Falls ein Agent diese Szenarien live pruefen soll: zuerst klaeren, ob es
  einen Bypass gibt (z. B. Recent-Projects-QMenu, siehe 2.17 — dort NICHT explizit gegen
  diesen Guard getestet), sonst ehrlich NICHT-TESTBAR melden statt zu erfinden.
- **Klick-Sequenz-Falle bei Checkbox-Reihen (Video/Audio-Grid):** Reihenabstand in der
  Media-Tabelle betraegt bei 3240x2160 ca. 50px zwischen Checkbox-Mittelpunkten (nicht
  31px wie beim ersten Versuch angenommen) — Reihe 1 y≈502, Reihe 2 y≈552, Reihe 3 y≈602.
  Falscher Row-Spacing fuehrt zu Doppel-Klicks auf dieselbe Checkbox (Toggle aus).
- **Grosses Audio (930 MB WAV) + BPM/Beatgrid-Analyse:** kann bei gleichzeitig hoher
  Hintergrundlast (hier 486 parallele Proxy-Tasks) zu MEHRMINUeTIGEN "Keine Rueckmeldung"-
  Phasen fuehren, die sich nach 30-90s von selbst aufloesen (kein echter Deadlock, siehe
  freeze_stacks.log: generelle Thread-Auslastung statt eindeutig blockierender Single-Call).
  "Timeline generieren"/"Auto-Edit" bleiben disabled ("Blockiert: Beatgrid fehlt") bis
  mindestens der BPM/Beatgrid-Analyseschritt (nicht die komplette Audio-V2-Pipeline)
  abgeschlossen ist.
- **Reproduzierbarer ECHTER Hard-Hang (neuer Bug, nicht B-nummeriert):** zweiter
  "Projekt oeffnen"-Klick WAEHREND ein TASKS-Abbruch (Abbrechen-Button) von hunderten
  Proxy-Jobs noch laeuft, kann die App fuer mehrere Minuten OHNE jede Log-Aktivitaet
  haengen lassen (main-thread stuck in
  `ui/controllers/project_management.py::_tasks_running_block`). Kein Erholen beobachtet
  (>4,5 Min gewartet) — Force-Kill noetig. Reproduktion: viele Proxy-Tasks laufen lassen,
  "Projekt oeffnen" -> Block-Dialog -> OK -> TASKS "Abbrechen" -> SOFORT erneut
  "Projekt oeffnen" klicken.
- **PB_LOG_LEVEL=DEBUG noetig fuer bestimmte Marker:** Manche Bugfix-Log-Marker (z. B.
  `[B-715] schedule SCHNITT snapshot sequence=...` fuer B-717-Verifikation) laufen nur auf
  DEBUG-Level. Default-Start hat KEIN DEBUG-Logging aktiv — vor entsprechenden Tests
  `PB_LOG_LEVEL=DEBUG` in der Shell setzen, bevor `gui_harness.py start` aufgerufen wird
  (Env wird an den Kindprozess vererbt).

### 2.26 B-794 Live-Race erfolgreich reproduziert — Keyframe-String-Guard greift nicht — NEU 2026-08-11
- **Ziel:** Nachtrag zu 2.25 fuer S7 (B-794). `_show_keyframe_strings` in
  `ui/controllers/edit_workspace.py` laeuft ueber `run_worker`/`BaseWorker`
  (workers/base.py), registriert KEINEN Task im `GlobalTaskManager` — der
  generelle B-465-Task-Running-Guard aus 2.25 sieht diesen Lauf nicht und
  blockt den Projektwechsel waehrend der Generierung NICHT. Anders als
  Auto-Edit/Cuts ist dieses Szenario ueber die normale GUI also grundsaetzlich
  testbar.
- **Button:** MATERIAL ANALYSE-Tab (nicht SCHNITT!) → rechtes Panel
  "Video-Clips analysieren" → Button "Keyframe-String" (`btn_keyframe_string`,
  media_workspace.py:708). Bei 3240x2160 ca. x=2339, y=667. Ergebnis-Textfeld
  direkt darunter (`keyframe_text`, media_workspace.py:735).
- **Timing-Falle:** `generate_keyframe_strings_for_project()` ist fuer
  realistische Projektgroessen (hier 486 Clips) KEIN Slow-Call mehr — Service-
  Level gemessen 0.0676s (M10-Fix: single Query statt N+1). Ein simpler
  Klick-dann-Screenshot-Ablauf (mehrere `gui_harness.py`-Subprozess-Aufrufe
  hintereinander) ist bereits SELBST langsamer als die 67ms Operation —
  das Ergebnis ist regelmaessig VOR dem ersten Screenshot fertig. Fuer einen
  echten Race-Versuch reicht der Harness in Mehrfach-Prozess-Form NICHT.
  Notwendig: ein einzelner Python-Prozess mit `pyautogui.PAUSE = 0`, der
  Klick-Keyframe-Button -> Tab-Wechsel -> "Projekt oeffnen"-Klick -> Pfad
  per Zwischenablage einfuegen (`win32clipboard`, schneller als `typewrite`)
  -> "Oeffnen"-Klick in **einem** Skript ohne Subprozess-Neustart abfeuert.
  Klick-zu-Klick-Zeiten von 40-300ms sind damit erreichbar. ACHTUNG: unter
  ~50ms ist der "Projekt oeffnen"-Dialog noch nicht input-bereit — Paste
  landet ins Leere, Feld bleibt leer, Oeffnen-Klick verpufft (Dialog bleibt
  offen). Sweet Spot war ~250-300ms Puffer nach dem Dialog-Oeffnen-Klick vor
  Paste+Oeffnen.
- **Methodik-Falle (wichtig fuer Wiederholung):** `keyframe_text` ist EIN
  einziges QTextEdit fuer die ganze App-Session, OHNE Reset-Code beim
  Projekt-Load/-Wechsel (grep bestaetigt: nur 3 Schreibstellen in
  edit_workspace.py, keine an einen Projekt-Load-Pfad gebunden). Ein
  Race-Versuch, der zweimal auf DASSELBE Quellprojekt mit identischem
  Ergebnis-Text zielt, ist NICHT interpretierbar — der Boxinhalt sieht im
  Zielprojekt gleich aus, egal ob der Guard gefeuert hat oder nicht. Vor
  jedem Race-Versuch die Box durch App-Neustart in den Platzhalter-Zustand
  zuruecksetzen (frischer Prozess = Widget nie beschrieben = Placeholder
  sichtbar) und das VOR dem Versuch per Screenshot belegen.
- **Live-Befund 2026-08-11 (FAIL — Bug reproduziert):** Sauberer Race (Box
  vorher nachweislich Platzhalter, Klick-zu-Klick 294ms): Wechsel LV-A → LV-B
  gelang ohne B-465-Dialog. Log zeigt `Projekt gewechselt`/`Projekt geoeffnet:
  LV-B`, aber KEINE `B-794: Keyframe-Strings verworfen`-Zeile. `keyframe_text`
  in LV-B zeigte danach LV-As Ergebnis (u. a. einen `_v3`-Clip-Eintrag, den
  LV-B gar nicht besitzt — LV-B hat nachweislich nur 2 Clips). Der B-794-Guard
  aus Commit `cc1db2c` (`_project_changed()` in `_on_finish`) hat NICHT
  gegriffen. Kontrolllauf (gleicher Klick ohne Wechsel danach) lief normal
  fehlerfrei. Kein Crash, kein Traceback — stiller Datenanzeige-Fehler.
  Report/Log: `logs/live-verify-2026-08-11-gui.log` (Abschnitt "NACHTRAG S7").

### 2.27 Live-Verify Runde 2 (B-799/B-800/B-797/B-644/B-580/B-798/B-605) — NEU 2026-08-11
- **B-799 Pre-Block nicht-modal (BESTAETIGT):** Der Guard-Dialog "... ist nicht moeglich,
  solange Hintergrund-Tasks laufen" (B-465-Pre-Block) ist tatsaechlich nicht-modal. Beweis:
  Klick auf einen Tab HINTER dem offenen Dialog wechselt den Tab sofort (sichtbar im
  Screenshot), waehrend die Box weiter offen bleibt. Zweite Ausloesung waehrend die erste
  Box offen ist erzeugt KEINE zweite Box (list-windows zeigt weiterhin genau 1 Fenster
  "Projekt oeffnen"), sondern nur einen zweiten Log-Eintrag -- die Box wird aktualisiert.
- **EXPORT-Tab-Klick-Falle:** `click-element --name-re "^EXPORT$"` trifft den QLabel
  "Export" auf dem PROJEKT-Cockpit (Text-Karte), NICHT den Tab. Fuer den echten Tab-Wechsel
  `find-element --name-re "Workflow"` nutzen (liefert `workspace_nav.workspace_btn`
  CheckBoxen "Projekt/Material und Analyse/Schnitt/Export Workflow" mit exakten
  Koordinaten) -- gleiches Muster wie schon in 2.21 fuer Schnitt/Material dokumentiert,
  gilt auch fuer Export.
- **Quick-Preview-Export-Buttons:** `Quick-Preview rendern` liegt bei y≈1294 (3240x2160),
  NICHT bei y≈796 wie ein erster Screenshot-Schaetzversuch ergab -- IMMER
  `find-element`/`click-element` fuer Export-Tab-Buttons nutzen statt Screenshot-Koordinaten
  zu schaetzen (Layout variiert je nach Timeline-Status-Panel-Hoehe).
- **NEUER BUG (nicht B-nummeriert):** PreviewExport (Quick-Preview 10s) bricht bei sehr
  grossen Quell-WAVs (hier ~976 MB) nach hartem 300s-ffmpeg-Timeout in der
  LUFS-Normalisierung ab (`RuntimeError: LUFS-Normalisierung Timeout nach 300s`,
  `services/export_service.py:1367`). Die Normalisierung scheint auf der KOMPLETTEN
  Audiodatei zu laufen statt nur auf dem Preview-Fenster. TaskEngine faengt den Fehler
  sauber ab (kein App-Crash, UI bleibt bedienbar, Fehler wird im TASKS-Panel sichtbar
  als "Fehler" mit Tooltip angezeigt) -- aber das Feature ist fuer grosse Audiodateien
  faktisch nicht nutzbar.
- **Stem-Separation laesst sich bei bereits vorhandenem Cache nicht ueber die UI
  neu triggern:** Weder der "Wiederholen"-Button in der Analyse-Status-Tabelle noch der
  globale "Stems"-Kachel-Button erzeugten einen sichtbaren neuen TaskEngine-Eintrag, wenn
  Stems fuer den Track bereits vollstaendig separiert vorliegen (4/4). Fuer B-605-artige
  Tests (Thread-Lifecycle waehrend laufender Separation) ist ein frisches, noch nicht
  separiertes Audio-Projekt notwendig.
- **Grosse Ordner-Importe (486 Dateien) erzeugen eine sehr langsame Proxy-Konvertierungs-
  Queue** (~0.3 Konvertierungen/Sekunde beobachtet, 20+ Minuten fuer volle Queue). Der
  TASKS-Panel-"Abbrechen"-Button stoppt nur EINEN TaskEngine-Task, NICHT die separate
  ConvertService-Queue (Proxy-Generierung laeuft nach Abbrechen-Klick unbeirrt weiter) --
  fuer schnelle Tests eher auf bereits vorhandene, durchanalysierte Testprojekte (z. B.
  `LV-A`/`LV-B` aus einer frueheren Session) zurueckgreifen statt neu zu importieren.

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

### 2.17 "Projekt oeffnen"-Button hat Recent-Projects-Quick-Menu — NEU 2026-07-19
- **Beobachtung:** Klick auf `Projekt oeffnen` (PROJEKT-Tab, ca. x=2503,
  y=253 bei 3240x2160) oeffnet NICHT immer den Datei-Browser-Dialog
  ("Projektordner waehlen..."-Textfeld). Wenn zuvor bereits ein anderes
  Projekt geoeffnet wurde, kann der Klick stattdessen ein QMenu mit
  zuletzt-geoeffneten Projekten treffen/anzeigen (Log zeigt
  `MouseRelease -> QMenu` SLOW EVENT statt Dialog-Fenster in
  `list-windows`). Projekt-Wechsel dann sofort ohne Pfad-Eingabe (<1s
  DB-Load). Fuer gezielte Tests: nach dem Klick immer per `list-windows`
  pruefen, ob ein Dialogfenster `"Projekt oeffnen"` ODER direkt der neue
  Projekttitel im Hauptfenster erschienen ist, bevor man blind den
  Pfad-Textfeld-Flow (2.2) fortsetzt.

### 2.18 Projekt-Wechsel hinterlaesst Stale-UI-Zaehler — NEU B-625-Klasse, 2026-07-19
- **Ziel:** Verifikation ob UI-Zaehler/Labels nach Projekt-Wechsel korrekt
  aus der neuen Projekt-DB neu geladen werden.
- **Befund (FAIL, reproduzierbar):** Nach Wechsel von Projekt A (z. B.
  "Test Project", 48 video_clips) zu Projekt B ("test-tabelle", 26
  video_clips) zeigt MATERIAL ANALYSE -> VIDEO das gruene Info-Banner
  weiterhin `"Timeline nutzt 1 von 48 Clips"` (48 = Zaehler von Projekt A)
  obwohl die sichtbare Grid-Liste korrekt 26 Zeilen fuer Projekt B zeigt.
  Root Cause (Code-Trace): `ui/controllers/edit_workspace.py:1194-1209`
  `_mark_timeline_usage()` liest `total = vm.rowCount()` von
  `self.window.video_pool_model` — dieses Model wird beim Projekt-Wechsel
  offenbar nicht sofort neu befuellt, waehrend das separate sichtbare Grid
  (`video_grid`) korrekt aktualisiert. Banner-Text kommt aus
  `ui/workspaces/media_workspace.py:418 set_timeline_usage_summary()`.
  Sobald im neuen Projekt ein neuer Auto-Edit-Lauf durchgefuehrt wird,
  aktualisiert sich der Zaehler korrekt (verifiziert: nach Auto-Edit in
  test-tabelle zeigte Label korrekt `"94 Cuts | Beat:54 | DJ-Mix:40 | 337s
  | 94 Segmente"`). Gleiches Muster auch im SCHNITT-Tab: die
  Cuts/Beat/Segmente-Zusammenfassung direkt ueber der Timeline zeigte nach
  Projekt-Wechsel kurzzeitig den alten Stand (`"5 Cuts | Beat:5 | 30s | 5
  Segmente"` von Projekt A), obwohl die CUTLISTE darunter bereits korrekt
  94 Cuts von Projekt B anzeigte — bis zum naechsten Auto-Edit-Run oder
  manuellen Refresh.
- **Schwere:** NIEDRIG/KOSMETISCH — keine Datenkorruption, DB bleibt
  korrekt (per DB-Inspector verifiziert: `video_clips` count stimmt exakt
  mit Projekt), nur die zusammenfassenden Info-Labels lesen ein
  stale gecachtes Model bis zum naechsten Rebuild-Trigger.

### 2.19 Auto-Edit mit realem Datensatz (26 Clips, 337s Audio, 4 Stems) — NEU 2026-07-19
- **Ziel:** Live-Verify Auto-Edit-Pfad mit echten Stems/Struktur-Daten
  (Gegenprobe zu 2.7, das nur synthetisches Fallback-Beatgrid hatte).
- **Ablauf:** SCHNITT-Tab, Button `Auto-Edit` oben rechts (bei 3240x2160
  ca. x=2555, y=222) — nutzt aktuell in der Audio/Video-Combo gewaehlten
  Track, kein Preset-Dialog wenn bereits eine Timeline existiert (nur im
  Empty-State erscheinen die Techno/Cinematic/House/Festival-Karten,
  siehe 2.7). Dauer real ca. 45s (Pacing-Plan via Ollama `gemma3:4b` +
  Stem-SNR-Gewichtung + SigLIP-Cross-Modal-Matching + Brain-V3-Reranker).
- **Live-Befund (PASS):** 94 Segmente erzeugt, Timeline korrekt
  gezeichnet (`ApplyAutoEditCommand.redo` in 70ms), Beat-Marker (goldene
  Linien) sichtbar auf Waveform (B-617 bestaetigt), kein Crash, kein
  neuer `freeze_stacks.log`-Eintrag waehrend des gesamten Laufs
  (Datei-mtime blieb auf Boot-Zeitpunkt stehen). NICHT "degradiert"
  (im Gegensatz zu 2.7 mit synthetischem Test Project ohne Stems) —
  echte `beat_this`-Onset-Daten vorhanden.
- **Nebenbefund (nicht fatal):** Log zeigt 6x
  `[Qt C++] QGraphicsScene::removeItem: item ...'s scene (0x0) is
  different from this scene (...)` waehrend `ApplyAutoEditCommand.redo`
  die alte Timeline-Szene raeumt. Keine Exception, kein sichtbarer
  Rendering-Fehler im Screenshot, aber ein Qt-Widget-Lifecycle-Warnsignal
  wert, im Auge zu behalten falls spaeter echte Rendering-Glitches
  auftreten.
- **Undo (K1):** `Ctrl+Z` nach Auto-Edit leert die Timeline sauber (V1/A1
  Spuren leer, Cutliste-Ueberschrift bleibt informativ), kein Crash.

### 2.20 App-Schliessen bei ungespeichertem Projekt via Harness-Kill
- **Beobachtung:** Wenn Fenstertitel `"... *"` (dirty/ungespeichert)
  zeigt, fuehrt `gui_harness.py kill` (graceful WM_CLOSE) NICHT zuverlaessig
  zum sauberen Beenden — Log zeigt `closeEvent: eingetreten (dirty=True,
  spontaneous=True)`, aber kein nachfolgendes `Cleanup-Tasks gestartet`
  vor Ablauf der Grace-Periode. Vermutung: App zeigt bei dirty-State einen
  "Speichern?"-Modal-Dialog, den WM_CLOSE nicht automatisch beantwortet —
  Harness muss dann auf `--force` (taskkill /F) zurueckfallen. Kein
  App-Bug, sondern Automatisierungs-Luecke: harness `kill` kennt diesen
  Dialog nicht. Fuer sauberen Graceful-Shutdown-Test: vor `kill` erst
  Ctrl+S oder "nicht speichern" im Dialog explizit klicken.
- 2026-08-11 (Live-Verify Runde 2, B-799/B-800/B-797/B-644/B-580/B-798/B-605): Flow 2.27
  (neu) ergaenzt. B-799 Pre-Block-Dialog nicht-modal bestaetigt (Klick hinter Box wirkt
  sofort), B-800 Keyframe-String-Feld wird bei Projektwechsel korrekt geleert, B-797
  Verwendungs-Banner-Nenner sofort korrekt nach Projektwechsel, B-644 Beatgrid-Linien
  bei 4 Zoomstufen visuell konsistent duenn, B-798 Bootstrap-Logging sauber. B-580
  (Export-Skip-Warnung) und B-605 (Stem-Thread-Lifecycle) NICHT-TESTBAR in dieser Runde
  (siehe Details oben). Neuer Bug gefunden: PreviewExport-LUFS-Timeout bei grossen WAVs.
  Report: `logs/live-verify-2026-08-11-runde2.log`.

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
- **Schritte:** _TODO: App starten, Zeit bis Hauptfenster interaktiv messen._
- **Erwartet:** Hauptfenster < ~3s interaktiv, kein 5s-Hang beim Brain-V3-Boot.
- **Freeze-Beobachtung:** früher bis 5s (`embedding_scheduler.start/wait_ready`).

### 2.2 Projekt öffnen / Projekt-Switch
- **Ziel:** Projekt-Load ohne Freeze (B-620, B-622, B-623).
- **Schritte:** _TODO: Menü/Toolbar Projekt öffnen → Projekt `test33` wählen._
- **Erwartet:** Timeline lädt, kein mehrsekündiger UI-Freeze.
- **Freeze-Beobachtung:** früher 2–14s (Blob-ORM-Loads); B-622 einmalig 42s.

### 2.3 Audio-/Video-Combo-Wechsel
- **Ziel:** B-625 (edit_workspace combo). Kein Freeze beim Umschalten.
- **Schritte:** _TODO: audio_combo / video_combo Dropdown → anderen Eintrag._
- **Erwartet:** Vorschau/Pacing-Kurve aktualisiert, kein Stall.

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
- **Schritte:** _TODO: Auto-Edit auslösen._
- **Erwartet:** Cuts erzeugt, kein wiederkehrender ~3s-Freeze, kein 42s-Hang beim Finish.

### 2.8 Undo Clip entfernen
- **Ziel:** B-625 (undo_commands RemoveClipCommand.undo).
- **Schritte:** _TODO: Clip entfernen → Strg+Z._
- **Erwartet:** kein Freeze beim Undo.

### 2.9 Media-Import
- **Ziel:** B-627 (submit_task fire-and-forget beim Import).
- **Schritte:** _TODO: Video importieren (Solo_Natur)._
- **Erwartet:** Import-Dialog blockiert nicht 5s beim Einreihen.

### 2.10 Anker-Sync (Dialog → Timeline-Marker) — NEU B-619
- **Ziel:** Dialog-Anker persistieren + als Cyan-Marker auf Timeline sehen.
- **Schritte:** _TODO: Pacing & Anker → „+Anker" (1–2 Anker) → „Sync"._
- **Erwartet:** Meldung „N Dialog-Anker synchronisiert"; **cyan-türkise vertikale
  Marker** erscheinen auf der Audio-Zeitachse der Timeline (getrennt von goldenen Beats).

---

## 3. Änderungslog
- 2026-07-14: Gerüst angelegt (Freeze-Sanierung B-619/622/623/624/625/626/627).
  Flow-Details TODO — erster GUI-Test befüllt Widget-Namen/Koordinaten.

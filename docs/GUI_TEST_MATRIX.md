# PB Studio — GUI Test Matrix

> **Aktualisiert 2026-05-09** für 4-Tab-SCHNITT-Layout (Commit-Range `3476b33..bf7bb11`).
> Neue Workflow-Rail: PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT.
> SCHNITT vereint AUTO-SCHNITT + REVIEW und enthält Sub-Tabs: Schnitt / Pacing & Anker / Audio / RL & Notes.

Diese Matrix beschreibt die User-Flows, die der `pb-gui-tester` Subagent durch die **echte GUI** klickt. Im Gegensatz zum alten Service-Layer-Test (der nur Python-Funktionen aufrief) wird hier die ganze App gestartet, Fenster per pywinauto/pyautogui bedient, nach jedem Schritt ein Screenshot gemacht, das Log gelesen und die DB inspiziert.

## Start-Zustand pro Lauf

- Python: `.venv310\Scripts\python.exe`
- App-Start: `python main.py` aus `PROJECT_ROOT`
- Log: `logs\pb_studio.log` wird vor jedem Lauf per Offset-Marker gelesen (keine Wahrheit löschen — Inkremente reichen)
- DB: `pb_studio.db` (aktuelle Produktions-DB). Read-only Zugriff via `gui_db_inspector.py`. Für destruktive Flows optional `--db` auf Kopie umlenken.
- Artefakte: `tests\qa_artifacts\*.png` + `tests\qa_artifacts\report_<ts>.md`

## Abbruchregeln

- Agent findet Crash-Marker im Log → Flow als **FAIL** markieren, Traceback in Report, Screenshot vom Zustand, nächster Flow.
- Fenster verschwindet unerwartet (kein `PB_studio` in Titelliste mehr) → Crash, App neu starten.
- Erwarteter DB-Delta tritt nicht ein → **FAIL** mit Snapshot-Diff.

---

## Flow 1 — App Startup (Smoke)

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | `start` | PID zurück, keine Exception in den ersten 10s Log |
| 2 | `wait-window --title "PB_studio" --timeout 60` | Fenster erscheint |
| 3 | `screenshot --label startup` | PNG zeigt Director's Cockpit mit NavBar |
| 4 | `find-crash` | crash_count = 0 |
| 5 | `kill` | Sauberes Beenden, keine "UNHANDLED EXCEPTION" zwischen Screenshot und Kill |

**FAIL-Bedingung:** Fenster erscheint nicht oder Crash in Log.

---

## Flow 2 — Workflow-Navigation

Die Workflow-Rail hat 4 Buttons: PROJEKT, MATERIAL & ANALYSE, SCHNITT, EXPORT (accessible_names vorhanden — pywinauto kann sie per Name finden). Der SCHNITT-Tab enthält zusätzlich die Sub-Tabs: Schnitt / Pacing & Anker / Audio / RL & Notes.

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | Klick auf "PROJEKT Workflow" | Projekt-Dashboard mit Status, Next-Step und Systemstatus sichtbar |
| 2 | Klick auf "MATERIAL & ANALYSE Workflow" | Material-Stage sichtbar: Import/Medienpool, Proxy/Convert, Audio-Komplettanalyse, Stems, Video-Pipeline |
| 3 | Klick auf "SCHNITT Workflow" | SCHNITT-Editor mit Sub-Tabs (Schnitt / Pacing & Anker / Audio / RL & Notes); Empty-State mit Preset-Buttons (Techno/Cinematic/House/Festival) wenn Timeline noch nicht erzeugt; CTA ohne Analyse gesperrt |
| 4 | Sub-Tab "Pacing & Anker" prüfen | Pacing-Controls + Anchor-Liste sichtbar |
| 5 | Sub-Tab "Audio" prüfen | Audio/Stem-Controls sichtbar |
| 6 | Sub-Tab "RL & Notes" prüfen | RL-Rules + Notizen sichtbar |
| 7 | Klick auf "EXPORT Workflow" | Export-Checkliste/Export-UI sichtbar; ohne Timeline gesperrt |

**Log-Check nach jedem Schritt:** keine neuen ERROR/CRITICAL Zeilen.

---

## Flow 3 — Audio-Import + Analyse (Golden Path)

**Test-Datei:** `vendor\beat_this\tests\It Don't Mean A Thing - Kings of Swing.mp3` (~3 Min, klein, schnell analysierbar)

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | Go to MATERIAL & ANALYSE Workflow | Import-Button sichtbar |
| 2 | Klick "Audio importieren" / Drag-Drop | Dialog oder Datei-Picker |
| 3 | Datei wählen | `audio_tracks`-Count +1 in DB |
| 4 | Klick "Analysieren" | Task erscheint in TaskManager, Log zeigt BeatAnalysis-Start |
| 5 | Warten bis Task completed (max 120s) | `beatgrids`-Count +1, `analysis_status` aktualisiert |
| 6 | Screenshot nach Abschluss | Waveform + Beat-Grid sichtbar |

**FAIL-Bedingung:** DB-Counts unverändert oder Task hängt > 120s.

---

## Flow 4 — Video-Import + Proxy + Scene-Detection

**Test-Datei:** irgendein MP4 aus `Solo_Natur\` Ordner (854×480, ~10s).

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | MATERIAL & ANALYSE Workflow → "Video importieren" | File-Picker |
| 2 | MP4 auswählen | `video_clips`-Count +1 |
| 3 | "Proxy erstellen" | `storage\proxies\` enthält neue Datei, DB.proxy_path gesetzt |
| 4 | "Szenen erkennen" | `scenes`-Count ≥ 1 für diesen Clip |
| 5 | Screenshot | Clip-Thumbnail + Szenenmarker sichtbar |

---

## Flow 5 — Timeline bauen + speichern (bisher crash-anfällig!)

Dieser Flow reproduziert den Crash aus der heutigen Session (`_mark_dirty` → `database.APP_ROOT`).

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | SCHNITT Workflow (Sub-Tab "Schnitt") | Timeline-View leer (Empty-State mit Preset-Buttons) oder mit aktueller Projekt-Timeline |
| 2 | "Timeline generieren" | Task läuft, `timeline_entries`-Delta ≥ 1 |
| 3 | **Nach Task-Ende:** kein Crash | `_mark_dirty` muss durchlaufen — Titel enthält `*` |
| 4 | `find-crash` nach Schritt 3 | crash_count = 0 |
| 5 | Ctrl+S / "Projekt speichern" | Titel-`*` verschwindet, kein Crash |

**KRITISCH:** Das ist der Regressionstest für den heutigen APP_ROOT-Fix und den QThread-Dangling-Fix.

---

## Flow 6 — Stems-Separation (GPU, langsam)

Optional, skippen wenn GPU nicht verfügbar oder Audio > 5 Min.

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | MATERIAL & ANALYSE Workflow | Stems-UI |
| 2 | "Stems erzeugen" für einen Track | Demucs-Task startet, Log zeigt GPU-Init |
| 3 | Warten (max 10 Min für 3-Min Track) | 4 Stems in `storage\stems\<track>\` |
| 4 | Wellenformen sichtbar | 4 Tracks im UI |

---

## Flow 7 — Convert (NVENC / libx264 Fallback)

Regressionstest für B2 aus dem alten Bericht.

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | MATERIAL & ANALYSE Workflow → Proxy / Convert | Preset-Dropdown |
| 2 | Preset "Edit-Proxy 540p" + Video auswählen | Kein NVENC-Crash, bei Treiber 461.40 → libx264 Fallback |
| 3 | Log-Check | `Falling back to libx264` statt `nvenc API version` |
| 4 | Output-Datei existiert | `exports\` enthält MP4 |

---

## Flow 8 — Deliver / Export

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | EXPORT Workflow | Export-Button |
| 2 | "Timeline exportieren" | Task läuft, kein Crash |
| 3 | Output vorhanden | `exports\<name>.mp4` > 0 Bytes |

---

## Flow 9 — Ollama / Chat (B1 Regressionstest)

| # | Aktion | Erwartung |
|---|--------|-----------|
| 1 | Chat/Agent-UI öffnen | Chat-Input sichtbar |
| 2 | Nachricht an gemma3:4b senden | **Content nicht leer** (B1-Fix: thinking-Feld Fallback) |
| 3 | Antwort wird gerendert | Keine leeren Chat-Bubbles |

---

## Report-Template

Der Subagent schreibt nach jedem Lauf: `tests\qa_artifacts\report_<yyyyMMdd_HHmmss>.md`

```markdown
# GUI Test Run — <Timestamp>

## Environment
- Branch: <git branch>
- Commit: <git rev-parse --short HEAD>
- Python/venv: .venv310
- App PID: <pid>

## Summary
| Flow | Status | Screenshots | Notes |
|------|--------|-------------|-------|
| 1 Startup | PASS/FAIL | 01_startup.png | … |
| 2 NavBar | … | … | … |

## Details

### Flow 1 — Startup
- Step 1: start → PID 12345
- Step 2: wait-window → found "PB_studio v0.5.0 — Director's Cockpit" after 3.4s
- Screenshot: ![startup](startup_20260414_140210.png)
- Log-Diff: (Zeilen seit Start)
- Crashes: 0

### Flow 5 — Timeline
- **FAIL**: … (Traceback aus Log)
- Screenshot: ![crash](timeline_crash_….png)
- DB-Snapshot vorher vs. nachher: …

## Bugs gefunden

### BUG-<id>: <Titel>
- **Flow/Step:** Flow 5, Step 3
- **Datei/Zeile aus Traceback:** ui\controllers\…:213
- **Screenshot:** …
- **Log-Ausschnitt:** …
- **Reproduktion:** 1. … 2. … 3. …
- **Erwartung vs. Realität:** …
```

---

## Wichtige Regeln für den Agent

1. **Vor jedem Lauf** `log-since --offset 0` merken → damit nur neue Zeilen verglichen werden.
2. **Nach jeder UI-Aktion** Screenshot + `log-since` + `find-crash`. Kein blinder Sprung zum nächsten Schritt.
3. **Bei Crash-Dialog auf dem Screen** erst Screenshot, *dann* "OK" klicken, *dann* Log dumpen.
4. **Kein Klick auf (0,0)** — pyautogui FAILSAFE bricht dort ab.
5. **DB-Read-only.** Niemals `query` mit `INSERT/UPDATE/DELETE` aufrufen — der Inspector blockt das sowieso.
6. **Keine "voll funktioniert"-Formulierungen im Report** wenn nicht jeder Schritt durch einen Screenshot belegt ist.

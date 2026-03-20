# Workflow Fix Bericht — PB_studio v0.4.0

## Sektor 1: PacingCurveWidget Vergroesserung

**Dateien:** `main.py` (PacingCurveWidget Klasse)

- `minimumHeight` von 55px auf **180px** erhoeht
- `maximumHeight` auf 16777215 (Qt max) gesetzt — Widget ist jetzt per QSplitter frei skalierbar
- **Kubische Spline-Interpolation** (cubicTo) statt linearer Verbindung — Kurve ist jetzt rund und organisch
- **Breiterer Pinsel** (Radius 6 statt 3) mit quadratischem Falloff fuer natuerlicheres Zeichengefuehl
- Sowohl Fill-Bereich als auch Kurven-Linie verwenden jetzt smooth Bezier-Pfade

## Sektor 2: Media Management (Audio/Video Trennung & Ordner-Import)

**Dateien:** `main.py` (MEDIA Workspace), `services/ingest_service.py`

### Video Pool + Audio Pool
- MEDIA Workspace zeigt jetzt **zwei getrennte Pools** (vertikaler QSplitter):
  - **VIDEO POOL** (oben, cyan Header) — Spalten: ID, Titel, Aufloesung, FPS, Codec, Dateipfad
  - **AUDIO POOL** (unten, pink Header) — Spalten: ID, Titel, BPM, Key, Stems, Dateipfad
- Beide Pools sind per Splitter frei skalierbar
- Pool-Selektion synchronisiert sich mit dem internen media_table (fuer Analyse-Buttons etc.)

### Ordner importieren
- Neuer Button **"Ordner importieren"** in der Import-Gruppe
- Nutzt `QFileDialog.getExistingDirectory` + `os.walk` fuer rekursiven Import
- Erkennt automatisch Audio- und Video-Dateien anhand der Extensions
- Zeigt Anzahl gefundener Dateien in der Konsole

### Sammlung bereinigen
- Neuer Button **"Sammlung bereinigen"** (rot) in der Verwaltungs-Gruppe
- Bestaetigung per QMessageBox (Yes/No Dialog)
- Loescht alle Medien-Eintraege aus der Datenbank (Original-Dateien bleiben erhalten)
- Neue Funktion `delete_all_media()` in `ingest_service.py`

## Sektor 3: Task Cancellation (Prozesse abbrechen)

**Dateien:** `main.py` (TaskManagerWidget, Worker-Klassen, PBWindow)

### Cancel-Button
- TaskManagerWidget ist jetzt ein QWidget (statt QTreeWidget) mit eigenem Layout
- Roter **"Abbrechen"**-Button im Header des Task-Managers
- Bricht den aktuell selektierten (oder ersten laufenden) Task ab
- Cancelled-Status wird gelb angezeigt

### CancellableMixin
- Neues `CancellableMixin` mit `cancel()` und `should_stop()` Methoden
- Alle 7 Worker-Klassen erben jetzt von CancellableMixin:
  - AnalysisWorker, VideoAnalysisWorker, StemSeparationWorker
  - AutoDuckingWorker, ExportWorker, AutoEditWorker, WaveformAnalysisWorker
- `_cancel_worker_for_task()` in PBWindow setzt cancelled-Flag und beendet Threads

## Sektor 4: EFFECTS → CONVERT (Batch-Processing)

**Dateien:** `main.py` (WorkspaceNavBar, CONVERT Workspace)

### Umbenennung
- NavBar-Button von "EFFECTS" zu **"CONVERT"** umbenannt
- Tooltip aktualisiert: "Videos standardisieren (Aufloesung, FPS, Format)"

### Video-Konverter Interface
- Drei Dropdowns:
  - **Aufloesung**: 1080p, 2K, 4K, 720p
  - **Framerate**: 30, 24, 25, 50, 60 fps
  - **Container**: mp4 (H.264), mp4 (H.265), mov (ProRes), mkv (H.264)
- Button **"Alle Videos standardisieren"** — konvertiert alle Videos im Pool
- Konvertierung per `ffmpeg` subprocess mit:
  - Scale + Padding (Seitenverhaeltnis beibehalten)
  - Ziel-FPS und Codec
  - Ausgabe in `converted/` Unterordner
- Fortschrittsbalken + detailliertes Konvertierungs-Log
- Task-Manager Integration (Fortschritt sichtbar)
- Legacy-Effekt-Controls als hidden refs erhalten (backward compatibility)

## Technische Details

| Aenderung | Datei | Zeilen (ca.) |
|-----------|-------|-------------|
| PacingCurveWidget | main.py | ~120 Zeilen modifiziert |
| Media Workspace | main.py | ~180 Zeilen neu |
| TaskManagerWidget | main.py | ~100 Zeilen neu |
| CONVERT Workspace | main.py | ~160 Zeilen neu |
| CancellableMixin | main.py | ~10 Zeilen neu |
| Pool sync methods | main.py | ~30 Zeilen neu |
| Folder import/clear | main.py | ~40 Zeilen neu |
| delete_all_media | ingest_service.py | ~8 Zeilen neu |

**Gesamtstand:** main.py 3089 Zeilen (vorher ~2751), Syntax OK

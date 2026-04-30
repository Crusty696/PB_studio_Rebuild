---
title: Audio/Video Media Redesign Design
date: 2026-04-30
status: draft-approved-for-planning
scope: media-workspace audio-video analysis UX
---

# Audio/Video Media Redesign Design

## Ziel

Die Bereiche Audio und Video im Media-Workspace werden von technischen Analyse-Tabs zu einem klaren Creator-Workflow umgebaut. Nutzer sollen Medien importieren, vorbereiten, passende Clips finden und danach in Auto-Schnitt/Export weiterarbeiten, ohne zwischen redundanten Bereichen wie `ANALYSE`, `STATUS`, `FILTER`, `Motion`, `SigLIP` und `Pipeline` unterscheiden zu muessen.

Der Status bleibt technisch vorhanden, wird aber nicht mehr als eigener Hauptbereich gezeigt. Sichtbarer Status gehoert direkt in Tabelle, Badges und Task-Dock.

## Kontext aus Code

Relevante Dateien:

- `ui/workspaces/media_workspace.py`
  - `_build_video_page()` baut aktuell Video-Tabelle plus Subtabs `ANALYSE`, `STATUS`, `FILTER`.
  - `_build_audio_page()` baut Audio-Tabelle plus Subtabs `ANALYSE`, `STATUS`, `FILTER`.
  - Audio-Filter ist aktuell nur Platzhalter.
- `ui/controllers/video_analysis.py`
  - `_analyze_selected_video()` startet `VideoBatchAnalysisWorker` fuer Metadaten und Proxy.
  - `_start_video_pipeline()` startet `VideoAnalysisPipelineWorker` fuer Szenen, Motion und SigLIP.
- `ui/controllers/audio_analysis.py`
  - Einzelaktionen starten `AnalysisWorker`, `WaveformAnalysisWorker`, `KeyDetectionWorker`, `LUFSAnalysisWorker`, `StructureDetectionWorker`, `StemSeparationWorker`.
  - `_analyze_all_sequential()` fuehrt aktuell BPM/Beats, Wellenform, Key, LUFS, Struktur, Stems nacheinander aus.
- `ui/widgets/analysis_status_panel.py` und `services/analysis_status_service.py`
  - Statusdaten und Schrittdefinitionen existieren bereits und sollen als interne Quelle bleiben.

Wichtigster Ist-Fehler: In Video starten `Motion`, `SigLIP` und `Video-Pipeline` laut Wiring dieselbe Vollpipeline. Das ist redundant und fuehrt zu falscher Erwartung.

## Externe Vergleichsmuster

Mindestens fuenf Ansaetze wurden verglichen:

- Final Cut Pro: Analyseoptionen beim Import oder nach Import, Fortschritt in Background Tasks.
  Quelle: https://support.apple.com/en-mide/guide/final-cut-pro/vera60734a4/mac
- Premiere Pro: Ingest/Proxy sind klar benannte Hintergrundprozesse; Proxy-Status gehoert in Projekt-/Metadatenansicht.
  Quelle: https://helpx.adobe.com/id_id/premiere/desktop/organize-media/ingest-proxy-workflow/ingest-and-proxy-workflow.html
- DaVinci Resolve: Media Pool, Metadaten und Smart Bins organisieren Material; Status/Metadata gehoert ans Asset.
  Quelle: https://www.blackmagicdesign.com/products/davinciresolve/media
- rekordbox: Track-Analyse bereitet Musik fuer DJ-Nutzung vor; BPM, Beatgrid, Waveform und Vocal-Position sind Library-Daten.
  Quelle: https://rekordbox.com/en/feature/overview/
- Ableton Live: Audio wird beim ersten Import analysiert und danach im Clip-Kontext bearbeitet; Warp/Marker sind Ergebnisdaten, nicht separate globale Tabs.
  Quelle: https://www.ableton.com/en/live-manual/11/audio-clips-tempo-and-warping/
- Traktor: `All` fuer Standardanalyse, `Special` fuer Expertenparameter. Standardweg bleibt einfach.
  Quelle: https://support.native-instruments.com/hc/en-us/articles/210311665-How-to-Set-Beatgrids-in-TRAKTOR

Uebernommenes Prinzip: PB Studio braucht einen Standardweg `Media vorbereiten` und einen kleinen Expertenbereich, nicht viele gleichrangige technische Buttons.

## Zielbild UI

### Gemeinsames Layout

Audio und Video bleiben als zwei Modi/Seiten im Media-Workspace erhalten. Beide Seiten bekommen:

- eine obere Toolbar mit Import, Prepare, Suche/Auswahl und Loeschen
- eine zentrale Tabelle oder Grid-Ansicht
- Status-Badges direkt pro Zeile
- Detailinformationen zur Auswahl unter oder neben der Tabelle
- Task-Fortschritt im bestehenden Task-Dock bzw. Bottom-Progress

Die Subtabs `ANALYSE`, `STATUS`, `FILTER` werden entfernt.

### Video-Seite

Sichtbare Hauptaktionen:

- `+ Video`
- `+ Ordner`
- `Media vorbereiten`
- `Semantisch suchen`
- `Loeschen`

`Media vorbereiten` startet fuer gewaehlte Videos eine klare sequentielle Vorbereitung:

1. `Proxy erstellen`
2. `Szenen finden`
3. `Bewegung messen`
4. `Mood-Matching vorbereiten`

Die technische Umsetzung darf weiterhin `VideoBatchAnalysisWorker` und `VideoAnalysisPipelineWorker` nutzen. Die UI zeigt aber Ergebnisnamen statt Modellnamen.

Zu entfernen oder zu verstecken:

- separate Buttons `Motion`
- separate Buttons `SigLIP`
- separater Button `Video-Pipeline`
- eigener `STATUS`-Tab
- leerer/halbfertiger `FILTER`-Tab

Video-Status-Badges:

- `Proxy`
- `Scenes`
- `Motion`
- `Mood`

Zustaende:

- `Missing`
- `Queued`
- `Running`
- `Ready`
- `Failed`

### Audio-Seite

Sichtbare Hauptaktionen:

- `+ Audio`
- `Track vorbereiten`
- `Stems vorbereiten`
- `Loeschen`

`Track vorbereiten` startet:

1. `Beats erkennen`
2. `Waveform berechnen`
3. `Tonart erkennen`
4. `Song-Struktur erkennen`

`Stems vorbereiten` bleibt getrennt, weil Demucs teuer ist und VRAM bindet.

Nicht mehr im Media-Hauptbereich:

- `LUFS`: gehoert in Export/Deliver, weil Lautheit finaler Ausgabe dient.
- `Auto-Ducking`: gehoert in Edit/Deliver, weil es Timeline-/Mixdown-Verhalten ist.
- `Effekte`: gehoeren nicht zu Audio/Video-Analyse. Helligkeit/Kontrast/Crossfade bleiben bei Timeline/Clip Inspector oder Deliver, nicht Media.
- `Mood/Genre` und `Spektral`: nur Advanced oder interne Vorbereitung, wenn Auto-Schnitt sie konkret nutzt.

Audio-Status-Badges:

- `Beats`
- `Wave`
- `Key`
- `Structure`
- `Stems`

## Naming-Regeln

Haupt-UI nutzt Nutzerziele, nicht Modellnamen:

- `beat_this` -> `Beats erkennen`
- `Demucs` -> `Stems trennen`
- `PySceneDetect` -> `Szenen finden`
- `RAFT` -> `Bewegung messen`
- `SigLIP` -> `Mood-Matching vorbereiten`
- `S_eff` -> `Cut Rhythm`

Modellnamen duerfen in Tooltips, Logs und Advanced Details stehen.

## Datenfluss

Video:

`Toolbar: Media vorbereiten` -> `VideoAnalysisController` -> TaskManager/WorkerDispatcher -> `VideoBatchAnalysisWorker` fuer Metadaten/Proxy -> `VideoAnalysisPipelineWorker` fuer Szenen/Motion/Embeddings -> `VideoClip`, `Scene`, `VectorDBService`, `AnalysisStatus` -> Tabelle/Badges refresh.

Audio:

`Toolbar: Track vorbereiten` -> `AudioAnalysisController` -> sequenzielle Worker -> `AudioAnalyzer`, `BeatAnalysisService`, `FrequencyAnalyzer`, `KeyDetectionService`, `StructureDetectionService` -> `AudioTrack`, `Beatgrid`, `WaveformData`, `StructureSegment`, `AnalysisStatus` -> Tabelle/Badges refresh.

Stems:

`Toolbar: Stems vorbereiten` -> `StemSeparationWorker` -> `StemSeparator` -> Stem-Pfade in `AudioTrack` -> Status-Badge refresh.

## Komponenten-Aenderungen

### `media_workspace.py`

- Subtab-Erzeugung fuer Audio/Video entfernen.
- Toolbar-Actions vereinheitlichen.
- Platzhalter-Filter entfernen.
- `AnalysisStatusPanel` nicht mehr dauerhaft sichtbar einbauen.
- Tabellenmodell um Badge/Status-Spalten erweitern oder bestehende Spalten in `MediaTableModel` dafuer nutzen.

### `workspace_setup.py`

- Redundantes Wiring von `btn_motion_analysis`, `btn_siglip_embeddings`, `btn_video_pipeline` entfernen.
- Neues Wiring:
  - `btn_prepare_video` -> neuer/umbenannter Controller-Einstieg
  - `btn_prepare_audio` -> `Track vorbereiten`
  - `btn_prepare_stems` -> Stem-Separation

### `video_analysis.py`

- Oeffentliche Controller-Methode fuer `prepare_selected_videos`.
- Interne Teilfunktionen koennen bleiben.
- Button-/Status-Texte klar an Prepare-Schritte anpassen.

### `audio_analysis.py`

- `Track vorbereiten` Sequenz ohne LUFS und ohne Stems.
- `Stems vorbereiten` separat.
- LUFS-Entry nur noch fuer Deliver/Advanced verfuegbar.

### `analysis_status_panel.py`

- Nicht loeschen.
- Als optionaler Detaildialog oder Kontextmenue-Ziel erhalten.
- Status-Service bleibt Quelle fuer Badges und Retry.

## Verschieben/Entfernen

Verschieben:

- LUFS -> Deliver/Export-Einstellungen oder Export-Preflight.
- Auto-Ducking -> Edit/Deliver Audio-Mixdown.
- Effekte -> Timeline/Clip Inspector/Deliver, nicht Media.

Entfernen aus sichtbarer Standard-UI:

- Video `Motion` Einzelbutton.
- Video `SigLIP` Einzelbutton.
- Video `Pipeline` Einzelbutton.
- Audio/Video `STATUS` Tabs.
- Audio/Video `FILTER` Tabs.
- leere Platzhalter-Hinweise.

Behalten intern:

- `AnalysisStatus` DB-Modell.
- `analysis_status_service`.
- `AnalysisStatusPanel` als Detail-/Debug-Ansicht.
- existierende Worker, solange sie korrekt benannt/wiederverwendet werden.

## Fehlerbehandlung

- Jeder Prepare-Schritt schreibt `AnalysisStatus`.
- Fehler stoppen nicht zwingend ganze Batch, sondern markieren betroffene Datei/Schritt als `Failed`.
- `Retry failed` kommt in Kontextmenue oder Detaildialog, nicht als permanenter Hauptbutton.
- Task-Dock zeigt laufende Jobs mit Abbruchmoeglichkeit, soweit bestehende Worker cancellable sind.

## Testing

Fokussierte Tests:

- Static/UI-Test: alte Labels `STATUS`, `FILTER`, `Motion`, `SigLIP`, `Video-Pipeline` erscheinen nicht mehr in Standard-Media-UI.
- Controller-Test: `prepare_selected_videos` erzeugt genau eine Video-Prepare-Task pro Auswahl.
- Controller-Test: `Track vorbereiten` enthaelt Beats/Waveform/Key/Struktur, aber nicht LUFS/Stems.
- Status-Test: bestehende `analysis_status_service`-Daten koennen Badges versorgen.
- Smoke: App startet, Media-Seite zeigt Video/Audio-Modus, Prepare-Buttons vorhanden.

Manuelle Pruefung:

- Ein Video importieren, `Media vorbereiten`, Tabelle zeigt Badges.
- Ein Audio importieren, `Track vorbereiten`, Tabelle zeigt Badges.
- `Stems vorbereiten` bleibt eigener schwerer Job.
- Fehlerfall zeigt `Failed` ohne UI-Blockade.

## Nicht-Ziele

- Kein Pipeline-Service-Refactor in diesem Schritt.
- Kein neues ML-Modell.
- Kein DB-Schema-Change, solange vorhandene Status- und Ergebnisdaten reichen.
- Kein Entfernen der Status-Infrastruktur.
- Kein Redesign von Auto-Schnitt, Review oder Export ausser Verschieben sichtbarer Actions an korrekten Ort.

## Offene Implementierungsentscheidung

Badge-Darstellung kann entweder direkt in `MediaTableModel` erfolgen oder ueber ein kleines Delegate/Renderer-Widget. Empfehlung fuer ersten Slice: `MediaTableModel` erweitert lesbare Statusspalten, weil es schneller testbar und weniger invasiv ist. Ein Delegate kann spaeter fuer bessere Optik folgen.

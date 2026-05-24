---
title: ComfyUI Audit - 30_Workflows/edl.json
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\edl.json
status: audited-no-code-change
next_reference_file: 30_Workflows\florence2_video_caption.api.json
---

# Audit: `30_Workflows\edl.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\edl.json
```

- Groesse: 355.733 Bytes.
- SHA256: `641938a6b6bbc924d721c7eb07c37e59fa2773f1bc77ee110f1c02a02d26d0e9`.
- JSON-Top-Level: Liste.
- Eintraege: 804.

## Belegter Inhalt

Jeder Eintrag hat exakt diese Felder:

- `idx`
- `mix_start`
- `mix_end`
- `window_dur`
- `cluster`
- `is_sequence`
- `is_manual`
- `audio_state`
- `clip`
- `trim_start`
- `trim_end`
- `theme`

Erster Eintrag:

```json
{
  "idx": 0,
  "mix_start": 0.0,
  "mix_end": 5.0,
  "window_dur": 5.0,
  "cluster": 8,
  "is_sequence": true,
  "is_manual": false,
  "audio_state": "break",
  "clip": "C:\\Users\\david\\Documents\\ComfyUI-Studio\\00_Assets\\01_Videos\\20250621_0258_Gothic_Dance_Magic_gen_01jy86rvxrfveashcec6cxnbsg.mp4",
  "trim_start": 0.0,
  "trim_end": 5.0,
  "theme": "gothic_demonic"
}
```

Letzter Eintrag:

```json
{
  "idx": 803,
  "mix_start": 3741.5164,
  "mix_end": 3746.5164,
  "window_dur": 5.0,
  "cluster": 15,
  "is_sequence": true,
  "is_manual": false,
  "audio_state": "break",
  "clip": "C:\\Users\\david\\Documents\\ComfyUI-Studio\\00_Assets\\01_Videos\\20250621_1157_Mystical_Jungle_Journey_gen_01jy95m0yyfywawfp7pgkk32e9.mp4",
  "trim_start": 0.0,
  "trim_end": 5.0,
  "theme": "mystic_nature"
}
```

## Datenqualitaet

- `idx` ist lueckenlos `0..803`.
- `mix_start` ist monoton.
- Keine Timeline-Ueberlappungen.
- Keine Timeline-Gaps.
- 803 von 803 Segmentuebergaengen sind kontigu.
- `mix_end - mix_start == window_dur` fuer alle Eintraege.
- `trim_end >= trim_start` fuer alle Eintraege.
- Timeline-Spanne: `0.0` bis `3746.5164` Sekunden.
- `is_sequence`: 804-mal `true`.
- `is_manual`: 804-mal `false`.
- Eindeutige Clip-Pfade: 119.
- Auf dieser Maschine existieren 119 von 119 eindeutigen Clip-Pfaden nicht unter dem gespeicherten absoluten Pfad.

Verteilungen:

- `audio_state`: `normal` = 608, `break` = 168, `drop` = 28.
- `theme`: `gothic_demonic` = 430, `mystic_nature` = 374.
- `cluster`: 8 = 392, 2 = 198, 15 = 113, 19 = 50, 1 = 15, 6 = 15, 5 = 13, 9 = 8.
- Haeufigste `window_dur`: 4.644s = 323, 4.6672s = 114, 4.7137s = 89, 4.7136s = 80.

## Funktion / Workflow aus der Datei

Belegt ist eine fertige Edit Decision List:

- globale Timeline-Position pro Segment,
- Quellclip als absoluter Dateipfad,
- Quelltrim pro Segment,
- Cluster-ID,
- Audio-Zustand,
- Theme,
- Sequenz-/Manual-Flags.

Nicht belegt:

- Auswahlalgorithmus,
- Scoring,
- Beat-/Phrase-Snap-Regel,
- Umgang mit fehlenden Clips,
- Persistenz in eine App-Datenbank,
- Export-/Renderpfad,
- UI-Workflow,
- Locking oder manuelle Nachbearbeitung.

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `services\pacing_beat_grid.py`: `TimelineSegment` mit `video_id`, `video_path`, `start`, `end`, `source_start`, `source_end`, `is_anchor`, `scene_id`, `crossfade_duration`, `section_type`.
- `services\pacing_service.py`: `auto_edit_phase3(...)` erzeugt Timeline-Segmente auf Basis von Audio-Dauer, Beats, Sections, Anchors, Clip-Offsets, Memory/Pipeline-Scoring und Source-Offsets.
- `database\models.py`: `TimelineEntry` persistiert `project_id`, `track`, `media_id`, `start_time`, `end_time`, `lane`, `crossfade_duration`, `source_start`, `source_end`, `brightness`, `contrast`, `locked`.
- `services\timeline_service.py`: `apply_auto_edit_segments(...)` schreibt Timeline atomar und lock-aware in die DB.
- `services\export_service.py`: `export_timeline(...)` liest `TimelineEntry`, mapped `media_id` zu `VideoClip`, beruecksichtigt `source_start/source_end`, preprocessed Clips und exportiert via FFmpeg.
- `services\timeline_state.py`: Snapshot-/Versionierungsmodell fuer Timeline-Zustand.

## Vergleich

Referenz:

- Speichert direkte absolute Dateipfade in der EDL.
- Hat `cluster`, `audio_state`, `theme` als flache Segment-Metadaten.
- Hat keine DB-ID, keine Projektbindung, keine Locking-Information, keine Crossfade-/Farbparameter.
- Kann auf einem anderen Benutzerpfad sofort ungueltig werden; alle 119 eindeutigen gespeicherten Clip-Pfade fehlen auf dieser Maschine.

PB Studio:

- Nutzt `media_id` statt absolute Clip-Pfade als Timeline-Identitaet.
- Fuehrt Timeline projektbezogen in `timeline_entries`.
- Hat Source-Offsets analog zu `trim_start`/`trim_end`.
- Hat Locking, Crossfade, Helligkeit/Kontrast, Snapshot, Integritaetsreparatur und Exportpfad.
- Hat Auto-Edit-Generatorcode; die Referenzdatei enthaelt nur dessen Ergebnis.

## Integrationsentscheidung

Keine App-Code-Aenderung.

Grund:

- Die Referenzdatei liefert keine nachweisbar bessere Logik, sondern nur eine fertige EDL.
- PB Studio besitzt die gleiche Kernstruktur plus staerkere Persistenz- und Export-Eigenschaften.
- Uebernahme direkter absoluter Dateipfade waere fuer PB schlechter als DB-basierte `media_id`-Referenzen.
- `cluster`, `audio_state` und `theme` koennen erst dann sinnvoll bewertet werden, wenn der Generator oder ein Konsument in weiteren Referenzdateien belegt ist.

## Ersetzter Code

Keiner.

## Neuer Code

Keiner.

## Verifikation

- Referenzdatei gelesen und JSON-Struktur geprueft.
- Segmentkontinuitaet, Dauer-Mathematik, Flags und Verteilungen berechnet.
- PB-Gegenstuecke per Dateiinspektion geprueft.
- Ein vermuteter PB-Pfad `services\video_pipeline\stages\cut_plan_stage.py` wurde geprueft und existiert nicht.
- Keine Tests ausgefuehrt, weil kein App-Code geaendert wurde.

## Naechste Datei

`30_Workflows\florence2_video_caption.api.json`

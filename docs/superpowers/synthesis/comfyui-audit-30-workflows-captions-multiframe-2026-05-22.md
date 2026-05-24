---
title: ComfyUI Audit - 30_Workflows/_captions_multiframe.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_captions_multiframe.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_clip_clusters.json
---

# Audit: `30_Workflows\_captions_multiframe.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_captions_multiframe.json
```

## Nachweisbare Fakten

- Groesse: 1.432.247 Bytes.
- SHA256: `95c745768b84bfceef1e0c274d921b0d716d845584972944f0e86ba1d7525835`.
- JSON Top-Level: `dict`.
- Eintraege: 745.
- Keys sind absolute Video-Pfade unter `C:/Users/david/Documents/ComfyUI-Studio/00_Assets/01_Videos/...`.
- Jeder Eintrag hat exakt die Keys `first`, `middle`, `last`.
- Jeder dieser drei Slots ist ein Dict mit exakt `caption` und `elapsed_sec`.
- Leere Captions: 0.
- Identische Captions ueber alle drei Slots: 0 Videos.
- Identische `first`/`middle`: 0 Videos.
- Identische `middle`/`last`: 3 Videos.
- Identische `first`/`last`: 1 Video.

## Slot-Stats

| Slot | Captions | Caption min | Caption max | Caption avg | elapsed min | elapsed max | elapsed avg | elapsed sum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `first` | 745 | 286 | 933 | 517.493 | 1.51 | 35.26 | 2.56 | 1907.38 |
| `middle` | 745 | 284 | 1001 | 522.548 | 1.55 | 9.84 | 2.588 | 1927.9 |
| `last` | 745 | 302 | 852 | 513.403 | 1.53 | 13.25 | 2.608 | 1943.01 |

## PB-Studio-Gegenstueck

- `services\video_pipeline\primitives\keyframe_selector.py`: `select_keyframes(..., mode="anchors_3")` erzeugt `start`, `mid`, `end` pro Szene.
- `services\video_pipeline\stages\keyframe_extract_stage.py`: extrahiert diese Keyframes und schreibt `keyframes.json` mit `scene_idx`, `role`, `time_s`, `path`.
- `services\video_pipeline\stages\vlm_caption_stage.py`: filtert `start`, `mid`, `end`, ruft `caption_keyframes` und schreibt `captions.json` mit `scene_idx`, `role`, `time_s`, `path`, `text`, `confidence`, `model_id`.
- `services\video_pipeline\stages\vlm_caption_service.py`: Stub-Modus ohne Backend; Live-Modus ruft `llm_backend.caption_image()` pro Frame.
- `services\video_analysis_service.py`: bestehender alter Pfad extrahiert pro Szene einen mittleren Keyframe und captiont diesen.
- `database\models.py`: `Scene.ai_caption`, `Scene.ai_mood`, `Scene.ai_tags`, `Scene.keyframe_path`, `Scene.keyframe_paths`.

## Vergleich

Referenz:

- Speichert pro Video drei VLM-Beschreibungen fuer Anfang, Mitte und Ende.
- Fuehrt keine Szenengrenzen, `scene_idx`, Frame-Pfade, Confidence oder Modell-ID.
- Enthalt Laufzeit-Messung pro Caption-Slot.

PB Studio:

- Neuer Pipeline-Pfad unter `services\video_pipeline` kann `start/mid/end` pro Szene abbilden und speichert `scene_idx`, Rolle, Zeit, Pfad, Confidence und Modell-ID.
- Alter produktiver Analysepfad in `services\video_analysis_service.py` arbeitet nachweisbar mit mittlerem Keyframe pro Szene.
- `VlmCaptionService` ist ohne gesetztes Backend nachweisbar Stub.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Datei beweist den Nutzen von Multi-Frame-Captions als Datenform, enthaelt aber keinen Generator, kein Prompting und keine bessere Modellintegration. PB Studio besitzt im neuen Pipeline-Code bereits eine strukturell bessere Zielstruktur (`start/mid/end` pro Szene plus Metadaten). Eine Umstellung des produktiven Analysepfads oder ein Backend-Anschluss waere App-Code-Architekturarbeit und aus dieser JSON-Datei allein nicht belegt.

## Offen

Wenn spaetere Referenzdateien den Generator fuer `_captions_multiframe.json` enthalten, pruefen:

- ob der alte produktive `video_analysis_service` auf mehrere Keyframe-Captions pro Szene erweitert werden soll;
- ob `elapsed_sec` als Caption-Telemetrie in PBs Analyse-Status oder Pipeline-Artefakte gehoert;
- ob Prompting/Parsing aus der Referenz bessere Caption-Qualitaet liefert als PBs aktueller oder geplanter VLM-Pfad.

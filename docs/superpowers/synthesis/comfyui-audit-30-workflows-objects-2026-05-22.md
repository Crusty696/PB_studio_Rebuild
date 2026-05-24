---
title: ComfyUI Audit - 30_Workflows/_objects.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_objects.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_ocr.json
---

# Audit: `30_Workflows\_objects.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_objects.json
```

## Nachweisbare Fakten

- Groesse: 274.189 Bytes.
- SHA256: `f2021cfd0b13362af64a10ea4b93f3f01f37763022d3cc6fd099322cc39e6b61`.
- JSON Top-Level: `dict`.
- Eintraege: 745.
- Jeder Value ist ein Dict mit exakt `output` und `elapsed_sec`.
- Leere `output`: 0.
- `output` Laenge min/max/avg: 19 / 1145 / 173.149.
- `elapsed_sec` min/max/avg/sum: 0.51 / 3.75 / 1.107 / 825.08.
- `<loc_...>` Token pro Output min/max/avg: 0 / 80 / 9.353.
- Outputs ohne `<loc_...>` Token: 149.
- Haeufige bereinigte Labels: `human face` 240, `No object detected.` 149, `mushroom` 35, `flower` 18, `person` 13, `footwear` 11.

## PB-Studio-Gegenstueck

- `database\models.py`: `Scene.ai_caption`, `Scene.ai_tags`, `Scene.siglip_tags`.
- `services\video_analysis_service.py`: Caption-Pfad erzeugt strukturierte Captions mit Tags, aber in den gelesenen Treffern kein Objekt-Bounding-Box-Schema.
- `services\actions\video_actions.py`: konsumiert `ai_tags` aus Caption-Daten.
- `services\brain_v3\schemas\video.py`: kennt `object_tags`, aber keine Bounding-Box-Koordinaten.
- Gelesene Suche nach `bbox`, `bounding`, `object_detection`, `loc_` zeigte kein produktives Objekt-BBox-Modul.

## Vergleich

Referenz:

- Enthaelt Objekt-/Regionserkennung mit lokalisierenden `<loc_...>` Tokens.
- Speichert Laufzeit pro Video.
- Ist vermutlich Florence-artiges Output-Format, aber die Datei enthaelt keinen Parser und keinen Generator.

PB Studio:

- Hat Tags und Object-Tags als semantische Labels.
- Hat in den gelesenen Dateien keine nachweisbare Persistenz fuer Objekt-Bounding-Boxes.
- Nutzt Tags fuer Rollen/Mood/Brain, aber keine Region-Koordinaten.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Datei zeigt einen echten moeglichen Feature-Gap: Objektlokalisierung. Sie liefert aber nur rohe Outputs mit `<loc_...>` Tokens, keine Koordinaten-Normalisierung, kein Prompting, kein Modell und kein Ziel-Schema. Eine Implementierung waere ohne Generator-/Workflow-Beleg geraten.

## Offen

Bei spaeteren Dateien gezielt pruefen:

- `florence2_video_caption.api.json` als moeglicher Generator/Workflow;
- wie `<loc_...>` in Pixel- oder Normalized-Boxen umgerechnet wird;
- ob PB ein `object_detections`-Schema pro Szene/Frame braucht;
- ob `object_tags` ohne Bounding-Boxes bereits ausreichen.

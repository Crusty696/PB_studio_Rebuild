---
title: ComfyUI Audit - 30_Workflows/_all_captions.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_all_captions.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_audio_curve.json
---

# Audit: `30_Workflows\_all_captions.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_all_captions.json
```

## Nachweisbare Fakten

- Groesse: 64.786 Bytes.
- SHA256: `a9816865eb175d6507593ad800a4eb02e253a6d2fb89933acbe0510d26c3c1b0`.
- JSON Top-Level: `dict`.
- Eintraege: 90.
- Key-Format: absolute Video-Pfade unter `C:/Users/david/Documents/ComfyUI-Studio/00_Assets/01_Videos/...`.
- Alle 90 Werte haben exakt Felder `caption` und `elapsed_sec`.
- Leere Captions: 0.
- Caption-Laenge: min 337, max 975, avg 530.8 Zeichen.
- `elapsed_sec`: min 1.55, max 4.57, avg 2.454, Summe 220.88.
- Erste Key: `C:/Users/david/Documents/ComfyUI-Studio/00_Assets/01_Videos/2025-06-25T22.19.31_1.mp4`.
- Letzte Key: `C:/Users/david/Documents/ComfyUI-Studio/00_Assets/01_Videos/20250614_0314_Mystical_Waterfall_Dance_gen_01jxp6w02me7hr4fq6wtadw5yz.mp4`.

## PB-Studio-Gegenstueck

- `database\models.py` speichert pro `Scene`: `ai_caption`, `ai_mood`, `ai_tags`.
- `services\video_analysis_service.py` erzeugt Caption-JSON mit Schema `{description, mood, motion, tags}` und Plain-Text-Fallback.
- `services\video_pipeline\stages\vlm_caption_stage.py` schreibt `captions.json` pro Keyframe mit `scene_idx`, `role`, `time_s`, `path`, `text`, `confidence`, `model_id`.
- `services\actions\video_actions.py` nutzt `ai_caption`, `ai_mood`, `ai_tags` fuer Clip-Beschreibungen.
- `services\analysis_status_service.py` markiert `ai_scene_caption`, wenn mindestens eine Szene `ai_caption` hat.

## Vergleich

Referenz:

- Speichert eine Caption pro Video-Pfad.
- Speichert Inferenzdauer pro Video-Caption als `elapsed_sec`.
- Speichert keine Szenenzeit, keine Keyframe-Rolle, keine Stimmung, keine Bewegungsklasse, keine Tags, kein Modell, keine Confidence.

PB Studio:

- Speichert Captions pro Szene beziehungsweise pro Keyframe-Artefakt.
- Speichert strukturierte Semantik: `description`, `mood`, `motion`, `tags`.
- Speichert Videoanalyse-Status in DB.
- Video-Pipeline-Stage speichert Modell-ID und Confidence im Stage-Artefakt.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Referenzdatei ist ein Datenartefakt, kein Code-Block und keine nachweisbare Erzeugungslogik. PB Studios vorhandenes Caption-Modell ist fuer App-Ziel und Datenweiterleitung reicher als diese Datei: szenenbezogen, strukturierter und mit Pipeline-Status verbunden. `elapsed_sec` ist als Telemetrie interessant, aber ohne Erzeugercode in dieser Datei nicht genug Beleg fuer eine sichere Integration.

## Offen

Wenn spaetere Workflow-Dateien den Generator fuer `_all_captions.json` enthalten, kann per separatem Befund geprueft werden, ob per-Caption-Latenz in PBs Caption-Stage uebernommen werden soll.


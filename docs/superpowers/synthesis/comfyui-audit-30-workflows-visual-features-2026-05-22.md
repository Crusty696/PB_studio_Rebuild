---
title: ComfyUI Audit - 30_Workflows/_visual_features.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_visual_features.json
status: audited-no-code-change
next_reference_file: 30_Workflows\Brücke_ComfyUI_API.md
---

# Audit: `30_Workflows\_visual_features.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_visual_features.json
```

## Nachweisbare Fakten

- Groesse: 109.167 Bytes.
- SHA256: `907f5239003f9367f16ff9cd8500ea0c798f132efa490d58dadaeb7932104136`.
- JSON Top-Level: `dict`.
- Eintraege: 391.
- Jeder Value hat exakt `colors`, `motion_score`, `motion_tag`.
- `colors`: immer exakt 3 Werte.
- Alle 1.173 Farbwerte sind gueltige Hex-Farben im Format `#RRGGBB`.
- Eindeutige Farbwerte: 1.167.
- `motion_score` min/max/avg: 0.0117 / 0.3164 / 0.150869.
- `motion_tag` Counts: `slow` 297, `dynamic` 64, `static` 30.

## PB-Studio-Gegenstueck

- `services\video_analysis_service.py`: berechnet `motion_score` pro Szene.
- `services\vector_db_service.py`: speichert `motion_score` je Embedding-Zeile.
- `services\pacing\bridge_mapping.py`, `services\pacing\scorer.py`: nutzen `motion_score`.
- `services\brain_v3\video\visual_curves.py`: berechnet Brightness, Saturation und Color Temperature.
- `services\brain_v3\storage\embedding_repository.py`: `VideoUnit` kann `motion_score`, `brightness`, `saturation`, `color_temp` speichern.
- Gelesene Suche zeigte kein produktives Feld fuer eine 3-Farb-Palette pro Clip.

## Vergleich

Referenz:

- Kompakte Clip-Level-Features: dominante Farbpalette plus Motion.
- Motion-Tags sind kategorisiert (`static`, `slow`, `dynamic`).
- Enthaelt keine Berechnungslogik fuer Farben oder Tag-Schwellen.

PB Studio:

- Hat Motion-Score und visuelle Kurven fuer Helligkeit/Saettigung/Farbtemperatur.
- Hat keine sichtbare persistierte dominante 3-Farb-Palette pro Clip.
- Arbeitet staerker szenen-/unitbezogen statt flach pro Clip-Pfad.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Datenform ist sinnvoll, aber die Datei enthaelt keinen Algorithmus fuer Farbauswahl und keine Schwellen fuer `motion_tag`. PB hat bereits Motion- und Visual-Curve-Grundlagen. Eine Palette-Erweiterung braucht Generatorbeleg und Zielschema.

## Offen

Wenn Generatorcode gefunden wird, pruefen:

- dominante Farbpalette pro Clip/Scene fuer UI, Suche oder Pacing;
- Schwellen fuer `static`/`slow`/`dynamic`;
- Mapping von Clip-Level-Features auf PBs Scene-/VideoUnit-Struktur.

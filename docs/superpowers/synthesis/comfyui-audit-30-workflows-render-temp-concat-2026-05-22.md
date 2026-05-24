---
title: ComfyUI Audit - 30_Workflows/_render_temp/_concat.txt
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_render_temp\_concat.txt
status: audited-no-code-change
next_reference_file: 30_Workflows\_visual_features.json
---

# Audit: `30_Workflows\_render_temp\_concat.txt`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_render_temp\_concat.txt
```

## Nachweisbare Fakten

- Groesse: 70.750 Bytes.
- SHA256: `cf9f154a61fe1273de2a5df63ad8f0fc5727d8b1e776fa9f363abc064a7fecaf`.
- Textzeilen: 804.
- Alle 804 Zeilen beginnen mit `file `.
- `duration`-Zeilen: 0.
- `inpoint`-Zeilen: 0.
- `outpoint`-Zeilen: 0.
- Leerzeilen: 0.
- Dateipfade zeigen auf `C:/Users/david/Documents/ComfyUI-Studio/30_Workflows/_render_temp/seg_00000.mp4` bis `seg_00803.mp4`.

## PB-Studio-Gegenstueck

- `services\export_service.py`: erzeugt FFmpeg-Concat-Dateien.
- `services\export_service.py`: nutzt `_sanitize_concat_path`.
- `services\export_service.py`: schreibt `file`, optional `inpoint`, `outpoint`, `duration`.
- `services\export_service.py`: ruft FFmpeg mit `-f concat -safe 0 -i <concat_file>` auf.
- `services\export_service.py`: verwaltet Temp-Files und Cleanup.

## Vergleich

Referenz:

- Minimaler FFmpeg-Concat-Demuxer-Input mit Segmentdateien.
- Keine Trim-/Duration-Information.
- Keine sichtbare Escape-/Sanitize-Logik in dieser Datei.

PB Studio:

- Hat bereits erweiterten Concat-Pfad mit Escaping, In-/Outpoints, Duration, Temp-Dateien und Cleanup.
- Unterstuetzt konforme Copy-Concats und komplexere Crossfade-Filterpfade.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Referenzdatei ist ein temporäres Render-Artefakt, kein besserer Code. PBs Exportlogik ist in den gelesenen Punkten funktional umfangreicher.

## Offen

Keine direkte offene Integration aus dieser Datei. Spaetere Render-Workflow-Dateien koennen trotzdem relevante FFmpeg-Parameter enthalten.

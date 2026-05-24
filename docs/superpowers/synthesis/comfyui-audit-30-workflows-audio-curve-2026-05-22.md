---
title: ComfyUI Audit - 30_Workflows/_audio_curve.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_audio_curve.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_beats.json
---

# Audit: `30_Workflows\_audio_curve.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_audio_curve.json
```

## Nachweisbare Fakten

- Groesse: 612.694 Bytes.
- SHA256: `0e33355d246ed4ee1b2e323567e3646971e65d0cac97aa20f8b5d861707efe1b`.
- JSON Top-Level: `dict`.
- Top-Level Keys: `sr`, `hop`, `frame_sec`, `per_sec`, `segments_sec`.
- `sr`: 22050.
- `hop`: 512.
- `frame_sec`: 0.023219954648526078.
- `per_sec` Keys: `rms`, `centroid`, `onset_strength`, `low_energy`, `mid_energy`, `high_energy`.
- Jede `per_sec`-Kurve hat 3.746 Werte.
- `segments_sec`: 20 Segmente, Labels 0 bis 7.
- Segment-Zeitspanne: 0.0 bis 3745.541 Sekunden.

## Feature-Stats

| Feature | min | max | avg |
|---|---:|---:|---:|
| `rms` | 0.0 | 1.0 | 0.581724 |
| `centroid` | 611.1576428423889 | 5823.494815156484 | 2442.068795 |
| `onset_strength` | 0.0 | 1.0 | 0.323319 |
| `low_energy` | 0.0 | 1.0 | 0.485879 |
| `mid_energy` | 0.0 | 1.0 | 0.41148 |
| `high_energy` | 0.0 | 1.0 | 0.294143 |

## PB-Studio-Gegenstueck

- `database\models.py`: `AudioTrack.energy_curve`, `AudioTrack.spectral_bands`, `Beatgrid.energy_per_beat`, `WaveformData.band_low`, `WaveformData.band_mid`, `WaveformData.band_high`, `StructureSegment`.
- `services\ai_audio_service.py`: erzeugt und speichert 3-Band-Waveform-Daten.
- `services\spectral_analysis_service.py`: berechnet Spektral-Centroids und Frequenzbaender.
- `services\onset_rhythm_service.py`: berechnet Onset-Staerke und Rhythmusdaten.
- `services\structure_detection_service.py`: nutzt Energie, Centroid und Bass fuer Struktursegmente.
- `ui\workspaces\schnitt\tab_audio.py`: nutzt `WaveformData`, `Beatgrid` und `StructureSegment` fuer SCHNITT-Audioanzeige.

## Vergleich

Referenz:

- Buendelt per-second RMS, Centroid, Onset und drei Frequenzbaender in einem JSON-Artefakt.
- Enthalt segmentierte Struktur als generische numerische Labels.
- Ist kompakt fuer Workflow-Handoff.

PB Studio:

- Persistiert Audioanalyse normalisiert und relationell pro Track.
- Hat 3-Band-Waveform mit hoherer Zeitaufloesung ueber `hop=512`/`sr=22050`-Kommentar in `WaveformData`.
- Hat separate Beatgrid-, Onset-, Spektral- und Strukturservices.
- Struktursegmente haben semantische Labels statt nur numerischer IDs.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Datei ist ein Datenartefakt, kein Code-Block und kein belegter Algorithmus. Die kompakte Zusammenfuehrung ist interessant, aber PB Studio hat die Daten bereits in spezialisierten DB-Tabellen und Services. Eine sichere Integration waere erst mit Generatorcode belegbar.

## Offen

Wenn spaetere Workflow-Dateien den Generator fuer `_audio_curve.json` enthalten, pruefen: ein optionales kompaktes `audio_feature_curve`-Exportartefakt fuer Debugging/Brain-Handoff. Keine Implementierung aus dieser Datei allein.


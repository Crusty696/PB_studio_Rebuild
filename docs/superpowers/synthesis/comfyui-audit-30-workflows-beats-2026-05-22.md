---
title: ComfyUI Audit - 30_Workflows/_beats.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_beats.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_captions_multiframe.json
---

# Audit: `30_Workflows\_beats.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_beats.json
```

## Nachweisbare Fakten

- Groesse: 195.456 Bytes.
- SHA256: `1a66bfbef33df80a148dd3d26b6075a9a42d2a6a4ba8c9933d8a03e7f60d6e04`.
- JSON Top-Level: `dict`.
- Top-Level Keys: `mix_duration_sec`, `global_tempo_bpm`, `total_beats`, `beats_sec`, `phrases_4_sec`, `phrases_8_sec`, `phrases_16_sec`.
- `mix_duration_sec`: 3745.5412244897957.
- `global_tempo_bpm`: 143.5546875.
- `total_beats`: 8697.
- `beats_sec`: 8.697 Werte, Zeitspanne 49.7139 bis 3731.5164 Sekunden.
- `beats_sec` Intervall-Statistik: avg 0.42339, min 0.3251, max 0.534 Sekunden.
- `phrases_4_sec`: 2.175 Werte, Zeitspanne 49.7139 bis 3731.5164 Sekunden.
- `phrases_8_sec`: 1.088 Werte, Zeitspanne 49.7139 bis 3731.5164 Sekunden.
- `phrases_16_sec`: 544 Werte, Zeitspanne 49.7139 bis 3728.1263 Sekunden.

## Phrase-Stats

| Array | Werte | avg diff | min diff | max diff |
|---|---:|---:|---:|---:|
| `beats_sec` | 8697 | 0.42339 | 0.3251 | 0.534 |
| `phrases_4_sec` | 2175 | 1.693561 | 1.486 | 1.8808 |
| `phrases_8_sec` | 1088 | 3.387123 | 3.1579 | 3.599 |
| `phrases_16_sec` | 544 | 6.77424 | 6.548 | 6.9892 |

## PB-Studio-Gegenstueck

- `database\models.py`: `Beatgrid` speichert `bpm`, `beat_positions`, `downbeat_positions`, `energy_per_beat`, `stem_weighted_energy`.
- `services\beat_analysis_service.py`: erzeugt Beats, Downbeats, BPM, Beat-Anzahl und speichert Beatgrid-Daten in `analyze_and_store`.
- `services\pacing_edit_helpers.py`: nutzt Beats, Downbeats und `energy_per_beat`; Downbeats werden bei groesseren Steps bevorzugt.
- `services\pacing\phrase_boundary_constraint.py`: erkennt 4/8/16-Bar-Phrase-Boundaries ueber `beat_idx % (bars * beats_per_bar) == 0` und bestraft gleichen Mood-Cluster an Boundary.
- `tests\test_services\test_phrase_boundary_constraint.py`: deckt Boundary-/Nicht-Boundary-Faelle fuer die Phrase-Constraint ab.

## Vergleich

Referenz:

- Buendelt Beat-Zeitpunkte, globale BPM und vorab berechnete 4/8/16-Phrase-Zeitpunkte in einem JSON-Artefakt.
- Ist als Handoff-/Cache-Datei fuer Workflows direkt konsumierbar.
- Enthaelt keine Downbeat-Liste und keine Energie pro Beat.

PB Studio:

- Speichert Beatgrid pro Track in der Datenbank.
- Fuehrt Downbeats und Energie pro Beat zusaetzlich zu Beats und BPM.
- Hat Phrase-Boundary-Logik als ableitbare Regel auf Beat-Indizes.
- Nutzt Downbeats in der Schnittpunkt-Erzeugung, nicht nur starre N-te-Beat-Arrays.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Datei ist ein Datenartefakt, kein belegter Generator oder besserer Algorithmus. Die vorab berechneten Phrase-Arrays sind fuer Export/Debugging nuetzlich, aber PB Studio besitzt die relevanten Rohdaten und eine bestehende Phrase-Boundary-Logik. Ohne Generatorcode waere eine App-Code-Aenderung eine unbelegte Architekturentscheidung.

## Offen

Wenn spaetere Referenzdateien Generatorcode fuer `_beats.json` enthalten, gezielt pruefen:

- ob Phrase-Zeitarrays als optionaler Debug-/Handoff-Export aus `Beatgrid` sinnvoll sind;
- ob die Referenz eine bessere Beat-/Phrase-Erkennung enthaelt als PBs aktuelle Beatgrid- und Downbeat-Verarbeitung.

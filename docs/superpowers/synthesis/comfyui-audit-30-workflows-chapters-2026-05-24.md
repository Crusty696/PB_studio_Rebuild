---
title: ComfyUI Audit - 30_Workflows/chapters.json
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\chapters.json
status: audited-no-code-change
next_reference_file: 30_Workflows\edl.json
---

# Audit: `30_Workflows\chapters.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\chapters.json
```

- Groesse: 1.950 Bytes.
- SHA256: `82b4d799eb5bd6b79408e2a2cae0abf9f7abb273b7aff5aaaf663f6061e627b9`.
- JSON-Top-Level: Liste.
- Eintraege: 14.

## Belegter Inhalt

Jeder Eintrag hat exakt diese Felder:

- `idx`
- `start`
- `end`
- `theme`
- `energy`

Erster Eintrag:

```json
{"idx": 0, "start": 0.0, "end": 274.7153, "theme": "gothic_demonic", "energy": 0.5935370887342559}
```

Letzter Eintrag:

```json
{"idx": 13, "start": 3586.531, "end": 3745.5412244897957, "theme": "mystic_nature", "energy": 0.3673126978812331}
```

## Datenqualitaet

- `idx` ist lueckenlos `0..13`.
- Zeitsegmente sind monoton und ohne Ueberlappung.
- Segmente sind kontigu: keine Gaps zwischen `end` und folgendem `start`.
- Gesamtdauer: `3745.5412244897957` Sekunden.
- Energie-Minimum: `0.3673126978812331`.
- Energie-Maximum: `0.7112622488880572`.
- Energie-Mittelwert: `0.5759471862924218`.
- Theme-Verteilung: `gothic_demonic` = 7, `mystic_nature` = 7.

## Funktion / Workflow aus der Datei

Belegt ist nur ein fertiges Kapitel-/Makrosegment-Artefakt:

- zeitliche Kapitelgrenzen,
- semantisches Theme pro Kapitel,
- Energie pro Kapitel.

Nicht belegt:

- Generatorcode,
- Schwellwerte,
- Audio-Feature-Quelle,
- Theme-Klassifizierer,
- Persistenzziel,
- Konsument oder Weiterleitung.

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `database\models.py`: `StructureSegment` mit `audio_track_id`, `start_time`, `end_time`, `label`, `energy`, `confidence`.
- `services\structure_detection_service.py`: `StructureDetectionService.detect(...)` erzeugt Segmente aus `energy_per_beat` oder direkt aus Audio.
- `services\structure_detection_service.py`: nutzt RMS-Energie, Spectral Centroid, Bass-Energie, Beat-Regularitaet, Genre-Erkennung, Segmentlabels und Confidence.
- Tests: `tests\test_services\test_structure_detection.py` prueft Segmentbildung, Gaps, DB-Speicherung und Update-Verhalten.

## Vergleich

Referenz:

- Kapitel sind bereits berechnete Exportdaten.
- Label-Feld heisst `theme`.
- Nur zwei belegte Theme-Werte: `gothic_demonic`, `mystic_nature`.
- Keine Confidence.
- Keine belegte Herleitung.

PB Studio:

- Fuehrt Audio-Struktur als persistierte `StructureSegment`-Datensaetze.
- Hat `label`, `energy`, `confidence`.
- Erzeugt Labels aus Audiofeatures und Beat-/Energie-Daten.
- Hat Tests fuer Segmentierung und Speicherung.

## Integrationsentscheidung

Keine App-Code-Aenderung.

Grund:

- Die Referenzdatei enthaelt keine bessere Logik, sondern nur fertige Daten.
- Das `theme`-Konzept ist in dieser Datei nicht hergeleitet; eine Uebernahme waere eine Annahme.
- PB Studio hat bereits ein Struktursegment-Modell mit Confidence und Generator-Service.
- Ohne Generator oder Konsument waere ein neues Theme-Feld eine unbewiesene Schema-Erweiterung.

## Ersetzter Code

Keiner.

## Neuer Code

Keiner.

## Verifikation

- Referenzdatei gelesen und JSON-Struktur geprueft.
- Statistik aus der Datei berechnet.
- PB-Gegenstuecke per Suche und Dateiinspektion geprueft.
- Keine Tests ausgefuehrt, weil kein App-Code geaendert wurde.

## Naechste Datei

`30_Workflows\edl.json`

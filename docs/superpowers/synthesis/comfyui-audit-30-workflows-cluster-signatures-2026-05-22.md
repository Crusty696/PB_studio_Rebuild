---
title: ComfyUI Audit - 30_Workflows/_cluster_signatures.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_cluster_signatures.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_cluster_summary.json
---

# Audit: `30_Workflows\_cluster_signatures.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_cluster_signatures.json
```

## Nachweisbare Fakten

- Groesse: 7.500 Bytes.
- SHA256: `fcf71de23e0bc6399c0a858af01be1816af1e49b9e9db82af0e0021ba0eed296`.
- JSON Top-Level: `dict`.
- Eintraege: 20.
- Keys: String-Cluster-IDs `0` bis `19`.
- Jeder Eintrag hat exakt: `size`, `avg_motion`, `std_motion`, `motion_distribution`, `mood_distribution`, `dominant_mood`, `avg_hue`, `avg_saturation`, `avg_brightness`, `color_temperature`, `energy_score`.
- `size` Summe: 391.
- `size` min/max/avg: 4 / 66 / 19.55.
- `avg_motion` min/max/avg: 0.064 / 0.177 / 0.1439.
- `std_motion` min/max/avg: 0.0199 / 0.0677 / 0.044215.
- `avg_hue` min/max/avg: 12.65 / 245.76 / 206.111.
- `avg_saturation` min/max/avg: 0.1464 / 0.5888 / 0.40858.
- `avg_brightness` min/max/avg: 0.3521 / 0.5433 / 0.43557.
- `energy_score` min/max/avg: 0.2061 / 0.2963 / 0.256525.
- `color_temperature`: 19 `cool`, 1 `warm`.
- `dominant_mood`: 20 leere Strings.
- `mood_distribution`: 20 leere Dicts.
- `motion_distribution` total: `slow` 297, `dynamic` 64, `static` 30.

## PB-Studio-Gegenstueck

- `workers\structure_enrichment.py`: schreibt `struct_style_bucket` mit `name`, `description`, `centroid_embedding`, `member_count`, `active`.
- `services\enrichment\style_bucket_clusterer.py`: berechnet Labels/Centroids, keine sichtbaren Motion-/Farb-Signaturen.
- `services\brain_v3\storage\embedding_repository.py`: `VideoUnit` kann `motion_score`, `brightness`, `saturation`, `color_temp` speichern.
- `services\brain_v3\video\visual_curves.py`: berechnet Brightness, Saturation und Color Temperature ueber Video-Samples.
- `services\brain_service.py`: listet aktive Style-Buckets mit `id`, `name`, `description`, `member_count`.

## Vergleich

Referenz:

- Hat pro Cluster aggregierte Motion-, Farb- und Energy-Signatur.
- Mood-Felder sind im konkreten Artefakt leer.
- Enthaelt keine Centroid-Vektoren und keine Formel fuer `energy_score`.

PB Studio:

- Style-Buckets haben Centroids und Member Count, aber in den gelesenen Dateien keine aggregierte visuelle Signatur am Bucket.
- Brain V3 speichert visuelle Features pro VideoUnit, nicht sichtbar aggregiert pro Style-Bucket.
- `description` in `struct_style_bucket` wird in `workers\structure_enrichment.py` beim Fit sichtbar als `NULL` geschrieben.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Referenz zeigt eine sinnvolle Bucket-Signatur als Datenform. Sie enthaelt aber keine Berechnungslogik und keine Formel fuer `energy_score`. Eine PB-Integration wuerde Schema-/Worker-/UI-Arbeit an `struct_style_bucket` oder Brain-V3-Aggregaten bedeuten. Das ist aus dieser Datei allein nicht belegbar implementierbar.

## Offen

Wenn Generatorcode gefunden wird, konkret pruefen:

- wie `energy_score` berechnet wird;
- ob PB `struct_style_bucket.description` oder ein JSON-Signature-Feld mit Motion/Farb-Aggregaten befuellen soll;
- ob Brain-V3-VideoUnit-Features pro Style-Bucket aggregiert werden koennen, ohne das App-Hauptziel zu aendern.

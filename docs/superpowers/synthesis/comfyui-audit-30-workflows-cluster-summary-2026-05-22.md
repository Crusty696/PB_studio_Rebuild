---
title: ComfyUI Audit - 30_Workflows/_cluster_summary.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_cluster_summary.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_objects.json
---

# Audit: `30_Workflows\_cluster_summary.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_cluster_summary.json
```

## Nachweisbare Fakten

- Groesse: 15.279 Bytes.
- SHA256: `71d71994390b86516e5b0d49f6d3a6d0b955ec1f27ea83f0967eb1c21179737b`.
- JSON Top-Level: `dict`.
- Eintraege: 20.
- Keys: String-Cluster-IDs `0` bis `19`.
- Jeder Eintrag hat exakt `size` und `sample_clips`.
- `size` Summe: 391.
- `size` passt fuer alle 20 Cluster zu `30_Workflows\_clip_clusters.json`.
- `sample_clips` Laenge: min 4, max 5, avg 4.95.
- 19 Cluster haben 5 Samples, 1 Cluster hat 4 Samples.
- Unbekannte Sample-Pfade: 0.
- Samples mit falscher Cluster-ID: 0.
- Doppelte Samples innerhalb der Listen: 0.

## PB-Studio-Gegenstueck

- `services\brain_service.py`: listet aktive Style-Buckets mit `id`, `name`, `description`, `member_count`.
- `services\brain_service.py`: `list_clips_with_tags` kann Clips nach `style_bucket_id` filtern.
- `ui`-Tests fuer Structure/Inspector/Graph zeigen Konsum von `style_bucket_id`, `style_bucket_name` und Nachbarn.
- `workers\structure_enrichment.py`: schreibt Bucket-Zugehoerigkeit in `struct_clip_tags`.

## Vergleich

Referenz:

- Liefert pro Cluster bis zu 5 Beispielclips.
- Ist fuer UI/Debugging/Handoff gut lesbar.
- Enthaelt keine Auswahlregel fuer `sample_clips`.

PB Studio:

- Kann Clips nach Style-Bucket listen.
- Speichert aber im Bucket selbst keine explizite Sample-Clip-Liste.
- Hat bessere DB-Beziehung statt statischer Pfadlisten.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Datei ist eine konsistente Summary, aber kein Code und keine Auswahlregel. PB Studio kann Beispielclips aus `struct_clip_tags`/Scenes zur Laufzeit ableiten. Eine persistierte Sample-Liste waere Cache-/UI-Arbeit und aus dieser Datei allein nicht belegt besser.

## Offen

Wenn Generatorcode gefunden wird, pruefen:

- wie Sampleclips gewaehlt werden;
- ob PB Structure/Graph-UI Top-Beispiele pro Style-Bucket aus DB ableiten sollte;
- ob ein Export `cluster_summary.json` fuer externe Workflow-Tools sinnvoll ist.

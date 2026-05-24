---
title: ComfyUI Audit - 30_Workflows/Frontmatter_Schema.md
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\Frontmatter_Schema.md
status: audited-no-code-change
next_reference_file: 30_Workflows\INDEX.md
---

# Audit: `30_Workflows\Frontmatter_Schema.md`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\Frontmatter_Schema.md
```

- Groesse: 14.559 Bytes.
- SHA256: `d757db9647156eef7fd439475930cc31ca184154cf0b28fbed26bfa6a86e1dab`.
- Markdown-Dokument mit YAML-Frontmatter.
- Eigenes Frontmatter: `type: schema-reference`, `project: ComfyUI-Studio`, `created: 2026-05-21`, `updated: 2026-05-21`, Tags zu Schema/Frontmatter/YAML/Dataview.

## Belegter Zweck

Die Datei dokumentiert ein Obsidian-/Dataview-Frontmatter-Schema fuer Video-Clip-Notes unter `00_Assets/01_Videos/**/*.md`.

Belegte Workflow-Idee:

- Clip-Note als menschenlesbarer Bericht plus YAML-Datensatz.
- Dataview/Bases lesen YAML-Felder als Datenbankspalten.
- Mehrstufige Skript-Pipeline schreibt Tech-, BPM-, Caption-, Mood-, Visual-, Florence-, Graph- und Storyboard-Felder.
- Manuelle Marker schuetzen Werte vor automatischer Ueberschreibung.
- Re-Runs sollen idempotent und resumable sein.

## Belegte Felder

Aus dem YAML-Beispiel extrahierte Felder: 24.

```text
tags, typ, inhalt, inhalt_first, inhalt_last, stimmung, stimmung_source,
bpm, bpm_confidence, bpm_source, dauer, pfad, aufloesung, fps, farben,
motion_score, motion_tag, objekte, personen, ocr_text, watermark,
siehe_auch, cluster, mix_position
```

Aus den Feldtabellen extrahierte Schema-Felder plus Manual-Marker: 24 Tabellenzeilen.

```text
dauer, pfad, aufloesung, fps, bpm, bpm_confidence, bpm_source,
inhalt, inhalt_first, inhalt_last, stimmung, stimmung_source, farben,
motion_score, motion_tag, objekte, personen, ocr_text, watermark,
siehe_auch, cluster, mix_position, bpm_source: manual,
stimmung_source: manual
```

Referenz-Widerspruch:

- Die Datei behauptet „18 produktive Frontmatter-Felder“.
- Das konkrete YAML-Beispiel enthaelt 24 Felder.
- Die Feldtabellen nennen 22 normale Felder plus 2 Manual-Marker-Zeilen.

## Datenpunkte und Weiterleitung

Belegte Datenbloecke:

- Tech: `dauer`, `pfad`, `aufloesung`, `fps`.
- BPM: `bpm`, `bpm_confidence`, `bpm_source`.
- Inhalt: `inhalt`, `inhalt_first`, `inhalt_last`.
- Stimmung: `stimmung`, `stimmung_source`.
- Visual: `farben`, `motion_score`, `motion_tag`.
- Florence: `objekte`, `personen`, `ocr_text`, `watermark`.
- Graph: `siehe_auch`, `cluster`.
- Storyboard: `mix_position`.

Belegte Schutzmarker:

- `bpm_source: manual`
- `stimmung_source: manual`
- manuelle Body-Sektion `## Notizen`

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `database\models.py`: `VideoClip` speichert technische Videodaten (`file_path`, `duration`, `width`, `height`, `fps`, `codec`) plus Pipeline-Artefaktpfade (`embeddings_path`, `motion_path`) und Status.
- `database\models.py`: `Scene` speichert Szenenzeiten, `energy`, `ai_caption`, `ai_mood`, `ai_tags`, Keyframe- und Embedding-Indizes.
- `database\models.py`: `StructureSegment`, `AIPacingMemory`, `TimelineEntry`, `ModelRegistry` decken Struktur-, Pacing-, Timeline- und Modell-Metadaten ab.
- `services\project_notes_service.py`: Projekt-Notes als DB-Textfeld mit atomarem SQLite-Upsert.
- `services\enrichment\role_classifier.py`: YAML-gesteuerte, gecachte Regelkonfiguration fuer Szenenrollen.

## Vergleich

Referenz:

- Obsidian-Frontmatter ist das primaere strukturierte Speicherformat.
- Source-Felder (`*_source`) und Manual-Marker sind explizit dokumentiert.
- YAML-Stolperfallen und Quote-Regeln sind praktisch dokumentiert.
- Schema-Doku enthaelt aber einen belegten Zaehldifferenz-Widerspruch.

PB Studio:

- Nutzt relationale SQLite-/SQLAlchemy-Tabellen statt Frontmatter als Hauptspeicher.
- Hat strukturiertere Persistenz, Fremdschluessel, Projektbindung, Soft-Delete und Indizes.
- Hat einzelne Source-/Confidence-Felder, aber kein einheitliches Feld-Provenance-Schema fuer alle Analysewerte.
- Hat Projekt-Notes, aber keine Obsidian-Dataview-Semantik als App-Kern.

## Integrationsentscheidung

Keine App-Code-Aenderung.

Grund:

- Die Referenzdatei ist Dokumentation, kein ausfuehrbarer Code.
- PBs Hauptspeicher ist DB-basiert; ein Wechsel auf Frontmatter wuerde PBs Grundkonzept veraendern.
- Die bessere Idee „Manual-Marker schuetzen automatisch berechnete Felder“ ist nur teilweise direkt uebertragbar und braeuchte DB-/UI-/Workflow-Entscheidungen.
- Der belegte Feldanzahl-Widerspruch macht die Referenz als 1:1-Schemaquelle unsauber.

## Ersetzter Code

Keiner.

## Neuer Code

Keiner.

## Offene Verbesserungsidee

Ein PB-eigenes Provenance-Konzept fuer Analysefelder kann sinnvoll sein, aber nur als separater Plan:

- pro Analysewert Quelle (`manual`, `vision`, `heuristic`, `pipeline`, `import`),
- manuelle Sperrmarker,
- UI-Anzeige und gezieltes Recompute-Verhalten,
- Migration fuer bestehende Daten.

Diese Datei allein reicht nicht als Implementierungsbeleg.

## Verifikation

- Referenzdatei voll gelesen.
- Dateigroesse, SHA256 und Feldanzahl berechnet.
- PB-Gegenstuecke per Dateiinspektion geprueft.
- Keine Tests ausgefuehrt, weil kein App-Code geaendert wurde.

## Naechste Datei

`30_Workflows\INDEX.md`

---
title: ComfyUI Audit - 30_Workflows/INDEX.md
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\INDEX.md
status: audited-no-code-change
next_reference_file: 30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json
---

# Audit: `30_Workflows\INDEX.md`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\INDEX.md
```

- Groesse: 4.817 Bytes.
- SHA256: `70edebae0661a89cca2517978da4e97529f36f8aef13a19ab78118df5a0bc2f5`.
- Markdown-Dokument mit YAML-Frontmatter.
- Eigenes Frontmatter: `type: workflow-index`, `project: ComfyUI-Studio`, `created: 2026-04-27`, `updated: 2026-05-21`.

## Belegter Zweck

Die Datei ist eine Workflow-Bibliotheks-Indexnote.

Belegt:

- verlinkt 16 Obsidian-Wiki-Notes,
- listet Pipeline-Dokumentation und 10 Stage-Detailnotes,
- erklaert Dateikonvention `*.json` vs. `*.json.api.json`,
- listet 5 Workflow-Namen,
- beschreibt eine noch nicht finale Manifest-Idee fuer ComfyUI-API-Bridge.

Extrahierte Workflow-Namen:

```text
psy_62min_auto_v3.json.api.json
LTX-2.3_ICLoRA_Motion_Track_Distilled.json
TEST_lipsync_60s_crusty.json
TECHNO_PARTY_T2V_10SEC.json
florence2_video_caption.api.json
```

## Datenpunkte und Weiterleitung

Die Datei enthaelt keine App-Datenpunkte, sondern Doku-/Navigationsdaten:

- Workflow-Dateityp-Konvention,
- Herkunftspfad der Original-Workflows,
- Bruecken-Konzept mit Input-Slots,
- erwartete Outputs im Manifest-Entwurf.

Manifest-Entwurf:

```yaml
inputs:
  primary_image:
    node_id: "12"
    field: "inputs.image"
    accepts: file_path
queue_mode: serial
expected_outputs:
  - node_id: "59"
    field: "filename_prefix"
```

## Referenz-Inkonsistenzen

- Die Datei nennt `TECHNO_PARTY_T2V_10SEC.json`; diese Datei ist im aktuellen `30_Workflows`-Listing nicht vorhanden.
- Die Datei nennt `Brücke_ComfyUI_API` als Instanz auf Port 8000, aber der Bruecken-TODO nennt `127.0.0.1:8188/prompt`.
- Die Datei nennt `Frontmatter_Schema` als „18 Frontmatter-Felder“, waehrend `Frontmatter_Schema.md` selbst im Beispiel 24 Felder enthaelt.

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `services\cockpit_orchestrator.py`: definiert Readiness-Schritte, naechste Cockpit-Aktion und Pipeline-Step-Spezifikationen fuer Audio/Video.
- `ui\workspaces\workflow_pages.py`: Director's-Cockpit-Seiten und Readiness-Karten.
- `services\video_pipeline\trigger_queue.py`: sequenzielle Stage-Queue.
- `services\video_pipeline\status_reporter.py`: Stage-Statusaggregation.
- `docs\user\beat_sync_workflow.md`: User-Workflow-Doku.

## Vergleich

Referenz:

- Gute menschliche Uebersicht ueber Workflows, Stage-Notes und API-/UI-Dateitypen.
- Manifest-Idee fuer Workflow-Input-/Output-Slots ist fachlich brauchbar, aber als TODO markiert und nicht final.
- Enthaltene Inventar-/Port-/Feldanzahl-Inkonsistenzen reduzieren 1:1-Verlaesslichkeit.

PB Studio:

- Hat bereits Cockpit-Readiness und UI-Workflow-Fuehrung in Code.
- Hat Pipeline-Status und Stage-Queues in Services.
- Hat keine ComfyUI-Workflow-Manifest-Schicht, weil ComfyUI nicht Teil der PB-App-Architektur ist.

## Integrationsentscheidung

Keine App-Code-Aenderung.

Grund:

- Die Datei ist Index-/Doku-Material, kein uebernehmbarer Code.
- Das Manifest ist explizit „noch nicht final“.
- PBs Workflow-Fuehrung ist app-intern bereits konkreter als diese Indexnote.
- ComfyUI-Manifest-Support waere ein neuer externer Runtime-Backendpfad und braucht separate Entscheidung.

## Ersetzter Code

Keiner.

## Neuer Code

Keiner.

## Offene Verbesserungsidee

Falls ComfyUI spaeter optionales Backend wird, kann die Manifest-Idee als Vorlage dienen:

- deklarative Inputs,
- Queue-Mode,
- erwartete Outputs,
- Workflow-Datei-Typ (`ui` vs. `api`),
- Validierung gegen vorhandene Node-IDs.

Diese Datei allein ist kein Implementierungsauftrag.

## Verifikation

- Referenzdatei voll gelesen.
- Dateigroesse, SHA256, Wiki-Links und Workflow-Namen extrahiert.
- PB-Gegenstuecke per Dateiinspektion geprueft.
- Keine Tests ausgefuehrt, weil kein App-Code geaendert wurde.

## Naechste Datei

`30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json`

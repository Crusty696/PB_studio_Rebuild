---
title: ComfyUI Audit - 30_Workflows/_ocr.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_ocr.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_render_temp\_concat.txt
---

# Audit: `30_Workflows\_ocr.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_ocr.json
```

## Nachweisbare Fakten

- Groesse: 146.796 Bytes.
- SHA256: `98ba544844abc979e9179c043bbff3cf51a9feff13764f3198ddf8e7067a7c0d`.
- JSON Top-Level: `dict`.
- Eintraege: 745.
- Jeder Value ist ein Dict mit exakt `output` und `elapsed_sec`.
- Leere Outputs: 0.
- Output-Laenge min/max/avg: 1 / 29 / 1.816.
- `elapsed_sec` min/max/avg/sum: 0.51 / 1.6 / 0.561 / 418.0.
- Eindeutige Outputs: 82.
- Haeufigste Outputs: `-` 279, `...` 91, `٠٠` 54, `1` 53, `in` 28, `..` 20, `O` 13, `C` 12.

## PB-Studio-Gegenstueck

- Gelesene Suche nach `OCR`, `ocr`, `text_recognition`, `easyocr`, `pytesseract`, `detected_text`, `text_regions` ergab keinen produktiven OCR-Service.
- `database\models.py`: `Scene.ai_caption`, `Scene.ai_tags`, `Scene.siglip_tags`; kein sichtbares OCR-Feld.
- `services\brain_v3\schemas\video.py`: `object_tags`, `mood_tags`, `style_tags`; kein sichtbares OCR-Feld.

## Vergleich

Referenz:

- Hat OCR-Ausgabe pro Video plus Laufzeit.
- Konkrete Outputs sind ueberwiegend sehr kurz und oft Platzhalter-/Rauschzeichen.
- Enthaelt keinen OCR-Generator, keine Bounding-Boxes, keine Confidence und keine Sprache.

PB Studio:

- Hat in den gelesenen Dateien kein OCR-Modul und kein OCR-Zielschema.
- Nutzt Text vor allem als Caption/Tags, nicht als erkannte Bildschrift.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Datei zeigt einen moeglichen OCR-Datenpunkt, aber die Ergebnisqualitaet ist aus den Daten fraglich und es fehlt Generator/Confidence/Zielschema. Eine OCR-Integration waere neue Funktionalitaet und aus dieser Datei allein nicht belegbar besser.

## Offen

Wenn Workflow-/Generatorcode gefunden wird, pruefen:

- welches OCR-Modell/Prompt genutzt wird;
- ob Confidence/Bounding-Boxes verfuegbar sind;
- ob PB OCR-Text fuer Suche, Safety oder Subtitle-Erkennung braucht.

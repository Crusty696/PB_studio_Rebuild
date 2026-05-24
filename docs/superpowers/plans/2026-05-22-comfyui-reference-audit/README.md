---
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
slug: comfyui-reference-audit
created: 2026-05-22
status: approved-for-implementation
reference_root: C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup
vault_mirror: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-comfyui-reference-audit-2026-05-22.md
vault_decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-050-comfyui-reference-audit-integration.md
---

# ComfyUI Studio Reference Audit + Integration

> **EINDEUTIGE PLAN-ID:** `COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22`

## User-Auftrag

Referenz-Verzeichnis:

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup
```

Analyse strikt file-by-file. Vergleich mit PB Studio. Pruefen:

1. Alle Funktionen und Workflows.
2. Art der Datengenerierung und Datenverarbeitung.
3. Nutzung, Verwaltung und Weiterleitung einzelner Datenpunkte.

Integration:

1. Nur nachweisbar bessere Code-Bloecke und Logik uebernehmen.
2. Anpassung an PB Studio direkt und fehlerfrei.
3. Ganze App-Teile duerfen ersetzt werden, wenn Qualitaet oder Performance nachweisbar besser ist.
4. Grundkonzept und Hauptziel von PB Studio duerfen sich nicht veraendern.

## Harte Grenzen

- Keine Annahmen. Unklar = lesen, testen oder User fragen.
- Kein App-Code ohne konkreten Referenzbeleg und PB-Studio-Zielvergleich.
- Kein Architekturwechsel ohne explizite Entscheidung.
- Kein Tool-/Library-Swap ohne explizite Entscheidung.
- Keine Status-Aussage `fixed` ohne Live-Verifikation nach AGENTS.md.
- GTX 1060 / CUDA-only-Regeln bleiben gueltig.
- PB Studio bleibt Director's Cockpit fuer Medienanalyse, Schnitt, Brain/Pipeline und Projekt-Workflows.

## Parallel-Regel

Der User hat Parallelarbeit am 2026-05-22 erlaubt.

Erlaubt:

- Read-only Inventarpruefung.
- Read-only App-side Suche nach Vergleichsmodulen.
- Read-only Analyse unabhaengiger Zielbereiche, wenn keine Dateien geschrieben werden.

Nicht erlaubt:

- Parallele Code-Integrationen.
- Parallele Statuswechsel.
- Paralleles Ueberspringen der Referenz-Reihenfolge.
- Mehrere halbfertige App-Code-Aenderungen.

Referenz-Traversal bleibt kanonisch sortiert nach relativem Pfad. User-Entscheidung 2026-05-22: `30_Workflows` wird als wichtigster Ordner vorgezogen und innerhalb dieses Ordners strikt sortiert abgearbeitet. Danach wird die globale Inventar-Reihenfolge fortgesetzt. Jede Referenzdatei bekommt Audit-Status.

## Phasen

### Phase 0 - Governance + Immutable File Inventory

Definition of Done:

- Registry-Eintrag existiert.
- Active Plan zeigt auf diese Plan-ID.
- Vault-Decision existiert.
- Vault-Mirror existiert.
- Referenz-Root existiert.
- Vollstaendige Datei-Liste als unveraenderlicher Audit-Anker erzeugt.
- Sortierregel dokumentiert: relativer Pfad, ordinal, case-insensitive.

### Phase 1 - File-by-File Reference Audit

Pro Referenzdatei:

1. Pfad exakt nennen.
2. Dateiinhalt lesen oder bei Binary/Media Metadaten erheben.
3. Zweck/Funktion aus Datei belegen.
4. PB-Studio-Gegenstueck finden oder dokumentieren: kein Gegenstueck gefunden.
5. Funktionen/Workflows vergleichen.
6. Datenpunkte, Datenfluss, Persistenz und Weiterleitung vergleichen.
7. Bessere Logik nur mit belegtem Grund markieren.
8. Wenn Integration sinnvoll: konkreten Zielpfad, Ersetzungsblock, Testplan und Risiko nennen.
9. Vault-Auditstatus schreiben.

### Phase 2 - Sequential Integration

Pro Verbesserungsblock:

1. Referenzbefund zitieren.
2. Zu ersetzenden PB-Studio-Code exakt nennen.
3. Begruendung: Qualitaet, Korrektheit, Performance oder Wartbarkeit.
4. Code editieren.
5. Import-/Syntaxcheck.
6. Betroffene Unit Tests.
7. Live-/UI-Test, falls UI/API/Pipeline betroffen.
8. Vault-Eintrag.
9. Commit mit ehrlichem Verifikationsstatus.

### Phase 3 - Final Synthesis

Definition of Done:

- Jede Referenzdatei hat Status.
- Jede uebernommene Logik hat Zielpfad, Testnachweis und Vault-Eintrag.
- Nicht uebernommene bessere Logik ist begruendet oder als offene Entscheidung markiert.
- Keine Veraenderung des PB-Studio-Hauptziels.

## Naechster erlaubter Task

```text
Phase 1 workflow-first reference audit from 30_Workflows row 22: 30_Workflows\Migration_Setup.md
```

## Phase 0 Ergebnis 2026-05-22

- Referenz-Root existiert: `C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup`.
- Datei-Inventar: `docs/superpowers/synthesis/comfyui-reference-file-inventory-2026-05-22.tsv`.
- Inventar-Zeilen: 12.517 inklusive Header, also 12.516 Referenzdateien.
- Inventar-SHA256: `c72785686328fd3ddff5b7d38b43ee2bab687975535804d702dd553dd65925c9`.
- Sortierregel: relativer Pfad, ordinal, case-insensitive.
- Erste Audit-Datei: `_lib\__pycache__\build_edl_v6.cpython-314.pyc`.
- Letzte Audit-Datei: `Tag_Stimmung_Heuristic.ps1`.
- User-Priorisierung nach Phase 0: `30_Workflows` zuerst; 42 Dateien; erste Workflow-Datei `30_Workflows\_all_captions.json`.
- `30_Workflows\_all_captions.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_audio_curve.json`.
- `30_Workflows\_audio_curve.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_beats.json`.
- `30_Workflows\_beats.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_captions_multiframe.json`.
- `30_Workflows\_captions_multiframe.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_clip_clusters.json`.
- `30_Workflows\_clip_clusters.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_clip_embeddings_keys.json`.
- `30_Workflows\_clip_embeddings_keys.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_clip_embeddings.npz`.
- `30_Workflows\_clip_embeddings.npz`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_clip_neighbors.json`.
- `30_Workflows\_clip_neighbors.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_cluster_signatures.json`.
- `30_Workflows\_cluster_signatures.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_cluster_summary.json`.
- `30_Workflows\_cluster_summary.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_objects.json`.
- `30_Workflows\_objects.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_ocr.json`.
- `30_Workflows\_ocr.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_render_temp\_concat.txt`.
- `30_Workflows\_render_temp\_concat.txt`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\_visual_features.json`.
- `30_Workflows\_visual_features.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\Brücke_ComfyUI_API.md`.
- `30_Workflows\Brücke_ComfyUI_API.md`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\chapters.json`.
- `30_Workflows\chapters.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\edl.json`.
- `30_Workflows\edl.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\florence2_video_caption.api.json`.
- `30_Workflows\florence2_video_caption.api.json`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\Frontmatter_Schema.md`.
- `30_Workflows\Frontmatter_Schema.md`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\INDEX.md`.
- `30_Workflows\INDEX.md`: auditiert, keine Code-Aenderung. Naechste Datei: `30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json`.
- `30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json`: auditiert, keine Code-Aenderung. Ergebnis: ComfyUI-GUI-Workflow fuer LTX-2.3-Videoerzeugung mit Motion-Track-Control, IC-LoRA und Distilled-LoRA; keine Integration, weil neuer ComfyUI/LTX-Backendpfad, Secret-/Runtime-/Output-Resolver und GTX-1060-VRAM-Entscheid noetig waeren. Naechste Datei: `30_Workflows\Migration_Setup.md`.

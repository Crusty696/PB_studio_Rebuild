# 38 — User-Triggers + Queue (Video)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

User-Modus B+C (laut Plan-Entscheidung 2026-05-19): per Schritt ODER sequentiell.

## Scope

- Pro Schritt: Start-Button im Status-Panel.
- Globaler "Alle ausstehenden starten" Button → topologisch sortiert + sequentiell.
- Multi-File-Batch: User markiert 50 Files → Batch-Queue.
- Pause / Resume / Cancel pro Schritt + global.
- Kein Auto-Start beim Import.

## Verifikation

- Per-Step funktioniert
- Sequentielle Alle-ausstehenden-Ausfuehrung
- Cancel sauber
- `pytest tests/test_services/test_video_user_triggers.py -v` gruen

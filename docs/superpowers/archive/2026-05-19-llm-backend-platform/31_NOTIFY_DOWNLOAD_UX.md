# 31 — Notify + Download-UX

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 3 UI
> Status: planned · 2026-05-19

## Ziel

Modell-Browser + Download-Progress + Empfehlungs-Toast.

## Scope

- Modell-Browser-Dialog (Tabs: Ollama-Hub / HuggingFace):
  - Filter: Rolle, Format, VRAM-Budget (live)
  - Inkompatible mit Tooltip-Begruendung ausgeblendet (Toggle-Button "anzeigen")
  - Quality-Score + Speed-Badge
- Download-Progress-Modal:
  - Pro Modell Progress-Bar + MB/s + ETA
  - Mehrere parallel? Nein, **sequentiell** (vermeidet Disk-Thrashing).
  - Pause / Cancel
- "Empfehlung"-Toast (non-modal):
  - "Besseres Modell <X> ist verfuegbar fuer Vision (Score 90 vs deine 70). [Jetzt laden] [Spaeter] [Nicht mehr fragen]"
  - Pro Rolle "Nicht mehr fragen"-Setting persistent

## Verifikation

- Download-Modal funktional, Cancel sauber
- Empfehlung erscheint nur 1× nach Suppression
- `pytest tests/test_ui/test_llm_notify.py -v` gruen

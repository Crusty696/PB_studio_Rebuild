# 28 — Hot-Reload-Modelle ohne App-Neustart

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

User waehlt in Settings neues Modell pro Rolle → keine App-Neustart noetig.

## Scope

- Selector cached aktiven Slot pro Rolle.
- Settings-Slot-Change-Signal → Slot wechseln:
  - Wenn Modell schon im RAM/VRAM (Ollama keep_alive) → nur Selector-Pointer wechseln, naechster Call nutzt neues Modell.
  - Wenn Modell nicht geladen → naechster Call laedt + Cold-Start (3-8 s).
- Laufende Streams werden **nicht** unterbrochen — neue Calls nutzen neuen Slot.
- Status-Dot blinkt orange waehrend Cold-Load.

## Verifikation

- Slot-Change-Test, anschliessender Chat-Call nutzt neues Modell
- Laufender Stream lebt weiter mit altem Modell bis fertig
- `pytest tests/test_services/test_llm_hot_reload.py -v` gruen

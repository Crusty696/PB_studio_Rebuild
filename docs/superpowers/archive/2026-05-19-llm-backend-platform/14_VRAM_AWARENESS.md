# 14 — VRAM-Awareness + Audio-V2 / Brain V3 Coexistenz

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Vermeiden dass LLM-Modell-Load die 6 GB der GTX 1060 sprengt, **wenn** Audio-V2 (Demucs/beat_this) oder Brain V3 (SigLIP) gerade GPU nutzen.

## Strategie (read-only, kein neuer Broker)

- Vor jedem Modell-Load: pynvml liest live `memory_free_gb`.
- VRAM-Budget = `memory_free_gb - safety_margin (0.5 GB)`.
- Auto-Selector nutzt dieses Budget statt Hard-Coded 5.5 GB.
- Wenn Budget zu klein:
  - kleineres Modell aus Fallback-Chain waehlen
  - oder Request queuen bis Budget frei
- LLM-Embeddings (CLAP, bge-m3) laufen **CPU-only** → kein VRAM-Beitrag von LLM-Embeddings-Seite.

## Beobachter

- `services/llm/vram_observer.py`:
  - Polling-Frequenz: 2 s
  - Cached Wert mit Timestamp
  - Event-Signal `vram_free_changed(gb)` an Settings-Dialog
- Lock-Holder-Awareness:
  - Existierender `GPU_EXECUTION_LOCK` (Audio-V2) **nicht** anfassen
  - Wenn pynvml meldet dass nur < 1 GB frei → Audio-V2 / Brain V3 aktiv annehmen → LLM-Inferenz queuen oder kleineres Modell

## Out of Scope

- VRAM-Broker-Redesign (alle Consumer reservieren explizit) — eigener Folge-Plan.

## Offene Klaerungs-Punkte

- [ ] Safety-Margin 0.5 GB oder konfigurierbar?
- [ ] Bei langem Audio-V2-Lauf: LLM-Inferenz queuen vs aktiv abbrechen?

## Verifikation

- Mit laufendem Demucs: LLM-Selector waehlt kleineres Modell oder wartet
- Crash-Frei bei mehrmaligem Wechsel
- `pytest tests/test_services/test_llm_vram_awareness.py -v` gruen

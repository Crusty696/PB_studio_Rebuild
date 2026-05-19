# 21 — Embeddings + Vector-Store (Hybrid CPU/GPU)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19 (User-Entscheidung Hybrid 2026-05-19)

## Ziel

Text- und Audio-Embeddings persistent speichern + durchsuchbar. **Hybrid CPU/GPU opportunistisch** — GPU wenn frei, sonst CPU.

## Embedding-Modelle

- `bge-m3` (1024 dim, multilingual)
- `nomic-embed-text` (768 dim, en)
- `mxbai-embed-large` (1024 dim, en)
- `CLAP` (Audio-Embedding, optional)

## Backend-Wahl pro Call (Hybrid-Logik)

```python
def choose_embed_device(model: ModelInfo, vram_observer, lock_status) -> str:
    """
    Default: CPU.
    Opportunistisch GPU wenn:
      - kein aktiver GPU_EXECUTION_LOCK (Audio-V2 / Brain V3 nicht aktiv)
      - vram_free_gb >= model.vram_gb + safety_margin (1.5 GB Default)
      - aktueller Reasoner-Slot belegt diesen VRAM nicht gleichzeitig
    Sonst: CPU.
    """
    if lock_status.busy:
        return "cpu"
    if vram_observer.free_gb < model.vram_gb + 1.5:
        return "cpu"
    if reasoner_slot_active() and reasoner_slot_vram_gb + model.vram_gb > 5.5:
        return "cpu"
    return "cuda:0"
```

### Pro Aufruf

- Batched-Embed:
  - Vor Batch-Start: Device-Wahl einmal pro Batch (nicht pro Sample, vermeidet Thrash).
  - GPU-Batch: ~100 Samples/Batch.
  - CPU-Batch: ~25 Samples/Batch.
- Cancel-aware: Batch-Worker prueft cancel_token zwischen Batches.
- VRAM-Wechsel waehrend Batch: nicht hot-wechseln, naechster Batch entscheidet neu.

## Storage

- SQLite mit numpy-Blob-Column (siehe D-011).
- **Per-Modell-Tabelle**: `embeddings_bge_m3`, `embeddings_nomic`, etc.
- Keine Mischung intra-search — Aehnlichkeitssuche nur intra-model.
- Index: anfangs Brute-Force-Cosine, spaeter optional usearch (siehe D-025).
- Cache-Key: `sha256(text + model_id)` → bestehender Vektor wiederverwendet.

## Out of Scope

- Re-Embed bei Modell-Wechsel — User-Hinweis "Mixed-Vector-Search aktiv".

## Offene Klaerungs-Punkte

- [ ] Safety-Margin 1.5 GB ok oder konfigurierbar?
- [ ] Hot-Reload-Embed-Modell waehrend Batch laeuft → Cancel + Restart oder weiter mit altem?
- [ ] CLAP-Embeds gehoeren konzeptionell zur Audio-Pipeline (V2-Erweiterung) — hier nur Konsumenten-API?

## Verifikation

- Bei freiem VRAM → Embed auf GPU, schneller als CPU-Pfad
- Bei aktivem Demucs → automatisch CPU-Pfad
- Cosine-Search liefert plausible Treffer
- `pytest tests/test_services/test_llm_embeddings.py -v` gruen

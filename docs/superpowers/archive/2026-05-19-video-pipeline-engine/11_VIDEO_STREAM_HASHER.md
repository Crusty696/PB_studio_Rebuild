# 11 — Video-/Audio-Stream-Hasher

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Container-uebergreifender Hash. MOV + MP4 mit identischem Stream → gleicher Hash → Dedup.

## Scope

```python
def stream_sha256(path: Path, *, kind: str) -> str:
    """
    kind="video": hash decoded video stream packets
    kind="audio": hash decoded audio stream packets
    Fast approximation: first 5 MB + last 5 MB + duration + codec params
    Optional: full-pass for exact content match (opt-in)
    """
```

- Fast-Mode: 10 MB total + Metadata (default).
- Strict-Mode: gesamtes Streampacket (optional, fuer kritische Dedup).

## Verifikation

- MP4 ↔ MOV remux identisch → gleicher Hash
- Modifiziertes Video → anderer Hash
- `pytest tests/test_services/test_stream_hasher.py -v` gruen

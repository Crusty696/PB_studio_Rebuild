# 13 — Adapter-Layer (Backward-compat)

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 2

## Ziel

Alte Pfade (z. B. `storage/stems/<track_id>/vocals.wav`) bleiben sichtbar fuer SCHNITT-Audio-Subtab + Stem-Player, OHNE V2-Code anzufassen.

## Scope

```python
# services/storage_provenance/adapter_layer.py

def resolve_artifact_path(track_id_or_sha, role: str) -> Path:
    """
    Funktioniert mit beiden:
      - track_id (V2-Pattern)
      - source_sha256 (neu)
    Returns konkrete Datei.
    """
```

- Junction/Symlink von `by_sha/<sha>/audio/stems/` -> `storage/stems/<track_id>/` damit V2-Code unveraendert weiterlaeuft.
- Pfad-Lookup-Service ueber `analysis_artifacts`-Tabelle.
- Fallback: alte Pfade direkt zurueckgeben wenn `by_sha/` nicht existiert.

## Verifikation

- SCHNITT-Audio-Subtab funktioniert ohne Aenderung
- Stem-Player findet Files
- `pytest tests/test_services/test_adapter_layer.py -v` gruen

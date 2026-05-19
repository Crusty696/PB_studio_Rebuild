# 12 — Dedup-Lookup

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 2

## Ziel

Pro Schritt vor Lauf: pruefen ob Job bereits erledigt fuer gleiche `(source_sha, step_id, step_version, params_hash)`.

## Scope

```python
def check_dedup(source_sha, step_id, step_version, params) -> DedupResult:
    """
    Returns:
      hit:   Job existiert + done -> Artefakt-Pfade reuse
      miss:  kein Job -> ausfuehren
      stale: existiert aber step_version aelter -> User-Hinweis
      partial: Job partial -> resume
    """
```

- Source: `analysis_jobs`-Tabelle.
- Im V2- und Plan-A-Orchestrator vor jedem Stage-Start aufgerufen.

## Verifikation

- Doppel-Aufruf desselben Steps -> 2. = hit
- `pytest tests/test_services/test_dedup_lookup.py -v` gruen

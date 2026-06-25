# 12 — Dedup-Lookup

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 2
> Status: code-complete-tests-green · 2026-06-14

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

## Progress 2026-06-14

- Implementiert `services/storage_provenance/dedup_lookup.py`.
- `stable_params_hash()` nutzt sortiertes JSON + SHA256.
- `check_dedup()` liefert `hit`, `miss`, `stale`, `partial` anhand `analysis_jobs`.
- Verifiziert in `tests/test_services/test_dedup_lookup.py`.
- Tier-2-Fokustests `9 passed`; Tier1+Tier2 kombiniert `15 passed`.
- Kein Produkt-Live-Verify. Kein `fixed` Marker.

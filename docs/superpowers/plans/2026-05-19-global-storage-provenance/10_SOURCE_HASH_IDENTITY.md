# 10 — Source-Hash Identity

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 2
> Status: code-complete-tests-green · 2026-06-14

## Ziel

`source_sha256` deterministisch berechnen. Audio + Video.

## Strategie

- Fast-Mode: `sha256(first_5MB + last_5MB + filesize + media_type)`.
- Strict-Mode: full-file (User-getriggert, fuer kritische Dedup).
- Audio-Stream-SHA + Video-Stream-SHA optional (nutzt Plan-A `11_VIDEO_STREAM_HASHER.md` + analog Audio).

## Verifikation

- Gleiche Datei → gleicher Hash
- 1-Bit-Modifikation → anderer Hash
- `pytest tests/test_services/test_source_hash.py -v` gruen

## Progress 2026-06-14

- Implementiert `services/storage_provenance/source_identity.py`.
- Fast-Mode: first 5 MiB + last 5 MiB + filesize + media_type.
- Strict-Mode: full-file + media_type.
- Verifiziert in Tier-2-Fokustests `9 passed`; Tier1+Tier2 kombiniert `15 passed`.
- Kein Produkt-Live-Verify. Kein `fixed` Marker.

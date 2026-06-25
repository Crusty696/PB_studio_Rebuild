# 31 — SCHNITT-Audio-Adapter (Backward-compat)

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3
> Status: code-complete-tests-green · 2026-06-14

## Ziel

SCHNITT-Audio-Subtab + Stem-Player nutzen weiter alte Pfade. Adapter macht sie sichtbar.

## Scope

- Beim Projekt-Open: Adapter-Layer (`13_ADAPTER_LAYER.md`) baut Junctions wenn fehlend.
- Verifikation: SCHNITT-Subtab oeffnet, Stems abspielbar, ohne SCHNITT-Code-Aenderung.

## Verifikation

- SCHNITT-Subtab integration-test
- `pytest tests/test_ui/test_schnitt_audio_adapter.py -v` gruen

## Progress 2026-06-14

- Implementiert `services/storage_provenance/schnitt_audio_adapter.py`.
- `ProjectManager.open_project()` ruft nach `database.init_db()` defensiv `ensure_schnitt_audio_adapter()` auf.
- Adapter nutzt `StorageMigrationService`, baut fehlende Stem-Junctions idempotent und blockiert Projekt-Open nicht bei Fehlern.
- Testpfad im aktuellen Repo: `tests/ui/test_schnitt_audio_adapter.py`.
- Verifiziert: SCHNITT-Adapter + Storage-Migration `5 passed`; OTK-021 Slice `20 passed`; py_compile gruen; `git diff --check` gruen.
- Kein echter GUI-Klick in SCHNITT-Audio-Subtab/Stem-Player. Kein `fixed` Marker.

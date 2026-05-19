# 31 — SCHNITT-Audio-Adapter (Backward-compat)

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 3

## Ziel

SCHNITT-Audio-Subtab + Stem-Player nutzen weiter alte Pfade. Adapter macht sie sichtbar.

## Scope

- Beim Projekt-Open: Adapter-Layer (`13_ADAPTER_LAYER.md`) baut Junctions wenn fehlend.
- Verifikation: SCHNITT-Subtab oeffnet, Stems abspielbar, ohne SCHNITT-Code-Aenderung.

## Verifikation

- SCHNITT-Subtab integration-test
- `pytest tests/test_ui/test_schnitt_audio_adapter.py -v` gruen

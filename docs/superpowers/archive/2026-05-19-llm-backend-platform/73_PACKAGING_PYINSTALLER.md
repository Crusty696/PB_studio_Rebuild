# 73 — Packaging mit PyInstaller (Bundled Ollama)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

PB Studio-Installer enthaelt Ollama-Binary + CUDA-DLLs. Keine externe Installation noetig.

## Scope

- PyInstaller `.spec`-Datei:
  ```python
  datas = [
      ("resources/llm/ollama/ollama.exe", "resources/llm/ollama/"),
      ("resources/llm/ollama/lib/*", "resources/llm/ollama/lib/"),
      ("config/llm_models.json", "config/"),
      ("THIRD_PARTY_LICENSES.md", "."),
  ]
  ```
- Pfad-Resolution:
  - `sys._MEIPASS` (PyInstaller frozen)
  - `Path(__file__).parents[2]` (dev-Mode)
- Erstes Entpacken nach `%APPDATA%/PBStudio/llm/ollama/` (read-only Spec-Path nicht beschreibbar).
- Code-Signing-Strategie (Windows AV False-Positive):
  - Selbst-signiert fuer privat OK
  - Falls Distribution geplant: EV-Cert noetig
- THIRD_PARTY_LICENSES.md (Ollama MIT, Modelle separat).
- Installer-Groesse erwartet ~400-600 MB inkl. Ollama-Binary + CUDA-DLLs.

## Verifikation

- Fresh-VM Install → App startet ohne extra Ollama
- AV-Scan (Defender) → kein False-Positive (oder Whitelist dokumentieren)
- PyInstaller-Build laeuft im CI gruen

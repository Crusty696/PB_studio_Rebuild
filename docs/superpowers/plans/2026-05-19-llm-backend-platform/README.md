---
plan_id: LLM-BACKEND-PLATFORM-2026-05-19
slug: llm-backend-platform
created: 2026-05-19
status: draft-approved-for-planning
authored_via: user-directed planning session 2026-05-19
authorized_by_user_at: 2026-05-19
vault_decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-044-llm-backend-platform-ollama-embed.md
NOT_TO_CONFUSE_WITH:
  - AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17  (Audio-Pipeline-Orchestrator, parallel, kein Overlap)
  - 2026-05-04-brain-v3-nvidia-plan                 (Brain V3, parallel, kein Overlap)
  - 2026-05-09-schnitt-workspace-redesign           (UI SCHNITT, parallel)
  - 2026-05-13-schnitt-usability-wiring-rebuild     (SCHNITT-Followup, parallel)
  - Plan A (geplant) 2026-05-XX-video-pipeline-engine   (Video, eigener Folge-Plan)
  - Plan C (geplant) 2026-05-XX-global-storage-and-provenance (Storage-Adapter + Provenance)
---

# LLM-Backend-Platform — Implementation Plan

> **EINDEUTIGE PLAN-ID:** `LLM-BACKEND-PLATFORM-2026-05-19`
> Pflicht-Tag in Commits / Vault / Tests / Skeptic-Reports.

**Ziel:** PB Studio bekommt eine eigene LLM-Backend-Schicht.
Ollama wird als Subprozess in die App eingebettet (kein externer Daemon noetig).
HuggingFace-Direkt-Download. Auto-Wahl bestes Modell pro Aufgabe.
LM-Studio als Stub (Folge-Plan aktiviert ihn).

**Hartregeln** (aus AGENTS.md / CLAUDE.md / D-040 / D-041 / D-042 / D-044):

- GTX 1060 (CUDA 11.3, Treiber 546.33) ist einzige zulaessige GPU.
- Nur User-autorisierte Aenderungen. Bei Unklarheit STOP + ASK.
- Vault-Update PRO Sub-Schritt mit Zeitstempel.
- Sprache zum User: Deutsch (Caveman ultra/full).
- `status: fixed` setzt **nur** der User.
- Code/Commits = normal, Status-Updates = caveman-knapp.
- TDD pro Task (RED → GREEN → REFACTOR).
- Conda-Env: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`.

**Tech-Anker:**

- Python: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`
- pytest: `"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest <path> -v --tb=short`
- Vault: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-llm-backend-platform-2026-05-19.md` (Mirror anlegen vor Phase-Start)
- Test-Datensatz: Solo_Natur (103 Files) + Crusty Progressive Psy Set2.mp3 (149 MB DJ-Mix). Lange Test-Daten siehe `61_LIVE_VERIFY_USER.md`.

---

## Architektur-Kurzform

```
PB Studio App
  ├── services/llm/
  │     ├── runtime/                  (Backend-Layer)
  │     │   ├── base.py               LlmBackend Protocol
  │     │   ├── ollama_embedded.py    Subprozess, eigener Port, eigene Models
  │     │   └── lmstudio_external.py  Stub (NotImplementedError)
  │     ├── registry.py               Modell-Registry (config/llm_models.json)
  │     ├── selector.py               Auto-Selector (Score + VRAM-Budget)
  │     ├── modelfile.py              Modelfile-Generator pro Modell/Rolle
  │     ├── downloaders/
  │     │   ├── hf.py                 HuggingFace Resume + Token
  │     │   └── ollama_pull.py        POST /api/pull mit SSE-Progress
  │     ├── queue.py                  Request-Queue + Streaming
  │     ├── caching.py                Response + Prompt-Cache
  │     ├── embeddings.py             CPU-only fuer LLM-Embeddings
  │     ├── tokens.py                 Keyring/DPAPI
  │     └── observability.py          Per-Request-Log + Usage-Stats
  ├── ui/dialogs/
  │     ├── setup_wizard.py           (erweitert um First-Run-LLM-Wahl)
  │     ├── settings_dialog.py        (LLM-Backend-Wahl, HF-Token)
  │     └── model_license_dialog.py   (Lizenz-Akzept)
  ├── resources/llm/ollama/           Gebundelte Ollama-Binary + CUDA-DLLs
  ├── config/llm_models.json          Modell-Registry-Daten
  └── %APPDATA%/PBStudio/llm/         Modell-Storage zur Laufzeit
        ├── ollama/                   Ollama-Daemon-Daten
        └── cache/hf_hub/             HuggingFace-Cache
```

---

## Phasen-Reihenfolge (Tier-Mapping, geschaerft 2026-05-19)

Tier-Definition wie in SCHNITT-Plan: **Tier 1** = Foundation (DB + Schemas).
**Tier 2** = wiederverwendbare **Building-Blocks** (Helper, Primitives, Algorithmen).
**Tier 3** = **Workspace + Services**, komponiert aus Tier-2-Bausteinen.
**Tier 4-6** = Tests + Infrastruktur.

| Tier | Inhalt | Doc-Files |
|---|---|---|
| **1 Foundation** | DB-Tabellen, Registry-Schema, Modell-Recherche | 01, 02, 03 |
| **2 Building-Blocks** | Wiederverwendbare Primitives + Algorithmen — kein Lifecycle, kein UI: Modelfile-Generator, Auto-Selector-Algorithmus, VRAM-Observer, Hardware-Probe + Filter, Request-Queue + Streaming-Primitive, Tool-Schema + Router, JSON-Schema-Validator, Context-Truncator, Caching-Primitive, Keyring-Wrapper, Pin-Logic | 12, 13, 14, 15, 16, 17, 18, 19, 20, 24, 25 |
| **3 Workspace + Services** | Komponierte Services + UI-Workspaces (nutzen Tier-2-Bausteine): Daemon-Lifecycle-Service, Backend-Provider-Klassen, Embeddings-Service, Downloader-Services, License-Dialog-Service, Update-Notify-Service, Hot-Reload-Slot-Manager, First-Run-Wizard, Notify-Download-UX, Settings-Dialog, Project-Pins-UI | 10, 11, 21, 22, 26, 27, 28, 30, 31, 32, 33 |
| **Caller-Migration** | Bestehende `ollama_service`-Caller umstellen (Inventory + Services + UI). Berührt Tier-3-Caller-Seite, deckt Coverage-Anforderung Tier 4 + 5 mit ab | 40, 41, 42 |
| **4 Service-Coverage** | Tests fuer Services ≥ 85 % | 50 |
| **5 Controller-Coverage** | Tests fuer Controller ≥ 85 % | 51 |
| **6 Test-Infra** | Mock-Daemon + Fixtures + In-Memory-DB | 60 |
| **Cross-Cutting (orthogonal)** | Quer-Themen die alle Tiers betreffen: Storage-Management, Error-Surface, Observability, Security (incl. Single-Instance), PyInstaller-Packaging, Update-Flow, Uninstall, Per-Project-Prefs, Multimodal-Plumbing | 23, 70, 71, 72, 73, 74, 75, 76, 77 |
| **Verifikation (Final)** | Live-Verify-User-Walkthrough, globaler E2E, Offene Fragen | 61, 90, 99 |

**Anmerkung zur Anwendung:** Tier-Disziplin **streng** bei Coverage-Phasen (4, 5, 6). Tier 1-3 werden in dieser Reihenfolge implementiert (Foundation → Building-Blocks → Workspace), aber innerhalb eines Tiers koennen mehrere Phasen parallel laufen. Caller-Migration + Cross-Cutting + Verifikation sind **bewusst ausserhalb** des reinen Tier-Konzepts (V2-Plan macht das aehnlich).

---

## Phasen-Datei-Verzeichnis (Tier-konform, geschaerft 2026-05-19)

### Tier 1 — Foundation
- [01_DB_LLM_TABLES.md](01_DB_LLM_TABLES.md) — Neue Tabellen / Migrationen
- [02_MODEL_REGISTRY_SCHEMA.md](02_MODEL_REGISTRY_SCHEMA.md) — `config/llm_models.json` Schema
- [03_RESEARCH_MODELS_2026.md](03_RESEARCH_MODELS_2026.md) — Modell-Liste 2026, Lizenz-Audit

### Tier 2 — Building Blocks (wiederverwendbare Primitives)
> Reine Algorithmen + Datenklassen + Generatoren, keine eigenen Lifecycles, kein UI. Werden von Tier-3-Services + UI zusammengesetzt.

- [12_MODELFILE_AND_PARAMS.md](12_MODELFILE_AND_PARAMS.md) — Modelfile-Generator + Templates
- [13_AUTO_SELECTOR.md](13_AUTO_SELECTOR.md) — Score-Algorithmus, Fallback-Chain
- [14_VRAM_AWARENESS.md](14_VRAM_AWARENESS.md) — pynvml-Observer (read-only)
- [15_HARDWARE_PROBE_AND_FILTER.md](15_HARDWARE_PROBE_AND_FILTER.md) — Probe + Filter-Regeln
- [16_REQUEST_QUEUE_AND_STREAMING.md](16_REQUEST_QUEUE_AND_STREAMING.md) — Queue + SSE-Parser
- [17_TOOL_CALLING.md](17_TOOL_CALLING.md) — Tool-Schema + Router-Primitive
- [18_JSON_STRUCTURED_OUTPUT.md](18_JSON_STRUCTURED_OUTPUT.md) — Schema-Validator
- [19_CONTEXT_TRUNCATION.md](19_CONTEXT_TRUNCATION.md) — Token-Counter + Truncator
- [20_CACHING_RESPONSE_PROMPT.md](20_CACHING_RESPONSE_PROMPT.md) — Cache-Primitive
- [24_SECRETS_AND_TOKENS.md](24_SECRETS_AND_TOKENS.md) — Keyring-Wrapper + Log-Scrubber
- [25_MODEL_PINS_AND_VERSIONS.md](25_MODEL_PINS_AND_VERSIONS.md) — Pin-Logic + Re-Run-Policy

### Tier 3 — Workspace + Services (komponiert aus Tier-2-Bausteinen)
> Klassen mit Lifecycle + UI-Komponenten.

- [10_BOOT_AND_LIFECYCLE.md](10_BOOT_AND_LIFECYCLE.md) — Daemon-Lifecycle-Service (Watchdog, PID, Shutdown)
- [11_BACKEND_LAYER.md](11_BACKEND_LAYER.md) — Backend-Provider-Klassen (Ollama-Impl + LMS-Stub)
- [21_EMBEDDINGS_AND_VECTOR_STORE.md](21_EMBEDDINGS_AND_VECTOR_STORE.md) — Embeddings-Service (Hybrid CPU/GPU)
- [22_DOWNLOADERS_HF_OLLAMA.md](22_DOWNLOADERS_HF_OLLAMA.md) — Downloader-Services (HF + Ollama-Pull)
- [26_MODEL_LICENSE_ACCEPT.md](26_MODEL_LICENSE_ACCEPT.md) — License-Dialog + Accept-Service
- [27_MODEL_UPDATE_NOTIFY.md](27_MODEL_UPDATE_NOTIFY.md) — Update-Check-Service
- [28_HOT_RELOAD_MODELS.md](28_HOT_RELOAD_MODELS.md) — Slot-Manager-Service
- [30_FIRST_RUN_WIZARD.md](30_FIRST_RUN_WIZARD.md) — Wizard-Workspace
- [31_NOTIFY_DOWNLOAD_UX.md](31_NOTIFY_DOWNLOAD_UX.md) — Browser + Toast-Dialog
- [32_SETTINGS_DIALOG_LLM.md](32_SETTINGS_DIALOG_LLM.md) — Settings-LLM-Sektion
- [33_PROJECT_SETTINGS_PINS_LLM.md](33_PROJECT_SETTINGS_PINS_LLM.md) — Pro-Projekt-Pins-UI

### Caller-Migration (beruehrt Tier 3 + Coverage-Beitrag Tier 4/5)
- [40_CALLER_MIGRATION_INVENTORY.md](40_CALLER_MIGRATION_INVENTORY.md) — Inventar
- [41_CALLER_MIGRATION_SERVICES.md](41_CALLER_MIGRATION_SERVICES.md) — Services umstellen
- [42_CALLER_MIGRATION_UI.md](42_CALLER_MIGRATION_UI.md) — UI umstellen

### Tier 4 — Service-Coverage
- [50_TESTS_SERVICES.md](50_TESTS_SERVICES.md) — ≥ 85 % pro Service

### Tier 5 — Controller-Coverage
- [51_TESTS_CONTROLLERS.md](51_TESTS_CONTROLLERS.md) — ≥ 85 % pro Controller

### Tier 6 — Test-Infra
- [60_TESTS_INFRA_MOCKS.md](60_TESTS_INFRA_MOCKS.md) — Mock-Ollama-Daemon + Fixtures

### Cross-Cutting (orthogonal zu allen Tiers)
- [23_STORAGE_MANAGEMENT_MODELS.md](23_STORAGE_MANAGEMENT_MODELS.md) — Disk-Probe, Cleanup, Custom-Drive
- [70_ERROR_SURFACE_LLM.md](70_ERROR_SURFACE_LLM.md) — Error-Mapping + Recovery
- [71_OBSERVABILITY_LLM.md](71_OBSERVABILITY_LLM.md) — Per-Request-Log, Usage-Stats
- [72_SECURITY.md](72_SECURITY.md) — Bind 127.0.0.1, Env-Whitelist, Single-Instance, Log-Scrub
- [73_PACKAGING_PYINSTALLER.md](73_PACKAGING_PYINSTALLER.md) — Bundled Ollama, Code-Sign
- [74_UPDATE_FLOW_LLM.md](74_UPDATE_FLOW_LLM.md) — Pinned Version, App-Update behaelt Modelle
- [75_UNINSTALL.md](75_UNINSTALL.md) — Cleanup, Keyring entfernen
- [76_PER_PROJECT_LLM_PREFS.md](76_PER_PROJECT_LLM_PREFS.md) — Projekt-Override
- [77_MULTIMODAL_PLUMBING.md](77_MULTIMODAL_PLUMBING.md) — VLM-base64, Omni-Audio-Chunks

### Verifikation (Final, ausserhalb Tier)
- [61_LIVE_VERIFY_USER.md](61_LIVE_VERIFY_USER.md) — User-Live-Test-Script
- [90_LIVE_VERIFY.md](90_LIVE_VERIFY.md) — Globaler E2E-Walkthrough
- [99_OPEN_QUESTIONS.md](99_OPEN_QUESTIONS.md) — Offene Klaerungspunkte

---

## Pflicht-Regeln pro Sub-Task

1. **Vault-Sync** sofort nach jedem Sub-Step (log.md Zeitstempel + Vault-Mirror).
2. **TDD** RED → GREEN → REFACTOR, pytest-Output dokumentiert.
3. **Commit-Format:** `llm-platform: <was>` + Body-Line `Plan: LLM-BACKEND-PLATFORM-2026-05-19`.
4. **Code/Tests** nur in Phasen-Files vorgegebener Scope. Keine While-I'm-here-Fixes.
5. **GPU-Hartregel** GTX 1060 / CUDA 11.3 only.
6. **Konflikt-Awareness:** `GPU_EXECUTION_LOCK` (Audio-V2) respektieren via read-only pynvml-Probe.

## Globaler Erfolgs-Test

User startet PB Studio frisch installiert, sieht First-Run-Wizard, waehlt Reasoner-Modell (z. B. qwen3:8b-q4), akzeptiert Lizenz, sieht Download-Progress, kommt zur Main-UI mit gruener LLM-Status-Anzeige. Chat-Dock funktioniert. Modell-Wechsel ueber Settings ohne App-Neustart. Bei zweiter Start-Instanz wird existierende vorgebracht (Single-Instance-Lock). Audio-V2-Pipeline laeuft parallel ohne VRAM-Crash.

## Plan-Abweichungs-Register

(Wird wie in SCHNITT-Plan gepflegt — Spalten: # / Bereich / Plan-Soll / Ist / Begruendung. Leer bis Implementation startet.)

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-020` on 2026-06-09.

- Original plan: `LLM-BACKEND-PLATFORM-2026-05-19`
- Original open work: Planning/review only; caller migration restrictions; open questions and live verify remain.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.

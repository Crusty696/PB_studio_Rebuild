---
plan_id: GLOBAL-STORAGE-PROVENANCE-2026-05-19
slug: global-storage-provenance
created: 2026-05-19
status: draft-approved-for-planning
authored_by_user_at: 2026-05-19
vault_decision: C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-046-global-storage-provenance.md
NOT_TO_CONFUSE_WITH:
  - AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17
  - LLM-BACKEND-PLATFORM-2026-05-19
  - VIDEO-PIPELINE-ENGINE-2026-05-19
  - 2026-05-04-brain-v3-nvidia-plan
  - 2026-05-09-schnitt-workspace-redesign
  - 2026-05-13-schnitt-usability-wiring-rebuild
---

# Global Storage + Provenance — Implementation Plan

> **EINDEUTIGE PLAN-ID:** `GLOBAL-STORAGE-PROVENANCE-2026-05-19`
> Pflicht-Tag in Commits / Vault / Tests / Skeptic-Reports.

**Ziel:** Storage- und Provenance-Layer **ueber** V2 (Audio) + Plan A (Video).

- Content-Address-Storage by `source_sha256`.
- Provenance-DB: `analysis_jobs`, `analysis_artifacts`, `step_deps`.
- Adapter fuer SCHNITT-Audio-Subtab (Backward-compat).
- Cross-Project-Reuse: Notify-only Toast.
- File-Tracking-Repair (Source-Move).
- Project-Export/Import inkl. Artefakten.

**Voraussetzung:** Plan A + Plan B Tier 1-2 abgeschlossen ODER zumindest V2 Live-Verify durch User.

**Hartregeln** (D-040 / D-041 / D-042 / D-046):

- GTX 1060 / CUDA 11.3 only
- Nur User-autorisierte Aenderungen
- Vault pro Sub-Schritt
- Caveman ultra/full
- `status: fixed` nur User
- TDD pro Task

---

## Architektur-Kurzform

```
PB Studio
├── services/storage_provenance/
│     ├── source_identity.py         SHA fuer Audio/Video/Image
│     ├── caller_migration.py        Pipeline-Caller -> analysis_jobs/artifacts
│     ├── cross_project_reuse.py     Import-Hinweis + AnalysisStatus-Reuse
│     ├── project_bundle.py          .pbbundle Export/Import
│     ├── file_tracking.py           Source-Move-Repair
│     ├── adapter_layer.py           alte Pfade -> globale Lookup
│     └── dedup_lookup.py            existing-analysis-check
├── ui/widgets/
│     └── storage_browser_dialog.py  Storage-Browser UI
└── %APPDATA%/PBStudio/storage/
        └── by_sha/<source_sha256>/
            ├── audio/    (Symlink/Junction zu V2-stems)
            ├── video/    (Symlink/Junction zu Plan-A-output)
            └── meta.json
```

---

## Phasen-Reihenfolge (Tier-Mapping)

| Tier | Inhalt | Doc-Files |
|---|---|---|
| **1 Foundation** | DB-Provenance, Storage-Layout-Spec | 01, 02 |
| **2 Building-Blocks** | Source-Hash, File-Tracking, Dedup-Lookup, Adapter | 10, 11, 12, 13 |
| **3 Workspace+Services** | Migration-Service, SCHNITT-Adapter, Cross-Project-Toast, Storage-Browser, Export | 30, 31, 32, 33, 34 |
| **Caller-Migration** | V2 + Plan A + SCHNITT-Caller adaptieren | 40 |
| **4-6 Tests** | Service / Controller / Infra | 50, 51, 60 |
| **Cross-Cutting** | Backup-Portability, Disk-Budget-Global | 70, 71 |
| **Verifikation** | Live-Verify + Open-Questions | 90, 99 |

---

## Phasen-Datei-Verzeichnis

### Tier 1
- [01_DB_PROVENANCE_TABLES.md](01_DB_PROVENANCE_TABLES.md)
- [02_STORAGE_LAYOUT_SPEC.md](02_STORAGE_LAYOUT_SPEC.md)

### Tier 2
- [10_SOURCE_HASH_IDENTITY.md](10_SOURCE_HASH_IDENTITY.md)
- [11_FILE_TRACKING_REPAIR.md](11_FILE_TRACKING_REPAIR.md)
- [12_DEDUP_LOOKUP.md](12_DEDUP_LOOKUP.md)
- [13_ADAPTER_LAYER.md](13_ADAPTER_LAYER.md)

### Tier 3
- [30_STORAGE_MIGRATION_SERVICE.md](30_STORAGE_MIGRATION_SERVICE.md)
- [31_SCHNITT_AUDIO_ADAPTER.md](31_SCHNITT_AUDIO_ADAPTER.md)
- [32_CROSS_PROJECT_REUSE_UX.md](32_CROSS_PROJECT_REUSE_UX.md)
- [33_STORAGE_BROWSER_UI.md](33_STORAGE_BROWSER_UI.md)
- [34_PROJECT_EXPORT_IMPORT.md](34_PROJECT_EXPORT_IMPORT.md)

### Caller-Migration
- [40_CALLER_MIGRATION.md](40_CALLER_MIGRATION.md)

### Tests
- [50_TESTS_SERVICES.md](50_TESTS_SERVICES.md)
- [51_TESTS_CONTROLLERS.md](51_TESTS_CONTROLLERS.md)
- [60_TESTS_INFRA.md](60_TESTS_INFRA.md)

### Cross-Cutting
- [70_BACKUP_PORTABILITY.md](70_BACKUP_PORTABILITY.md)
- [71_DISK_BUDGET_GLOBAL.md](71_DISK_BUDGET_GLOBAL.md)

### Verifikation
- [90_LIVE_VERIFY.md](90_LIVE_VERIFY.md)
- [99_OPEN_QUESTIONS.md](99_OPEN_QUESTIONS.md)

---

## Pflicht-Regeln

1. **Voraussetzung:** Plan A Tier 1-2 + Plan B Tier 1-2 oder gleichwertig.
2. **V2 nicht anfassen** — Adapter mappt nur.
3. **Vault-Sync** pro Sub-Step.
4. **TDD** pro Task.
5. **Commit-Format:** `storage-prov: <was>` + Body-Line `Plan: GLOBAL-STORAGE-PROVENANCE-2026-05-19`.

## Globaler Erfolgs-Test

User importiert eine bereits in Projekt A analysierte Datei in Projekt B → Notify-Toast erscheint, alle Analysen sofort gruen ohne Re-Run. User verschiebt Source-Datei auf Festplatte → App findet Datei via SHA wieder, kein Daten-Verlust. SCHNITT-Audio-Subtab funktioniert unveraendert ueber Adapter.

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-021` on 2026-06-09.

- Original plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19`
- Original open work: Planning/review only until prerequisites and active selection.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.

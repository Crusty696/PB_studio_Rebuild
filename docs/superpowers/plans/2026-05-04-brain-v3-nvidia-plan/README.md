# PB Studio — Brain V3 (NVIDIA-Plan, finale Fassung)

> **Cross-Plan-Awareness — 3 neue Plaene 2026-05-19 (aktualisiert 2026-05-19):**
>
> Drei neue Plaene laufen parallel:
> 1. `VIDEO-PIPELINE-ENGINE-2026-05-19` (Plan A) — Video-Analyse mit eigener SigLIP-Instanz. **D-032 getrennte dev-brain vs app-brain bleibt eingehalten**; Brain V3 SigLIP unangetastet, VRAM-Coexistenz via read-only pynvml-Probe. Mirror `wiki/synthesis/plan-video-pipeline-engine-2026-05-19.md` · Decision `D-045`.
> 2. `LLM-BACKEND-PLATFORM-2026-05-19` (Plan B) — Embedded Ollama + HF + Auto-Selector. **Keine neuen Direkt-Calls** auf `services/ollama_service.py` / `ollama_client.py` einfuegen — werden in Plan-B Phase 41/42 durch `services/llm/` ersetzt. Falls Brain V3 neue LLM-Reasoner-Calls braucht: das geplante `services/llm/`-Interface nutzen sobald Tier 2 Phase 11 ready. Mirror `wiki/synthesis/plan-llm-backend-platform-2026-05-19.md` · Decision `D-044`.
> 3. `GLOBAL-STORAGE-PROVENANCE-2026-05-19` (Plan C) — Content-Address-Storage + Provenance. **Brain V3 bleibt isoliert**, kein Provenance-Crosswalk noetig. Mirror `wiki/synthesis/plan-global-storage-provenance-2026-05-19.md` · Decision `D-046`.
>
> **Konkret fuer Brain V3:** GPU-Pfad unangetastet. LLM-Pfad (falls noetig) ueber Plan B `services/llm/`.

**Datum:** 2026-05-04
**Ersetzt:** den frueheren Plan im Project-Cache
(`019dec39-5473-77a5-aad3-cad252d86d0c/docs/`)
**Hardware-Ziel:** **NVIDIA GTX 1060 6 GB Pascal (Compute 6.1)**
**Stack:** Python 3.10.20 / torch 1.12.1+cu113 / transformers 4.38.2 / sqlite-vec
**Frontend:** PySide6 6.11 (NICHT C# WPF wie urspruenglich geplant)
**Architektur-Standard (User-Direktive 2026-05-05, F1):** reine PySide6-
Desktop-Anwendung mit **in-process** Service-Aufrufen. Kein FastAPI-
Server, kein REST-Layer. Brain V3 wird ueber einen `BrainV3Service`-
Fassaden-Wrapper direkt aus PySide6-Slots aufgerufen.
**Trennung:** strikt isoliert von Brain V1 (`services/brain_service.py`) und
Brain V2 (`services/brain_v2/`) auf Code-Namespace- und DB-Pfad-Ebene.
V3-Code lebt in `services/brain_v3/`, V3-DBs in `%APPDATA%\PB_Studio\brain_v3\`.

**Refactor-Erlaubnis (User-Direktive 2026-05-05, F2):** V1 + V2 +
V0-App-Code (`ui/`, `services/pacing/`, `ui/controllers/import_media.py`
usw.) **duerfen umgebaut** werden. Pro Refactor an V1/V2 ist eine
Live-Verifikation der V1/V2-Funktion (Regression-Test, funktional
unveraendert) erforderlich.

---

## Status pro Phase

**Status-Spalten-Definition (User-Direktive 2026-05-05, F3 + F4):**
- **Code-Status**: pytest-Wahrheit (Module implementiert, Unit-Tests gruen)
- **App-Sync-Status**: ist die App so verdrahtet, dass dieses Phasen-
  Stueck wirklich aufgerufen wird, wenn der User die App im Echtbetrieb
  benutzt?
- **Live-verifiziert**: ist ein realer User-Workflow durchlaufen, der
  diesen Code-Pfad anlaeuft, mit Log-Auswertung gruen?

| Phase | Code-Status | App-Sync-Status | Live-verifiziert |
|---|---|---|---|
| 0 — GPU-Coexistenz-Spike | DONE | n/a (Spike, kein App-Pfad) | ✓ Lauf 20260503_115926 |
| 1 — Datenseite | code-complete (35 pytest) | **PENDING** (Mix-Import-Hook nicht geliefert) | ✗ pending App-Sync |
| 2 — Embedding-Pipeline | code-complete (70 pytest + Validation-Spike) | **PENDING** (Embedding-on-Import nicht verdrahtet) | ✗ pending App-Sync |
| 3 — Brain-Core (Beta-Bernoulli) | code-complete (112/112 pytest, Lauf 2026-05-05) | **PENDING** (Brain-Store-Health-Check beim App-Boot fehlt) | ✗ pending App-Sync |
| 4 — Pacing-Integration | TODO | TODO (parallel zu Code-Phase) | — |
| 5 — PySide6-UI | TODO | TODO | — |
| 6 — Härtung | TODO | TODO | — |

---

## Dokumente

| # | Datei | Inhalt |
|---|---|---|
| — | `README.md` | Diese Datei |
| 01 | `01_ARCHITECTURE.md` | System-Architektur, Datenfluss, V3-Isolation, PySide6-UI |
| 02 | `02_DECISIONS.md` | 24 finale Designentscheidungen (Original 20 + 4 NVIDIA-spezifisch) |
| 03 | `03_TECH_STACK.md` | cu113/transformers 4.38.2 + reale VRAM-Zahlen aus Spike |
| 04 | `04_DATA_MODEL.md` | SQLite-Schemas, V3-DB-Pfade, sqlite-vec, PRAGMAs, Migrations |
| 05 | `05_BRIDGE_AXES.md` | 17 Achsen + 6 Slots + 5 Backoff-Levels + Beta-Bernoulli |
| 06 | `06_PHASES.md` | 7 Phasen mit DoD pro Phase, kalibriert mit Spike-Daten |
| 07 | `07_RISKS.md` | Risiko-Matrix, R10 widerlegt, R16 entspannt, +R15/R16/R17 |
| 08 | `08_VERIFICATION.md` | Mapping frueherer verify-Skripte → NVIDIA-Spikes/Tests |
| 09 | `09_REVERIFICATION_2026-05-04.md` | 2. Verify-Welle — alle Behauptungen mit anderen Quellen re-bestätigt, 1 Präzisierung (R15 cu126→cu128) |
| 10 | `10_OPEN_POINTS_VALIDATION.md` | Open-Points-Spike — F-Measure 0.75, 500-Clip-Hochrechnung, HNSW-Eval, Demucs-Coexistenz, NVENC, PySide6-Boot |
| — | `phase_blueprints/` | 4 detaillierte Build-Anweisungen für Phase 3-6 (jeweils mit State-Banner 🟢/🔴) |

---

## Wichtige Real-Daten aus Phase-0-Spike (`outputs/spike_brain_v3_gpu/20260503_115926/`)

| Workload | Frueher angenommen | NVIDIA-Realität (gemessen) |
|---|---|---|
| Total VRAM | 16 GB (frueheres Setup) | GTX 1060 **6143.9 MB** |
| System-Reserve (Display + andere) | nicht beziffert | **~927 MB** |
| CUDA-Kontext-Init | nicht beziffert | **~310 MB** |
| Brain-nutzbarer VRAM | "wahrscheinlich 12 GB" | **~4.9 GB** |
| CLAP `laion/larger_clap_music` | 1.6–2.0 GB FP32 | **742 MB FP32** |
| SigLIP-2 `siglip2-base-patch16-384` (Vision) | "vermutlich OOM bei batch=8" | **355 MB load, 758 MB reserved bei batch=8** ✓ läuft |
| CLAP + SigLIP-2 koexistent | "wahrscheinlich nicht möglich" | **1178 MB reserved, läuft** ✓ |

---

## Validierte Plan-Korrekturen

- **#16 (SigLIP-2 Modell):** funktioniert mit transformers 4.38.2 mittels
  `AutoImageProcessor` (NICHT `AutoProcessor` — Tokenizer-Crash). KEIN
  transformers-Upgrade nötig. V1/V2-Stack bleibt unangetastet.
- **#17 (Inferenz-Pfad):** PyTorch 1.12.1+cu113 (nicht 2.5.1+cu124 wie
  ursprünglich im NVIDIA-Plan-Entwurf angenommen). `pb-studio` conda-env
  ist Migrations-Ziel.
- **#21 (Sequenzieller Lifecycle):** von "PFLICHT" auf "Defensive" runter —
  Coexistenz beider Modelle ist VRAM-mäßig möglich. Lock bleibt für
  Demucs/RAFT/NVENC.
- **#22 (FP32 Default):** bestätigt. FP16 nicht nötig auf 6 GB.
- **R10 (SigLIP-2 batch=8 sprengt 6 GB):** **WIDERLEGT** durch Spike-Messung.
- **R16 (Coexistenz aller GPU-Workloads):** TENDENZIELL ENTSPANNT
  (~3.5 GB Headroom mit beiden Brain-Modellen aktiv).

---

## Verbindlich aus User-Klärungen

- **Frueherer Plan im Project-Cache wird durch dieses Dokumentenset ERSETZT.**
- **Brain V1 + V2 (services/brain_service.py + services/brain_v2/) duerfen
  umgebaut werden** (User-Direktive 2026-05-05, F2). Pro Refactor ist
  eine Live-Verifikation der V1/V2-Funktion erforderlich. V3 bleibt
  als separater Namespace und mit getrennten DB-Pfaden — auch wenn
  V1/V2-Code refactored wird, kollidieren die Daten-Pfade nicht.
- **App-Eingriffspunkte für V3** (Pacing-Pipeline-Hook, Audio/Video-Import-Hooks,
  GPULockMiddleware-Erweiterung, neuer Brain-Tab, neuer in-process
  `BrainV3Service`-Fassaden-Wrapper) sind freigegeben für V3-Phase-4-Arbeit.
- **Vector-Store: sqlite-vec** (Engine-Konsistenz mit V3-SQLite-Stores).

---

## Aufwand-Schätzung

```text
Total:               4-7 Wochen netto
Phase 0:             DONE (live-verifiziert)
Phase 1:             code-complete (35 pytest), App-Sync pending
Phase 2:             code-complete (70 pytest + Validation-Spike), App-Sync pending
Phase 3:             code-complete (112/112 pytest, Lauf 2026-05-05), App-Sync pending
Phase 1-3 App-Sync (nachgeholt): 1-2 Tage  ← naechster Schritt vor Phase 4
Phase 4 (Pacing-Integration + in-process BrainV3Service): 3-5 Tage
Phase 5 (PySide6-UI: 4-Klick-Popup, Stats-Tab, Lern-Session-Dialog): 3-5 Tage
Phase 6 (Härtung: Backup, NVENC-Konflikt-Test, Lizenz-Attribution): laufend
```

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-010` on 2026-06-09.

- Original plan: `BRAIN-V3-NVIDIA-2026-05-04`
- Original open work: Phase 1-3 App-Sync/live pending, Pre-Phase-4 PacingConfig spike, NVENC parallel, real DJ-mix validation.
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.

---
plan: CONSULTING-TEAM-UND-LUECKEN-KONSOLIDIERUNG-2026-05-31
status: proposed-needs-user-selection
created: 2026-05-31
author: Claude (Opus 4.8)
governance: |
  Dieser Plan ist ein KONSOLIDIERUNGS-/FINDINGS-Plan. Er überschreibt NICHT den
  aktiven Plan (PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25). Keine Code-Änderung ist
  autorisiert, bis der User explizit einen Task auswählt. status: fixed setzt nur
  der User. Hartregel: nur explizit angewiesene Änderungen.
sources:
  - .codex/skills/consulting-team/ (Skill-Quelle)
  - ~/.claude/skills/consulting-team/ (Install-Ziel)
  - docs/superpowers/ACTIVE_PLAN.md
  - docs/superpowers/PLAN_REGISTRY.md
  - C:/Brain-Bug/projects/pb-studio/wiki/bugs/
  - C:/Brain-Bug/projects/pb-studio/log.md (Eintrag 2026-05-31 16:00)
---

# Konsolidierungs-Plan — consulting-team Skill + Lücken/Bugs (2026-05-31)

## Auftrag (User-Wortlaut)

> "übernim den consulting-team skill antigravity und codex installiere den auch
> bei dir, suche nach lücken und bugs und gleiche es mit obsidian ab und erstelle
> danach einen neuen plan mit allem drin"

Geklärt via Rückfrage: Skill existiert als Datei (in `.codex/skills/`), Ziel = **beides**
(Skill-Setup-Lücken **und** PB-Studio-Code-Lücken).

## Was erledigt (verifiziert)

1. **Skill installiert.** `consulting-team` von `C:/Users/David Lochmann/.codex/skills/consulting-team/`
   nach `C:/Users/David Lochmann/.claude/skills/consulting-team/` kopiert. In Claude-Code-Skill-Liste
   registriert (erscheint als triggerbar via `/consulting-team`, `/ct`).
   - Skill-Funktion: 7-Personen Anti-Sycophancy Multi-Persona-Review (Engagement Manager,
     Senior Partner, Analyst, Domain Expert, Risk Officer, Devil's Advocate, Synthesizer).
2. **Skill-Lücken-Scan.** Alle Skill-Files gelesen (SKILL.md, INSTALL.md, TESTS.md, 7 Personas,
   8 Frameworks, 3 References).
3. **PB-Studio-Scan.** Read-only via Explore-Subagent: Plan-Status, offene Bugs, Pipeline-Lücken.
4. **Obsidian-Abgleich.** Vault refresht, Log-Eintrag gesetzt (2026-05-31 16:00).

---

## TEIL A — consulting-team Skill: Lücken & Bugs

> **WICHTIG:** Diese Findings sind dokumentiert, **nicht** auto-gefixt (Hartregel:
> nur explizit angewiesene Änderungen). User muss Fix pro Punkt freigeben.

### A-1 🔴 GPU-Stack-Kontamination (Verstoß gegen GPU-Hartregel)

Der Skill behauptet an 5 Stellen, PB Studios GPU-Stack sei **AMD ROCm / RX 7800 XT**.
Projekt-Hartregel: **einzige zulässige GPU = NVIDIA GTX 1060 (CUDA 11.3)**. Der Domain Expert
würde damit systematisch falsches Stack-Reasoning liefern (z.B. ROCm-Kompatibilität prüfen,
wo CUDA gilt).

| Datei | Zeile | Ist | Soll |
|-------|-------|-----|------|
| `personas/domain-expert.md` | 20 | `GPU: AMD ROCm (Windows)` | `GPU: NVIDIA CUDA (GTX 1060, CUDA 11.3)` |
| `personas/domain-expert.md` | 27 | `... + AMD ROCm + ...` | `... + NVIDIA CUDA + ...` |
| `personas/domain-expert.md` | 56 | `Stack: PySide6 + Python + AMD ROCm` | `... + NVIDIA CUDA` |
| `references/caveman-mode.md` | 33 | Keep-Beispiel `"ROCm"` | `"CUDA"` |
| `frameworks/pre-mortem.md` | 43 | `asyncio + AMD-ROCm-Calls` | `asyncio + CUDA-Calls` |
| `TESTS.md` | 75 | `VRAM-Verbrauch auf AMD RX 7800 XT, ROCm-Kompatibilität` | `VRAM auf GTX 1060 (6 GB), CUDA-Kompatibilität` |

**Counter-Proposal:** Bulk-Replace `AMD ROCm`/`ROCm`/`RX 7800 XT` → CUDA/GTX 1060 in den 6 Stellen.
Pro-Datei-Freigabe nötig.

### A-2 🟡 Tote Skill-Referenzen

`SKILL.md:24` und `INSTALL.md:106` verweisen auf Skills `code-auditor` / `full-stack-auditor`
für reine Code-Tasks. Diese existieren **nicht** in `~/.claude/skills/`. User-Stack hat
stattdessen `bug-hunter`, `code-review-and-quality`, `pb-deep-auditor`, `pb-rebuild-*`.

**Counter-Proposal:** Referenzen auf vorhandene Skills umbiegen (z.B. `bug-hunter` /
`pb-deep-auditor`) oder entfernen.

### A-3 🟢 web_search Tool-Name

Analyst- + Domain-Expert-Persona referenzieren `web_search`. In Claude Code heißt das Tool
`WebSearch`. Modell versteht den Intent — kosmetisch. Optional angleichen.

### A-4 🟢 Plattform-Claim ungetestet

`SKILL.md` behauptet identisches Verhalten in "Claude Code / Desktop / Cowork". In dieser
Umgebung nur Claude Code verifiziert. Kein Bug — nur ungeprüfte Behauptung.

---

## TEIL B — PB Studio: Lücken & offene Bugs

### B-Status: Aktiver Plan
- **PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25** — `approved-for-implementation`
- Nächster offener Task laut ACTIVE_PLAN: **Task 55 = B-417** (Stale chat worker result refresh)

### B-1 🟠 62 Bugs `code-fix-pending-live-verification`
Statisch grün, **Live-Verifikation ausstehend**. Code-Edit ≠ Bug fixed (TOP RULE).

| Area | Bugs | Live-Status |
|------|------|-------------|
| 3 Project/Import | B-351, B-352 | Pywinauto-Smoke + SQLite-Magic offen |
| 5 Video-Pipeline | B-360, B-361, B-365, B-366, B-367 | komplett ungetestet |
| 6 Brain/Pacing | B-370, B-371, B-373, B-374, B-377 | ungetestet |
| 7 Schnitt-UI | B-384–B-391 | B-384/385/386 PASS; B-387/B-390 INCONCLUSIVE |
| 8 Export/Delivery | B-393–B-408 | Run 1: Export 10/10 + Batch 7/7 PASS; Feinarbeiten offen |
| 9 Chat/Agent | B-409–B-417 | komplett ungetestet (kritischer Pfad) |
| 10 Packaging | B-421–B-430 | Run 1: 7/7 PASS; Rest ungetestet |

### B-2 🟠 Ältere Open-Bugs außerhalb Fixplan
Nicht im aktiven Fixplan, weiter offen:
- **B-280** folder-import-empty-project → Fallback auf Project-1 (Datenverlust-Risiko)
- **B-283** harness open-project window verschwindet (Crash)
- **B-310** schnitt-workspace half-wired UX (Core-Wiring)
- **B-327** stem-separation m4a nicht erkannt
- **B-333/B-334** VRAM-Leak / GPU-Lock-aware dead
- **B-336** Model-Manager FP16-Pascal (GPU-Fallback)
- B-282, B-287–291 (UX/Progress-Feedback)

### B-3 🟢 Code-TODOs (niedrige Dichte → Code reif)
- `services/brain_v3/__init__.py:27-29` Phase 5 UI / Phase 6 Härtung
- `services/timeline_service.py:124` Deferred T4.10/D16 Lock-Handling
- `scripts/eval_shot_type_prompts.py:111` 50 Clips manuell labeln (User-Task)

### B-4 Geparkte Pläne (warten auf User-Aktivierung)
- BRAIN-V3-NVIDIA — `code-complete-live-pending` (App-Sync Phase 1-3)
- SCHNITT-WORKSPACE-REDESIGN — Phase 12 live verify pending
- SCHNITT-USABILITY-WIRING-REBUILD — Task 8 live verify pending
- AUDIO-V2-RECONCILE — `approved-for-planning` (blockiert bis Reconciliation)
- VIDEO-PIPELINE-ENGINE / COMFYUI-REFERENCE-AUDIT — approved-for-implementation

---

## TEIL C — Obsidian-Abgleich (Reconciliation)

- **Konsistent:** Vault `wiki/bugs/` Bug-States == Subagent-Scan == ACTIVE_PLAN.md (Stand 2026-05-27).
- **Neu (war nicht im Vault):** consulting-team Skill-Install + die 6 Skill-Findings A-1..A-4.
  → Per Log-Eintrag 2026-05-31 16:00 nachgezogen.
- **Schlüssel-Diskrepanz:** Skill (Teil A-1) glaubt GPU = AMD ROCm. Vault + Code + GPU-Hartregel =
  NVIDIA GTX 1060 / CUDA. Skill-Realität widerspricht Vault-Wahrheit → A-1 ist Pflicht-Fix bevor
  der Skill für PB-Studio-Reviews genutzt wird.

---

## Empfohlene Reihenfolge (Vorschlag — User wählt)

1. **A-1 fixen** (GPU-Kontamination) — bevor consulting-team für PB-Studio-Themen läuft.
2. **A-2 fixen** (tote Skill-Refs) — billig.
3. **B-1 Live-Verify** weiterführen: kritischer Pfad **Area 9 Chat (B-409–B-417)** + Rest Area 8.
   Via `pb-gui-tester` / `pb-functional-tester` mit echtem Test-Datensatz.
4. **B-2 ältere Open-Bugs** triagieren (B-280/B-283 = Datenverlust/Crash zuerst).
5. Geparkte Pläne (Teil B-4) nur auf explizite User-Aktivierung.

## Offene Entscheidungen (User)

- [ ] Skill-Fixes A-1/A-2 freigeben? (pro Datei oder Bulk)
- [ ] Welcher Strang zuerst — Skill-Hardening (A) oder PB-Live-Verify (B)?
- [ ] Soll dieser Plan in PLAN_REGISTRY.md eingetragen werden, oder bleibt er reines Findings-Dokument?

---

## Umsetzungsstand 2026-05-31 (User-Freigabe "alles")

| Item | Status | Beleg |
|------|--------|-------|
| A-1 GPU-Kontamination (6 Stellen) | DONE | ~/.claude + .codex gesynct, grep CLEAN |
| A-2 tote Skill-Refs (2 Stellen) | DONE | → bug-hunter/pb-deep-auditor |
| B-439 delete_all_media Datenverlust | CODE-FIX + TESTS GRÜN | ingest_service.py:537 Resolver-Swap; test_b439 grün; B-280-Suite 21 passed |
| B-440 RAFT /8-Crash | CODE-FIX + TESTS GRÜN | raft_motion_service.py Replicate-Pad; 3 unit + 1 live-RAFT (echtes Modell, GTX1060) grün |
| e2e-Blindspot non-/8 | DONE | test_video_pipeline_e2e_live.py::test_raft_real_model_non_divisible_by_8 |
| PLAN_REGISTRY-Eintrag | DONE | Zeile CONSULTING-TEAM-UND-LUECKEN-KONSOLIDIERUNG-2026-05-31 |
| B-333 Live-VRAM | KEIN LEAK reproduziert | peak 1847MB < 6144; SigLIP ModelManager-resident by design |

**Offen (status:fixed nur User):** App-Workflow-Live-Verify B-439 (Sammlung bereinigen ohne aktives Projekt) + B-440 (RAFT in App-verdrahteter Pipeline — video_pipeline noch nicht App-integriert).

**Geänderte Projekt-Dateien:** services/ingest_service.py, services/video_pipeline/stages/raft_motion_service.py, tests/test_services/test_b440_raft_divisible_by_8.py (neu), tests/test_services/test_cycle12_critical_batch.py, tests/test_services/test_video_pipeline_e2e_live.py, docs/superpowers/PLAN_REGISTRY.md, docs/superpowers/plans/2026-05-31-...md (neu).

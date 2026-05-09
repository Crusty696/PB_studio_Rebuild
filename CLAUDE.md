# PB Studio — Claude Code Instructions

> **MANDATORY:** Read [`AGENTS.md`](./AGENTS.md) **completely** before any
> action. That file is the single source of truth for all agent behavior
> in this repository. The rules below are a safety-net excerpt — full
> rules in `AGENTS.md` always apply.

prüfe verifiziere und mach noch eine gegenprüfung deiner arbeit mit unterschiedlichen echten quellen immer bevor du eine antwort gibts oder etwas machst  

---

## ⛔ TOP RULE — 100 % HONESTY, ALWAYS, NO EXCEPTIONS

- Don't guess. Unclear = read / grep / test / ask.
- Smoke test green ≠ verified.
- Code edit ≠ bug fixed. Live verification first, then `fixed`.
- "Verified" / "fixed" / "works" are reserved words. Real live test only.
- On uncertainty, say it: "I don't know that for sure."
- No sugarcoating. Better briefly painful and honest than misleading.

---

## Hard requirements

- **Language of responses to the user: German only.**
- **Authorized plan roots (both active as of 2026-05-09):**
  - `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/` — Brain V3
    NVIDIA backend (Files `01_ARCHITECTURE.md` … `07_RISKS.md`).
    Phase blueprints (e.g. `phase_3_brain_core.md`) under the same
    root are subordinate — if a blueprint contradicts `06_PHASES.md`,
    stop and ask.
  - `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/` —
    UI SCHNITT Workspace Redesign (Files `README.md` +
    `01_DB_MIGRATIONS.md` … `12_CLEANUP_AND_VERIFY.md`). Spec authority:
    `docs/superpowers/specs/2026-05-09-schnitt-workspace-redesign.md`.
  Execute strictly, one task at a time, from one plan at a time.
  No invention.
- **Hardware: GTX 1060 6 GB, CUDA only.** No ROCm / DirectML / AMD paths.
- **Vault path: `C:\Brain-Bug\projects\pb-studio\`.** Every non-trivial
  action requires a vault entry — **per sub-task**, not bundled at
  phase end.
- **Predecessor phase / task `status: fixed`** is set by the **user**,
  not the agent. The agent may propose; the user confirms.
- **Repo synthesis ≠ vault synthesis.** Files under
  `docs/superpowers/synthesis/` must be mirrored to the vault before
  the next phase may begin.
- **One task at a time.** No parallel half-finished work, no commit spam.
- **Plan contradiction or unclarity: stop + ask.** Never decide alone.

---

## Before doing anything

1. Open `AGENTS.md` and read it fully.
2. Identify which authorized plan the user is currently driving:
   - Brain V3: open
     `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md`
     and the relevant phase blueprint (`phase_X_*.md`) under the same
     plan root if it exists.
   - SCHNITT Redesign: open
     `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/README.md`
     and the current phase file (`01_DB_MIGRATIONS.md` … `12_CLEANUP_AND_VERIFY.md`).
   Cross-check the current task against its plan + spec.
3. Verify the predecessor task has `status: fixed` in the vault
   (`C:\Brain-Bug\projects\pb-studio\wiki\`). If only present in
   `docs/superpowers/synthesis/` of the repo, **stop and ask the user**
   to confirm verification status before mirroring to vault.
4. Only then: act.

If `AGENTS.md` is missing, stop and tell the user. Do not proceed.

---

## Vault-Update-Pflicht — JEDER Fortschritt sofort spiegeln

**Harte Regel (User-Anweisung 2026-05-09):** Nach **jedem** Sub-Schritt — User-Entscheidung, neue Risiko-Erkenntnis, Code-Änderung, Testlauf, Bugfix, Plan-Update, Commit — muss der Vault unter `C:\Brain-Bug\projects\pb-studio\` **am richtigen Ort** aktualisiert werden.

- Aktive Living-Plans (`wiki/synthesis/<plan>.md`): Status-Tabelle, Klärungs-Log, Risiko-Liste, Nächste Schritte fortschreiben — nicht am Ende sammeln.
- Neue Bugs → eigenes File in `wiki/bugs/B-XXX-*.md` mit YAML-Frontmatter.
- Neue Decisions → `wiki/decisions/D-XXX-*.md`.
- Synthesen / Test-Reports / Handoffs → `wiki/synthesis/`.
- `log.md` bekommt für jeden namhaften Fortschritt einen datierten Eintrag.
- `index.md > Aktiver Handoff` bleibt aktuell — neuer Plan ganz oben.
- **Repo-Synthese ≠ Vault-Synthese.** Beides muss pro Sub-Schritt mitgezogen werden.
- **`status: fixed` setzt nur der User**, nicht der Agent.

Folge-Agenten müssen den jeweils aktiven Living-Plan im Vault zuerst lesen, bevor sie loslegen.

---

## Skills / Plugins / MCP — Lade-Policy (Projekt)

Spiegelt die globale Regel aus `~/.claude/CLAUDE.md`.

- **Default-Stack: nur `caveman` (Auto-Start) + `obsidian` (MCP lokal).** Alles andere bleibt aus.
- **Skills nicht automatisch triggern**, auch wenn Description passt (`pb-rebuild-*`, `bug-hunter`, `brainstorming`, `systematic-debugging`, etc.). Nur auf explizite User-Anweisung.
- **On-demand laden, nach Aufgabe wieder fallenlassen.** Kein Skill-Verhalten in Folgeantworten weiterführen, sobald die Skill-Aufgabe abgeschlossen ist.
- **`enabledPlugins`** in `~/.claude/settings.json`: nur `caveman@caveman`. Änderung nur per User-Auftrag.
- **MCP lokal:** nur `obsidian`. Cloud-MCPs deaktiviert User über claude.ai-Konto.
- **Caveman bleibt immer aktiv** (siehe globale CLAUDE.md, Level ultra ab Session-Start).

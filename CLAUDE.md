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
- **Plan-Governance:** `AGENTS.md` is source of truth. Current plan
  authority comes from `docs/superpowers/PLAN_REGISTRY.md` plus
  `docs/superpowers/ACTIVE_PLAN.md`, not from a hardcoded plan list.
  Execute strictly, one task at a time, from one selected plan at a time.
  No invention.
- **HARTREGEL — Vault-Update PRO Sub-Schritt mit Zeitstempel (User-Anweisung 2026-05-11):**
  Nach JEDEM Sub-Schritt (Code-Edit, Setting, destruktive Aktion, App-Start/-Crash,
  neuer Bug, Decision, Live-Verify) sofort log.md im Vault aktualisieren. Format:
  `## YYYY-MM-DD HH:MM <kategorie> | <kurz>` + 1-3 Zeilen Detail + Pfade. Max. 1
  Konversations-Turn ungeloggt. Vault = single source of truth — wenn dort etwas
  fehlt, kann Agent nicht zurueck-recherchieren und User muss sich wiederholen.
- **HARTREGEL — nur explizit angewiesene Aenderungen (User-Anweisung 2026-05-11):**
  Der Agent darf ausschliesslich das machen, was der User explizit verlangt hat.
  Keine eigenmaechtigen Code-Aenderungen, keine "Verbesserungen", keine
  "While-I'm-here"-Fixes, keine Bulk-Replaces ohne pro-Datei-User-OK. Bei
  Unklarheit STOP + ASK. Bestehende funktionierende Funktionen niemals ohne
  explizite User-Anweisung modifizieren. Git + Log konsultieren statt raten.
- **HARTREGEL GPU (User-Anweisung 2026-05-11):** Einzige zulaessige GPU
  ist die **NVIDIA GeForce GTX 1060 (6 GB VRAM, CUDA 11.3 /
  Treiber 546.33)**.
  - **Stack-Realitaet (verifiziert 2026-06-12):** Treiber 546.33
    (nvidia-smi: CUDA 12.3 runtime-faehig), conda-env `pb-studio` mit
    Python 3.10.20, torch 1.12.1+cu113 (CUDA verfuegbar), numpy 1.26.4,
    onnxruntime-gpu 1.18.1. Kanonische Install-Quelle: `environment.yml`
    + `requirements-py310-cu113.txt`. Aeltere Doku mit Treiber 461.40
    oder torch 2.x ist historisch bzw. Fremd-Maschine.
  - PyTorch: ausschliesslich `torch.device("cuda:0")`.
  - FFmpeg: ausschliesslich `-hwaccel cuda`, `h264_nvenc`, `hevc_nvenc`.
  - OpenCV: falls cuda-Build, `cv2.cuda.setDevice(0)`.
  - Wenn eine Library kein CUDA-Backend bietet → **CPU**. Niemals einen
    anderen GPU-Backend installieren oder importieren.
  - Die interne Intel-iGPU wird nicht angesprochen — weder Inferenz,
    noch Encode/Decode, noch Filter-Beschleunigung.
  - Bei Verstoss/Unsicherheit: stoppen + User fragen.
- **Vault path: `C:\Brain-Bug\projects\pb-studio\`.** Every non-trivial
  action requires a vault entry — **per sub-task**, not bundled at
  phase end.
- **Obsidian Vault Brain tooling:** use
  `C:\Users\David Lochmann\plugins\obsidian-vault-brain\skills\obsidian-vault-brain\SKILL.md`
  and `C:\Users\David Lochmann\plugins\obsidian-vault-brain\scripts\vault_brain.py`
  for vault refresh/search/get/append. Refresh index before vault-state
  answers; read only directly relevant notes.
- **Predecessor phase / task `status: fixed`** is set by the **user**,
  not the agent. The agent may propose; the user confirms.
- **Repo synthesis ≠ vault synthesis.** Files under
  `docs/superpowers/synthesis/` must be mirrored to the vault before
  the next phase may begin.
- **One task at a time.** No parallel half-finished work, no commit spam.
- **Plan contradiction or unclarity: stop + ask.** Never decide alone.
- **Worktree hygiene:** before any action run `git status --short --branch`.
  Dirty state is not allowed as normal handoff. Unknown dirty changes mean
  stop, report paths, ask user. Multi-agent work requires separate Git
  worktree + separate branch per agent/task. End every handoff clean, stashed
  with name, or explicitly user-approved dirty and documented.

---

## Before doing anything

1. Open `AGENTS.md` and read it fully.
2. Run `powershell -ExecutionPolicy Bypass -File tools\agent_start.ps1`.
   If it reports `BLOCKED`, stop and follow its instruction.
3. Open `docs/superpowers/PLAN_REGISTRY.md` and
   `docs/superpowers/ACTIVE_PLAN.md`.
4. Identify the one selected active plan. If `ACTIVE_PLAN.md` says
   `blocked-needs-user-selection`, do not start app-code work; ask the
   user to choose one plan unless the current request is explicitly
   governance/plan-selection work.
5. Cross-check the current task against the selected plan, its Registry
   row, its Decision file, and its Vault living-plan mirror.
6. Verify the predecessor task has `status: fixed` in the vault
   (`C:\Brain-Bug\projects\pb-studio\wiki\`). If only present in
   `docs/superpowers/synthesis/` of the repo, **stop and ask the user**
   to confirm verification status before mirroring to vault.
7. Only then: act.
8. If worktree is dirty before task start, resolve tracking/handoff first:
   commit, named stash, or user decision. Do not build on unknown changes.

Before ending or switching agents, run
`powershell -ExecutionPolicy Bypass -File tools\agent_handoff.ps1` and resolve
dirty/unpushed state before handoff.

If `AGENTS.md` is missing, stop and tell the user. Do not proceed.

## How to choose current task

Use the same sequence as `AGENTS.md`: Registry -> Active Plan -> selected
repo plan -> Vault mirror -> Decision file -> next unambiguous task. If
`ACTIVE_PLAN.md` is `blocked-needs-user-selection`, ask for one plan before
product/app-code work.

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

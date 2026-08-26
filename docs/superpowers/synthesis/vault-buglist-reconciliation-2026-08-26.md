# Vault-Buglisten-Abgleich 2026-08-26

Status: documentation-complete
Plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
Scope: Vault-Frontmatter gegen aktuellen App-Code, fokussierte Belegakten und
Git-Historie; keine App-Code-Aenderung, kein autonomes `fixed`.

## Ergebnis

- Kanonische aktuelle Statussicht erneuert:
  `wiki/synthesis/stability-status-current.md` im PB-Studio-Vault.
- 12 `open`, 0 `in_progress`, 1 `partial-fix`, 45
  `code-fix-pending-live-verification`, 26 `agent-fixed-await-user`, 13
  `fixed-unverified`, 6 `deferred`, 1
  `agent-complete-await-user-marker`.
- Aktive naechste Produkttask bleibt B-901.
- B-861 bis B-864 gehoeren zum pausierten Auditplan, nicht zur aktiven
  Produkttask.
- B-865 war die einzige belegte stale Arbeitsmarkierung: Commit `9f49429`,
  aktueller `current_project_path`-Guard, 11 dokumentierte Fokus-PASS und
  isolierter App-Neustart. Korrigiert auf `agent-fixed-await-user`.
- B-618 bleibt ehrlich `partial-fix`; urspruengliche Crashursache unbekannt.
- B-832/B-867 bleiben Produktentscheidungen. B-888/B-893/B-894/B-895
  bleiben ohne Live-Repro/Fix offen. B-870 bleibt beobachteter Crash ohne
  Root Cause. Keine dieser Grenzen wurde umgedeutet.

## Aktuelle Codebelege

- B-832: Vibe-Zweig liegt weiter hinter dem erfolgreichen Scoring-Return in
  `services/pacing_edit_helpers.py`.
- B-865: `ui/controllers/project_management.py` nutzt
  `ProjectManager.current_project_path`; Fokusvertrag in
  `tests/ui/test_b773_auto_resume_last_project.py` deckt Boot-DB-Row ab.
- B-888: Kandidatensortierung nutzt weiterhin nur Score als Sortierschluessel.
- B-893: Reranker faellt weiterhin auf Motion `medium` zurueck.
- B-894: Pipeline persistiert `brain_v3_scores`; No-Signal-Achsen werden dort
  nicht mitpersistiert.
- B-901: bleibt laut Active Plan naechste Task; in diesem Audit nicht gefixt.

## Verifikation

- Frontmatter aller `wiki/bugs/B-*.md` read-only inventarisiert.
- Betroffene Symbole im aktuellen App-/Testcode mit `rg` revalidiert.
- Commit `9f49429` mit `git show` belegt.
- Keine Testausfuehrung: reine Status-/Dokumentationskorrektur; vorhandene
  Live-/Testbelege wurden nicht als neue Verifikation verkauft.

## Geaenderte Authority-Dateien

- Vault `wiki/bugs/B-865-auto-resume-boot-db-row-blockiert-recent.md`
- Vault `wiki/synthesis/stability-status-current.md`

# PB-Studio-Rebuild — CLAUDE.md

Diese Datei delegiert vollständig an die `AGENTS.md` und das zentrale Brain-Bug Wiki.

## 🧠 Zentrales Wiki (Single Source of Truth)

Das Gehirn für dieses Projekt liegt im Brain-Bug Vault:
**Pfad:** `C:\Brain-Bug\projects\pb-studio\`

Lies die `AGENTS.md` in diesem Verzeichnis (`C:\Brain-Bug\AGENTS.md`) für die
vollständigen Anweisungen und Pfade zum Wiki.

## 📝 Vault-Pflege ist Pflicht (nicht optional)

Jede nicht-triviale Tätigkeit in diesem Projekt hinterlässt einen Eintrag im
Vault — **vor dem Chat-Abschluss**, nicht danach:

| Aktion | Vault-Eintrag |
|---|---|
| Bug gefixt | `wiki/bugs/B-XXX-<slug>.md` auf `status: fixed` + `log.md` Eintrag |
| Neuer Bug gefunden | `wiki/bugs/B-XXX-<slug>.md` anlegen (letzte ID per `ls`) |
| Architektur-Entscheidung | `wiki/decisions/D-XXX-<slug>.md` |
| Deep-Analysis einer Datei | `wiki/code/modules/<slug>.md` + `log.md` |
| Funktionstest (real data / E2E) | `wiki/synthesis/functional-test-<scope>-YYYY-MM-DD.md` |
| Commit mit Produkt-Change | `log.md` Eintrag mit Commit-Hash |
| Sprint-Ende / Orchestrator-Cycle | `wiki/synthesis/<titel>-YYYY-MM-DD.md` |

**Regel:** Kein Vault-Eintrag = Task nicht abgeschlossen.

Die spezialisierten pb-* Skills (pb-commander, pb-rebuild-master, pb-rebuild-fixer,
pb-rebuild-tester, pb-rebuild-orchestrator, pb-functional-tester) haben ihre
konkreten Vault-Pflichten jeweils am Ende ihrer `SKILL.md`.

Ein `SessionStart`-Hook (`.claude/hooks/vault_check.sh`) warnt, wenn Commits
ohne Vault-Update aufgelaufen sind. Die Warnung ist **nicht blockierend** —
der Agent ist verantwortlich, sie ernst zu nehmen.

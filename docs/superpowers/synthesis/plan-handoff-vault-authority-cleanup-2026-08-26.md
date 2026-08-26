# Plan-, Handoff- und Vault-Authority-Bereinigung — 2026-08-26

Status: documentation-complete
Plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
Scope: Governance/Dokumentation; kein Produktcode-Fix

## Ergebnis

- Kanonischer `docs/superpowers/plans/`-Ordner enthält nur aktiven Masterplan
  und ausdrücklich pausierten Auditplan.
- Fixed-/Legacy-Pläne in `archive/completed-*`, superseded Pläne in
  `archive/superseded-plans/`; Archiv global als `NOT AUTHORITY` definiert.
- 32 historische Planwurzeln in 80 Repo-/Vault-Dateien auf vorhandene
  Archivziele umgestellt; Windows- und Forward-Slash-Pfade berücksichtigt.
- 193 eindeutige Archivpfad-Tokens geprüft: 0 fehlende Ziele.
- Historische, nie erzeugte Soll-Artefakte als solche beschrieben, ohne
  falsche Dateilinks.
- Pausierter Auditplan intern widerspruchsfrei auf `paused` gesetzt.
- Aktueller Repo-Handoff neu aufgebaut; drei alte Repo-Handoffs vollständig
  archiviert und sichtbar entwertet.
- 14 stale Vault-Synthese-/Planmirror-Status, drei alte Vault-Handoffs und
  fünf alte `Current Next Task`-Überschriften entwertet.
- Vault-Index auf einen aktuellen Handoff reduziert; kompletter Altverlauf
  verlustfrei in `handoff-archiv.md` bewahrt.
- Buglisten-Abgleich: 12 `open`, 0 `in_progress`, 1 `partial-fix`, 45
  pending-live, 26 agent-fixed, 13 fixed-unverified, 6 deferred. B-865 auf
  `agent-fixed-await-user` korrigiert; kein `fixed` gesetzt.

## Verifikation

- `tests/test_docs/test_plan_governance.py -q`: 3 passed in 0.13 s.
- Planordner: 2 Dateien, exakt aktiv + pausiert.
- Exakte Planpfadziele: 0 fehlend.
- Archivpfadziele: 0 fehlend.
- Repo-Archiv: 0 rohe aktive Status-/`Current Next Task`-Marker.
- Vault-Synthesen: einziger laufender Marker ist aktiver Masterplan-Mirror.
- `git diff --check`: keine Whitespace-Fehler; drei CRLF→LF-Hinweise.
- Keine App-, UI-, GPU- oder Gesamttests: für reinen Governance-Scope nicht
  ausgeführt.

## Ehrliche Grenze

Historische Dokumente enthalten weiterhin damalige Begriffe und Aufgaben als
Geschichte. Banner, Archivstatus und Authority-Reihenfolge entwerten sie.
Absolute Garantie gegen jede künftige Fehlinterpretation ist nicht möglich;
alle in diesem Audit identifizierten vermeidbaren Authority- und Linkquellen
sind bereinigt.

## Nächste autorisierte Produkttask

`STAB-5 / B-901 Update-Controls im Defaultpfad erreichbar machen und Repo-Default korrigieren`.

# PB Studio Active Plan

status: blocked-needs-user-selection
active_plan_id: none
next_allowed_task: none
updated: 2026-05-20

## Meaning

Es ist absichtlich kein Produkt-/Feature-Plan aktiv. Nach der Governance-Vereinheitlichung muss der User genau einen Plan aus `docs/superpowers/PLAN_REGISTRY.md` auswaehlen, bevor ein Agent Code-Arbeit an App-Funktionen startet.

## Agent Behavior

- Wenn `status: blocked-needs-user-selection`: keine App-Code-Arbeit starten.
- Erlaubt bleibt nur Read-only-Analyse, Plan-Auswahl-Beratung oder explizit vom User beauftragte Governance-/Dokumentationsarbeit.
- Sobald User einen Plan waehlt, diese Datei aktualisieren:
  - `status: active`
  - `active_plan_id: <PLAN-ID>`
  - `next_allowed_task: <exakte Task aus Plan/Vault>`
  - `updated: <YYYY-MM-DD>`

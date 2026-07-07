# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-AUDIT-FIXPLAN-2026-07-07
repo_plan: docs/superpowers/plans/2026-07-07-audit-fixplan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-audit-fixplan-2026-07-07.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-064-audit-fixplan-und-vollintegration.md
updated: 2026-07-07

## Why This Plan Is Active

User-Auftrag 2026-07-07 (Chat-Session): "mach diesen plan mit allen skills
subagenten und tools ... arbeite parallel und autonom" — explizite Freigabe
fuer den Audit-Fixplan. Vorgaenger `PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN`
ist `code-complete-live-pending` mit NUR-User-Aktion offen (Sichtung +
`fixed`-Marker) — keine Agent-Arbeit blockiert.

Wichtig: R3-Freigabe-Matrix des Plans bleibt bindend. A1/A2/B5/B6 duerfen
erst NACH SCHNITT-`fixed` durch den User laufen. Sofort erlaubt: A0, A3,
danach B1-B4, B7.

Verbindlicher Nachfolger nach Abschluss+Test:
`PB-STUDIO-NEUBAUTEN-VOLLINTEGRATION-2026-07-07` (hohe Prioritaet, kein
anderer Plan dazwischen). Danach Rueckkehr-Reihenfolge zu OTK-021 gemaess
User-Entscheidung zu gegebener Zeit.

## Current Next Task

```text
Phase SOFORT: A0 E2E-Render-Smoke-Test (Testset Solo_Natur + Crusty-Mix)
-> A3 DB-010-Nachruest-Migration (P2 praeventiv) -> B1-B4, B7 (Repro-Gate
R1 pro Finding). A1/A2/B5/B6 warten auf SCHNITT-`fixed` durch User.
```

## Agent Behavior

- Pflicht-Regeln R1-R4 aus dem Plan sind bindend (Repro-Gate, Tracks,
  Freigabe-Matrix, Paket-Kopplung).
- GPU-Regel unveraendert (GTX 1060 / cuda:0 / NVENC; sonst CPU).
- Vault-Eintrag pro Sub-Schritt; ein Commit pro Task; `fixed` nur User.
- Track C/D: KEIN Code, keine Loeschungen unter diesem Plan.

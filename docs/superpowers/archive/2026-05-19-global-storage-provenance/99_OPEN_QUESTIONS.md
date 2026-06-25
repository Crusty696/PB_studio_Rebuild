# 99 — Offene Klaerungs-Punkte

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19`

## Architektur

- [ ] Junction vs Symlink auf Windows — Junctions ohne Admin, Symlinks brauchen Admin. Standardmaessig Junction?
- [ ] Migration physisch (Verschieben) vs Junction-only — Default ist Junction. Physisch-Migration als User-getriggert?
- [ ] V2 P2-9 Implementation: muss V2 Provenance-Aware werden ODER reicht es dass Plan-C-Migration nach V2-Run laeuft?

## DB

- [ ] `analysis_jobs.params_hash` Berechnung: Dict-stable-Hash (json sorted + sha256)?
- [ ] DB-Schema-Version-Migration zwischen App-Updates

## UI

- [ ] Cross-Project-Reuse-Toast Cooldown (z. B. 1× pro Session)?
- [ ] Storage-Browser Performance bei 10000+ Files?

## Cross-Plan

- [ ] Plan A + Plan B abwarten oder parallel implementieren?
- [ ] V2-Live-Verify durch User: vor Plan-C-Start verpflichtend?

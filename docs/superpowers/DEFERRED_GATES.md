# PB Studio Deferred Gates

Purpose: hard reminder list for user-approved deferrals. A deferred gate is not
fixed and not forgotten. Before release/fixed status, each gate must be either
live-verified or explicitly re-decided by the user.

## Active Deferred Gates

| gate_id | source_task | status | must_happen_later | reason | evidence |
|---|---|---|---|---|---|
| DG-001 | OTK-019 Video Pipeline Engine | h22-na-PLUS-evidence-lost | **H2.2 = NICHT ANWENDBAR (User 2026-06-18, B-542):** kein QMediaPlayer/flüssiges Playback. **⛔ EVIDENZ-VERLUST (Audit 2026-06-18):** Die zuvor als „grün" geführten Heavy-Punkte **H1, H1.3, H2.1-alt, H3, G.\*** sind NICHT überprüfbar — alle Belege gelöscht (0/6 vorhanden). Status dieser Punkte = `unverifiable-evidence-lost`, NICHT grün. Vor echtem Release neu fahren + Belege committen. **H2.1-NEU (18.06.)** ist echt (`h264_nvenc`-Proxy existiert), liegt in `storage/H2.2-Playback/storage/proxies/` (NICHT im leeren `test-report/dg001-h22-retry/`). | User deferred 2026-06-14; H2.2 struck 2026-06-18. **Nachverifizierung 2026-06-18 (Punkt 5, echte E2E-Läufe, KEIN Seed):** B-539 Schreibpfad+Cross-Reuse, Tier 31 Adapter, Block-1 Migration-30/Caller-40 jetzt ECHT verifiziert (echtes Demucs, model="Demucs", open_project-Junction). env STABIL (90s, kein Crash/Leak). Neuer Bug **B-547** (Storage-Browser GUI-Delete löscht Dateien nicht). Backup-70+Disk-Budget-71 = toter Code. B-539-Funktion echt, Robustheit B-543..B-546 offen. Siehe `wiki/synthesis/verifikations-gesamtaudit-2026-06-18.md`. | **GELÖSCHT/unauffindbar:** `outputs/h1_scale.log`, `C:\PB_Studio_H1_3\*`, `test-report/e2e-live-acceptance-20260615/*`, `test-report/e2e-h3-concurrency-20260615`. **Vorhanden:** `storage/H2.2-Playback/storage/proxies/*_edit_proxy.mp4` (H2.1-neu); `wiki/synthesis/verifikations-gesamtaudit-2026-06-18.md`; B-541, B-542, B-543..B-546 |

## Rules

- Deferred gate does not permit `fixed`.
- Deferred gate must be named in any downstream task that depends on it.
- If downstream implementation touches the deferred area, re-check the gate.
- Before release, every active deferred gate needs user decision or live proof.

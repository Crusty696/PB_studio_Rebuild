# PB Studio Deferred Gates

Purpose: hard reminder list for user-approved deferrals. A deferred gate is not
fixed and not forgotten. Before release/fixed status, each gate must be either
live-verified or explicitly re-decided by the user.

## Active Deferred Gates

| gate_id | source_task | status | must_happen_later | reason | evidence |
|---|---|---|---|---|---|
| DG-001 | OTK-019 Video Pipeline Engine | h3-reverified-PLUS-evidence-lost | **H2.2 = NICHT ANWENDBAR (User 2026-06-18, B-542):** kein QMediaPlayer/flüssiges Playback. **⛔ EVIDENZ-VERLUST (Audit 2026-06-18):** Die zuvor als „grün" geführten Heavy-Punkte **H1, H1.3, H2.1-alt, G.\*** sind NICHT überprüfbar — Belege gelöscht. Status dieser Punkte = `unverifiable-evidence-lost`, NICHT grün. **H3-NEU (23.06.) PASS:** finaler Run `20260623-050437`, echter paralleler GTX1060-Lauf mit `htdemucs_ft` (`reused=False`, vier Stems, Audio 8/8) und SigLIP+RAFT (Video 7/7), beide Threads beendet, kein Deadlock/OOM, Peak 4534/6144 MiB, Wall 36.375 s. Versionierter Beleg: `docs/superpowers/synthesis/dg001-h3-concurrency-live-2026-06-23.md`. **H2.1-NEU (18.06.)** ist echt (`h264_nvenc`-Proxy existiert), liegt in `storage/H2.2-Playback/storage/proxies/`. | User deferred 2026-06-14; H2.2 struck 2026-06-18. **Nachverifizierung 2026-06-18:** B-539 Schreibpfad+Cross-Reuse, Tier 31 Adapter, Block-1 Migration-30/Caller-40 echt verifiziert. **H3 2026-06-23 neu verifiziert.** B-547 offen; Backup-70+Disk-Budget-71 bleiben toter Code. | **Neu vorhanden/versioniert:** `scripts/diag/verify_dg001_h3_concurrency.py`, `docs/superpowers/synthesis/dg001-h3-concurrency-live-2026-06-23.md`. **Weiter verloren/offen:** H1/H1.3/G.* Altbelege. **Vorhanden:** `storage/H2.2-Playback/storage/proxies/*_edit_proxy.mp4`; `wiki/synthesis/verifikations-gesamtaudit-2026-06-18.md`; B-541, B-542, B-543..B-546 |

## Rules

- Deferred gate does not permit `fixed`.
- Deferred gate must be named in any downstream task that depends on it.
- If downstream implementation touches the deferred area, re-check the gate.
- Before release, every active deferred gate needs user decision or live proof.

# PB Studio Deferred Gates

Purpose: hard reminder list for user-approved deferrals. A deferred gate is not
fixed and not forgotten. Before release/fixed status, each gate must be either
live-verified or explicitly re-decided by the user.

## Active Deferred Gates

| gate_id | source_task | status | must_happen_later | reason | evidence |
|---|---|---|---|---|---|
| DG-001 | OTK-019 Video Pipeline Engine | resolved-h22-not-applicable | **H2.2 = NICHT ANWENDBAR (User-Entscheidung 2026-06-18, B-542):** App hat keinen QMediaPlayer / kein flüssiges Video-Playback (nur ffmpeg-Frame-Vorschau ~10 fps) — „ruckelfrei"-Verdikt nicht prüfbar, als Gate-Kriterium gestrichen. Übrige Punkte bereits grün: H1 62-min scale (`H1_EXIT 0`), H1.3 4h pipeline (`failed_count=0`), **H2.1 NVENC export (re-verifiziert 2026-06-18 mit bin/ffmpeg 6.1.1 nach B-541-Fix)**, H3 concurrent Demucs+Video, SCHNITT GUI widgets. | User chose 2026-06-14 to defer the heavy gate; H1.3 done 2026-06-15. H2.2 was found non-applicable 2026-06-18 (no QMediaPlayer in app) and struck by user. **Honesty-Vorbehalt:** mehrere GUI-Punkte (B-539 T32, T31, Block 1) wurden mit DB-Seeds statt vollem End-to-End-GUI-Flow verifiziert — als PASS dokumentiert, aber nicht vollständig produkt-durchgespielt. | `outputs/h1_scale.log`; `test-report/e2e-h3-concurrency-20260615`; `test-report/dg001-h22-retry/` (NVENC proxy h264_nvenc); `docs/superpowers/DG-001_LIVE_VERIFY.md`; B-541, B-542; Decision `D-063-storage-provenance-prereq-waiver.md` |

## Rules

- Deferred gate does not permit `fixed`.
- Deferred gate must be named in any downstream task that depends on it.
- If downstream implementation touches the deferred area, re-check the gate.
- Before release, every active deferred gate needs user decision or live proof.

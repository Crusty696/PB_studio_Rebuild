# PB Studio Quellstand-Konsolidierung — 2026-06-22

status: code-integrated-non-live-suite-green-live-e2e-pending
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 source consolidation before 90 Live-Verify
branch: codex/OTK-021-source-consolidation-2026-06-22
base: origin/main@9570374

## Ergebnis

Sauberer Integrationsbranch erstellt. Dirty Originalrepo blieb unverändert.

Integriert:

- 16 committed OTK-021-/Recovery-Commits via Merge `5f428ec`;
- B-549 via `91d62c1`;
- B-554 via `d833492`;
- Auto-Edit-State-Refresh/BUG-A via `7de108a`.

## Verification

- OTK-021 Merge-Fokus: `39 passed`.
- B-549 Fokus: `3 passed`.
- B-554 Fokus: `8 passed`.
- BUG-A Fokus: `30 passed`.
- kombinierte Suite: `80 passed in 9.07s`.
- `compileall`: grün.
- Ruff geänderte Produktpfade: `All checks passed!`.
- `git diff --check origin/main...HEAD`: grün.
- B-554- und BUG-A-Dateien: SHA-256-identisch zum belegten dirty Originalstand.

Erster Vollsuite-Versuch:

- Command: `pytest -q -m "not gui and not e2e and not live_gpu and not long_form"`.
- Ergebnis: pytest INTERNALERROR während Collection.
- Ursache: `tests/test_video_analysis_real.py:93` führt import-time
  `sys.exit(1)` aus.
- Collection-Blocker danach separat mit Commit `ab6cfab` entfernt.

Zweiter Vollsuite-Lauf:

- Command: `pytest -q -m "not gui and not e2e and not live_gpu and not long_form"`.
- Ergebnis: `2759 passed, 45 skipped, 5 deselected, 2 failed` in 526.86 s.
- B-556: Plan-Governance-Test löst alten Vault-Pfad `C:\Brain-Bug\...`
  nicht auf.
- B-557: Caller-Migration-Testdouble akzeptiert neues `should_stop`-Argument
  von `StemGenStage` nicht.

Autonomer Folge-Loop:

- B-556: Legacy-Vault-Relocation, Commit `757fa6e`.
- B-559: Legacy-Benutzer-Home-Relocation, Commit `6414d2a`.
- B-557: Testdouble-Vertrag, Commit `23b48fd`.
- B-560: QApplication-notify-Testisolation, Commit `bd37aff`.
- B-561: Windows-Manifest-Lock-Contention, Commit `94d8111`.
- Finale Nicht-Live-Suite:
  `2762 passed, 45 skipped, 5 deselected, 41 warnings` in 528.36 s.
- Orchestrator-Report: `test-report/ORCHESTRATOR-FINAL-REPORT.md`.

Zusätzlicher Tool-Fix:

- B-555 Commit `d37e710`: Release-Gate CP1252-sicher; unerwartete
  Gate-Exitcodes blockieren Handoff separat.
- Fokustests: `8 passed`.
- Reale CLI-/Handoff-Prüfung: Gate Exit 2, Normal-Handoff Exit 0,
  `-ReleaseGate` Exit 4; kein Unicode-Traceback.

Lokale Testumgebung:

- B-558: `pytest.exe` war im `pb-studio`-Conda-Env installiert, dessen
  `Scripts`-Ordner fehlte aber im Benutzer-PATH.
- `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\Scripts` dauerhaft
  dem Benutzer-PATH vorangestellt; keine Paketinstallation.
- Verifikation mit neu aufgebautem Machine+User-PATH:
  `pytest 9.1.0`; `tests/test_scripts/test_release_gate_cli.py` = `2 passed`.
- Bereits laufende Terminals müssen neu gestartet werden.

## Grenzen

- Kein neuer kompletter GUI-/GPU-E2E.
- B-549 Mid-Stage-Promptheit stützt sich auf früheren Live-Beleg 1,20 s.
- B-554 stützt sich zusätzlich auf früheren GUI-Beleg: 52 Clips, Modell 1×,
  76 s, kein Hang.
- BUG-A stützt sich zusätzlich auf früheren GUI-Beleg.
- Keine Bug-/Planphase wurde auf `fixed` gesetzt.
- Branch auf `origin` gepusht, noch nicht nach `main` gemergt.
- Nicht-Live-Suite vollständig grün.
- GUI/GPU-End-to-End und DG-001 bleiben offen.

## Nächster Schritt

OTK-021 Live-Verifikation/DG-001 nach gültiger Live-Teststrategie ausführen.
Main-Integration bleibt bis Live-/Release-Entscheid gestoppt.

## Live-Preflight 2026-06-22

Verdikt: `BLOCKED`.

- PyTorch `1.12.1+cu113`, CUDA false.
- GTX 1060: `CM_PROB_PHANTOM`.
- H.264-/HEVC-NVENC: `CUDA_ERROR_NO_DEVICE`.
- App nicht gestartet; Intel-/CPU-Ersatz gemäß GPU-Hartregel verboten.
- Report: `test_reports/LIVE_VERIFY_OTK021_DG001_2026-06-22.md`.

Fortsetzung erst nach Hardware-Recovery und grünem CUDA-/NVENC-Preflight.

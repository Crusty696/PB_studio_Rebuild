# 74 — Decoder-Lizenz (FFmpeg / PyAV)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Scope

- FFmpeg-Builds:
  - LGPL-Build (default) — sicher fuer Distribution.
  - GPL-Build (mit x264) — Vorsicht: GPL gilt fuer ganze App wenn dynamisch gelinkt.
- PyAV bindet gegen System-FFmpeg.
- Fuer PB Studio Bundling: LGPL-Build mitliefern.
- `THIRD_PARTY_LICENSES.md` ergaenzen:
  - FFmpeg LGPL
  - PyAV BSD-2
  - PySceneDetect BSD-3
  - RAFT BSD-3 (torchvision-Modul)
  - SigLIP Apache 2.0 (siehe D-008)

## Verifikation

- FFmpeg-Build-Variante dokumentiert
- Lizenz-Datei vollstaendig

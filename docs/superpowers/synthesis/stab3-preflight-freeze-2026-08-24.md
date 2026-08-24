---
title: STAB-3 Preflight Freeze
date: 2026-08-24
status: agent-complete
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
phase: STAB-3 PREP
current_commit: bc29c5140c44ac5b04174dc7f291d8ca4afb7e83
---

# STAB-3 Preflight Freeze

## Fixierte Basis

- Projekt: isolierter Stability-Run `20260823T0438-w4-video/project`.
- Medien: 28 Videoquellen mit vollstaendigen `stream_sha256`, 95
  Videosegmente, 1 Audiosegment, insgesamt 96 Timelinezeilen.
- Media-Set-Digest: `8a8dc37354a7e457f4ebd5a5edc5cde20c87fa01229da59f0bfaa7b632033df7`.
- Timeline-Digest: `f21f6a032b4c6b811a1e798e72a12ca3fded455325d2929ca81542d3449f0d31`.
- Audio SHA256: `C9F2AD1B3B9E29ADCF70837CFA9621D140821EFD4344421C3B8DC2FAF69448C1`.
- Seed: `PB_PACING_SEED=42` fuer alle folgenden Pacinglaeufe.
- Settings SHA256: `E45A9F851A87F5D74D664EAE35E927190807682AC54477CF1FB635B8C194823C`;
  LLM-Strategist AUS, Studio Brain AN.
- Ollama 0.21.2 SHA256 `4A5EAE4C...`; Settingsmodell bleibt
  `AuditAid/PaddleOCR-VL-1.6-0.9B:latest`, gebunden an Manifest
  `71306567...`, Modelllayer `e791f710...`, Projektor `204d757d...`.
- SigLIP2 `google/siglip2-base-patch16-384` v1.0, HF-Revision
  `f775b65a79762255128c981547af89addcfe0f88`.
- Auto-Edit/V1-V2-SigLIP `google/siglip-so400m-patch14-384`, HF-Revision
  `9fdffc58afc957d1a03a25b10dba0329ab15c2a3`, Modellblob
  `ea2abad2b7f8a9c1aa5e49a244d5d57ffa71c56f720c94bc5d240ef4d6e1d94a`
  (3,511,950,624 Bytes). B-886 korrigiert das urspruenglich unvollstaendige
  Inventar; Produktkonfiguration blieb unveraendert.
- CLAP `laion/larger_clap_music` v1.0; lokaler Cache fehlt und wird nicht
  still heruntergeladen oder ersetzt. Enricher v1.

## Baseline

- DB quick_check ok; SHA256 `06DCB5BB...`.
- `mem_pacing_run=5`, `mem_decision=486`, `mem_learned_pattern=0`,
  `mem_user_feedback_event=0`, `av_pacing_data=1`.
- Relevante App-/Ollama-/FFmpeg-Prozesse bei Capture: 0.

## Grenzen

- Keine Modellwahl geaendert. LLM-/VLM-Entscheidungen bleiben Userrecht.
- Fehlender CLAP-Cache ist sichtbare Voraussetzung, kein verdeckter Download.
- `latest` wird nicht als immutable behauptet; exakte Manifest-/Layer-Digests
  binden diesen Lauf.

Evidence: `tests/qa_artifacts/stab3_preflight_freeze_20260824.json`.

Naechste einzige Task: `STAB-3 / Auto-Edit A inklusive Rangfolge, 18
Brain-Achsen, Pacing, Pattern und Gewichten`.

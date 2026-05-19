# 60 — Tier 6: Test-Infra + Mocks

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Status: planned · 2026-05-19

## Scope

- Fixture `mock_video_decoder` — synthetisches Video (numpy frames, deterministisch).
- Fixture `mock_scene_detect` — gibt feste Szenenliste zurueck.
- Fixture `mock_siglip` — gibt Dummy-Embeddings.
- Fixture `mock_raft` — Dummy-Flow.
- Fixture `mock_vlm_caption` — Dummy-Captions.
- Fixture `mock_v2_outputs` — synthetische V2-Audio-Outputs fuer Cross-Modal-Test.
- Fixture `synthetic_long_video` — geloopte Test-Datei fuer Long-form-Coverage-Test.
- pytest-Marker:
  - `@pytest.mark.live_video` — nur mit echtem GPU
  - `@pytest.mark.long_form` — 4 h Test-Datei

## Verifikation

- Suite offline ohne echte GPU lauffaehig

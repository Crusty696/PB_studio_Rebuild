# DG-001 H1 User-WAV 4h Produktionspipeline - 2026-07-02

status: agent-live-pass
gate: DG-001 H1.3
hardware: NVIDIA GeForce GTX 1060 6 GB, CUDA 11.3
runner: `scripts/diag/verify_dg001_h1_4h_pipeline.py`

## Ergebnis

Finaler User-WAV Ersatzmedium-Run:

- Start: `2026-07-02T07:17:44+0200`
- Ende: `2026-07-02T11:25:21+0200`
- Wall Time: `14857.297 s`
- Result: `pass`
- Input: `test-report/dg001-h1-4h-20260701-userwav/input_4h_real_video_userwav_exact4h.mp4`
- Input SHA256: `6E78D39218DB839544EEF116F126CEE600D520B35C3BE69D061209448C06EA6B`
- Duration: `14400.000000 s`
- Video: H.264, 1280x720, 24 fps, `345599` frames
- Audio: AAC, 48000 Hz, stereo

## Stage-Status

| Stage | Status | Beleg |
|---|---:|---|
| proxy_gen | skipped | Checkpoint aus erstem User-WAV Lauf, `proxy.mp4` vorhanden |
| scene_detect | skipped | Checkpoint, 148 Szenen |
| keyframe_extract | skipped | Checkpoint, 7343 Keyframes |
| siglip_embed | skipped | Checkpoint, `7343 x 1152`, float16 |
| raft_motion | done | 14399 Motion-Paare, 14845.203 s |
| vlm_caption | done | 148 Stub-Captions |
| cross_modal | done | 40 Suggestions |

## Artefakte

Root:

```text
test-report/dg001-h1-4h-20260701-userwav/
```

Pflichtartefakte vorhanden:

- `result.json`
- `pipeline_storage/proxy.mp4`
- `pipeline_storage/scenes.json`
- `pipeline_storage/keyframes.json`
- `pipeline_storage/embeddings.npy`
- `pipeline_storage/motion.json`
- `pipeline_storage/motion.progress.jsonl`
- `pipeline_storage/captions.json`
- `pipeline_storage/cut_plan.json`
- `pipeline_storage/checkpoint.json`

## Fix waehrend Lauf

Erster User-WAV Lauf blieb in `raft_motion` ohne GPU/CPU-Aktivitaet haengen. Fix:

- `RaftMotionStage` schreibt `motion.progress.jsonl` pro Motion-Paar.
- Resume kann vorhandene Motion-Paare wiederverwenden.
- Finales `motion.json` bleibt unveraendert Pflichtartefakt.

## Verifikation

Vor Resume:

- `python -m py_compile services/video_pipeline/stages/raft_motion_stage.py scripts/diag/verify_dg001_h1_4h_pipeline.py` gruen.
- `pytest tests/test_services/test_raft_frame_reuse.py tests/test_services/test_b363_video_pipeline_cancel_status.py tests/test_services/test_video_stages_advanced.py::test_raft_stage_with_mock_service -q` = `7 passed`.

Nach Resume:

- `result.json`: `status=pass`.
- Coverage: `scene_count=148`, `keyframe_count=7343`, `embedding_shape=[7343,1152]`, `motion_pair_count=14399`, `caption_count=148`, `cut_suggestion_count=40`.
- Kein Stage-Fehler, `failed=0`, `cancelled=False`.

## Ehrliche Grenze

Dies beweist DG-001 H1.3 mit dem vom User akzeptierten User-WAV-Ersatzmedium. Es beweist nicht Clean-VM-Installation; das bleibt `VM-001`.

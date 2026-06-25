# 10 — Video-Decoder-Primitive (Multi-Format)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Einheitliches Lese-Interface fuer MP4 / MOV / MKV / AVI / WebM mit H.264 / H.265 / AV1 / VP9.

## Scope

```python
# services/video_pipeline/primitives/decoder.py
class VideoDecoder:
    def probe(self, path: Path) -> VideoMeta: ...
    def iter_frames(self, path: Path, *, start_s: float = 0, end_s: float | None = None,
                    sample_every_n: int = 1) -> Iterator[np.ndarray]: ...
    def extract_frame(self, path: Path, time_s: float) -> np.ndarray: ...
    def extract_audio_stream(self, path: Path, target_wav: Path) -> Path: ...
```

- Bibliothek: `av` (PyAV) — Wrapper um FFmpeg, gut wartbar.
- Fallback: `imageio-ffmpeg` falls PyAV-Probleme.
- Hardware-Decode wenn moeglich (NVDEC via FFmpeg `-hwaccel cuda`).

## Verifikation

- Alle Format-Varianten lesbar
- Frame-Extract timestamp-genau (±1 Frame)
- NVDEC aktiv messbar (GPU-Last)
- `pytest tests/test_services/test_video_decoder.py -v` gruen

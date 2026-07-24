"""B-684: Der Embedder-Unload muss seinen GPU-Cleanup unter dem GpuSerializer
serialisieren (wie die embed-Pfade), sonst feuert empty_cache/synchronize
un-serialisiert gegen live ModelManager-Kernels (Heap-Corruption 0xC0000374).
"""

import contextlib


class _SpySerializer:
    def __init__(self):
        self.holders = []

    @contextlib.contextmanager
    def acquire(self, holder=None):
        self.holders.append(holder)
        yield


def test_video_embedder_unload_uses_serializer():
    from services.brain.video.video_embedder import Siglip2VideoEmbedder

    spy = _SpySerializer()
    emb = Siglip2VideoEmbedder(serializer=spy)  # Modell lazy -> nicht geladen

    emb.unload()

    assert "siglip2_unload" in spy.holders, (
        "unload() muss serializer.acquire() nehmen (B-684)"
    )


def test_audio_embedder_unload_uses_serializer():
    from services.brain.audio.audio_embedder import ClapAudioEmbedder

    spy = _SpySerializer()
    emb = ClapAudioEmbedder(serializer=spy)

    emb.unload()

    assert "clap_unload" in spy.holders, (
        "unload() muss serializer.acquire() nehmen (B-684)"
    )

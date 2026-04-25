"""B-055 fix: get_all_audio / get_all_video haben keinen stillen 5000-Cap mehr.

Default-`limit=None` lädt ALLES, nichts wird stillschweigend abgeschnitten.
Caller (Media-Pool, Pacing-Engine) sehen die volle Sammlung.
"""
from __future__ import annotations

import inspect

from services.ingest_service import get_all_audio, get_all_video


def test_get_all_audio_default_limit_is_none():
    sig = inspect.signature(get_all_audio)
    assert sig.parameters["limit"].default is None, (
        "B-055: Default-Limit für get_all_audio muss None sein (kein stiller 5000-Cap)"
    )


def test_get_all_video_default_limit_is_none():
    sig = inspect.signature(get_all_video)
    assert sig.parameters["limit"].default is None, (
        "B-055: Default-Limit für get_all_video muss None sein (kein stiller 5000-Cap)"
    )

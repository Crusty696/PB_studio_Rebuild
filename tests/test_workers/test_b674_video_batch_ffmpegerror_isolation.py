"""B-674: ein Clip-Fehler (FFmpegError / Proxy-Timeout) darf die Batch-Video-
Analyse nicht abbrechen.

``VideoBatchAnalysisWorker`` fing pro Clip nur ``(ValueError, RuntimeError,
OSError)``. ``FFmpegError`` (kaputte Datei / NVENC-Fail) und
``subprocess.TimeoutExpired`` (Proxy-Timeout) erben von ``Exception`` und
entkamen dem Tupel -> aeusseres ``except Exception`` -> die GANZE Batch brach ab.
"""

import subprocess

from services.errors import FFmpegError
from workers import video as vmod


def _run_batch_with_failure(monkeypatch, qtbot, failing_clip, exc):
    calls = []

    class _FakeAnalyzer:
        def analyze_and_store(self, clip_id, should_stop=None):
            calls.append(clip_id)
            if clip_id == failing_clip:
                raise exc
            return {"width": 1920, "height": 1080, "fps": 30}

    monkeypatch.setattr(vmod, "VideoAnalyzer", _FakeAnalyzer)

    worker = vmod.VideoBatchAnalysisWorker(batch=[(1, "a"), (2, "b"), (3, "c")])
    done, errs, finished, fatal = [], [], [], []
    worker.item_done.connect(lambda cid, info: done.append(cid))
    worker.item_error.connect(lambda cid, msg: errs.append(cid))
    worker.finished.connect(lambda d, e: finished.append((d, e)))
    worker.error.connect(lambda msg: fatal.append(msg))

    worker.run()
    return calls, done, errs, finished, fatal


def test_ffmpegerror_on_one_clip_isolated(monkeypatch, qtbot):
    calls, done, errs, finished, fatal = _run_batch_with_failure(
        monkeypatch, qtbot, failing_clip=2,
        exc=FFmpegError("corrupt / nvenc fail", returncode=1),
    )
    assert calls == [1, 2, 3], "alle Clips muessen versucht werden (kein Abbruch)"
    assert done == [1, 3]
    assert errs == [2], "der kaputte Clip wird als Item-Fehler markiert"
    assert finished == [(2, 1)], "finished mit 2 ok / 1 Fehler"
    assert fatal == [], "kein batch-fataler error"


def test_proxy_timeout_on_one_clip_isolated(monkeypatch, qtbot):
    calls, done, errs, finished, fatal = _run_batch_with_failure(
        monkeypatch, qtbot, failing_clip=2,
        exc=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=300),
    )
    assert calls == [1, 2, 3]
    assert done == [1, 3]
    assert errs == [2]
    assert finished == [(2, 1)]
    assert fatal == []

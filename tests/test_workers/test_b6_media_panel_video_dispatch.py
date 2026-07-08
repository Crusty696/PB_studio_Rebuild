"""AUDIT-FIXPLAN B6 (PIPE-013): Media-Panel-Re-Analyse muss den
DB-Resolve-Pfad des VideoAnalysisPipelineWorker nutzen.

Der Worker resolvet file_path (Proxy-First) NUR, wenn die Batch-Eintraege
2-Tupel ``(clip_id, title)`` sind (workers/video.py::run, len==2-Check).
Der fruehere Aufruf ``VideoAnalysisPipelineWorker(video_id)`` erzeugte ein
3-Tupel ``(id, "", "")`` — kein Resolve, leerer Pfad, Analyse lief nur
ueber den FileNotFoundError/TOCTOU-Fallback aufs Original.
"""
from workers.video import VideoAnalysisPipelineWorker


def test_positional_single_arg_produces_unresolvable_batch():
    """Dokumentiert den Alt-Bug: positional int -> 3-Tupel mit leerem Pfad."""
    worker = VideoAnalysisPipelineWorker(42)
    assert worker._batch == [(42, "", "")]
    # len==3 -> run() ueberspringt den DB-Resolve-Zweig
    assert len(worker._batch[0]) != 2


def test_two_tuple_batch_enables_db_resolve():
    """Die B6-Fix-Form: 2-Tupel-Batch triggert den DB-Resolve in run()."""
    worker = VideoAnalysisPipelineWorker(batch=[(42, "Mein Clip")])
    assert worker._batch == [(42, "Mein Clip")]
    assert len(worker._batch[0]) == 2


def test_media_workspace_dispatch_uses_two_tuple_batch():
    """Regression-Guard auf Quelltext-Ebene: der Media-Panel-Dispatch darf
    nie wieder auf die positionale Ein-Argument-Form zurueckfallen."""
    import inspect
    import ui.workspaces.media_workspace as mw

    src = inspect.getsource(mw.MediaWorkspace._dispatch_video_analysis)
    assert "VideoAnalysisPipelineWorker(batch=[(video_id, title)])" in src
    assert "VideoAnalysisPipelineWorker(video_id)" not in src

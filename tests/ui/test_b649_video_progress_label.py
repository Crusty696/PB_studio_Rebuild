"""B-649: Video-Analyse-Batch-Pfad muss ein eigenes Fortschrittsbalken-Format
setzen, sonst zeigt der (mit der Audio-Analyse geteilte) Balken das alte
"Audio-V2:"-Label.

Source-Inspection-Pin (analog test_cycle5_high_batch): garantiert, dass
_analyze_selected_video ein Video-eigenes setFormat aufruft und NICHT ein
Audio-V2-Label stehen laesst.
"""
from __future__ import annotations

import inspect


def test_video_batch_sets_own_progressbar_format():
    from ui.controllers.video_analysis import VideoAnalysisController

    src = inspect.getsource(VideoAnalysisController._analyze_selected_video)
    assert "setFormat(" in src, (
        "B-649: _analyze_selected_video muss setFormat auf dem geteilten "
        "progress_bar aufrufen, sonst bleibt das Audio-V2-Label stehen."
    )
    assert "Video-Analyse" in src, (
        "B-649: das gesetzte Format muss ein Video-Label ('Video-Analyse') "
        "sein, nicht das geerbte 'Audio-V2'."
    )
    # Kein Audio-V2 als tatsaechliches Balken-Format (Kommentare duerfen den
    # String erklaerend enthalten; nur ein setFormat("Audio... waere der Bug).
    assert 'setFormat("Audio' not in src and "setFormat('Audio" not in src, (
        "B-649: der Video-Pfad darf kein Audio-Label als Balken-Format setzen."
    )

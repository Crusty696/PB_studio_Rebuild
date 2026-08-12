"""B-774-Luecke: der Audio-Pfad behandelte einen toten CUDA-Kontext nicht.

Belegt im B-331-Langlauf (2026-08-12, repo-weiter Grep): ``CudaContextLostError``
kam im gesamten Audio-Pfad **kein einziges Mal** vor. Der Kontexttod-Pfad war
ausschliesslich im Video-Worker verdrahtet (``workers/video.py:626-657``),
waehrend ``workers/audio.py`` einen gestorbenen Kontext als gewoehnlichen Fehler
abfing.

Zwei Folgen:
1. ``mark_cuda_context_lost()`` wurde nie gerufen — die naechsten Modell-Loads
   liefen weiter gegen den toten Kontext, statt app-weit auf CPU zurueckzufallen.
2. Der User bekam einen technischen Traceback-Text statt der klaren
   Neustart-Anweisung aus ``format_user_error``.

Das ist gerade im Audio-Pfad relevant: eine Demucs-Trennung dauert Minuten bis
Stunden — genau der Zeitraum, in dem ein Treiber-Reset oder ein dGPU-Unplug
wahrscheinlich ist.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def worker():
    from workers.audio import StemSeparationWorker

    w = StemSeparationWorker.__new__(StemSeparationWorker)
    w.track_id = 42
    w._errored = False
    w.error = MagicMock()
    w.finished = MagicMock()
    return w


def test_b774_audio_erkennt_kontexttod_als_solchen(worker):
    """Ein toter Kontext muss mark_cuda_context_lost ausloesen."""
    from workers.audio import StemSeparationWorker

    fehler = RuntimeError("CUDA error: unspecified launch failure")
    mm = MagicMock()
    mm.cuda_health_check.return_value = False  # Kontext ist tot

    sep = MagicMock()
    sep.separate_and_store.side_effect = fehler
    worker.progress = MagicMock()
    worker.should_stop = lambda: False

    with patch("services.model_manager.ModelManager", return_value=mm), \
         patch("services.ai_audio_service.StemSeparator", return_value=sep), \
         patch("workers.audio.mark_started"), \
         patch("workers.audio.mark_error"):
        StemSeparationWorker.run(worker)

    assert mm.mark_cuda_context_lost.called, (
        "B-774: mark_cuda_context_lost() wurde nicht gerufen — die naechsten "
        "Modell-Loads laufen weiter gegen den toten CUDA-Kontext."
    )


def test_b774_audio_meldet_neustart_statt_traceback(worker):
    """Der User braucht die Handlungsanweisung, nicht den CUDA-Rohtext."""
    from workers.audio import StemSeparationWorker

    fehler = RuntimeError("CUDA error: unspecified launch failure")
    mm = MagicMock()
    mm.cuda_health_check.return_value = False

    sep = MagicMock()
    sep.separate_and_store.side_effect = fehler
    worker.progress = MagicMock()
    worker.should_stop = lambda: False

    with patch("services.model_manager.ModelManager", return_value=mm), \
         patch("services.ai_audio_service.StemSeparator", return_value=sep), \
         patch("workers.audio.mark_started"), \
         patch("workers.audio.mark_error"):
        StemSeparationWorker.run(worker)

    assert worker.error.emit.called, "es wurde gar kein Fehler gemeldet"
    meldung = str(worker.error.emit.call_args[0][1])
    assert "neu starten" in meldung.lower(), (
        f"B-774: der User bekommt den Rohtext statt der Neustart-Anweisung: {meldung!r}"
    )


def test_b774_oom_ist_kein_kontexttod(worker):
    """Abgrenzung: 'out of memory' darf NICHT als Kontexttod gelten.

    Sonst wuerde ein blosser VRAM-Engpass die App app-weit auf CPU schalten —
    die B-356-Chunk-Halbierung waere damit wirkungslos.
    """
    from workers.video import _is_cuda_context_error

    assert _is_cuda_context_error(RuntimeError("CUDA out of memory")) is False


def test_b774_audio_pfad_kennt_den_kontexttod_ueberhaupt():
    """Belegt am Produktivcode, dass die Luecke geschlossen ist.

    Ohne diesen Test pruefen die Faelle oben nur das Mock-Verhalten.
    """
    import inspect

    from workers import audio

    quelle = inspect.getsource(audio)
    assert "_is_cuda_context_error" in quelle, (
        "B-774: workers/audio.py erkennt einen toten CUDA-Kontext nicht — "
        "genau die Luecke, die der B-331-Langlauf aufgedeckt hat."
    )
    assert "mark_cuda_context_lost" in quelle, (
        "B-774: der Audio-Pfad meldet den Kontexttod nicht an den ModelManager."
    )

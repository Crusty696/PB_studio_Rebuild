from workers.audio_analysis import BaseAnalysisWorker


class CancelDuringAnalyzeWorker(BaseAnalysisWorker):
    def __init__(self):
        super().__init__(audio_track_id=11, file_path="C:/audio.wav")
        self.saved = False

    def _step_key(self) -> str:
        return "dummy_cancel"

    def _start_message(self) -> str:
        return "start"

    def _analyze(self):
        self.cancel()
        return {"value": 1}

    def _done_message(self, result) -> str:
        return "done"

    def _value_summary(self, result) -> dict:
        return {"value": result["value"]}

    def _save_to_db(self, result) -> None:
        self.saved = True

    def _result_to_dict(self, result) -> dict:
        return result


def test_b357_base_analysis_worker_cancel_after_analyze_skips_persist(monkeypatch):
    import workers.audio_analysis as mod

    calls = []
    monkeypatch.setattr(mod, "mark_started", lambda *args, **kwargs: calls.append(("started", args)))
    monkeypatch.setattr(mod, "mark_done", lambda *args, **kwargs: calls.append(("done", args)))
    monkeypatch.setattr(mod, "mark_error", lambda *args, **kwargs: calls.append(("error", args)))
    monkeypatch.setattr(mod, "mark_cancelled", lambda *args, **kwargs: calls.append(("cancelled", args)))

    worker = CancelDuringAnalyzeWorker()
    finished = []
    errors = []
    worker.finished.connect(lambda track_id, result: finished.append((track_id, result)))
    worker.error.connect(lambda track_id, msg: errors.append((track_id, msg)))

    worker.run()

    assert worker.saved is False
    assert ("cancelled", ("audio", 11, "dummy_cancel")) in calls
    assert not [name for name, _args in calls if name in {"done", "error"}]
    assert finished == [(11, {})]
    assert errors == []

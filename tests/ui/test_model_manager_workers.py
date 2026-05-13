import json


class _FakeSocket:
    connect_calls: list[tuple[str, int]] = []
    should_fail = False

    def settimeout(self, _timeout) -> None:
        pass

    def connect(self, addr) -> None:
        self.connect_calls.append(addr)
        if self.should_fail:
            raise OSError("connection refused")

    def close(self) -> None:
        pass


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps({"version": "0.6.8"}).encode("utf-8")


def test_ollama_status_worker_rewrites_localhost_to_loopback(monkeypatch, qapp) -> None:
    import socket
    import urllib.request

    from ui.dialogs.model_manager_dialog import _OllamaStatusWorker

    _FakeSocket.connect_calls = []
    _FakeSocket.should_fail = False
    opened_urls = []

    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: _FakeSocket())

    def fake_urlopen(req, timeout):
        opened_urls.append(req.full_url)
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    worker = _OllamaStatusWorker("http://localhost:11434")
    success = []
    errors = []
    worker.success.connect(success.append)
    worker.error.connect(errors.append)

    worker.run()

    assert _FakeSocket.connect_calls == [("127.0.0.1", 11434)]
    assert opened_urls == ["http://127.0.0.1:11434/api/version"]
    assert success == ["0.6.8"]
    assert errors == []


def test_ollama_status_worker_emits_daemon_error_before_urllib(monkeypatch, qapp) -> None:
    import socket
    import urllib.request

    from ui.dialogs.model_manager_dialog import _OllamaStatusWorker

    _FakeSocket.connect_calls = []
    _FakeSocket.should_fail = True
    urlopen_calls = []

    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: _FakeSocket())
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: urlopen_calls.append((a, kw)))

    worker = _OllamaStatusWorker("http://localhost:11434")
    errors = []
    worker.error.connect(errors.append)

    worker.run()

    assert _FakeSocket.connect_calls == [("127.0.0.1", 11434)]
    assert urlopen_calls == []
    assert errors and errors[0].startswith("Daemon nicht erreichbar:")


def test_download_worker_catches_baseexception_and_emits_finished_false(monkeypatch, qapp) -> None:
    from services import model_lifecycle_service
    from ui.dialogs.model_manager_dialog import _DownloadWorker

    class FakeService:
        def pull_ollama_model(self, _model_id, progress_cb=None):
            raise SystemExit("boom")

    monkeypatch.setattr(
        model_lifecycle_service,
        "get_model_lifecycle_service",
        lambda _url: FakeService(),
    )

    worker = _DownloadWorker("http://localhost:11434", "gemma3:4b", "ollama")
    finished = []
    worker.finished.connect(finished.append)

    worker.run()

    assert finished == [False]

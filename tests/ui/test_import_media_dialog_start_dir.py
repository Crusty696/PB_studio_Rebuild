from pathlib import Path
from types import SimpleNamespace


def test_last_import_dir_uses_stored_existing_directory(monkeypatch, tmp_path, qapp) -> None:
    from ui.controllers import import_media

    stored = tmp_path / "stored"
    stored.mkdir()

    class FakeSettings:
        def value(self, _key, _default="", type=str):
            return str(stored)

    monkeypatch.setattr(import_media, "QSettings", lambda *_args: FakeSettings())

    assert import_media._last_import_dir("audio") == str(stored)


def test_import_audio_passes_start_dir_and_saves_selection(monkeypatch, tmp_path, qapp) -> None:
    from ui.controllers import import_media
    from ui.controllers.import_media import ImportMediaController
    real_dialog = import_media.QFileDialog

    start_dir = tmp_path / "music"
    start_dir.mkdir()
    selected = start_dir / "track.wav"
    selected.write_text("x", encoding="utf-8")
    calls = {}
    saved = []
    processed = []

    monkeypatch.setattr(import_media, "_last_import_dir", lambda kind: str(start_dir))
    monkeypatch.setattr(import_media, "_save_import_dir", lambda kind, path: saved.append((kind, path)))

    class _Signal:
        def connect(self, cb):
            calls["finished_cb"] = cb

    class FakeDialog:
        Option = real_dialog.Option
        FileMode = real_dialog.FileMode
        DialogCode = real_dialog.DialogCode

        def __init__(self, parent, title, directory, ext_filter=""):
            calls["parent"] = parent
            calls["title"] = title
            calls["directory"] = directory
            calls["filter"] = ext_filter
            self.finished = _Signal()

        def setFileMode(self, mode):
            calls["file_mode"] = mode

        def setOption(self, option, enabled=True):
            calls["options"] = (option, enabled)

        def setAttribute(self, *_args):
            pass

        def selectedFiles(self):
            return [str(selected)]

        def open(self):
            calls["opened"] = True

    monkeypatch.setattr(import_media, "QFileDialog", FakeDialog)

    ctrl = ImportMediaController(SimpleNamespace())
    monkeypatch.setattr(ctrl, "_process_imports", lambda paths, media_type: processed.append((paths, media_type)))

    ctrl._import_audio()
    calls["finished_cb"](real_dialog.DialogCode.Accepted)

    assert calls["directory"] == str(start_dir)
    assert calls["options"] == (real_dialog.Option.DontUseNativeDialog, True)
    assert calls["opened"] is True
    assert saved == [("audio", str(selected))]
    assert processed == [([str(selected)], "audio")]


def test_import_audio_cancel_does_not_save_selection(monkeypatch, tmp_path, qapp) -> None:
    from ui.controllers import import_media
    from ui.controllers.import_media import ImportMediaController
    real_dialog = import_media.QFileDialog

    start_dir = tmp_path / "music"
    start_dir.mkdir()
    saved = []
    processed = []
    calls = {}

    monkeypatch.setattr(import_media, "_last_import_dir", lambda kind: str(start_dir))
    monkeypatch.setattr(import_media, "_save_import_dir", lambda kind, path: saved.append((kind, path)))
    class _Signal:
        def connect(self, cb):
            calls["finished_cb"] = cb

    class FakeDialog:
        Option = real_dialog.Option
        FileMode = real_dialog.FileMode
        DialogCode = real_dialog.DialogCode

        def __init__(self, *_args):
            self.finished = _Signal()

        def setFileMode(self, *_args):
            pass

        def setOption(self, *_args):
            pass

        def setAttribute(self, *_args):
            pass

        def selectedFiles(self):
            return []

        def open(self):
            pass

    monkeypatch.setattr(import_media, "QFileDialog", FakeDialog)

    ctrl = ImportMediaController(SimpleNamespace())
    monkeypatch.setattr(ctrl, "_process_imports", lambda paths, media_type: processed.append((paths, media_type)))

    ctrl._import_audio()
    calls["finished_cb"](real_dialog.DialogCode.Rejected)

    assert saved == []
    assert processed == [([], "audio")]


def test_import_folder_passes_start_dir_and_saves_folder(monkeypatch, tmp_path, qapp) -> None:
    from ui.controllers import import_media
    from ui.controllers.import_media import ImportMediaController
    real_dialog = import_media.QFileDialog

    start_dir = tmp_path / "start"
    start_dir.mkdir()
    selected = tmp_path / "selected"
    selected.mkdir()
    calls = {}
    settings_values = {}

    monkeypatch.setattr(import_media, "_last_import_dir", lambda kind: str(start_dir))

    class _Signal:
        def connect(self, cb):
            calls["finished_cb"] = cb

    class FakeDialog:
        Option = real_dialog.Option
        FileMode = real_dialog.FileMode
        DialogCode = real_dialog.DialogCode

        def __init__(self, parent, title, directory):
            calls["directory"] = directory
            self.finished = _Signal()

        def setFileMode(self, mode):
            calls["file_mode"] = mode

        def setOption(self, option, enabled=True):
            calls.setdefault("options", []).append((option, enabled))

        def setAttribute(self, *_args):
            pass

        def selectedFiles(self):
            return [str(selected)]

        def open(self):
            calls["opened"] = True

    class FakeSettings:
        def setValue(self, key, value) -> None:
            settings_values[key] = value

    monkeypatch.setattr(import_media, "QFileDialog", FakeDialog)
    monkeypatch.setattr(import_media, "QSettings", lambda *_args: FakeSettings())

    fake_worker_dispatcher = SimpleNamespace(
        _start_worker_thread=lambda *_args, **_kwargs: None,
    )
    fake_window = SimpleNamespace(
        console_text=SimpleNamespace(append=lambda *_args: None),
        status_bar=SimpleNamespace(showMessage=lambda *_args: None),
        worker_dispatcher=fake_worker_dispatcher,
    )

    ImportMediaController(fake_window)._import_folder()
    calls["finished_cb"](real_dialog.DialogCode.Accepted)

    assert calls["directory"] == str(start_dir)
    assert (real_dialog.Option.DontUseNativeDialog, True) in calls["options"]
    assert (real_dialog.Option.ShowDirsOnly, True) in calls["options"]
    assert calls["opened"] is True
    assert settings_values == {"import/last_dir_folder": str(selected)}

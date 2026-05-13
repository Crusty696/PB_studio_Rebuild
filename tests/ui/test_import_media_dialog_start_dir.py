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

    start_dir = tmp_path / "music"
    start_dir.mkdir()
    selected = start_dir / "track.wav"
    selected.write_text("x", encoding="utf-8")
    calls = {}
    saved = []
    processed = []

    monkeypatch.setattr(import_media, "_last_import_dir", lambda kind: str(start_dir))
    monkeypatch.setattr(import_media, "_save_import_dir", lambda kind, path: saved.append((kind, path)))

    def fake_get_open_file_names(parent, title, directory, ext_filter):
        calls["parent"] = parent
        calls["title"] = title
        calls["directory"] = directory
        calls["filter"] = ext_filter
        return [str(selected)], ""

    monkeypatch.setattr(import_media.QFileDialog, "getOpenFileNames", fake_get_open_file_names)

    ctrl = ImportMediaController(SimpleNamespace())
    monkeypatch.setattr(ctrl, "_process_imports", lambda paths, media_type: processed.append((paths, media_type)))

    ctrl._import_audio()

    assert calls["directory"] == str(start_dir)
    assert saved == [("audio", str(selected))]
    assert processed == [([str(selected)], "audio")]


def test_import_audio_cancel_does_not_save_selection(monkeypatch, tmp_path, qapp) -> None:
    from ui.controllers import import_media
    from ui.controllers.import_media import ImportMediaController

    start_dir = tmp_path / "music"
    start_dir.mkdir()
    saved = []
    processed = []

    monkeypatch.setattr(import_media, "_last_import_dir", lambda kind: str(start_dir))
    monkeypatch.setattr(import_media, "_save_import_dir", lambda kind, path: saved.append((kind, path)))
    monkeypatch.setattr(
        import_media.QFileDialog,
        "getOpenFileNames",
        lambda parent, title, directory, ext_filter: ([], ""),
    )

    ctrl = ImportMediaController(SimpleNamespace())
    monkeypatch.setattr(ctrl, "_process_imports", lambda paths, media_type: processed.append((paths, media_type)))

    ctrl._import_audio()

    assert saved == []
    assert processed == [([], "audio")]


def test_import_folder_passes_start_dir_and_saves_folder(monkeypatch, tmp_path, qapp) -> None:
    from ui.controllers import import_media
    from ui.controllers.import_media import ImportMediaController

    start_dir = tmp_path / "start"
    start_dir.mkdir()
    selected = tmp_path / "selected"
    selected.mkdir()
    calls = {}
    settings_values = {}

    monkeypatch.setattr(import_media, "_last_import_dir", lambda kind: str(start_dir))

    def fake_get_existing_directory(parent, title, directory):
        calls["directory"] = directory
        return str(selected)

    class FakeSettings:
        def setValue(self, key, value) -> None:
            settings_values[key] = value

    monkeypatch.setattr(import_media.QFileDialog, "getExistingDirectory", fake_get_existing_directory)
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

    assert calls["directory"] == str(start_dir)
    assert settings_values == {"import/last_dir_folder": str(selected)}

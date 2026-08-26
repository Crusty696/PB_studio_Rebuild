from pathlib import Path

from ui.dialogs import about


def test_b902_about_docs_packaged_open_and_missing_warning(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("PB Studio", encoding="utf-8")
    opened = []
    warnings = []

    monkeypatch.setattr(about, "_documentation_path", lambda: readme)
    monkeypatch.setattr(
        about.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    monkeypatch.setattr(
        about.QMessageBox,
        "warning",
        lambda *_args: warnings.append(_args),
    )

    about.AboutDialog._open_docs()
    assert [Path(path) for path in opened] == [readme]
    assert warnings == []

    readme.unlink()
    about.AboutDialog._open_docs()
    assert len(warnings) == 1

    spec_text = Path("pb_studio.spec").read_text(encoding="utf-8")
    assert "(str(ROOT / 'README.md'), '.')" in spec_text

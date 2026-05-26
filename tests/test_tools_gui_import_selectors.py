from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_b351_audio_gui_tool_matches_media_ui_selectors():
    src = (ROOT / "tools" / "gui" / "gui_audio_import.py").read_text(encoding="utf-8")

    assert 'control_type="Button"' in src
    assert '_click_button(main_win, "Audio Modus")' in src
    assert '_click_button(main_win, "Audio importieren")' in src
    assert "RadioButton" not in src
    assert "Audio importieren" in src


def test_b351_video_gui_tool_matches_media_ui_selectors():
    src = (ROOT / "tools" / "gui" / "gui_video_import.py").read_text(encoding="utf-8")

    assert 'control_type="Button"' in src
    assert '_click_button(main_win, "Video Modus")' in src
    assert '_click_button(main_win, "Ordner importieren")' in src
    assert "RadioButton" not in src
    assert "Ordner" in src

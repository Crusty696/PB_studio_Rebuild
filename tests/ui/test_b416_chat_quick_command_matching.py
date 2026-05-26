from __future__ import annotations


def test_b416_auto_edit_quick_command_does_not_match_explanation_sentence():
    from ui.chat_dock import ChatDock

    assert ChatDock._match_auto_edit_command("erklaere pacing") is False


def test_b416_analyze_quick_command_does_not_match_explanation_sentence():
    from ui.chat_dock import ChatDock

    assert ChatDock._match_analyze_command("analysiere bitte den begriff") is False


def test_b416_quick_commands_still_match_explicit_commands():
    from ui.chat_dock import ChatDock

    assert ChatDock._match_auto_edit_command("pacing") is True
    assert ChatDock._match_analyze_command("analysiere alle videos") is True

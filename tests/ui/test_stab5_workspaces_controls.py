"""STAB-5 Controls #141-#190: Workspaces (Convert, Deliver, Media) elementgenau belegen.

- ConvertWorkspace (#141-#146)
- DeliverWorkspace (#147-#154)
- MediaWorkspace (#155-#167)
- MediaWorkspace Pagination (#168-#169 manual-excluded)
- MediaWorkspace / Analysis (#170-#190)
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


# ── ConvertWorkspace (#141-#146) ──────────────────────────────────────────


def test_141_convert_resolution_combo() -> None:
    """Control #141: ConvertWorkspace.convert_resolution (QComboBox)."""
    app = _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace

    ws = ConvertWorkspace()
    try:
        ws.show()
        app.processEvents()
        combo = ws.convert_resolution
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Ziel-Aufloesung"
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == [
            "1920x1080 (1080p)",
            "2560x1440 (2K)",
            "3840x2160 (4K)",
            "1280x720 (720p)",
        ]

        emitted: list[int] = []
        combo.currentIndexChanged.connect(emitted.append)
        combo.setCurrentIndex(2)
        app.processEvents()
        assert emitted == [2]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_142_convert_fps_combo() -> None:
    """Control #142: ConvertWorkspace.convert_fps (QComboBox)."""
    app = _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace

    ws = ConvertWorkspace()
    try:
        ws.show()
        app.processEvents()
        combo = ws.convert_fps
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Ziel-Framerate"
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == ["30 fps", "24 fps", "25 fps", "50 fps", "60 fps"]

        emitted: list[int] = []
        combo.currentIndexChanged.connect(emitted.append)
        combo.setCurrentIndex(1)
        app.processEvents()
        assert emitted == [1]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_143_convert_format_combo() -> None:
    """Control #143: ConvertWorkspace.convert_format (QComboBox)."""
    app = _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace

    ws = ConvertWorkspace()
    try:
        ws.show()
        app.processEvents()
        combo = ws.convert_format
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Ziel-Containerformat"
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == [
            "mp4 (H.264)",
            "mp4 (H.265/HEVC)",
            "mov (ProRes)",
            "mkv (H.264)",
            "mp4 (Kopieren/Copy)",
        ]

        emitted: list[int] = []
        combo.currentIndexChanged.connect(emitted.append)
        combo.setCurrentIndex(1)
        app.processEvents()
        assert emitted == [1]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_144_btn_standardize_all() -> None:
    """Control #144: ConvertWorkspace.btn_standardize_all (QPushButton)."""
    app = _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace

    ws = ConvertWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_standardize_all
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Alle Videos standardisieren"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_145_effects_clip_combo() -> None:
    """Control #145: ConvertWorkspace.effects_clip_combo (QComboBox)."""
    app = _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace

    ws = ConvertWorkspace()
    try:
        ws.show()
        ws._tabs.setCurrentIndex(1)
        app.processEvents()
        combo = ws.effects_clip_combo
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Clip fuer Effekte waehlen"
    finally:
        ws.deleteLater()
        app.processEvents()


def test_146_btn_apply_effects() -> None:
    """Control #146: ConvertWorkspace.btn_apply_effects (QPushButton)."""
    app = _qapp()
    from ui.workspaces.convert_workspace import ConvertWorkspace

    ws = ConvertWorkspace()
    try:
        ws.show()
        ws._tabs.setCurrentIndex(1)
        app.processEvents()
        btn = ws.btn_apply_effects
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Effekte anwenden"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


# ── DeliverWorkspace (#147-#154) ──────────────────────────────────────────


def test_147_deliver_resolution_combo() -> None:
    """Control #147: DeliverWorkspace.resolution_combo (QComboBox)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        combo = ws.resolution_combo
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Export Aufloesung"
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == ["1920x1080", "1280x720", "854x480", "3840x2160"]

        emitted: list[int] = []
        combo.currentIndexChanged.connect(emitted.append)
        combo.setCurrentIndex(1)
        app.processEvents()
        assert emitted == [1]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_148_deliver_fps_combo() -> None:
    """Control #148: DeliverWorkspace.fps_combo (QComboBox)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        combo = ws.fps_combo
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Export Bildrate"
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == ["30", "24", "25", "60"]

        emitted: list[int] = []
        combo.currentIndexChanged.connect(emitted.append)
        combo.setCurrentIndex(1)
        app.processEvents()
        assert emitted == [1]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_149_deliver_preset_combo() -> None:
    """Control #149: DeliverWorkspace.preset_combo (QComboBox)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        combo = ws.preset_combo
        assert combo.isVisibleTo(ws) is True
        assert combo.isEnabled() is True
        assert combo.accessibleName() == "Export Preset"
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == [
            "Standard (H.264 fast)",
            "Hohe Qualitaet (H.264 slow)",
            "Draft (schnell)",
        ]
        data = [combo.itemData(i) for i in range(combo.count())]
        assert data == ["standard", "high", "draft"]

        emitted: list[int] = []
        combo.currentIndexChanged.connect(emitted.append)
        combo.setCurrentIndex(1)
        app.processEvents()
        assert emitted == [1]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_150_btn_preview() -> None:
    """Control #150: DeliverWorkspace.btn_preview (QPushButton)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_preview
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Quick-Preview (10s)"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_151_btn_export() -> None:
    """Control #151: DeliverWorkspace.btn_export (QPushButton)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_export
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Video exportieren"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_152_btn_refresh_production() -> None:
    """Control #152: DeliverWorkspace.btn_refresh_production (QPushButton)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_refresh_production
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Aktualisieren"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_153_btn_preview_play() -> None:
    """Control #153: DeliverWorkspace.btn_preview_play (QPushButton)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_preview_play
        assert btn.text() == "Play"
        btn.setEnabled(True)
        app.processEvents()
        assert btn.isEnabled() is True

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_154_btn_preview_stop() -> None:
    """Control #154: DeliverWorkspace.btn_preview_stop (QPushButton)."""
    app = _qapp()
    from ui.workspaces.deliver_workspace import DeliverWorkspace

    ws = DeliverWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_preview_stop
        assert btn.text() == "Stop"
        btn.setEnabled(True)
        app.processEvents()
        assert btn.isEnabled() is True

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


# ── MediaWorkspace (#155-#167) ────────────────────────────────────────────


def test_155_btn_mode_video() -> None:
    """Control #155: MediaWorkspace.btn_mode_video (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_mode_video
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "VIDEO"
        assert btn.isChecked() is True
        assert ws.mode_stack.currentIndex() == 0
    finally:
        ws.deleteLater()
        app.processEvents()


def test_156_btn_mode_audio() -> None:
    """Control #156: MediaWorkspace.btn_mode_audio (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_mode_audio
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "AUDIO"

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert btn.isChecked() is True
        assert ws.mode_stack.currentIndex() == 1
    finally:
        ws.deleteLater()
        app.processEvents()


def test_157_btn_add_to_timeline() -> None:
    """Control #157: MediaWorkspace.btn_add_to_timeline (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_add_to_timeline
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Zur Timeline hinzufuegen"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_158_btn_import_video() -> None:
    """Control #158: MediaWorkspace.btn_import_video (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_import_video
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "+ Video"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_159_btn_import_folder() -> None:
    """Control #159: MediaWorkspace.btn_import_folder (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_import_folder
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "+ Ordner"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_160_btn_delete_selected_video() -> None:
    """Control #160: MediaWorkspace.btn_delete_selected_video (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_delete_selected_video
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Loeschen"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_161_btn_trash() -> None:
    """Control #161: MediaWorkspace.btn_trash (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_trash
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Papierkorb"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_162_btn_clear_all() -> None:
    """Control #162: MediaWorkspace.btn_clear_all (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_clear_all
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Sammlung bereinigen"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_163_btn_search() -> None:
    """Control #163: MediaWorkspace.btn_search (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_search
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Suchen"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_164_btn_search_clear() -> None:
    """Control #164: MediaWorkspace.btn_search_clear (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_search_clear
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "X"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_165_btn_select_all_video() -> None:
    """Control #165: MediaWorkspace.btn_select_all_video (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_select_all_video
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Alle"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_166_btn_video_list_view() -> None:
    """Control #166: MediaWorkspace.btn_video_list_view (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_video_list_view
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "☰"

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert ws._video_pool_stack.currentIndex() == 0
    finally:
        ws.deleteLater()
        app.processEvents()


def test_167_btn_video_grid_view() -> None:
    """Control #167: MediaWorkspace.btn_video_grid_view (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_video_grid_view
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "⊞"

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert ws._video_pool_stack.currentIndex() == 1
    finally:
        ws.deleteLater()
        app.processEvents()


def test_168_169_pagination_manual_excluded() -> None:
    """Controls #168-#169: MediaWorkspace.btn_video_page_prev/next (manual-excluded)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        assert hasattr(ws, "btn_video_page_prev") is True
        assert hasattr(ws, "btn_video_page_next") is True
        assert ws.btn_video_page_prev.isVisible() is False
        assert ws.btn_video_page_next.isVisible() is False
    finally:
        ws.deleteLater()
        app.processEvents()


# ── MediaWorkspace / Analysis Actions (#170-#190) ─────────────────────────


def test_170_btn_analyze_video() -> None:
    """Control #170: MediaWorkspace.btn_analyze_video (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_analyze_video
        assert btn.isEnabled() is True
        assert btn.text() == "Szenen"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_171_btn_video_pipeline() -> None:
    """Control #171: MediaWorkspace.btn_video_pipeline (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_video_pipeline
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Video komplett analysieren"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_172_btn_keyframe_string() -> None:
    """Control #172: MediaWorkspace.btn_keyframe_string (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        app.processEvents()
        btn = ws.btn_keyframe_string
        assert btn.isVisibleTo(ws) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Keyframe-String"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_173_btn_import_audio() -> None:
    """Control #173: MediaWorkspace.btn_import_audio (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_import_audio
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "+ Audio"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_174_btn_import_folder_audio() -> None:
    """Control #174: MediaWorkspace._btn_import_folder_audio (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws._btn_import_folder_audio
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "+ Ordner"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_175_btn_delete_selected_audio() -> None:
    """Control #175: MediaWorkspace.btn_delete_selected_audio (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_delete_selected_audio
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "Loeschen"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_176_btn_select_all_audio() -> None:
    """Control #176: MediaWorkspace.btn_select_all_audio (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_select_all_audio
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "Alle"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_177_btn_audio_list_view() -> None:
    """Control #177: MediaWorkspace.btn_audio_list_view (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_audio_list_view
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "☰"

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert ws._audio_pool_stack.currentIndex() == 0
    finally:
        ws.deleteLater()
        app.processEvents()


def test_178_btn_audio_grid_view() -> None:
    """Control #178: MediaWorkspace.btn_audio_grid_view (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_audio_grid_view
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "⊞"

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert ws._audio_pool_stack.currentIndex() == 1
    finally:
        ws.deleteLater()
        app.processEvents()


def test_179_btn_audio_page_prev() -> None:
    """Control #179: MediaWorkspace.btn_audio_page_prev (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_audio_page_prev
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "◀"
        btn.setEnabled(True)
        app.processEvents()

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_180_btn_audio_page_next() -> None:
    """Control #180: MediaWorkspace.btn_audio_page_next (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_audio_page_next
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "▶"
        btn.setEnabled(True)
        app.processEvents()

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_181_btn_analyze() -> None:
    """Control #181: MediaWorkspace.btn_analyze (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_analyze
        assert btn.text() == "BPM / Beatgrid"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_182_btn_waveform() -> None:
    """Control #182: MediaWorkspace.btn_waveform (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_waveform
        assert btn.text() == "Wellenform"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_183_btn_key_detect() -> None:
    """Control #183: MediaWorkspace.btn_key_detect (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_key_detect
        assert btn.text() == "Tonart"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_184_btn_lufs_analyze() -> None:
    """Control #184: MediaWorkspace.btn_lufs_analyze (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_lufs_analyze
        assert btn.text() == "LUFS"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_185_btn_mood_classify() -> None:
    """Control #185: MediaWorkspace.btn_mood_classify (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_mood_classify
        assert btn.text() == "Mood / Genre"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_186_btn_spectral_analyze() -> None:
    """Control #186: MediaWorkspace.btn_spectral_analyze (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_spectral_analyze
        assert btn.text() == "Spektralanalyse"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_187_btn_structure_detect() -> None:
    """Control #187: MediaWorkspace.btn_structure_detect (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_structure_detect
        assert btn.text() == "Songstruktur"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_188_btn_stem_separate() -> None:
    """Control #188: MediaWorkspace.btn_stem_separate (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_stem_separate
        assert btn.text() == "Stems"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_189_btn_auto_duck() -> None:
    """Control #189: MediaWorkspace.btn_auto_duck (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_auto_duck
        assert btn.text() == "Auto-Ducking"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()


def test_190_btn_analyze_all() -> None:
    """Control #190: MediaWorkspace.btn_analyze_all (QPushButton)."""
    app = _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    try:
        ws.show()
        ws.switch_to_audio()
        app.processEvents()
        btn = ws.btn_analyze_all
        assert btn.isVisibleTo(ws) is True
        assert btn.text() == "Audio komplett analysieren"

        clicked: list[bool] = []
        btn.clicked.connect(lambda: clicked.append(True))
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert clicked == [True]
    finally:
        ws.deleteLater()
        app.processEvents()

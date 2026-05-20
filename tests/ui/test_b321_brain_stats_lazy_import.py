from __future__ import annotations

import inspect


def test_pbwindow_init_does_not_import_brain_v3_stats_panel() -> None:
    import main

    init_source = inspect.getsource(main.PBWindow.__init__)

    assert "from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel" not in init_source
    assert "_load_brain_v3_stats_panel" in dir(main.PBWindow)

from pathlib import Path


def test_b342_startup_check_thread_quits_and_deletes_on_all_done_paths():
    """B-342: StartupCheckWorker-QThread must quit on success and exit path."""
    src = Path("main.py").read_text(encoding="utf-8")

    exit_comment = "User chose \"Beenden\""
    exit_idx = src.find(exit_comment)
    assert exit_idx > 0, "Startup dialog exit branch not found"
    exit_window = src[exit_idx: exit_idx + 360]
    assert "window._startup_check_thread.quit()" in exit_window
    assert "app.quit()" in exit_window

    load_idx = src.find("window.timeline_view.load_from_db()")
    assert load_idx > 0, "Startup success branch not found"
    success_window = src[load_idx: load_idx + 180]
    assert "window._startup_check_thread.quit()" in success_window

    assert (
        "window._startup_check_thread.finished.connect(\n"
        "                window._startup_check_worker.deleteLater"
    ) in src
    assert (
        "window._startup_check_thread.finished.connect(\n"
        "                window._startup_check_thread.deleteLater"
    ) in src

"""B-056 + B-057 + B-058 + B-059 + B-060 Batch-6 (Worker-Concurrency)."""

from __future__ import annotations

import inspect


def test_b056_proxy_creation_semaphore_limits_parallel() -> None:
    """B-056: ProxyCreationWorker.run nutzt _PROXY_CREATION_SEMAPHORE
    (BoundedSemaphore mit value=2)."""
    from workers import import_export

    assert hasattr(import_export, "_PROXY_CREATION_SEMAPHORE")
    sem = import_export._PROXY_CREATION_SEMAPHORE
    # BoundedSemaphore lockt sich selbst auf value=2 — nach 2 acquire+1 release
    # darf nicht mehr als 2x release gehen, sonst wirft ValueError
    cls_name = type(sem).__name__
    assert "Semaphore" in cls_name

    src = inspect.getsource(import_export.ProxyCreationWorker.run)
    assert "_PROXY_CREATION_SEMAPHORE" in src
    assert "with " in src


def test_b057_batchconvert_worker_uses_gpu_execution_lock() -> None:
    """B-057: BatchConvertWorker.run wrappt run-Logik mit GPU_EXECUTION_LOCK."""
    from workers.import_export import BatchConvertWorker

    src = inspect.getsource(BatchConvertWorker)
    assert "GPU_EXECUTION_LOCK" in src, (
        "B-057: BatchConvertWorker muss GPU_EXECUTION_LOCK verwenden."
    )


def test_b058_folder_import_worker_walks_in_thread() -> None:
    """B-058: FolderImportWorker.__init__ akzeptiert walk_root, run() macht
    den os.walk-Scan im Worker-Thread (nicht im Main-Thread)."""
    from workers.import_export import FolderImportWorker

    sig = inspect.signature(FolderImportWorker.__init__)
    assert "walk_root" in sig.parameters, (
        "B-058: FolderImportWorker.__init__ braucht walk_root-Parameter."
    )

    src = inspect.getsource(FolderImportWorker.run)
    assert "walk_root" in src or "os.walk" in src


def test_b058_import_folder_controller_passes_walk_root() -> None:
    """B-058: ui.controllers.import_media._import_folder uebergibt walk_root
    an FolderImportWorker statt selbst zu walken."""
    from ui.controllers.import_media import ImportMediaController

    src = inspect.getsource(ImportMediaController._import_folder)
    assert "walk_root" in src
    # kein os.walk im Controller mehr — nur Code-Zeilen pruefen,
    # Docstring/Kommentare duerfen den Begriff erwaehnen.
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith(("#", '"', "'"))
    ]
    code_text = "\n".join(code_lines)
    assert "os.walk(" not in code_text


def test_b059_convert_accepts_timeout_parameter() -> None:
    """B-059: services.convert_service.convert akzeptiert timeout-Parameter
    und reicht ihn an _run_ffmpeg_with_progress weiter."""
    from services.convert_service import convert, _run_ffmpeg_with_progress

    sig = inspect.signature(convert)
    assert "timeout" in sig.parameters, (
        "B-059: convert() braucht timeout-Parameter."
    )

    inner_sig = inspect.signature(_run_ffmpeg_with_progress)
    assert "timeout" in inner_sig.parameters

    inner_src = inspect.getsource(_run_ffmpeg_with_progress)
    # Wall-Clock-Watchdog vorhanden
    assert "timeout_watchdog" in inner_src or "_timeout_watch" in inner_src
    assert "timed_out" in inner_src


def test_b059_proxy_creation_worker_passes_timeout() -> None:
    """B-059: ProxyCreationWorker reicht timeout an convert() durch."""
    from workers.import_export import ProxyCreationWorker

    src = inspect.getsource(ProxyCreationWorker)
    assert "timeout=" in src, (
        "B-059: ProxyCreationWorker muss timeout an convert() durchreichen."
    )


def test_b060_clear_all_media_has_error_handler() -> None:
    """B-060: _clear_all_media uebergibt on_error-Callback an start_task."""
    from ui.controllers.import_media import ImportMediaController

    src = inspect.getsource(ImportMediaController._clear_all_media)
    assert "on_error=" in src
    assert "_on_error" in src
    # Der Handler zeigt eine sichtbare User-Meldung
    assert "QMessageBox" in src or "status_bar" in src


def test_b060_delete_selected_media_has_error_handler() -> None:
    """B-060: _delete_selected_media uebergibt on_error-Callback an start_task."""
    from ui.controllers.import_media import ImportMediaController

    src = inspect.getsource(ImportMediaController._delete_selected_media)
    assert "on_error=" in src
    assert "_on_error" in src
    assert "QMessageBox" in src or "status_bar" in src

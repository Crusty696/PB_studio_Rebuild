"""B-219 — WinError 32 (file-lock) Retry-Mechanismus.

Pipeline-Worker und BatchAnalysisWorker laufen oft direkt nacheinander
auf denselben Proxy-Files. Auf Windows kann der File-Handle nach
cv2.release()/FFmpeg-exit/AV-Scan einige hundert ms blockiert bleiben —
naive Folge-Operation crasht mit `[WinError 32] Der Prozess kann nicht
auf die Datei zugreifen, da sie von einem anderen Prozess verwendet wird`.

Tests verifizieren:
1. _is_windows_file_lock_error erkennt WinError 32.
2. _retry_on_file_lock wiederholt mit exponential Backoff.
3. Bei dauerhaftem Lock wird der Original-Fehler durchgereicht.
4. Andere OSError-Typen werden NICHT geretryt (kein Verstecken).
5. create_proxy ueberlebt einen einmaligen Lock auf stat()/unlink().
"""
from __future__ import annotations

import inspect
import os


def test_b219_lock_detection_recognises_winerror32() -> None:
    from services.video_service import _is_windows_file_lock_error

    err = OSError(13, "Permission denied")
    err.winerror = 32  # type: ignore[attr-defined]
    assert _is_windows_file_lock_error(err) is True, (
        "B-219: WinError 32 muss als Lock-Fehler erkannt werden."
    )


def test_b219_lock_detection_ignores_other_oserror() -> None:
    from services.video_service import _is_windows_file_lock_error

    err = OSError(2, "No such file or directory")
    assert _is_windows_file_lock_error(err) is False, (
        "B-219: ENOENT (No such file) ist KEIN Lock — darf nicht geretryt werden."
    )


def test_b219_retry_succeeds_after_transient_lock() -> None:
    """Funktion failt 2x mit WinError 32, dann success — retry muss greifen."""
    from services.video_service import _retry_on_file_lock

    attempts = [0]

    def _flaky():
        attempts[0] += 1
        if attempts[0] < 3:
            err = OSError(13, "locked")
            err.winerror = 32  # type: ignore[attr-defined]
            raise err
        return "OK"

    result = _retry_on_file_lock("test", _flaky, attempts=5, base_delay_s=0.001)
    assert result == "OK"
    assert attempts[0] == 3


def test_b219_retry_gives_up_after_max_attempts() -> None:
    """Wenn der Lock dauerhaft bleibt, raised der Original-Fehler."""
    from services.video_service import _retry_on_file_lock
    import pytest

    def _always_locked():
        err = OSError(13, "locked")
        err.winerror = 32  # type: ignore[attr-defined]
        raise err

    with pytest.raises(OSError) as exc_info:
        _retry_on_file_lock("test", _always_locked, attempts=3, base_delay_s=0.001)

    assert getattr(exc_info.value, "winerror", None) == 32, (
        "B-219: nach max Retries muss der Original-Fehler durchgereicht werden."
    )


def test_b219_retry_does_not_swallow_non_lock_errors() -> None:
    """Andere OSError (z.B. FileNotFoundError) duerfen NIE geretryt werden."""
    from services.video_service import _retry_on_file_lock
    import pytest

    attempts = [0]

    def _missing():
        attempts[0] += 1
        raise FileNotFoundError(2, "No such file")

    with pytest.raises(FileNotFoundError):
        _retry_on_file_lock("test", _missing, attempts=5, base_delay_s=0.001)

    assert attempts[0] == 1, (
        "B-219: FileNotFoundError ist KEIN transienter Lock — darf nicht geretryt werden."
    )


def test_b219_create_proxy_uses_retry_for_stat_and_unlink() -> None:
    """Source-Inspect: create_proxy ruft _retry_on_file_lock fuer stat/unlink."""
    from services.video_service import VideoAnalyzer

    src = inspect.getsource(VideoAnalyzer.create_proxy)
    # stat-pfad muss retry-wrapped sein:
    assert "_retry_on_file_lock" in src, (
        "B-219: create_proxy muss _retry_on_file_lock fuer Lock-anfaellige "
        "Operationen einsetzen."
    )
    # mindestens 3 unlink-Stellen (timeout, cancel, 0-byte) muessen wrapped sein:
    assert src.count("_retry_on_file_lock") >= 3, (
        "B-219: alle 3 unlink-Pfade in create_proxy (timeout/cancel/0-byte) muessen retry haben."
    )


def test_b219_persistent_lock_raises_clear_ffmpeg_error(tmp_path) -> None:
    """Wenn der Lock dauerhaft bleibt, soll create_proxy nicht crashen,
    sondern eine sprechende FFmpegError mit AV-Scanner-Hinweis liefern."""
    from services.video_service import VideoAnalyzer
    from services.errors import FFmpegError
    import pytest

    # Vorbereitung: ein vorhandener Proxy + Mock dass stat dauerhaft locked ist.
    # Wir konstruieren das durch monkeypatching des _retry_on_file_lock,
    # so dass es immer mit WinError 32 raised.
    from services import video_service

    original_retry = video_service._retry_on_file_lock

    def _always_locked_retry(operation, func, *args, **kwargs):
        err = OSError(13, f"persistent lock on {operation}")
        err.winerror = 32  # type: ignore[attr-defined]
        raise err

    video_service._retry_on_file_lock = _always_locked_retry  # type: ignore[assignment]

    # Wir muessen einen "vorhandenen Proxy" simulieren — sonst geht der Code
    # gar nicht in den retry-Pfad. Dafuer monkeypatchen wir _proxy_dir.
    proxy_dir = tmp_path / "proxies"
    proxy_dir.mkdir()
    fake_src = tmp_path / "test_video.mp4"
    fake_src.write_bytes(b"x" * 100)
    fake_proxy = proxy_dir / "test_video_proxy.mp4"
    fake_proxy.write_bytes(b"y" * 50)  # nicht-leer

    original_proxy_dir = video_service._proxy_dir
    video_service._proxy_dir = lambda: proxy_dir  # type: ignore[assignment]

    try:
        analyzer = VideoAnalyzer()
        # Der Proxy existiert + size>0; wegen unserem Mock raised stat() aber
        # WinError 32. Erwartet: FFmpegError mit klarer Message ODER
        # Fallback-Pfad (size>0 aus dem except-Block).
        try:
            result = analyzer.create_proxy(str(fake_src))
            # Falls der except-Block den size>0-Fallback nimmt, ist das auch OK
            # (User sieht keinen Crash).
            assert str(fake_proxy.resolve()) == result
        except FFmpegError as ferr:
            assert "gelockt" in str(ferr).lower() or "locked" in str(ferr).lower()
    finally:
        video_service._retry_on_file_lock = original_retry  # type: ignore[assignment]
        video_service._proxy_dir = original_proxy_dir  # type: ignore[assignment]

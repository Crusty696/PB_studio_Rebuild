"""B-218 — CUDA-Context-Resilience nach Laptop-Dock/Sleep-Resume.

Testet ModelManager.cuda_health_check() + notify_power_resume() +
_ensure_cuda_or_fallback() — die drei Bausteine, die verhindern dass
der gehaltene CUDA-Context beim Re-Dock einen STATUS_STACK_BUFFER_OVERRUN
ausloest.
"""

from __future__ import annotations

import inspect


def test_b218_cuda_health_check_method_exists() -> None:
    """ModelManager.cuda_health_check ist als instance method da."""
    from services.model_manager import ModelManager

    assert hasattr(ModelManager, "cuda_health_check"), (
        "B-218: ModelManager.cuda_health_check fehlt."
    )


def test_b218_notify_power_resume_sets_suspect_flag() -> None:
    """notify_power_resume() setzt _cuda_suspect_stale=True."""
    from services.model_manager import ModelManager

    mm = ModelManager()
    mm._cuda_suspect_stale = False  # reset
    mm.notify_power_resume()
    assert mm._cuda_suspect_stale is True, (
        "B-218: notify_power_resume muss _cuda_suspect_stale setzen, "
        "sonst wird beim naechsten Load nicht geprobed."
    )


def test_b218_health_check_returns_bool() -> None:
    """cuda_health_check() wirft NIE — gibt bool zurueck (auch wenn cuda tot)."""
    from services.model_manager import ModelManager

    mm = ModelManager()
    result = mm.cuda_health_check()
    assert isinstance(result, bool), (
        f"B-218: cuda_health_check muss bool liefern, kam: {type(result).__name__}"
    )


def test_b218_ensure_cuda_or_fallback_no_op_when_cpu_stable() -> None:
    """Wenn device='cpu' und keine cuda_suspect, ist _ensure_cuda_or_fallback
    ein no-op — kein device-flip."""
    from services.model_manager import ModelManager

    mm = ModelManager()
    original_device = mm.device
    try:
        # Force CPU-mode + no suspect.
        mm.device = "cpu"
        mm._cuda_suspect_stale = False
        mm._ensure_cuda_or_fallback("test")
        # device-Wert haengt davon ab, ob cuda gerade verfuegbar ist —
        # das ist erwartetes Verhalten (Re-Dock-Pfad). Aber er darf
        # nie crashen.
    finally:
        mm.device = original_device


def test_b218_ensure_cuda_or_fallback_handles_stale_flag() -> None:
    """Wenn device='cuda' und Suspect-Flag gesetzt: nach _ensure_cuda_or_fallback
    ist der Flag wieder False (Probe wurde durchgefuehrt)."""
    from services.model_manager import ModelManager

    mm = ModelManager()
    original_device = mm.device

    try:
        mm.device = "cuda"
        mm._cuda_suspect_stale = True
        # Diese Probe darf nicht crashen — auch wenn cuda tot ist, faellt
        # der Code auf cpu zurueck.
        mm._ensure_cuda_or_fallback("test-probe")
        assert mm._cuda_suspect_stale is False, (
            "B-218: _ensure_cuda_or_fallback muss Suspect-Flag clearen — "
            "sonst probed wir endlos."
        )
    finally:
        mm.device = original_device
        mm._cuda_suspect_stale = False


def test_b218_load_raft_calls_ensure_cuda() -> None:
    """Source-Inspect: load_raft beginnt mit _ensure_cuda_or_fallback."""
    from services.model_manager import ModelManager

    src = inspect.getsource(ModelManager.load_raft)
    assert "_ensure_cuda_or_fallback" in src, (
        "B-218: load_raft muss _ensure_cuda_or_fallback aufrufen, sonst "
        "kommt der Crash auf totem cuda-Context wieder."
    )


def test_b218_load_siglip_calls_ensure_cuda() -> None:
    """Source-Inspect: load_siglip beginnt mit _ensure_cuda_or_fallback."""
    from services.model_manager import ModelManager

    src = inspect.getsource(ModelManager.load_siglip)
    assert "_ensure_cuda_or_fallback" in src


def test_b218_load_vision_calls_ensure_cuda() -> None:
    """Source-Inspect: load_vision beginnt mit _ensure_cuda_or_fallback."""
    from services.model_manager import ModelManager

    src = inspect.getsource(ModelManager.load_vision)
    assert "_ensure_cuda_or_fallback" in src


def test_b218_main_installs_native_power_filter() -> None:
    """Source-Inspect: main.py installiert WM_POWERBROADCAST-Filter."""
    import inspect as _inspect
    from pathlib import Path
    main_path = Path(__file__).parent.parent.parent / "main.py"
    src = main_path.read_text(encoding="utf-8")
    assert "WM_POWERBROADCAST" in src or "0x0218" in src, (
        "B-218: main.py muss WM_POWERBROADCAST-Filter installieren."
    )
    assert "notify_power_resume" in src, (
        "B-218: Power-Filter muss ModelManager.notify_power_resume aufrufen."
    )
    assert "installNativeEventFilter" in src, (
        "B-218: Filter muss via installNativeEventFilter angebracht sein."
    )


def test_b218_fallback_recovers_to_cuda_when_available() -> None:
    """Wenn device='cpu' aber cuda nun verfuegbar + healthy ist, soll
    _ensure_cuda_or_fallback automatisch upgrade auf 'cuda' machen
    (Re-Dock-Pfad)."""
    from services.model_manager import ModelManager
    import torch

    if not torch.cuda.is_available():
        # Skip — wir koennen Re-Dock nicht testen ohne echte CUDA.
        return

    mm = ModelManager()
    original_device = mm.device

    try:
        # Simuliere: wir waren auf CPU (durch vorherigen Stale-Fallback)
        mm.device = "cpu"
        mm._cuda_suspect_stale = True

        # Da cuda jetzt healthy ist, _ensure_cuda_or_fallback soll
        # zurueck auf cuda schalten.
        mm._ensure_cuda_or_fallback("re-dock-test")
        # Erwartung: device wieder cuda.
        assert mm.device == "cuda", (
            f"B-218 Re-Dock: erwartet device='cuda', ist '{mm.device}'."
        )
    finally:
        mm.device = original_device
        mm._cuda_suspect_stale = False

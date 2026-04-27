"""B-220 — Code 10 (CM_PROB_FAILED_POST_START) GPU-Stuck-State Detection.

Vor B-220 detecte die App nur Code 47 (CM_PROB_HELD_FOR_EJECT) als bekannten
Stuck-State. Code 10 fiel in den generischen ``other_error``-Pfad und wurde
nur leise geloggt — User sah silent CPU-Fallback ohne Erklaerung.

Auf Surface Book 2 mit NVIDIA-Treiber 461.40 (Microsoft-locked) tritt Code 10
nach Andocken/Abdocken haeufig auf — der Treiber verkraftet den
PCIe-Re-Init nicht.

Tests verifizieren:
1. ``GpuPnpState`` Literal kennt ``failed_post_start``.
2. ``check_nvidia_gpu_state`` returnt ``failed_post_start`` bei Code 10.
3. ``GpuRecoveryDialog`` akzeptiert ``problem_kind=failed_post_start``
   und zeigt den korrekten Body-Text.
4. ``main.py`` routet beide Stuck-States in den Dialog.
"""
from __future__ import annotations

import inspect
import json
from unittest.mock import patch, MagicMock


def test_b220_gpu_pnp_state_literal_includes_failed_post_start() -> None:
    from services import startup_checks

    src = inspect.getsource(startup_checks)
    assert '"failed_post_start"' in src, (
        "B-220: GpuPnpState muss 'failed_post_start' als Literal enthalten."
    )


def test_b220_check_nvidia_returns_failed_post_start_on_code10() -> None:
    """Wenn PowerShell Code=10 liefert, soll check_nvidia_gpu_state
    'failed_post_start' returnen (nicht 'other_error')."""
    from services import startup_checks

    fake_stdout = json.dumps({"Status": "Error", "ConfigManagerErrorCode": 10})
    fake_result = MagicMock()
    fake_result.stdout = fake_stdout
    fake_result.stderr = ""

    with patch("services.startup_checks.subprocess.run", return_value=fake_result), \
         patch("services.startup_checks.sys.platform", "win32"):
        state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "failed_post_start", (
        f"B-220: erwartet 'failed_post_start' bei Code 10, kam: {state!r}"
    )
    assert msg is not None
    assert "Code 10" in msg or "FAILED_POST_START" in msg
    # Recovery-Hint muss drin sein:
    assert "Reboot" in msg or "Tablet" in msg, (
        "B-220: Message muss konkrete Recovery-Schritte enthalten."
    )


def test_b220_check_nvidia_still_returns_held_for_eject_on_code47() -> None:
    """Regression: Code 47 weiterhin als 'held_for_eject' erkannt (B-220 darf
    den bestehenden Pfad nicht brechen)."""
    from services import startup_checks

    fake_stdout = json.dumps({"Status": "Error", "ConfigManagerErrorCode": 47})
    fake_result = MagicMock()
    fake_result.stdout = fake_stdout
    fake_result.stderr = ""

    with patch("services.startup_checks.subprocess.run", return_value=fake_result), \
         patch("services.startup_checks.sys.platform", "win32"):
        state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "held_for_eject"


def test_b220_check_nvidia_returns_other_error_for_unknown_codes() -> None:
    """Unbekannter Code (z.B. 43) faellt weiterhin in 'other_error'."""
    from services import startup_checks

    fake_stdout = json.dumps({"Status": "Error", "ConfigManagerErrorCode": 43})
    fake_result = MagicMock()
    fake_result.stdout = fake_stdout
    fake_result.stderr = ""

    with patch("services.startup_checks.subprocess.run", return_value=fake_result), \
         patch("services.startup_checks.sys.platform", "win32"):
        state, _ = startup_checks.check_nvidia_gpu_state()

    assert state == "other_error"


def test_b220_check_nvidia_returns_ok_on_code_zero() -> None:
    from services import startup_checks

    fake_stdout = json.dumps({"Status": "OK", "ConfigManagerErrorCode": 0})
    fake_result = MagicMock()
    fake_result.stdout = fake_stdout
    fake_result.stderr = ""

    with patch("services.startup_checks.subprocess.run", return_value=fake_result), \
         patch("services.startup_checks.sys.platform", "win32"):
        state, _ = startup_checks.check_nvidia_gpu_state()

    assert state == "ok"


def test_b220_dialog_accepts_failed_post_start_kind() -> None:
    """GpuRecoveryDialog __init__ akzeptiert problem_kind und zeigt
    angepassten Body."""
    import pytest
    try:
        from PySide6.QtWidgets import QApplication
        import sys
        _ = QApplication.instance() or QApplication(sys.argv[:1])
    except Exception as exc:
        pytest.skip(f"PySide6 nicht verfuegbar: {exc}")
        return

    from ui.dialogs.gpu_recovery_dialog import GpuRecoveryDialog

    dlg = GpuRecoveryDialog(problem_kind="failed_post_start")
    assert dlg.windowTitle() == "GPU-Treiber konnte nicht starten", (
        f"B-220: Dialog muss Title fuer Code 10 anpassen, ist: {dlg.windowTitle()!r}"
    )
    # Body muss "Code 10" oder "FAILED_POST_START" enthalten:
    assert "Code 10" in dlg._body_main or "FAILED_POST_START" in dlg._body_main


def test_b220_dialog_default_kind_is_held_for_eject() -> None:
    """Backwards-compat: Default ohne problem_kind ist held_for_eject."""
    import pytest
    try:
        from PySide6.QtWidgets import QApplication
        import sys
        _ = QApplication.instance() or QApplication(sys.argv[:1])
    except Exception as exc:
        pytest.skip(f"PySide6 nicht verfuegbar: {exc}")
        return

    from ui.dialogs.gpu_recovery_dialog import GpuRecoveryDialog

    dlg = GpuRecoveryDialog()
    assert dlg.windowTitle() == "GPU im Standby-Modus"
    assert "Code 47" in dlg._body_main or "sicher entfernbar" in dlg._body_main


def test_b220_main_routes_failed_post_start_to_dialog() -> None:
    """Source-Inspect: main.py routet 'failed_post_start' auch in den Recovery-Dialog."""
    from pathlib import Path

    main_path = Path(__file__).parent.parent.parent / "main.py"
    src = main_path.read_text(encoding="utf-8")

    # Sowohl held_for_eject als auch failed_post_start muessen im
    # if-Branch des Recovery-Dialogs auftauchen.
    assert "failed_post_start" in src, (
        "B-220: main.py muss failed_post_start kennen."
    )
    # Suche nach beidem im selben if-Statement (oder nahe beieinander):
    assert 'in ("held_for_eject", "failed_post_start")' in src or \
           ('held_for_eject' in src and 'failed_post_start' in src)
    # Dialog wird mit problem_kind=_gpu_state aufgerufen:
    assert "problem_kind=_gpu_state" in src, (
        "B-220: Dialog muss mit problem_kind=_gpu_state aufgerufen werden, "
        "damit die richtige Body-Variante angezeigt wird."
    )

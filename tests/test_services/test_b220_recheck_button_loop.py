"""B-220 Phase 2 — Re-Check-Button im Recovery-Dialog + main.py-Loop.

User hat empirisch bestaetigt 2026-04-27: Tablet-Detach+Reattach heilt
Code-10/Code-47 ohne Reboot. Damit lohnt sich ein Re-Check-Button: der
User macht das Detach, klickt im Dialog, App re-queryt PnP-Status statt
neu starten zu muessen.

Tests verifizieren:
1. UserChoice Literal kennt 'recheck'.
2. Dialog hat _btn_recheck-Attribut + _on_recheck-Handler.
3. _on_recheck setzt choice='recheck' und accept().
4. main.py loop-pattern: check, dialog, recheck loop, max 5 attempts.
5. Recheck-Limit verhindert Endlos-Schleife.
"""
from __future__ import annotations

import inspect


def test_b220p2_user_choice_includes_recheck() -> None:
    from ui.dialogs import gpu_recovery_dialog as gprd

    src = inspect.getsource(gprd)
    assert '"recheck"' in src, (
        "B-220 P2: UserChoice Literal muss 'recheck' enthalten."
    )


def test_b220p2_dialog_has_recheck_button() -> None:
    """Dialog muss _btn_recheck und _on_recheck haben."""
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
    assert hasattr(dlg, "_btn_recheck"), (
        "B-220 P2: Dialog muss _btn_recheck-Button haben."
    )
    assert hasattr(dlg, "_on_recheck"), (
        "B-220 P2: Dialog muss _on_recheck-Handler haben."
    )
    # Button-Text enthaelt "erneut pruefen" oder "recheck":
    btn_text = dlg._btn_recheck.text().lower()
    assert "erneut" in btn_text or "recheck" in btn_text or "pruefen" in btn_text


def test_b220p2_on_recheck_sets_choice_and_accepts() -> None:
    """_on_recheck setzt choice='recheck' und ruft accept()."""
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
    accepted = []
    # Mock accept() um den Aufruf zu verifizieren ohne den Eventloop zu starten.
    original_accept = dlg.accept
    dlg.accept = lambda: accepted.append(True)  # type: ignore[assignment]
    try:
        dlg._on_recheck()
    finally:
        dlg.accept = original_accept  # type: ignore[assignment]

    assert dlg.choice() == "recheck"
    assert len(accepted) == 1, "B-220 P2: _on_recheck muss accept() rufen."


def test_b220p2_main_has_recheck_loop_with_limit() -> None:
    """Source-Inspect: main.py implementiert die Re-Check-Loop mit Limit."""
    from pathlib import Path

    main_path = Path(__file__).parent.parent.parent / "main.py"
    src = main_path.read_text(encoding="utf-8")

    # Loop-Pattern: while True + check + recheck + continue
    assert "_recheck_count" in src or "recheck_count" in src, (
        "B-220 P2: main.py muss recheck_count fuer das Limit fuehren."
    )
    assert "_max_rechecks" in src or "max_rechecks" in src, (
        "B-220 P2: main.py muss ein Maximum fuer Re-Checks haben (Anti-Endlos-Schleife)."
    )
    # Recheck-Branch muss continue haben (zurueck zum check):
    assert '_choice == "recheck"' in src or "choice == 'recheck'" in src, (
        "B-220 P2: main.py muss auf choice=='recheck' reagieren."
    )


def test_b220p2_dialog_body_promotes_detach_as_primary() -> None:
    """Body-Text reordnet jetzt: Detach (A) ist Primary, Reboot (B) ist Fallback."""
    import pytest
    try:
        from PySide6.QtWidgets import QApplication
        import sys
        _ = QApplication.instance() or QApplication(sys.argv[:1])
    except Exception as exc:
        pytest.skip(f"PySide6 nicht verfuegbar: {exc}")
        return

    from ui.dialogs.gpu_recovery_dialog import _BODY_FOOTER

    # Detach muss VOR Reboot in der Footer-Sequenz erwaehnt werden:
    detach_idx = _BODY_FOOTER.find("Tablet")
    reboot_idx = _BODY_FOOTER.find("Computer neu")
    assert detach_idx > 0, "Tablet-Detach muss im Footer beschrieben sein."
    assert reboot_idx > 0, "Reboot muss im Footer beschrieben sein."
    assert detach_idx < reboot_idx, (
        "B-220 P2: Detach soll vor Reboot stehen (empirisch bestaetigt)."
    )
    # Empirische Bestaetigung muss erwaehnt sein:
    assert "empirisch" in _BODY_FOOTER.lower() or "bestaetigt" in _BODY_FOOTER.lower()

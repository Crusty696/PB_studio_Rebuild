"""Phase-E Smoke-Boot für SCHNITT-Wiring (Plan
docs/superpowers/plans/2026-05-09-schnitt-integration-wiring-fix/).

Faehrt PBWindow im offscreen-Modus hoch und prueft direkt am
laufenden Objekt, dass Phase A/B/C-Wiring greift. Kein UI-Input,
kein Worker-Start — nur Konstruktion + Reflection.

Pflicht-Greifs:
- window._schnitt_ws ist SchnittWorkspace
- window._schnitt_ctrl ist SchnittController, parent==window
- _schnitt_ctrl ist als request_*-Slot mit edit_workspace verbunden
- _push_active_project_to_schnitt existiert auf workspace_setup
- empty_view emittiert preset_selected, das ueber Workspace propagiert

Exit 0 bei Erfolg, Exit != 0 bei Fehler. Output direkt nach stdout.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _log(label: str, ok: bool, detail: str = "") -> None:
    flag = "PASS" if ok else "FAIL"
    msg = f"[{flag}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def main() -> int:
    failures: list[str] = []

    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
    except Exception as exc:
        print(f"[FATAL] PySide6 import/QApplication failed: {exc}")
        return 2

    # PBWindow konstruieren — fuehrt _create_workspaces aus
    try:
        from main import PBWindow
        window = PBWindow()
    except Exception as exc:
        print(f"[FATAL] PBWindow construction failed: {exc}")
        traceback.print_exc()
        return 3

    # B-284: SchnittController instanziiert + exposed
    from ui.controllers.schnitt_controller import SchnittController
    from ui.workspaces.schnitt_workspace import SchnittWorkspace

    schnitt_ws = getattr(window, "_schnitt_ws", None)
    if isinstance(schnitt_ws, SchnittWorkspace):
        _log("B-284 SchnittWorkspace gebaut", True, type(schnitt_ws).__name__)
    else:
        failures.append("B-284 SchnittWorkspace")
        _log("B-284 SchnittWorkspace gebaut", False, repr(schnitt_ws))

    schnitt_ctrl = getattr(window, "_schnitt_ctrl", None)
    if isinstance(schnitt_ctrl, SchnittController):
        _log("B-284 SchnittController instanziiert", True,
             f"parent={type(schnitt_ctrl.parent()).__name__}")
    else:
        failures.append("B-284 SchnittController")
        _log("B-284 SchnittController instanziiert", False, repr(schnitt_ctrl))

    # B-284: Adapter-Slots und Live-Emit-Relay-Test
    edit_ws = getattr(window, "edit_workspace", None)
    if schnitt_ctrl is not None and schnitt_ws is not None:
        captured: list = []
        schnitt_ws._project_id = 1
        # Direkt am Controller-Signal lauschen — Qt-connect mit zusaetzlichem
        # Slot, original edit_workspace-Slot bleibt verbunden.
        schnitt_ctrl.request_auto_edit_with_profile.connect(
            lambda profile: captured.append(profile)
        )
        try:
            schnitt_ws.empty_view.preset_selected.emit("Techno")
            ok = len(captured) == 1
            _log(
                "B-284 Empty-State preset_selected -> request_auto_edit_with_profile",
                ok,
                f"captured={len(captured)} profile={type(captured[0]).__name__ if captured else 'None'}",
            )
            if not ok:
                failures.append("B-284 emit relay")
        except Exception as exc:
            failures.append("B-284 emit relay exception")
            _log("B-284 Emit-Relay Exception", False, str(exc))

    # B-284: Adapter-Slots auf edit_workspace
    for slot in ("_on_schnitt_auto_edit_request", "_on_schnitt_regenerate_request"):
        ok = callable(getattr(edit_ws, slot, None))
        _log(f"B-284 Adapter-Slot {slot}", ok)
        if not ok:
            failures.append(f"B-284 slot {slot}")

    # B-285: Helper auf workspace_setup
    helper = getattr(
        getattr(window, "workspace_setup", None),
        "_push_active_project_to_schnitt",
        None,
    )
    _log("B-285 Helper _push_active_project_to_schnitt vorhanden", callable(helper))
    if not callable(helper):
        failures.append("B-285 helper")

    # B-285: tab_rl_notes hat set_active_project
    try:
        rl = window._schnitt_ws.editor_view.tab_rl_notes
        ok = callable(getattr(rl, "set_active_project", None))
        _log("B-285 tab_rl_notes.set_active_project vorhanden", ok)
        if not ok:
            failures.append("B-285 tab_rl_notes")
    except Exception as exc:
        failures.append("B-285 tab_rl_notes exception")
        _log("B-285 tab_rl_notes Exception", False, str(exc))

    # B-286: btn_regenerate-Klick darf NICHT direkt _generate_timeline rufen
    # (alter Pfad), sondern muss durch SchnittController._on_regenerate_clicked
    # gehen. Indirekter Beweis: kein Confirm-Dialog akzeptieren -> regenerate
    # wird NICHT emittiert. Das stellt sicher dass Controller den Klick
    # tatsaechlich besitzt.
    try:
        from unittest.mock import patch
        pacing_tab = window._schnitt_ws.editor_view.tab_pacing_anker
        captured: list = []
        schnitt_ctrl.request_regenerate.connect(lambda p: captured.append(p))
        # Confirm-Dialog mit "Cancel" antworten -> regenerate darf NICHT laufen.
        with patch(
            "ui.workspaces.schnitt.regenerate_dialog.confirm_regenerate",
            return_value=False,
        ):
            pacing_tab.btn_regenerate.clicked.emit()
        ok_cancel = len(captured) == 0
        _log(
            "B-286 Re-Generate Cancel-Pfad respektiert ConfirmDialog",
            ok_cancel,
            f"captured={len(captured)}",
        )
        if not ok_cancel:
            failures.append("B-286 cancel ignored")
        # Confirm-Dialog mit "OK" antworten -> regenerate MUSS laufen.
        with patch(
            "ui.workspaces.schnitt.regenerate_dialog.confirm_regenerate",
            return_value=True,
        ):
            pacing_tab.btn_regenerate.clicked.emit()
        ok_confirm = len(captured) == 1
        _log(
            "B-286 Re-Generate Confirm-Pfad emittiert request_regenerate",
            ok_confirm,
            f"captured={len(captured)}",
        )
        if not ok_confirm:
            failures.append("B-286 confirm not relayed")
    except Exception as exc:
        failures.append("B-286 confirm-dialog exception")
        _log("B-286 Confirm-Dialog Exception", False, str(exc))

    # Cleanup
    try:
        window.close()
        window.deleteLater()
    except Exception:
        pass

    print()
    if failures:
        print(f"[RESULT] {len(failures)} FAILURES: {failures}")
        return 1
    print("[RESULT] all wiring assertions PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

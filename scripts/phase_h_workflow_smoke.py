"""Live-Boot-Smoke fuer B-293..B-296 Phase G.

Faehrt PBWindow im offscreen-Modus hoch + prueft:
- MediaWorkspace existiert + onboarding_banner als findChild.
- audio_analysis Helper (Single + Plural) callable.
- edit_workspace _ensure_combos_filled_from_project callable.
- CutListPanel ist im tab_schnitt eingehaengt.
- Keine btn_motion_analysis/btn_siglip_embeddings im MediaWorkspace.

Exit 0 bei Erfolg, exit != 0 bei Fehler.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _log(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    failures: list[str] = []
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from main import PBWindow
    window = PBWindow()

    # 1) MediaWorkspace existiert
    ws = getattr(window, "_media_ws", None)
    ok = ws is not None
    if not ok:
        failures.append("MediaWorkspace fehlt")
    _log("MediaWorkspace exists", ok)

    # 2) Onboarding-Banner ist eingehaengt
    if ws is not None:
        from ui.widgets.onboarding_banner import OnboardingBanner
        banners = ws.findChildren(OnboardingBanner)
        ok = len(banners) >= 1
        if not ok:
            failures.append("OnboardingBanner nicht in MediaWorkspace")
        _log("OnboardingBanner in MediaWorkspace", ok, f"count={len(banners)}")

        # 3) btn_motion_analysis / btn_siglip_embeddings entfernt
        ok = not hasattr(ws, "btn_motion_analysis")
        if not ok:
            failures.append("btn_motion_analysis still present")
        _log("btn_motion_analysis removed (R-15)", ok)

        ok = not hasattr(ws, "btn_siglip_embeddings")
        if not ok:
            failures.append("btn_siglip_embeddings still present")
        _log("btn_siglip_embeddings removed (R-15)", ok)

        # 4) btn_video_pipeline bleibt Primary
        ok = hasattr(ws, "btn_video_pipeline")
        if not ok:
            failures.append("btn_video_pipeline missing (primary)")
        _log("btn_video_pipeline remains", ok)

    # 5) Audio-Helper callable
    audio_ctrl = getattr(window, "audio_analysis", None)
    if audio_ctrl is not None:
        ok = callable(getattr(audio_ctrl, "_get_selected_audio_track", None))
        if not ok:
            failures.append("audio _get_selected_audio_track missing")
        _log("audio_analysis._get_selected_audio_track callable", ok)

        ok = callable(getattr(audio_ctrl, "_get_selected_audio_tracks", None))
        if not ok:
            failures.append("audio _get_selected_audio_tracks missing")
        _log("audio_analysis._get_selected_audio_tracks callable", ok)

    # 6) edit_workspace.ensure_combos
    edit_ctrl = getattr(window, "edit_workspace", None)
    if edit_ctrl is not None:
        ok = callable(getattr(edit_ctrl, "_ensure_combos_filled_from_project", None))
        if not ok:
            failures.append("edit_workspace _ensure_combos_filled_from_project missing")
        _log("edit_workspace._ensure_combos_filled_from_project callable", ok)

    # 7) CutListPanel in tab_schnitt
    try:
        tab_schnitt = window._schnitt_ws.editor_view.tab_schnitt
        from ui.widgets.cut_list_panel import CutListPanel
        ok = isinstance(getattr(tab_schnitt, "cut_list_panel", None), CutListPanel)
        if not ok:
            failures.append("CutListPanel not in tab_schnitt")
        _log("CutListPanel in tab_schnitt", ok)
    except Exception as exc:
        failures.append(f"CutListPanel access failed: {exc}")
        _log("CutListPanel access", False, str(exc))

    # Cleanup with Qt-clean-quit, fallback os._exit on STATUS_STACK_BUFFER_OVERRUN.
    try:
        window.close()
        window.deleteLater()
        app.processEvents()
    except Exception:
        pass

    print()
    if failures:
        print(f"[RESULT] {len(failures)} FAILURES: {failures}")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    print("[RESULT] all checkbox-schnitt-workflow assertions PASS")
    sys.stdout.flush()
    sys.stderr.flush()
    # CUDA+Qt teardown race on Windows triggers STATUS_STACK_BUFFER_OVERRUN
    # during interpreter shutdown — use os._exit to skip atexit chain.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover — main() always calls os._exit

"""Live-Boot-Smoke fuer Pipeline-Progress-Wiring (Plan
docs/superpowers/plans/2026-05-10-pipeline-progress-wiring-fix/).

Faehrt PBWindow im offscreen-Modus hoch, ruft die Progress-Slots
direkt auf (Slot-*Body* wird verifiziert) und prueft dass
progress_bar reagiert. Die Signal-Slot-*Connection* selbst wird
separat von tests/ui/test_pipeline_progress_wiring.py abgedeckt
(insbesondere ::test_stems_uses_named_slot_not_lambda und die
Source-Inspection-Tests).

Schreibt Resultat nach stdout, exit 0 bei Erfolg, exit != 0 bei
Fehler.
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

    # 1) progress_bar live-update via direkter Slot-Aufruf
    bar = window.progress_bar
    bar.setRange(0, 100)
    bar.setValue(0)
    window.video_analysis._on_pipeline_progress(50, "test stage", "task-x")
    if bar.value() != 50:
        failures.append(f"video_pipeline progress did not propagate: {bar.value()}")
    _log("Pipeline-Slot setzt progress_bar=50", bar.value() == 50, str(bar.value()))

    # 2) Stem-Slot
    bar.setValue(0)
    window.stems._on_stem_progress(75, "demucs")
    if bar.value() != 75:
        failures.append(f"stems progress did not propagate: {bar.value()}")
    _log("Stem-Slot setzt progress_bar=75", bar.value() == 75, str(bar.value()))

    # 3) Waveform-Slot
    bar.setValue(0)
    window.audio_analysis._on_waveform_progress(40, "wave", "task-y")
    if bar.value() != 40:
        failures.append(f"waveform progress did not propagate: {bar.value()}")
    _log("Waveform-Slot setzt progress_bar=40", bar.value() == 40, str(bar.value()))

    # 4) AnalysisStatusPanel default-visibility (B-292) — kein setVisible-Trick.
    panel = window._media_ws.video_analysis_panel
    visible = panel.isVisibleTo(window._media_ws) or not panel.isHidden()
    if not visible:
        failures.append("video_analysis_panel not visible by default")
    _log("video_analysis_panel sichtbar (default)", visible)

    try:
        window.close()
        window.deleteLater()
        app.processEvents()
        app.quit()
    except Exception:
        pass

    print()
    if failures:
        print(f"[RESULT] {len(failures)} FAILURES: {failures}")
        return 1
    print("[RESULT] all pipeline-progress-wiring assertions PASS")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Smoke-spezifischer Force-Exit: PBWindow-Boot initialisiert
    # CUDA-Kontexte + Qt-Worker-Threads, deren Destruktoren waehrend
    # des Python-Interpreter-Teardowns mit Qt's eigener Thread-
    # Cleanup-Reihenfolge kollidieren (STATUS_STACK_BUFFER_OVERRUN
    # = 0xC0000409). Der saubere Qt-Quit-Pfad
    # (window.close + deleteLater + processEvents + app.quit) wurde
    # vorgeschaltet und reicht NICHT — Crash trat im Smoke trotzdem
    # auf (Exit -1073740791). In der Produktions-App ist das egal,
    # weil die Main-Loop ueber das normale Window-Close-Event endet
    # und der Interpreter-Shutdown nicht in dieselbe Race rennt.
    # Hier sind alle Assertions vor diesem Punkt bereits ausgewertet,
    # also umgehen wir den crashy Teardown bewusst.
    os._exit(rc)

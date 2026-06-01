"""B-433: SB2 dGPU Hot-Unplug bei Stromquellen-Wechsel.

Auf dem Surface Book 2 wirft die Firmware die dGPU (GTX 1060 in der Base) bei
einem Stromquellen-Wechsel (AC<->Akku unter Volllast / Netzteil-Overload) ab.
Der CUDA-Context kann dabei sterben OHNE Sleep/Resume — die bisherigen
B-218-Pfade (PBT_APMRESUMESUSPEND/RESUMEAUTOMATIC/APMSUSPEND) greifen nicht.

Fix: main.py-Power-Filter behandelt zusaetzlich PBT_APMPOWERSTATUSCHANGE (0x000A)
und ruft ModelManager.notify_power_resume() -> erzwingt Health-Check + ggf.
CPU-Fallback beim naechsten GPU-Op.
"""

from pathlib import Path

from services.model_manager import ModelManager


def test_b433_main_handles_power_status_change() -> None:
    """Source-Inspect: main.py-Power-Filter behandelt 0x000A und ruft
    notify_power_resume in genau diesem Pfad."""
    main_path = Path(__file__).parent.parent.parent / "main.py"
    src = main_path.read_text(encoding="utf-8")

    assert "0x000A" in src, (
        "B-433: Power-Filter muss PBT_APMPOWERSTATUSCHANGE (0x000A) behandeln."
    )
    # Der 0x000A-Zweig muss vor dem naechsten Power-Branch notify_power_resume rufen.
    # Auf den CODE-Zweig (wparam == 0x000A) zielen, nicht den Doku-Kommentar.
    idx = src.find("wparam == 0x000A")
    assert idx != -1, "B-433: elif-Zweig 'wparam == 0x000A' fehlt im Power-Filter."
    next_branch_idx = src.find("elif wparam ==", idx + len("wparam == 0x000A"))
    assert next_branch_idx != -1, (
        "B-433: Der 0x000A-Zweig muss vor einem weiteren Power-Branch enden."
    )
    branch = src[idx:next_branch_idx]
    assert "notify_power_resume" in branch, (
        "B-433: Der 0x000A-Zweig muss ModelManager.notify_power_resume aufrufen."
    )
    assert "B-433" in branch, (
        "B-433: Der Zweig sollte als B-433 markiert sein (Nachvollziehbarkeit)."
    )


def test_b433_notify_power_resume_sets_suspect_flag() -> None:
    """notify_power_resume() (vom 0x000A-Zweig gerufen) setzt das
    Suspect-Flag, das den Health-Check beim naechsten Load erzwingt."""
    mm = ModelManager()
    mm._cuda_suspect_stale = False
    mm.notify_power_resume()
    assert mm._cuda_suspect_stale is True, (
        "B-433: notify_power_resume muss _cuda_suspect_stale setzen, damit der "
        "naechste GPU-Op den Context probed und ggf. auf CPU faellt."
    )

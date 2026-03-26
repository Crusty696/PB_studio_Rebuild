"""Final Swarm Integration Test - alle 3 Agenten."""
import sys
import os

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import time
    import json
    import torch

    print("=" * 60, flush=True)
    print("PB STUDIO 3-AGENTEN SWARM - FINAL TEST", flush=True)
    print("=" * 60, flush=True)

    print(f"Device: {'CUDA' if torch.cuda.is_available() else 'CPU'}", flush=True)

    import services.register_actions
    from services.action_registry import action_registry
    from services.model_manager import ModelManager

    VIDEO_WITH_AUDIO = r"C:\Users\david\Documents\test_data\video\Sora_20250622_0307_100_Generations\Gothic_Goddess_Bioluminescent_Jungle_Video.mp4"
    VIDEO_NO_AUDIO = r"C:\Users\david\Documents\test_data\video\generation 4\20250612_2109_Neon_Forest_Rave_gen_01jxjzjy17ez3t5v8ca6dbka6a.mp4"

    mm = ModelManager()
    results = {}
    total_start = time.time()

    # TEST 1: Audio-Stream-Check
    print("\n[TEST 1] Video ohne Audio -> Fehler erwartet", flush=True)
    r = action_registry.execute("transcribe_audio", {"file_path": VIDEO_NO_AUDIO})
    ok = "Keine Audio-Spur" in str(r.get("error", ""))
    results["audio_stream_check"] = ok
    print(f"  {'PASS' if ok else 'FAIL'}: {r.get('error', 'no error')}", flush=True)

    # TEST 2: Whisper Transkription
    print("\n[TEST 2] Whisper auf 8s Video mit Audio", flush=True)
    start = time.time()
    r = action_registry.execute("transcribe_audio", {"file_path": VIDEO_WITH_AUDIO})
    elapsed = time.time() - start
    has_no_error = r.get("error") is None
    results["whisper_transcription"] = has_no_error
    print(f"  {'PASS' if has_no_error else 'FAIL'}: lang={r.get('language')}, segments={r.get('segment_count')}, {elapsed:.1f}s", flush=True)
    print(f"  Text: {r.get('full_text', '(kein Text)')[:150]}", flush=True)
    print(f"  Model: {mm.current_model_id} ({mm.model_type})", flush=True)

    # TEST 3: Vision-Analyse
    print("\n[TEST 3] Vision-Analyse auf Video", flush=True)
    mode = "GPU/Moondream2" if torch.cuda.is_available() else "CPU/OpenCV-Fallback"
    print(f"  Modus: {mode}", flush=True)
    start = time.time()
    r = action_registry.execute("analyze_video_content", {
        "file_path": VIDEO_NO_AUDIO,
        "interval_sec": 5.0,
        "max_frames": 2,
    })
    elapsed = time.time() - start
    ok = isinstance(r, dict) and r.get("error") is None and len(r.get("scenes", [])) > 0
    results["vision_analysis"] = ok
    print(f"  {'PASS' if ok else 'FAIL'}: {elapsed:.1f}s", flush=True)
    if ok:
        for s in r.get("scenes", []):
            print(f"  [{s['timestamp_sec']}s] {s['description'][:120]}", flush=True)
    else:
        print(f"  Error: {r.get('error')}", flush=True)

    # TEST 4: Model Swap
    print("\n[TEST 4] Model Swap Verification", flush=True)
    mm.load_whisper("tiny")
    ok = mm.model_type == "whisper" and mm.current_model_id == "whisper-tiny"
    results["model_swap"] = ok
    print(f"  {'PASS' if ok else 'FAIL'}: type={mm.model_type}, id={mm.current_model_id}", flush=True)
    mm.unload()
    ok2 = mm.current_model_id is None
    results["model_unload"] = ok2
    print(f"  {'PASS' if ok2 else 'FAIL'}: unloaded={mm.current_model_id is None}", flush=True)

    # TEST 5: Orchestrator Multi-Step Detection
    print("\n[TEST 5] Orchestrator Multi-Step Detection", flush=True)
    from agents.orchestrator_agent import OrchestratorAgent
    orch = OrchestratorAgent()
    tests_ok = all([
        orch._detect_multi_step("Analysiere Bild und Ton von Video 1"),
        orch._detect_multi_step("Was passiert im Video und was wird gesagt?"),
        not orch._detect_multi_step("Analysiere das Audio"),
    ])
    results["multi_step_detection"] = tests_ok
    print(f"  {'PASS' if tests_ok else 'FAIL'}", flush=True)

    # TEST 6: Full Agent Routing
    print("\n[TEST 6] Agent Routing", flush=True)
    from agents.audio_agent import AudioAgent
    from agents.vision_agent import VisionAgent
    a = orch._route_to_agent("Transkribiere Audio Track 1")
    v = orch._route_to_agent("Was passiert visuell im Video?")
    ok = isinstance(a, AudioAgent) and isinstance(v, VisionAgent)
    results["agent_routing"] = ok
    print(f"  {'PASS' if ok else 'FAIL'}: audio={type(a).__name__}, vision={type(v).__name__}", flush=True)

    # SUMMARY
    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60, flush=True)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'} {name}", flush=True)
    print(f"\nResult: {passed}/{total} tests passed ({total_elapsed:.1f}s total)", flush=True)
    print("=" * 60, flush=True)

    # Save results
    output_path = os.path.join(os.path.dirname(__file__), "swarm_test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved: {output_path}", flush=True)


if __name__ == "__main__":
    main()

import sys, json, os
sys.stdout = open("C:/Users/david/Documents/App_Projekte/PB_studio_Rebuild/poc_bt_log.txt", "w")
sys.stderr = sys.stdout

try:
    import torch, time, numpy as np

    R = {}
    sr = 22050
    torch.cuda.empty_cache()

    print("importing beat_this...", flush=True)
    from beat_this.inference import Audio2Beats

    torch.cuda.reset_peak_memory_stats()
    model = Audio2Beats(device='cuda', dbn=False)
    R["model_vram_mb"] = round(torch.cuda.memory_allocated() / 1024**2)
    print(f"Model: {R['model_vram_mb']} MB", flush=True)

    for dur in [30, 60, 120, 300]:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        sig = np.random.randn(sr * dur).astype(np.float32) * 0.1
        t0 = time.time()
        try:
            b, d = model(sig, sr)
            dt = time.time() - t0
            peak = round(torch.cuda.max_memory_allocated() / 1024**2)
            R[f"{dur}s"] = {"ok": True, "time_s": round(dt,2), "vram_peak_mb": peak, "beats": len(b), "downbeats": len(d)}
            print(f"{dur}s: {dt:.1f}s, VRAM peak {peak} MB, {len(b)} beats, {len(d)} downbeats", flush=True)
        except torch.cuda.OutOfMemoryError:
            R[f"{dur}s"] = {"ok": False, "error": "OOM"}
            print(f"{dur}s: OOM!", flush=True)
            torch.cuda.empty_cache()
        del sig

    # Real audio test - 60s chunk
    torch.cuda.empty_cache()
    from beat_this.preprocessing import load_audio
    test_file = r"C:\Users\david\Documents\test_data\audio\Crusty_Progressive Psy Set2.mp3"
    print(f"Loading audio: {test_file}", flush=True)
    signal, file_sr = load_audio(test_file)
    total_dur = len(signal) / file_sr
    R["real_audio_duration_s"] = round(total_dur)
    print(f"Audio loaded: {total_dur:.0f}s", flush=True)

    for chunk_dur in [60, 120]:
        chunk = signal[:int(chunk_dur * file_sr)]
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        try:
            b, d = model(chunk, file_sr)
            dt = time.time() - t0
            peak = round(torch.cuda.max_memory_allocated() / 1024**2)
            bpm = round(60.0 / float(np.median(np.diff(b))), 1) if len(b) > 1 else None
            R[f"real_{chunk_dur}s"] = {
                "ok": True, "time_s": round(dt,2), "vram_peak_mb": peak,
                "beats": len(b), "downbeats": len(d), "bpm": bpm,
                "first_beats": [round(float(x),3) for x in b[:5]],
                "first_downbeats": [round(float(x),3) for x in d[:5]],
            }
            print(f"Real {chunk_dur}s: {dt:.1f}s, VRAM {peak} MB, {len(b)} beats, {len(d)} downbeats, BPM={bpm}", flush=True)
        except torch.cuda.OutOfMemoryError:
            R[f"real_{chunk_dur}s"] = {"ok": False, "error": "OOM"}
            print(f"Real {chunk_dur}s: OOM!", flush=True)
            torch.cuda.empty_cache()

    with open("C:/Users/david/Documents/App_Projekte/PB_studio_Rebuild/poc_bt_results.json", "w") as f:
        json.dump(R, f, indent=2)
    print("DONE", flush=True)

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FATAL: {e}", flush=True)

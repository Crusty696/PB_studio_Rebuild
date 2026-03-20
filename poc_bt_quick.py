import torch, time, numpy as np, json, sys

R = {}
sr = 22050
torch.cuda.empty_cache()

from beat_this.inference import Audio2Beats
torch.cuda.reset_peak_memory_stats()
model = Audio2Beats(device='cuda', dbn=False)
R["model_vram_mb"] = round(torch.cuda.memory_allocated() / 1024**2)
print(f"Model: {R['model_vram_mb']} MB", flush=True)

# Test increasing durations
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

with open("C:/Users/david/Documents/App_Projekte/PB_studio_Rebuild/poc_bt_results.json", "w") as f:
    json.dump(R, f, indent=2)
print("DONE", flush=True)

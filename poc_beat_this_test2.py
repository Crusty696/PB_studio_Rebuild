"""Quick VRAM scaling test for beat_this"""
import torch, time, numpy as np, sys, json

OUT = "C:/Users/david/Documents/App_Projekte/PB_studio_Rebuild/poc_beat_this_results.json"
results = {}

torch.cuda.empty_cache()
sr = 22050

from beat_this.inference import Audio2Beats

torch.cuda.reset_peak_memory_stats()
model = Audio2Beats(device='cuda', dbn=False)
vram_model = torch.cuda.memory_allocated() / 1024**2
results["model_vram_mb"] = round(vram_model)

for dur in [30, 60, 120, 300, 600]:
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    signal = np.random.randn(sr * dur).astype(np.float32) * 0.1
    t0 = time.time()
    try:
        beats, downbeats = model(signal, sr)
        t1 = time.time()
        vram_peak = torch.cuda.max_memory_allocated() / 1024**2
        results[f"{dur}s"] = {
            "time": round(t1-t0, 2),
            "vram_peak_mb": round(vram_peak),
            "beats": len(beats),
            "downbeats": len(downbeats),
            "status": "OK"
        }
    except torch.cuda.OutOfMemoryError:
        results[f"{dur}s"] = {"status": "OOM"}
        torch.cuda.empty_cache()
    del signal

# Now test with real audio - load and chunk it
torch.cuda.empty_cache()
try:
    from beat_this.preprocessing import load_audio
    test_file = r"C:\Users\david\Documents\test_data\audio\Crusty_Progressive Psy Set2.mp3"
    signal, file_sr = load_audio(test_file)
    total_dur = len(signal) / file_sr
    results["real_audio_duration_s"] = round(total_dur)

    # Process first 120 seconds only
    chunk_samples = int(120 * file_sr)
    chunk = signal[:chunk_samples]

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    beats, downbeats = model(chunk, file_sr)
    t1 = time.time()
    vram_peak = torch.cuda.max_memory_allocated() / 1024**2

    results["real_120s_chunk"] = {
        "time": round(t1-t0, 2),
        "vram_peak_mb": round(vram_peak),
        "beats": len(beats),
        "downbeats": len(downbeats),
        "first_5_beats": [round(float(b), 3) for b in beats[:5]],
        "first_5_downbeats": [round(float(b), 3) for b in downbeats[:5]],
        "bpm": round(60.0 / float(np.median(np.diff(beats))), 1) if len(beats) > 1 else None
    }
except Exception as e:
    results["real_audio_error"] = str(e)

# CPU test for comparison
del model
torch.cuda.empty_cache()
try:
    model_cpu = Audio2Beats(device='cpu', dbn=False)
    signal30 = np.random.randn(sr * 30).astype(np.float32) * 0.1
    t0 = time.time()
    beats, downbeats = model_cpu(signal30, sr)
    t1 = time.time()
    results["cpu_30s"] = {"time": round(t1-t0, 2), "beats": len(beats)}
    del model_cpu
except Exception as e:
    results["cpu_error"] = str(e)

with open(OUT, "w") as f:
    json.dump(results, f, indent=2)

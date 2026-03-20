"""
PoC #3: beat_this Machbarkeit auf Windows + GTX 1060 (6GB VRAM)
================================================================
Wegwerf-Skript. Testet Installation, Import, CUDA, VRAM, Inferenz.
"""
import sys
import time
import subprocess
import os
import json

SEPARATOR = "=" * 70
RESULTS = {
    "python_version": sys.version,
    "installation": None,
    "import_ok": False,
    "cuda_available": False,
    "vram_total_mb": None,
    "vram_model_mb": None,
    "vram_peak_inference_mb": None,
    "model_load_time_s": None,
    "inference_time_s": None,
    "beats_returned": False,
    "downbeats_returned": False,
    "num_beats": 0,
    "num_downbeats": 0,
    "estimated_bpm": None,
    "madmom_required": None,
    "errors": [],
    "verdict": None,
}

TEST_AUDIO = None
test_dir = r"C:\Users\david\Documents\test_data\audio"
if os.path.isdir(test_dir):
    for f in os.listdir(test_dir):
        if f.endswith(('.wav', '.mp3', '.m4a', '.flac')):
            TEST_AUDIO = os.path.join(test_dir, f)
            break

def section(title):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


# ── 1. System Info ──────────────────────────────────────────
section("1. SYSTEM INFO")
print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")
print(f"Test-Audio: {TEST_AUDIO}")

# Check torch + CUDA
try:
    import torch
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    RESULTS["cuda_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
        total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**2
        RESULTS["vram_total_mb"] = round(total_vram)
        print(f"Total VRAM: {total_vram:.0f} MB")
    HAS_CUDA = torch.cuda.is_available()
except ImportError:
    print("ERROR: PyTorch not installed!")
    HAS_CUDA = False


# ── 2. Install beat-this ────────────────────────────────────
section("2. INSTALL beat-this")
try:
    import beat_this
    print(f"beat_this already installed")
    RESULTS["installation"] = "OK (already installed)"
    INSTALLED = True
except ImportError:
    print("beat_this not found. Installing with pip...")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "beat-this"],
        capture_output=True, text=True, timeout=600
    )
    install_time = time.time() - t0

    if result.returncode == 0:
        print(f"Installation OK in {install_time:.1f}s")
        RESULTS["installation"] = "OK"
        INSTALLED = True

        # Check if madmom was pulled in
        if "madmom" in result.stdout.lower() + result.stderr.lower():
            print("[WARN] madmom was pulled as dependency!")
            RESULTS["madmom_required"] = True
        else:
            RESULTS["madmom_required"] = False
    else:
        err = result.stderr[-1500:] if result.stderr else result.stdout[-1500:]
        print(f"Installation FAILED:\n{err}")
        RESULTS["installation"] = "FAILED"
        RESULTS["errors"].append(f"pip install failed: {err[:500]}")
        INSTALLED = False


# ── 3. Check madmom dependency ──────────────────────────────
section("3. MADMOM CHECK")
try:
    import madmom
    print(f"madmom IS installed (potential problem)")
    RESULTS["madmom_required"] = True
except ImportError:
    print("madmom NOT installed (good - beat_this should work without it)")
    if RESULTS["madmom_required"] is None:
        RESULTS["madmom_required"] = False


# ── 4. Import beat_this ─────────────────────────────────────
section("4. IMPORT beat_this")
IMPORT_OK = False
if INSTALLED:
    try:
        import beat_this
        print("import beat_this: OK")
        print(f"  dir: {[x for x in dir(beat_this) if not x.startswith('_')]}")

        from beat_this.inference import File2Beats
        print("from beat_this.inference import File2Beats: OK")

        # Check File2Beats signature
        import inspect
        sig = inspect.signature(File2Beats.__init__)
        print(f"  File2Beats params: {list(sig.parameters.keys())}")

        IMPORT_OK = True
        RESULTS["import_ok"] = True
    except ImportError as e:
        print(f"Import FAILED: {e}")
        RESULTS["errors"].append(f"import failed: {e}")
    except Exception as e:
        print(f"Import ERROR: {type(e).__name__}: {e}")
        RESULTS["errors"].append(f"import error: {e}")


# ── 5. Model Loading + VRAM ─────────────────────────────────
MODEL = None
if IMPORT_OK:
    section("5. MODEL LOADING + VRAM")

    device = "cuda" if HAS_CUDA else "cpu"
    print(f"Device: {device}")

    if HAS_CUDA:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        vram_before = torch.cuda.memory_allocated() / 1024**2
        print(f"VRAM before load: {vram_before:.1f} MB")

    t0 = time.time()
    try:
        MODEL = File2Beats(device=device, dbn=False)  # dbn=False avoids madmom
        load_time = time.time() - t0
        RESULTS["model_load_time_s"] = round(load_time, 2)
        print(f"Model loaded in {load_time:.2f}s (dbn=False, no madmom)")

        if HAS_CUDA:
            vram_after = torch.cuda.memory_allocated() / 1024**2
            vram_peak = torch.cuda.max_memory_allocated() / 1024**2
            vram_model = vram_after - vram_before
            RESULTS["vram_model_mb"] = round(vram_model)
            print(f"VRAM model footprint: {vram_model:.0f} MB")
            print(f"VRAM peak during load: {vram_peak:.0f} MB")
            print(f"VRAM remaining: {RESULTS['vram_total_mb'] - vram_after:.0f} MB")
    except Exception as e:
        print(f"Model load FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        RESULTS["errors"].append(f"model load: {e}")


# ── 6. Inference ────────────────────────────────────────────
if MODEL is not None:
    section("6. INFERENCE TEST")

    if TEST_AUDIO is None:
        print("No test audio files found in test_data/audio/")
    else:
        print(f"File: {os.path.basename(TEST_AUDIO)}")
        file_size_mb = os.path.getsize(TEST_AUDIO) / 1024**2
        print(f"Size: {file_size_mb:.1f} MB")

        if HAS_CUDA:
            torch.cuda.reset_peak_memory_stats()
            vram_before_inf = torch.cuda.memory_allocated() / 1024**2

        t0 = time.time()
        try:
            result = MODEL(TEST_AUDIO)
            inference_time = time.time() - t0
            RESULTS["inference_time_s"] = round(inference_time, 2)
            print(f"Inference time: {inference_time:.2f}s")

            if HAS_CUDA:
                vram_peak_inf = torch.cuda.max_memory_allocated() / 1024**2
                RESULTS["vram_peak_inference_mb"] = round(vram_peak_inf)
                print(f"VRAM peak during inference: {vram_peak_inf:.0f} MB")

            # Parse result
            if isinstance(result, tuple) and len(result) == 2:
                beats, downbeats = result
                RESULTS["beats_returned"] = len(beats) > 0
                RESULTS["downbeats_returned"] = len(downbeats) > 0
                RESULTS["num_beats"] = len(beats)
                RESULTS["num_downbeats"] = len(downbeats)
                print(f"Beats: {len(beats)}, Downbeats: {len(downbeats)}")
                if len(beats) > 1:
                    intervals = [b2 - b1 for b1, b2 in zip(beats[:-1], beats[1:])]
                    avg_interval = sum(intervals) / len(intervals)
                    bpm = 60.0 / avg_interval if avg_interval > 0 else 0
                    RESULTS["estimated_bpm"] = round(bpm, 1)
                    print(f"Estimated BPM: {bpm:.1f}")
                if len(beats) > 0:
                    print(f"First 5 beats (s): {[round(float(b), 3) for b in beats[:5]]}")
                if len(downbeats) > 0:
                    print(f"First 5 downbeats (s): {[round(float(b), 3) for b in downbeats[:5]]}")
            elif isinstance(result, dict):
                print(f"Result keys: {list(result.keys())}")
                for k, v in result.items():
                    if hasattr(v, '__len__'):
                        print(f"  {k}: {len(v)} items")
            else:
                print(f"Result type: {type(result)}, value: {result}")

        except Exception as e:
            print(f"Inference FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            RESULTS["errors"].append(f"inference: {e}")


# ── 7. VRAM Budget ──────────────────────────────────────────
section("7. VRAM BUDGET ANALYSIS (GTX 1060 6GB)")
if HAS_CUDA and MODEL is not None:
    total = RESULTS["vram_total_mb"]
    model = RESULTS.get("vram_model_mb", 0) or 0
    peak = RESULTS.get("vram_peak_inference_mb", 0) or 0
    demucs_est = 1800  # typical demucs htdemucs VRAM

    print(f"Total VRAM:              {total} MB")
    print(f"beat_this model:         {model} MB")
    print(f"beat_this peak (infer):  {peak} MB")
    print(f"Demucs estimate:         ~{demucs_est} MB")
    print()
    print(f"Sequential use (load one, unload, load other):")
    print(f"  beat_this fits:        {'YES' if peak < total else 'NO'} ({peak}/{total} MB)")
    print(f"  demucs fits:           {'YES' if demucs_est < total else 'NO'} (~{demucs_est}/{total} MB)")
    print(f"  Both sequential:       {'FEASIBLE' if max(peak, demucs_est) < total else 'TIGHT'}")
else:
    print("Cannot measure - no CUDA or model not loaded")


# ── 8. Cleanup ──────────────────────────────────────────────
if MODEL is not None:
    del MODEL
    if HAS_CUDA:
        torch.cuda.empty_cache()
        vram_cleanup = torch.cuda.memory_allocated() / 1024**2
        print(f"\nVRAM after cleanup: {vram_cleanup:.1f} MB")


# ── 9. Librosa Fallback ────────────────────────────────────
section("8. LIBROSA FALLBACK CHECK")
try:
    import librosa
    print(f"librosa available: {librosa.__version__}")
    if TEST_AUDIO:
        t0 = time.time()
        y, sr = librosa.load(TEST_AUDIO, sr=22050, duration=30)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        t1 = time.time()
        beat_times = librosa.frames_to_time(beats, sr=sr)
        print(f"librosa beat_track: {len(beat_times)} beats in {t1-t0:.2f}s, tempo={tempo}")
        print(f"WARNING: librosa has NO downbeat detection!")
except ImportError:
    print("librosa not installed")
except Exception as e:
    print(f"librosa test error: {e}")


# ── VERDICT ─────────────────────────────────────────────────
section("FINAL VERDICT")

if RESULTS["installation"] and "OK" in str(RESULTS["installation"]) and RESULTS["import_ok"]:
    vram_peak = RESULTS.get("vram_peak_inference_mb", 0) or 0
    if vram_peak > 5000:
        RESULTS["verdict"] = f"NO-GO: VRAM too high ({vram_peak}MB for 6GB card)"
    elif RESULTS.get("madmom_required"):
        RESULTS["verdict"] = "CONDITIONAL GO: works but madmom dependency is problematic"
    elif RESULTS.get("errors"):
        RESULTS["verdict"] = f"CONDITIONAL GO: works with issues: {RESULTS['errors']}"
    else:
        RESULTS["verdict"] = "GO: beat_this works on Windows + CUDA, fits in 6GB VRAM"
elif not INSTALLED:
    RESULTS["verdict"] = "NO-GO: installation failed"
else:
    RESULTS["verdict"] = "NO-GO: import failed"

print(json.dumps(RESULTS, indent=2, default=str))
print(f"\n>>> {RESULTS['verdict']} <<<")
print(SEPARATOR)

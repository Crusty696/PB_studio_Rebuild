
import os
import sys
import platform
import subprocess

print("=== PB Studio Hardware Diag ===")
print(f"OS: {platform.system()} {platform.release()}")
print(f"Python: {sys.version}")

try:
    import torch
    print(f"PyTorch Version: {torch.__version__}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA Version: {torch.version.cuda}")
        print(f"GPU Device: {torch.cuda.get_device_name(0)}")
        print(f"VRAM Total: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    else:
        print("CUDA NOT AVAILABLE (This is the problem!)")
except ImportError:
    print("PyTorch not installed!")

print("\n--- Environment Variables ---")
for key in ["CUDA_VISIBLE_DEVICES", "OLLAMA_KEEP_ALIVE"]:
    print(f"{key}: {os.environ.get(key)}")

print("\n--- Windows GPU Info (WMIC) ---")
try:
    # M-10 FIX: Removed shell=True to prevent command injection
    res = subprocess.check_output(
        ["wmic", "path", "win32_VideoController", "get", "name"],
        timeout=10
    ).decode()
    print(res)
except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
    print(f"Could not get WMIC info: {e}")

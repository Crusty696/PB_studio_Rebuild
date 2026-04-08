import sys
import os
from pathlib import Path
PROJECT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

from services.startup_checks import check_system
import sys

print("Running check_system()...")
status = check_system(Path("."))
print(f"FFmpeg OK: {status.ffmpeg_ok}")
print(f"FFprobe OK: {status.ffprobe_ok}")
print(f"CUDA OK: {status.cuda_ok}")
print(f"Disk OK: {status.disk_ok} ({status.disk_free_gb:.2f} GB)")
print(f"Ollama OK: {status.ollama_ok}")
print(f"Errors: {status.errors}")
print(f"Warnings: {status.warnings}")

if status.errors:
    print("\nSYSTEM HAS ERRORS!")
    sys.exit(1)
else:
    print("\nSYSTEM IS OK (or has only warnings)")
    sys.exit(0)

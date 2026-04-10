
import os
import sys
import subprocess
import torch
from pathlib import Path

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        return f"Fehler beim Ausführen: {e}"

def check_gpu_health():
    print("="*60)
    print("   PB STUDIO - GPU HARDWARE & SOFTWARE HEALTH CHECK")
    print("="*60)

    # 1. Windows Hardware Status
    print("\n[1/4] Windows Geräte-Status...")
    gpu_status = run_cmd("Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' } | Select-Object Name, Status | Format-Table -HideTableHeaders")
    if "OK" in gpu_status:
        print(f" ✅ HARDWARE: {gpu_status.strip()} ist bereit.")
    else:
        print(f" ❌ HARDWARE-FEHLER: {gpu_status.strip() or 'NVIDIA nicht gefunden'}")
        print("    -> Bitte PC neu starten oder Treiber neu installieren.")

    # 2. PyTorch CUDA Link
    print("\n[2/4] PyTorch & CUDA Verbindung...")
    try:
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            print(f" ✅ CUDA: Aktiv. Gerät: {device_name}")
        else:
            print(" ❌ CUDA: Nicht verfügbar (PyTorch kann die GPU nicht nutzen).")
    except Exception as e:
        print(f" ❌ CUDA-INITIALISIERUNGSFEHLER: {e}")

    # 3. VRAM & Memory Check
    print("\n[3/4] VRAM Auslastung...")
    if torch.cuda.is_available():
        try:
            free, total = torch.cuda.mem_get_info(0)
            free_gb = free / 1024**3
            total_gb = total / 1024**3
            print(f" ✅ SPEICHER: {free_gb:.1f} GB von {total_gb:.1f} GB frei.")
            if free_gb < 1.0:
                print(" ⚠️ WARNUNG: Sehr wenig VRAM frei. Schließe andere Programme (Browser, Ollama).")
        except Exception as e:
            print(f" ❌ VRAM-Check fehlgeschlagen: {e}")
    else:
        print(" ── VRAM-Check übersprungen (kein CUDA).")

    # 4. FFmpeg NVENC Unterstützung
    print("\n[4/4] Video-Hardware-Encoder (NVENC)...")
    ffmpeg_path = os.path.join("bin", "ffmpeg.exe")
    if os.path.exists(ffmpeg_path):
        encoders = run_cmd(f"{ffmpeg_path} -hide_banner -encoders")
        if "h264_nvenc" in encoders:
            print(" ✅ NVENC: Hardware-Encoding ist verfügbar.")
        else:
            print(" ❌ NVENC: Hardware-Encoding fehlt in FFmpeg oder wird vom Treiber blockiert.")
    else:
        print(" ❌ FFmpeg nicht im bin-Ordner gefunden.")

    print("\n" + "="*60)
    print("   DIAGNOSE BEENDET")
    print("="*60)

if __name__ == "__main__":
    check_gpu_health()

# STAB-6 — Release Build & Packaging Evidence (2026-08-29)

status: code-complete-live-pending

## Zusammenfassung

Der vollständige Produktions-Build für PB Studio v0.5.0 wurde erfolgreich durchgeführt.
Sowohl der PyInstaller Frozen-Build (`dist/pb_studio/`) als auch das NSISBI-Payload-Installerpaar (`pb_studio_setup_v0.5.0.exe` + `.nsisbin`) wurden fehlerfrei generiert und per Smoke-Test validiert.

## Erzeugte Artefakte

1. **Frozen App Ordner (`ART-001`):** `dist/pb_studio/` (Gesamtgröße: 4.98 GB)
   - PyInstaller 6.20.0 mit Python 3.10.21, PyTorch 1.12.1+cu113 (NVIDIA GTX 1060).
   - 38 doppelte Top-Level DLLs (3.55 GB) durch `prune_pyinstaller_dist.py` bereinigt.
   - Enthält alle erforderlichen Binaries: `pb_studio.exe`, `ffmpeg.exe`, `ffprobe.exe`, Qt6 DLLs, PyTorch/CUDA DLLs.
2. **Installer Stub (`ART-002`):** `dist/pb_studio_setup_v0.5.0.exe` (411.947 Bytes)
3. **NSISBI Payload (`ART-003`):** `dist/pb_studio_setup_v0.5.0.nsisbin` (2.630.208.589 Bytes, ~2.63 GB)

## Smoke Test Ergebnisse (`installer/smoke_test.py`)

- `dist/pb_studio/pb_studio.exe` vorhanden (Size >= 10 MB: 35 MB)
- Qt6 DLLs (Qt6Core, Qt6Widgets, Qt6Gui) vorhanden
- CUDA/Torch DLLs (torch_cuda*, cudart*, cublas*, cudnn*) vorhanden
- Asset- & Laufzeit-Verzeichnisse (resources/, knowledge/, config/, translations/) vorhanden
- FFmpeg-Binaries (`ffmpeg.exe`, `ffprobe.exe`) vorhanden
- **Verdict:** `Smoke test passed.`

## Nächste Schritte

- Clean-VM Installation und End-to-End Live-Verifikation der installierten App.
- Übergang zu Phase STAB-7 (Abschluss).

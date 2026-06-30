# PB Studio Deployment Guide

**Version:** 0.5.0  
**Target Platform:** Windows 11 (64-bit)  
**Build System:** PyInstaller + NSISBI/NSIS
**Target Runtime:** Python 3.10 + CUDA 11.3 / cu113 (NVIDIA GTX 1060 compatible)

---

## Overview

This guide covers building and deploying PB Studio for production distribution. The deployment package includes:

1. **Executable Build** — PyInstaller-bundled application with all dependencies
2. **Windows Installer** — NSIS-based setup executable
3. **Configuration Templates** — Production-ready environment configuration
4. **Setup Scripts** — Post-installation environment configuration

---

## Prerequisites

### Development Environment
- Windows 11 (64-bit)
- Python 3.10 (managed via Miniconda/Anaconda recommended)
- Git
- NSISBI 7069-1 for the production installer payload (standard NSIS 3.x is
  useful for syntax checks but cannot package this CUDA bundle as one classic
  installer on this machine)
- CUDA-compatible GPU (GTX 1060 6GB minimum)

### Required Tools
```bash
# Setup Conda Environment (Recommended)
conda create -n pb-studio python=3.10 -y
conda activate pb-studio

# Upgrade pip
pip install --upgrade pip

# Install standard NSIS if needed for local checks
# Download from: https://nsis.sourceforge.io/
#
# Install NSISBI 7069-1 for the production installer:
#   downloads.sourceforge.net/project/nsisbi/nsisbi3.04.1/nsis-binary-7069-1.zip
# Expected local path used by installer\build_installer.bat:
#   %LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1\Bin\makensis.exe
```

---

## Build Process

### 1. Prepare Build Environment

Ensure your conda environment `pb-studio` is activated, then:

```bash
# Navigate to project root
cd C:\Users\[your-username]\Documents\PB_studio_Rebuild

# Install dependencies using the active cu113 requirements file
pip install -r requirements-py310-cu113.txt --extra-index-url https://download.pytorch.org/whl/cu113

# Verify FFmpeg is on PATH
ffmpeg -version
```

### 2. Run Build Script

The build process is automated via `installer\build_installer.bat`:

```bash
# From project root
installer\build_installer.bat
```

**Build Timeline:**
- PyInstaller compilation: about 20 minutes on the current target machine
- Post-build prune removes duplicated top-level Torch/CUDA DLLs
- Expected pruned output size: about 5.5 GB on the current cu113 build
- NSISBI packaging: about 15-20 minutes
- Total time: ~15-30 minutes

**Output:**
- `dist\pb_studio\` — Application folder with all dependencies
- `dist\pb_studio_setup_v0.5.0.exe` — NSISBI installer stub
- `dist\pb_studio_setup_v0.5.0.nsisbin` — NSISBI external payload; must be
  shipped beside the EXE

### 3. Build Verification

The build script automatically runs smoke tests. Manual verification:

```bash
# Check executable exists
dir dist\pb_studio\pb_studio.exe

# Check total bundle size (current pruned cu113 build is about 5.5 GB)
python -c "import pathlib; root=pathlib.Path('dist/pb_studio'); print(f'{sum(p.stat().st_size for p in root.rglob(\"*\") if p.is_file()) / 1024**3:.2f} GB')"

# Run installer smoke test
python installer\smoke_test.py
```

---

## Deployment Package Structure

```
dist/
├── pb_studio/                          # Application folder
│   ├── pb_studio.exe                   # Main executable
│   ├── _internal/                      # Dependencies
│   │   ├── torch/                      # PyTorch + CUDA libs
│   │   ├── PySide6/                    # Qt framework
│   │   ├── resources/                  # App resources
│   │   ├── config/                     # Runtime config defaults
│   │   ├── translations/               # Qt/app translations
│   │   └── knowledge/                  # AI knowledge base
│   └── [CUDA DLLs and dependencies]
│
├── pb_studio_setup_v0.5.0.exe          # NSISBI installer stub
└── pb_studio_setup_v0.5.0.nsisbin      # NSISBI payload, required beside EXE
```

---

## Installation

### End-User Installation

1. **Download** `pb_studio_setup_v0.5.0.exe` and
   `pb_studio_setup_v0.5.0.nsisbin` into the same folder
2. **Run installer** (requires admin rights)
3. **Choose installation directory** (default: `C:\Program Files\PB Studio`)
4. **Complete installation** — Start Menu shortcuts created
5. **Run first-time setup** (see Configuration below)

### System Requirements (End Users)

| Component | Requirement |
|-----------|-------------|
| OS | Windows 11 (64-bit) |
| GPU | NVIDIA GPU with CUDA support (GTX 1060 6GB minimum) |
| RAM | 16 GB minimum, 32 GB recommended |
| Disk Space | 25 GB (20 GB for app + 5 GB for models) |
| Internet | Required for first-time model downloads |

---

## Configuration

### First-Time Setup

On first launch, PB Studio will:

1. Create user configuration directory: `%USERPROFILE%\.pb_studio\`
2. Download AI models to: `%USERPROFILE%\.cache\`
   - Demucs (stem separation): ~300 MB
   - SigLIP (vision): ~1.8 GB
   - Moondream2 (vision LLM): ~1.7 GB
   - beat_this (beat detection): ~200 MB

### Environment Configuration

Create `%USERPROFILE%\.pb_studio\config.env`:

```env
# Hugging Face API Token (required for model downloads)
HUGGINGFACE_API_TOKEN=hf_your_token_here

# GPU Configuration (optional)
CUDA_VISIBLE_DEVICES=0

# Model Cache (optional, defaults to %USERPROFILE%\.cache)
# HF_HOME=C:\Models\huggingface
```

### Production Configuration

For production deployments:

1. **Model Pre-caching** — Download models before distribution
2. **Offline Mode** — Bundle models with installer
3. **GPU Selection** — Configure CUDA device for multi-GPU systems
4. **Logging** — Enable application logging for support

See `docs/PRODUCTION_CONFIG.md` for advanced configuration.

---

## Testing

### Pre-Deployment Testing Checklist

- [ ] **Clean VM Test** — Install on fresh Windows 11 VM (no Python)
- [ ] **GPU Detection** — Verify CUDA GPU is detected
- [ ] **Model Download** — Confirm models download successfully
- [ ] **Video Import** — Load sample video file
- [ ] **Audio Analysis** — Run beat detection on sample audio
- [ ] **Stem Separation** — Test Demucs stem extraction
- [ ] **Scene Detection** — Verify video scene analysis
- [ ] **Auto-Edit** — Generate automated beat-synced edit
- [ ] **Export** — Render final video with audio normalization
- [ ] **UI Responsiveness** — Test timeline, waveform, chat dock

### Automated Testing

```bash
# Run integration tests
python installer\smoke_test.py

# Run application tests
pytest tests/integration/
```

---

## Distribution

### Code Signing (Recommended)

For production distribution, code-sign the installer:

```bash
# Windows code signing with certificate
signtool sign /f your_certificate.pfx /p password /t http://timestamp.digicert.com dist\pb_studio_setup_v0.5.0.exe
```

### Distribution Channels

1. **Direct Download** — Host installer on website/CDN
2. **Package Manager** — Submit to Chocolatey/winget
3. **Microsoft Store** — Package as MSIX (requires modifications)

---

## Troubleshooting

### Build Issues

**Problem:** PyInstaller fails with missing module
- **Solution:** Add missing module to `hiddenimports` in `pb_studio.spec`

**Problem:** CUDA DLLs not included
- **Solution:** Verify CUDA Toolkit installed, check `collect_all('torch')`

**Problem:** Large build size (>25 GB)
- **Solution:** Normal with CUDA. Consider excluding unused torch backends.

### Installation Issues

**Problem:** Installer fails with "not enough disk space"
- **Solution:** Ensure 25 GB free space on target drive

**Problem:** Application won't start
- **Solution:** Check NVIDIA drivers installed, verify GPU compatibility

**Problem:** Models fail to download
- **Solution:** Verify internet connection, check HUGGINGFACE_API_TOKEN

---

## Maintenance

### Version Updates

1. Update version in:
   - `pyproject.toml`
   - `pb_studio.spec` (line 2)
   - `installer/build_installer.bat` (line 10)
   - `installer/pb_studio.nsi` (line 23)
   - `installer/version_info.txt`

2. Rebuild installer
3. Update changelog
4. Tag release in git

### Dependency Updates

To update dependencies:

```bash
# Update dependencies inside requirements-py310-cu113.txt and verify
pip install -r requirements-py310-cu113.txt --extra-index-url https://download.pytorch.org/whl/cu113
```

> **Note on requirements.txt:** The root `requirements.txt` is maintained as a **legacy / future Python 3.11 + cu124** stack (requiring driver >= 550) and is **not** the active runtime for the GTX 1060 targeting production deployment. Always use `requirements-py310-cu113.txt` for active GTX 1060 targeting.

---

## Support

For deployment issues:
- Check `docs/TROUBLESHOOTING.md`
- Review build logs in `build/pb_studio/`
- Contact: [support contact]

---

**Last Updated:** 2026-05-27  
**Build System Version:** PyInstaller 6.x + NSIS 3.x

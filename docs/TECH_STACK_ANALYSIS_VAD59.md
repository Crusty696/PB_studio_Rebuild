# Tech Stack Analysis — VAD-59

**Date:** 2026-04-10  
**Agent:** TechStackManager  
**Task:** Verify and fix CUDA compatibility across entire tech stack

---

## Current State Analysis

### 1. Python Environment

**System Python:**
- Version: 3.14.4 (in PATH)
- Location: C:\Python314

**Virtual Environment (.venv):**
- Python Version: 3.11.9 ✓
- Location: C:\Users\David Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\.venv
- Status: Correctly configured for requirements.txt constraints

**Requirements Constraint:**
- All packages specify: `python_version >= "3.11" and python_version < "3.13"`
- **COMPATIBLE** with venv Python 3.11.9

---

### 2. GPU Hardware

**Detected GPUs:**
- Primary: **NVIDIA GeForce GTX 1060** (6GB VRAM)
- Secondary: Intel UHD Graphics 620 (integrated)

**GTX 1060 Specifications:**
- Architecture: Pascal (GP106)
- Compute Capability: 6.1
- CUDA Support: Up to CUDA 12.x ✓
- VRAM: 6GB GDDR5

**NVIDIA Driver:**
- Version: **461.40** ❌ CRITICALLY OUTDATED
- Max CUDA Support: 11.2 (driver limitation)
- Location: C:\Program Files\NVIDIA Corporation\NVSMI\
- Required: NVIDIA Driver ≥520.61 for CUDA 12.4 support
- **BLOCKER:** Current driver is 5+ years old (2021), cannot support CUDA 12.x

---

### 3. PyTorch Stack — CRITICAL MISMATCH

**Current Installation (in .venv):**
```
PyTorch:     2.0.1+cu117  ❌ OUTDATED
torchvision: (unknown, likely matching cu117)
torchaudio:  (unknown, likely matching cu117)
CUDA:        11.7
cuDNN:       8500
```

**Required (requirements.txt):**
```
PyTorch:     2.5.1+cu124  ✓ TARGET
torchvision: 0.20.1+cu124 ✓ TARGET  
torchaudio:  2.5.1+cu124  ✓ TARGET
CUDA:        12.4
```

**Version Delta:**
- PyTorch: 2.0.1 → 2.5.1 (5 minor versions behind)
- CUDA: 11.7 → 12.4 (major version jump)

**Impact:**
- 🔴 Performance degradation from missing optimizations
- 🔴 Potential model compatibility issues
- 🔴 Missing CUDA 12.x features and optimizations
- 🔴 Inconsistent behavior with requirements.txt specification

---

### 4. NVIDIA CUDA Packages Analysis

**requirements.txt lines 53-64:**
All NVIDIA CUDA packages are **Linux-only** (platform_system == "Linux" and platform_machine == "x86_64"):
- nvidia-cublas-cu12==12.1.3.1
- nvidia-cuda-cupti-cu12==12.1.105
- nvidia-cuda-nvrtc-cu12==12.1.105
- nvidia-cuda-runtime-cu12==12.1.105
- nvidia-cudnn-cu12==9.1.0.70
- nvidia-cufft-cu12==11.0.2.54
- nvidia-curand-cu12==10.3.2.106
- nvidia-cusolver-cu12==11.4.5.107
- nvidia-cusparse-cu12==12.1.0.106
- nvidia-nccl-cu12==2.21.5
- nvidia-nvjitlink-cu12==12.9.86
- nvidia-nvtx-cu12==12.1.105

**Status on Windows:**
- ✓ **EXPECTED BEHAVIOR**: These packages will NOT install on Windows
- ✓ **NO ACTION NEEDED**: PyTorch for Windows bundles CUDA runtime internally
- ✓ **CORRECT**: Windows users rely on PyTorch's bundled CUDA, not separate CUDA packages

---

### 5. ML/AI Stack Status

**Ollama Service:**
- Status: Configured for AMD RX 7800 XT (HSA_OVERRIDE_GFX_VERSION='11.0.0')
- Model: gemma4:e4b
- Port: 11434
- Issue: ⚠️ AMD GPU config but NVIDIA GPU present (configuration mismatch?)

**ML Packages Installed:**
- accelerate: 1.13.0 ✓
- demucs: 4.0.1 ✓
- faster-whisper: 1.2.1 ✓
- beat-this: 0.1 ✓
- transformers: (version TBD)
- ctranslate2: 4.7.1 ✓

---

### 6. Dependencies Requiring CUDA

**Core CUDA-dependent packages:**
1. **PyTorch** (torch 2.0.1+cu117) — PRIMARY ISSUE
2. **Demucs** (audio separation) — requires CUDA for real-time processing
3. **SigLIP** (vision model) — requires CUDA
4. **RAFT** (optical flow) — requires CUDA
5. **beat_this** (beat detection) — can use CUDA acceleration

**All require PyTorch cu124 upgrade for consistency.**

---

## Critical Issues Identified

### Issue 1: PyTorch CUDA Version Mismatch
- **Severity:** CRITICAL
- **Current:** PyTorch 2.0.1+cu117
- **Required:** PyTorch 2.5.1+cu124
- **Impact:** Performance degradation, potential model incompatibilities, missing CUDA 12.x optimizations

### Issue 2: NVIDIA Driver Critically Outdated — **BLOCKER**
- **Severity:** **CRITICAL BLOCKER**
- **Current:** Driver 461.40 (January 2021, supports CUDA 11.2 max)
- **Required:** Driver ≥520.61 (for CUDA 12.4 support)
- **Gap:** Driver is 5+ years outdated
- **Impact:** 
  - ❌ **CANNOT upgrade to PyTorch 2.5.1+cu124** with current driver
  - ❌ CUDA 12.x applications will fail to initialize
  - ❌ Major performance and stability issues
  - ❌ Missing 5 years of bug fixes and optimizations
- **Action Required:** Driver MUST be updated BEFORE PyTorch upgrade

### Issue 3: Ollama AMD Configuration on NVIDIA Hardware
- **Severity:** MEDIUM
- **Current:** HSA_OVERRIDE_GFX_VERSION set for AMD RX 7800 XT
- **Hardware:** NVIDIA GTX 1060 present
- **Impact:** Configuration mismatch; Ollama may not utilize NVIDIA GPU

### Issue 4: Package Versions May Be Outdated
- **Severity:** MEDIUM
- **Current:** Many packages installed but versions unknown
- **Required:** Full verification against requirements.txt
- **Impact:** Potential bugs, missing features, security vulnerabilities

---

## Recommended Action Plan

### Phase 1: NVIDIA Driver Upgrade (**CRITICAL BLOCKER** — MUST BE DONE FIRST)

**Current State:**
- Driver: 461.40 (Jan 2021)
- Max CUDA: 11.2
- Location: C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe

**Required Actions:**
1. Download latest NVIDIA Game Ready or Studio Driver for GTX 1060:
   - Recommended: Driver 560.x+ (latest stable as of Apr 2026)
   - Minimum: Driver 520.61 (first to support CUDA 12.4)
   - Source: https://www.nvidia.com/Download/index.aspx

2. Uninstall current driver 461.40:
   ```
   Use DDU (Display Driver Uninstaller) in Safe Mode for clean removal
   OR use Windows "Add/Remove Programs" → NVIDIA Graphics Driver
   ```

3. Install new driver:
   - Run downloaded installer
   - Choose "Custom Installation" → "Clean Install"
   - Reboot system

4. Verify installation:
   ```bash
   nvidia-smi  # Should show Driver ≥520.61, CUDA ≥12.4
   ```

**⚠️ CRITICAL:** Do NOT attempt PyTorch cu124 installation before driver upgrade!

### Phase 2: PyTorch Stack Upgrade (CRITICAL)
1. Uninstall current PyTorch stack:
   ```bash
   .venv/Scripts/pip uninstall torch torchvision torchaudio -y
   ```

2. Install PyTorch 2.5.1+cu124:
   ```bash
   .venv/Scripts/pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 --extra-index-url https://download.pytorch.org/whl/cu124
   ```

3. Verify installation:
   ```python
   import torch
   print(torch.__version__)  # Should be 2.5.1+cu124
   print(torch.cuda.is_available())  # Should be True
   print(torch.cuda.get_device_name(0))  # Should show GTX 1060
   ```

### Phase 3: Full Dependency Sync (MEDIUM)
1. Generate current package list with versions
2. Compare against requirements.txt
3. Update all outdated packages
4. Verify no conflicts or missing dependencies

### Phase 4: Configuration Fixes (LOW)
1. Review Ollama AMD configuration
2. Adjust for NVIDIA GPU if needed
3. Update environment variables

### Phase 5: Verification & Testing (CRITICAL)
1. Run startup_checks.py
2. Verify CUDA detection
3. Test model loading (Demucs, SigLIP, RAFT)
4. Generate verification report

---

## GTX 1060 CUDA 12.4 Compatibility Matrix

| Component | Required Version | GTX 1060 Support |
|-----------|------------------|------------------|
| CUDA Toolkit | 12.4 | ✓ Supported (Compute 6.1) |
| NVIDIA Driver | ≥520.61 | ✓ Supported |
| PyTorch | 2.5.1+cu124 | ✓ Compatible |
| Compute Capability | 6.1 | ✓ Pascal architecture |

**Conclusion:** GTX 1060 (Pascal, Compute 6.1) fully supports CUDA 12.4 and PyTorch 2.5.1+cu124.

---

## Next Steps

1. ✅ Analysis complete — documented current state
2. ⏳ Check NVIDIA driver installation and version
3. ⏳ Upgrade PyTorch stack to cu124
4. ⏳ Sync all dependencies
5. ⏳ Test CUDA availability
6. ⏳ Generate final verification report

# CUDA Compatibility Fix Plan — VAD-59

**Status:** Analysis Complete — Critical Blocker Identified  
**Date:** 2026-04-10  
**Agent:** TechStackManager

---

## 🔴 CRITICAL BLOCKER FOUND

**NVIDIA Driver is 5+ years outdated and CANNOT support CUDA 12.x**

```
Current:  NVIDIA Driver 461.40 (Jan 2021) → Max CUDA 11.2
Required: NVIDIA Driver ≥520.61         → CUDA 12.4+ support
```

**Impact:** PyTorch 2.5.1+cu124 upgrade is BLOCKED until driver is updated.

---

## Current State Summary

### ✅ Working Components
- Python 3.11.9 venv (correct version)
- GTX 1060 detected (6GB VRAM, Pascal arch)
- Most ML packages installed (demucs, beat_this, faster-whisper, etc.)

### ❌ Critical Issues
1. **NVIDIA Driver 461.40** → Needs ≥520.61 (5 years outdated!)
2. **PyTorch 2.0.1+cu117** → Needs 2.5.1+cu124 (outdated)
3. **Driver supports max CUDA 11.2** → Blocks CUDA 12.4 upgrade

---

## Required Fix Sequence

### 🔥 Step 1: Update NVIDIA Driver (MUST BE DONE FIRST)

**Current:** Driver 461.40 (CUDA 11.2 max)  
**Target:** Driver 560.x+ (recommended) or 520.61+ (minimum)

**Actions:**
1. Download latest GTX 1060 driver from nvidia.com
2. Uninstall driver 461.40 (use DDU in Safe Mode for clean removal)
3. Install new driver (Custom → Clean Install)
4. Reboot system
5. Verify: `nvidia-smi` should show Driver ≥520.61

**Download:** https://www.nvidia.com/Download/index.aspx  
**GPU:** GeForce GTX 1060  
**OS:** Windows 11 64-bit

---

### 🔧 Step 2: Upgrade PyTorch Stack (AFTER Driver Update)

**Current:** PyTorch 2.0.1+cu117  
**Target:** PyTorch 2.5.1+cu124

**Commands (in .venv):**
```bash
# Activate venv
.venv\Scripts\activate

# Uninstall old PyTorch
pip uninstall torch torchvision torchaudio -y

# Install PyTorch 2.5.1+cu124
pip install torch==2.5.1+cu124 torchvision==0.20.1+cu124 torchaudio==2.5.1+cu124 --extra-index-url https://download.pytorch.org/whl/cu124

# Verify
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

**Expected Output:**
```
PyTorch: 2.5.1+cu124
CUDA: True
GPU: NVIDIA GeForce GTX 1060
```

---

### ✅ Step 3: Verify All Dependencies

**Run full package check:**
```bash
pip list > installed_packages.txt
pip check  # Check for conflicts
```

**Update outdated packages:**
```bash
pip install -r requirements.txt --upgrade
```

---

### 🧪 Step 4: Test CUDA Functionality

**Run startup checks:**
```bash
python -m services.startup_checks
```

**Test model loading:**
```python
from services.model_manager import ModelManager

mm = ModelManager()
print(f"Device: {mm.device}")  # Should be 'cuda'
print(f"GPU: {mm._log_gpu_hardware()}")  # Should show GTX 1060
```

---

## Why This Matters

### Current Problems:
- ❌ PyTorch cu117 vs requirements.txt cu124 → Version mismatch
- ❌ Driver 461.40 too old → Can't initialize CUDA 12.x
- ❌ Missing 5 years of optimizations → Performance degradation
- ❌ Incompatibility risk → Models may fail to load

### After Fix:
- ✅ Driver ≥520.61 → Full CUDA 12.4 support
- ✅ PyTorch 2.5.1+cu124 → Matches requirements.txt exactly
- ✅ All ML models (Demucs, SigLIP, RAFT, beat_this) → CUDA accelerated
- ✅ 5 years of bug fixes + optimizations → Stability & performance

---

## GTX 1060 Compatibility Confirmation

| Component | Version | GTX 1060 Support |
|-----------|---------|------------------|
| GPU Architecture | Pascal (Compute 6.1) | ✅ Supported |
| Latest NVIDIA Driver | 560.x (Apr 2026) | ✅ Supported |
| CUDA 12.4 | Toolkit | ✅ Compatible |
| PyTorch 2.5.1+cu124 | ML Framework | ✅ Compatible |

**Conclusion:** GTX 1060 fully supports all required technologies.

---

## Execution Order (Step-by-Step)

1. ✅ **Analysis Complete** — Issues identified and documented
2. ⏸️ **Awaiting User Action** — NVIDIA driver upgrade (manual installation)
3. ⏳ **After driver update** — PyTorch stack upgrade (automated)
4. ⏳ **After PyTorch upgrade** — Dependency verification
5. ⏳ **Final step** — CUDA functionality testing

---

## What I Did

✅ Analyzed Python environment (venv Python 3.11.9 — correct)  
✅ Verified GPU hardware (GTX 1060 6GB detected)  
✅ Located nvidia-smi (C:\Program Files\NVIDIA Corporation\NVSMI\)  
✅ Checked driver version (461.40 — CRITICAL: too old!)  
✅ Verified PyTorch version (2.0.1+cu117 — outdated)  
✅ Created comprehensive analysis (docs/TECH_STACK_ANALYSIS_VAD59.md)  
✅ Identified CRITICAL BLOCKER (driver must be updated first)  
✅ Created fix plan with exact commands

---

## Next Steps

**Immediate (Manual):**
- User must download and install NVIDIA Driver ≥520.61
- Reboot system after driver installation

**After Driver Update (Automated):**
- I will upgrade PyTorch stack to cu124
- I will verify all dependencies
- I will run CUDA functionality tests
- I will generate final verification report

**Ready to proceed once driver is updated!**

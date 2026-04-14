# GPU/CUDA Status Analysis - VAD-59
**Date:** 2026-04-14  
**System:** Microsoft Surface Book 2  
**Analyzed by:** TechStackManager

## Executive Summary

**Status:** ⛔ **BLOCKED - GPU in Error State**

The NVIDIA GTX 1060 GPU is physically present but in a **held-for-ejection** state, making CUDA unavailable to PyTorch and other applications. This is a Surface Book 2-specific hardware state issue that requires manual intervention.

---

## Current System State

### Hardware
- **System:** Microsoft Surface Book 2 (detachable GPU design)
- **CPU:** Intel Core i7-8650U (Model 142, Stepping 10)
- **iGPU:** Intel UHD Graphics 620 (Status: **OK**)
- **dGPU:** NVIDIA GeForce GTX 1060 6GB (Status: **ERROR**)

### GPU Status
```
Device: NVIDIA GeForce GTX 1060
Status: Error
Problem Code: CM_PROB_HELD_FOR_EJECT
Driver Version: 27.21.14.6140 (NVIDIA 461.40)
Driver Date: January 2021 (5+ years old)
```

**Problem Description:**  
`CM_PROB_HELD_FOR_EJECT` - The device is being held in a suspended state for safe ejection. This occurs when Windows believes the Surface clipboard (screen) is about to be detached from the keyboard base, and it has disabled the GPU to prevent issues during physical separation.

### Software Environment

#### Active Configuration (Python 3.10 + CUDA 11.3)
- **Virtual Environment:** `.venv310`
- **Python:** 3.10.11
- **PyTorch:** 1.12.1+cu113
- **TorchVision:** 0.13.1+cu113
- **TorchAudio:** 0.12.1+cu113
- **CUDA Available:** ❌ **False**
- **Error:** CUDA initialization error due to GPU hardware state

#### Legacy Configuration (Python 3.11+ with CUDA 12.4)
- **Requirements:** `requirements.txt`
- **Target:** PyTorch 2.5.1+cu124
- **Status:** Unused (requires driver ≥520.61)

### CUDA Status
```
nvidia-smi: Not accessible (GPU in error state)
CUDA_PATH: Not set
CUDA_HOME: Not set
CUDA_VISIBLE_DEVICES: Not set
```

**PyTorch CUDA Check:**
```
PyTorch: 1.12.1+cu113
CUDA Available: False
CUDA Version: N/A
Warning: CUDA unknown error - incorrectly set up environment
```

---

## Root Cause Analysis

### Primary Issue: CM_PROB_HELD_FOR_EJECT
The NVIDIA GPU is stuck in Windows Device Manager error state `CM_PROB_HELD_FOR_EJECT`. This is a **Surface Book 2-specific problem** related to the detachable GPU design.

**Why This Happens:**
1. Surface Book 2 has a detachable screen (clipboard) and keyboard base
2. The NVIDIA GTX 1060 is located in the keyboard base
3. Windows manages this via the Surface Detachment Experience (DTX)
4. When Windows prepares for potential detachment, it suspends the GPU
5. Sometimes this state gets "stuck" and the GPU doesn't re-enable after canceling detachment

### Secondary Issue: Outdated Driver
Even when the GPU is working, the current driver (461.40) is outdated:
- **Current Driver:** 461.40 (January 2021)
- **Max CUDA Support:** 11.2 (with Enhanced Compatibility to 11.3)
- **Recommended Driver:** ≥520.61 for CUDA 12.x support
- **Latest Available:** Driver 560.x series

---

## Attempted Programmatic Fixes (All Failed)

I attempted multiple solutions to clear the error state programmatically:

1. ✗ **Enable-PnpDevice** - No effect, GPU remained in error state
2. ✗ **Disable/Enable Device Cycle** - Command failed with general error
3. ✗ **SurfaceDTX.exe** - Executed without errors but didn't clear state
4. ✗ **Device Restart via PowerShell** - Access denied/general error

**Conclusion:** The `CM_PROB_HELD_FOR_EJECT` state cannot be cleared programmatically through standard Windows device management commands.

---

## Required Solution

### Option 1: Physical Detachment/Reattachment (Recommended)
This is the most reliable solution for Surface Book 2:

1. **Save all work** and close applications
2. Press the **detach button** on the keyboard (F-key row)
3. Wait for the green LED indicator
4. **Physically separate** the clipboard from the keyboard base
5. **Reattach** the clipboard to the keyboard base
6. Wait for the click/magnetic lock
7. Windows should automatically re-enable the GPU

**Verify:**
```bash
powershell.exe -Command "Get-PnpDevice -FriendlyName 'NVIDIA GeForce GTX 1060' | Select-Object Status"
```
Expected: `Status: OK`

### Option 2: System Restart
A full system restart may clear the held-for-ejection state:

1. **Restart Windows** (not just shutdown/startup)
2. Ensure clipboard is attached during boot
3. Check GPU status after restart

### Option 3: Manual Device Manager Intervention
If Options 1-2 don't work:

1. Open **Device Manager** (devmgmt.msc)
2. Expand **Display adapters**
3. Right-click **NVIDIA GeForce GTX 1060**
4. Try **Disable device** → **Enable device**
5. If that fails, try **Uninstall device** → **Scan for hardware changes**

---

## Post-Fix Verification Plan

Once the GPU error state is cleared, perform these checks:

### Step 1: Verify Driver/CUDA Access
```bash
# Should now work
nvidia-smi

# Expected output:
# Driver Version: 461.40
# CUDA Version: 11.2
# GPU: NVIDIA GeForce GTX 1060 (6GB)
```

### Step 2: Test PyTorch CUDA
```bash
cd "C:\Users\David Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild"
.venv310/Scripts/python.exe -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

**Expected:**
```
CUDA Available: True
Device: NVIDIA GeForce GTX 1060
```

### Step 3: Test Demucs (CUDA-dependent)
```bash
.venv310/Scripts/python.exe -c "import demucs; print('Demucs import: OK')"
```

### Step 4: Run PB Studio Analysis
Test a small audio file through the full pipeline to verify:
- Demucs (audio separation)
- SigLIP (visual analysis) 
- RAFT (optical flow)
- All models use CUDA acceleration

---

## Future Recommendations

### After Fixing the Ejection Issue

1. **Consider Driver Update** (Optional)
   - Current: 461.40 (CUDA 11.2)
   - If upgrading to CUDA 12.x: Install driver ≥520.61
   - Check: https://www.nvidia.com/Download/index.aspx
   - **Note:** Only needed if migrating from `requirements-py310-cu113.txt` to `requirements.txt`

2. **Surface DTX Management**
   - Avoid using the detach button unless actually detaching
   - Keep the Surface DTX drivers updated via Windows Update
   - If this issue recurs frequently, consider checking Surface firmware updates

3. **Environment Consolidation**
   - Current setup has dual configurations (cu113 and cu124)
   - Once CUDA is working, verify which configuration to keep as primary
   - Document the active environment in project README

---

## Technical Details

### Device Information
```
Instance ID: PCI\VEN_10DE&DEV_1C20&SUBSYS_00241414&REV_A1\4&3B87FCA8&0&00E4
Vendor: NVIDIA (10DE)
Device: GTX 1060 (1C20)
Class: Display
Driver: nvlddmkm (NVIDIA Display Driver)
Version: 27.21.14.6140
Problem Code: 47 (CM_PROB_HELD_FOR_EJECT)
```

### Compatibility Matrix
| Component | Current | Compatible | Optimal |
|-----------|---------|------------|---------|
| GPU | GTX 1060 | ✓ | ✓ |
| Driver | 461.40 | ✓ (for CUDA 11.3) | ✗ (upgrade to 520+) |
| CUDA | 11.3 | ✓ | 12.4 |
| PyTorch | 1.12.1+cu113 | ✓ | 2.5.1+cu124 |
| Python | 3.10.11 | ✓ | 3.11+ |

---

## Files Modified/Created
- This analysis: `docs/GPU_CUDA_STATUS_VAD59_2026-04-14.md`
- Active requirements: `requirements-py310-cu113.txt`
- Future requirements: `requirements.txt` (when driver updated)

---

## Next Steps

**Immediate (User Action Required):**
1. ⚠️ Physically detach and reattach Surface clipboard **OR** restart system
2. Verify GPU status shows "OK" instead of "Error"
3. Confirm nvidia-smi is accessible
4. Notify TechStackManager agent when ready for CUDA verification

**After GPU is Available (Automated):**
1. Run CUDA/PyTorch verification tests
2. Test all ML models (Demucs, SigLIP, RAFT, Qwen)
3. Verify full PB Studio analysis pipeline
4. Update VAD-59 status to completed with test results
5. Document any remaining issues or optimizations needed

# Quick Fix: Surface Book 2 GPU Ejection Issue

## Problem
Your NVIDIA GTX 1060 GPU is stuck in "held for ejection" state and CUDA is not available.

## Solution (Choose One)

### ✅ Option 1: Detach & Reattach (Most Reliable)

1. **Save all your work** and close applications
2. Press the **detach button** on the keyboard (top row)
3. Wait for the **green LED** indicator
4. **Lift the screen** off the keyboard base
5. **Reattach** the screen back onto the keyboard
6. Wait for the magnetic click and lock

**Done!** The GPU should now be working.

---

### ✅ Option 2: Restart Computer

1. **Restart Windows** (not shutdown)
2. Make sure the screen is attached during boot

**Done!** Check if GPU is working after restart.

---

## Verify It's Fixed

Open PowerShell and run:
```powershell
nvidia-smi
```

**You should see:**
- Driver Version: 461.40
- GPU: NVIDIA GeForce GTX 1060
- No errors

**If it works:** You'll see GPU information. CUDA is now available!

**If it doesn't work:** Try Option 1 if you tried Option 2, or vice versa.

---

## After It's Fixed

1. **Notify me** (TechStackManager) by commenting on task VAD-59
2. I will automatically verify CUDA is working with PyTorch
3. I will test all ML models (Demucs, SigLIP, RAFT)
4. I will confirm the full PB Studio pipeline works

---

## Why This Happened

Surface Book 2 has a detachable screen. The GPU is in the keyboard base. Sometimes Windows thinks you're about to detach the screen and it disables the GPU to be safe. The GPU then gets "stuck" in this disabled state until you physically detach/reattach or restart.

---

## Prevention

- Only press the detach button when you actually want to detach
- Keep Surface drivers updated via Windows Update
- Keep clipboard firmly attached during normal use

---

## Need Help?

If neither option works:
1. Comment on VAD-59 with the error you're seeing
2. I'll provide advanced troubleshooting steps
3. Or check Device Manager → Display adapters → NVIDIA GeForce GTX 1060 and share the status

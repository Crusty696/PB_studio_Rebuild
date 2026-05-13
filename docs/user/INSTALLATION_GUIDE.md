# PB Studio Installation Guide

**Version:** 0.5.0  
**For:** End users (DJs, video creators, content producers)

---

## Welcome to PB Studio!

PB Studio is a beat-synchronized video editing tool that automatically cuts your videos to match your music. This guide will help you install and set up PB Studio on your Windows computer.

---

## System Requirements

Before installing, make sure your computer meets these requirements:

### Minimum Requirements
- **Operating System:** Windows 11 (64-bit)
- **Processor:** x86_64 quad-core (Intel Core i5 or equivalent)
- **RAM:** 16 GB
- **Graphics Card:** NVIDIA GTX 1060 with 6 GB VRAM or better
- **Storage:** 25 GB free space (20 GB for app + 5 GB for AI models)
- **Internet:** Required for initial setup and model downloads

### Recommended Requirements
- **Processor:** x86_64 8+ cores (Intel Core i7/i9 or equivalent)
- **RAM:** 32 GB or more
- **Graphics Card:** NVIDIA RTX 3060 with 12 GB VRAM or better
- **Storage:** SSD with 50 GB+ free space

### Important Notes
- ⚠️ **NVIDIA GPU Required:** PB Studio requires an NVIDIA graphics card with CUDA support. Other GPUs are not supported.
- ⚠️ **Windows 11 Only:** Windows 10 may work but is not officially supported.

---

## Installation Steps

### Step 1: Download PB Studio

Download the installer:
- **File:** `pb_studio_setup_v0.5.0.exe`
- **Size:** ~10-15 GB (large due to included AI libraries)

### Step 2: Verify Graphics Drivers

Before installing, make sure you have the latest NVIDIA drivers:

1. Open **NVIDIA GeForce Experience** (if installed)
2. Go to **Drivers** tab
3. Click **Check for updates**
4. Install any available updates

**Or download manually:**
- Visit: https://www.nvidia.com/drivers
- Enter your graphics card model
- Download and install the latest driver

### Step 3: Run the Installer

1. **Locate** the downloaded file: `pb_studio_setup_v0.5.0.exe`
2. **Right-click** the file → **Run as administrator**
3. **Allow** User Account Control (UAC) prompt
4. **Follow** the installation wizard:
   - Choose installation location (default: `C:\Program Files\PB Studio`)
   - Create desktop shortcut (recommended)
   - Add to Start Menu (recommended)
5. **Wait** for installation to complete (5-10 minutes)

### Step 4: First-Time Setup

After installation completes, run the environment setup:

1. **Find** the Start Menu shortcut: **PB Studio Setup**
2. **Run as administrator** (right-click → Run as administrator)
3. The setup wizard will:
   - Create configuration folders
   - Check for NVIDIA GPU
   - Verify CUDA support
   - Prompt for Hugging Face token (see below)

### Step 5: Get Hugging Face Token

PB Studio needs a free Hugging Face account to download AI models:

1. **Visit:** https://huggingface.co/join
2. **Create** a free account
3. **Go to:** https://huggingface.co/settings/tokens
4. **Click:** "New token"
5. **Name:** "PB Studio"
6. **Type:** Select "Read"
7. **Create token**
8. **Copy** the token (starts with `hf_`)
9. **Paste** into the setup wizard when prompted

**Important:** Keep this token private! Don't share it with others.

### Step 6: First Launch

1. **Launch** PB Studio from:
   - Desktop shortcut, or
   - Start Menu → PB Studio
2. **Wait** for AI models to download (~4 GB)
   - This happens automatically on first launch
   - Takes 10-30 minutes depending on internet speed
   - You can see progress in the splash screen
3. **Complete!** PB Studio is ready to use

---

## After Installation

### Verifying Installation

To confirm everything is working:

1. **Launch PB Studio**
2. **Check GPU status:**
   - Look for "NVIDIA [Your GPU Model]" in the status bar
   - Should show "CUDA Ready" or green indicator
3. **Test with sample project:**
   - File → New Project
   - Import a short video and audio file
   - Run Smart Director to test auto-editing

### Folder Locations

**Application:**
```
C:\Program Files\PB Studio\
```

**Your Configuration:**
```
C:\Users\[YourName]\.pb_studio\config.env
```

**Downloaded AI Models:**
```
C:\Users\[YourName]\.cache\huggingface\
```

**Your Projects:**
```
C:\Users\[YourName]\Documents\PB Studio Projects\
```

---

## Troubleshooting

### Installation Issues

#### "Not enough disk space"
- **Solution:** Free up at least 25 GB on your C: drive
- Delete temporary files: `Win + R` → `cleanmgr` → Clean up system files

#### "NVIDIA GPU not detected"
- **Check:** Is your GPU an NVIDIA card?
  - Right-click Desktop → Display settings → Advanced display → Display adapter properties
- **Update:** Install latest NVIDIA drivers from nvidia.com/drivers
- **Verify:** Open Task Manager → Performance → GPU 0 (should show NVIDIA)

#### "Installation failed" or "Installer corrupted"
- **Re-download:** The installer file may be corrupted
- **Disable antivirus:** Temporarily disable antivirus during installation
- **Run as admin:** Right-click installer → Run as administrator

### First Launch Issues

#### "Models failed to download"
- **Check internet:** Make sure you're connected
- **Verify token:** Hugging Face token must start with `hf_` and have Read permissions
- **Manual config:** Edit `C:\Users\[YourName]\.pb_studio\config.env`
  - Find line: `HUGGINGFACE_API_TOKEN=`
  - Add your token: `HUGGINGFACE_API_TOKEN=hf_yourTokenHere`
  - Save and restart PB Studio

#### "Application crashes on startup"
- **Update drivers:** Install latest NVIDIA drivers
- **Check GPU:** Make sure GPU is working (test with another GPU application)
- **View logs:** Check `C:\Users\[YourName]\.pb_studio\logs\app.log` for errors

#### "Out of memory" error
- **Close apps:** Close other applications using GPU (games, video editors)
- **Restart:** Restart your computer to clear GPU memory
- **Check VRAM:** Your GPU needs at least 6 GB VRAM

---

## Getting Started

Now that PB Studio is installed, check out:

- **Quick Start Guide:** `docs/user/QUICK_START.md`
- **Tutorial Videos:** [Link to tutorials]
- **User Manual:** Help → User Guide (in application)

---

## Updating PB Studio

When a new version is released:

1. **Download** the new installer
2. **Run** the installer (it will automatically remove the old version)
3. **Your projects and settings are preserved**

---

## Uninstalling PB Studio

If you need to uninstall:

1. **Start Menu** → Settings → Apps
2. **Find** "PB Studio"
3. **Click** Uninstall
4. **Note:** Your projects in Documents folder are NOT deleted

To completely remove all files:
- Delete: `C:\Users\[YourName]\.pb_studio\`
- Delete: `C:\Users\[YourName]\.cache\huggingface\` (optional, saves 5 GB)
- Delete: `C:\Users\[YourName]\Documents\PB Studio Projects\` (only if you want to delete your projects)

---

## Need Help?

### Documentation
- User Guide: Help → User Guide (in app)
- Keyboard Shortcuts: Help → Shortcuts
- FAQs: `docs/user/FAQ.md`

### Support
- Report bugs: [GitHub Issues]
- Community: [Discord/Forum link]
- Email: [support email]

### System Information

When reporting issues, include:
- PB Studio version (Help → About)
- Windows version (Win + Pause/Break)
- GPU model (Task Manager → Performance → GPU)
- Error message or log file

---

## Tips for Best Performance

1. **Close background apps** before editing (especially browsers with many tabs)
2. **Use an SSD** for your project files (much faster than HDD)
3. **Keep GPU drivers updated** (check monthly)
4. **Work with proxy files** for 4K+ videos (PB Studio generates these automatically)
5. **Save frequently** (File → Save or Ctrl+S)

---

**Enjoy creating with PB Studio!** 🎬🎵

---

**Last Updated:** 2026-04-07  
**Version:** 0.5.0

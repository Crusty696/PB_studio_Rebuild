# PB Studio — Installation Guide

**Version:** 0.5.0

This guide walks you through installing PB Studio from scratch with detailed troubleshooting for common issues.

---

## System Requirements

### Minimum Requirements

| Component | Requirement |
|---|---|
| **Operating System** | Windows 10 (64-bit) or Windows 11 |
| **GPU** | NVIDIA GTX 1060 (6 GB VRAM minimum) |
| **CPU** | Intel Core i5 or AMD Ryzen 5 (4+ cores recommended) |
| **RAM** | 16 GB |
| **Storage** | 10 GB free space (50 GB+ recommended for projects) |
| **CUDA** | 12.x (auto-installed with PyTorch) |
| **FFmpeg** | Latest stable release |
| **Python** | 3.11 or 3.12 |

### Recommended Requirements

| Component | Recommendation |
|---|---|
| **GPU** | NVIDIA RTX 3060 or better (12+ GB VRAM) |
| **RAM** | 32 GB |
| **CPU** | Intel Core i7/i9 or AMD Ryzen 7/9 |
| **Storage** | SSD with 100+ GB free space |

> **Important:** PB Studio requires an NVIDIA GPU with CUDA support. AMD GPUs and integrated graphics are not supported. CPU-only mode is not available.

---

## Pre-Installation Checklist

Before installing PB Studio, verify these prerequisites:

### 1. Check GPU Compatibility

Open Command Prompt and run:

```bash
nvidia-smi
```

You should see your GPU model and driver version. If the command fails:
- Install or update your NVIDIA GPU drivers from [nvidia.com/drivers](https://www.nvidia.com/drivers)
- Restart your computer after driver installation

### 2. Verify CUDA Support

Your NVIDIA driver includes CUDA support. Check your CUDA version:

```bash
nvcc --version
```

If `nvcc` is not found, this is normal — PyTorch will install CUDA libraries during Poetry installation.

### 3. Install FFmpeg

Download FFmpeg from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) (Windows builds).

**Installation steps:**
1. Extract the FFmpeg archive to `C:\ffmpeg`
2. Add `C:\ffmpeg\bin` to your Windows PATH:
   - Right-click **This PC** → **Properties** → **Advanced system settings**
   - Click **Environment Variables**
   - Under **System variables**, select **Path** → **Edit**
   - Click **New** and add `C:\ffmpeg\bin`
   - Click **OK** to save
3. Verify installation:

```bash
ffmpeg -version
```

You should see FFmpeg version information.

---

## Installation Steps

### Step 1: Install Python

Download Python 3.11 or 3.12 from [python.org](https://www.python.org/downloads/).

**During installation:**
- ✓ Check "Add Python to PATH"
- ✓ Check "Install for all users"
- Choose "Customize installation"
- ✓ Enable "pip"
- ✓ Enable "Add Python to environment variables"

Verify installation:

```bash
python --version
pip --version
```

### Step 2: Install Poetry

Open Command Prompt as Administrator and run:

```bash
pip install poetry
```

Verify installation:

```bash
poetry --version
```

### Step 3: Clone the Repository

```bash
git clone <repo-url>
cd pb-studio-rebuild
```

If you don't have Git installed, download it from [git-scm.com](https://git-scm.com).

### Step 4: Configure Hugging Face Token

Create a `.env` file in the project root directory:

```env
HF_TOKEN=your_token_here
```

**To get a Hugging Face token:**
1. Go to [huggingface.co](https://huggingface.co)
2. Create a free account (or log in)
3. Go to **Settings** → **Access Tokens**
4. Click **New token** → **Read** access is sufficient
5. Copy the token and paste it into your `.env` file

> The token is only required for the first run to download AI models. After models are cached locally, the app works fully offline.

### Step 5: Install Dependencies

In the project directory, run:

```bash
poetry install
```

This will:
- Create a virtual environment
- Install PyTorch with CUDA 12.8 support
- Install all ML models (Demucs, beat_this, RAFT, SigLIP)
- Install PySide6 and all other dependencies

**Installation time:** 5–15 minutes depending on your internet connection.

### Step 6: Verify Installation

Run the Setup Wizard:

```bash
poetry run python main.py
```

On first launch, the **Setup Wizard** will verify:
- FFmpeg installation
- GPU availability and CUDA support
- ML model availability (downloads missing models)

If all checks pass, the main application window will open.

---

## Troubleshooting Installation Issues

### FFmpeg not found

**Symptom:** Setup Wizard shows "FFmpeg not detected" or "FFmpeg not found on PATH."

**Solutions:**
1. Verify FFmpeg is in your PATH:
   ```bash
   where ffmpeg
   ```
   This should show `C:\ffmpeg\bin\ffmpeg.exe` (or your installation path).

2. If FFmpeg is not found:
   - Check that you added `C:\ffmpeg\bin` to your system PATH (not user PATH)
   - Restart Command Prompt after changing PATH
   - Restart your computer if the issue persists

3. Alternative: Place `ffmpeg.exe`, `ffprobe.exe`, and `ffplay.exe` directly in the `pb-studio-rebuild/` project directory.

### CUDA not available

**Symptom:** Setup Wizard shows "CUDA not available" or app runs very slowly.

**Solutions:**
1. Verify your GPU is NVIDIA:
   ```bash
   nvidia-smi
   ```
   If this fails, your GPU drivers are not installed or your GPU is not NVIDIA.

2. Update GPU drivers:
   - Go to [nvidia.com/drivers](https://www.nvidia.com/drivers)
   - Download the latest driver for your GPU model
   - Install and restart

3. Verify PyTorch sees your GPU:
   ```bash
   poetry run python -c "import torch; print(torch.cuda.is_available())"
   ```
   This should print `True`. If it prints `False`:
   - Reinstall PyTorch with CUDA support:
     ```bash
     poetry install --sync
     ```

### Model download fails

**Symptom:** "Failed to download model from Hugging Face" or "HTTP 401 Unauthorized."

**Solutions:**
1. Verify your Hugging Face token is correct in `.env`
2. Check your internet connection
3. Try downloading models manually:
   ```bash
   poetry run python -c "from transformers import AutoModel; AutoModel.from_pretrained('google/siglip-so400m-patch14-384')"
   ```
4. If the issue persists, check Hugging Face status at [status.huggingface.co](https://status.huggingface.co)

### Poetry install fails

**Symptom:** `poetry install` fails with dependency conflicts.

**Solutions:**
1. Update Poetry to the latest version:
   ```bash
   pip install --upgrade poetry
   ```
2. Clear Poetry cache:
   ```bash
   poetry cache clear --all pypi
   ```
3. Remove the virtual environment and reinstall:
   ```bash
   poetry env remove python
   poetry install
   ```

### Out of memory during model loading

**Symptom:** "CUDA out of memory" during first launch or analysis.

**Solutions:**
1. Close other GPU-intensive applications (games, video editors, browsers with hardware acceleration)
2. Set a VRAM limit in **Settings → Performance** after first launch
3. If you have less than 6 GB VRAM, PB Studio may not run reliably

### Application crashes on startup

**Symptom:** Window appears briefly then closes, or Python error on startup.

**Solutions:**
1. Check the log file:
   ```bash
   type logs\pb_studio.log
   ```
2. Common causes:
   - Corrupted database: Delete `pb_studio.db` and restart
   - Missing models: Delete `~/.cache/huggingface` and let the app re-download
   - Qt/PySide6 issue: Reinstall PySide6:
     ```bash
     poetry run pip install --force-reinstall PySide6
     ```

---

## Post-Installation Configuration

### Performance Settings

Open **Edit → Settings → Performance** to configure:

| Setting | Recommendation |
|---|---|
| **VRAM Limit** | Set to 80% of your total VRAM |
| **Proxy Quality** | 720p for 8+ GB VRAM, 540p for 6 GB VRAM |
| **Thread Count** | Set to your CPU core count |

### Project Defaults

Configure default export settings in **Edit → Settings → Export**:

| Setting | Recommendation |
|---|---|
| **LUFS Target** | -14 LUFS for YouTube/streaming |
| **Codec** | H.265 NVENC for best quality/size |
| **Resolution** | 1080p (or match your source footage) |

---

## Updating PB Studio

To update to a new version:

```bash
git pull origin main
poetry install --sync
```

Models and database schema are automatically migrated on launch.

---

## Uninstallation

To completely remove PB Studio:

1. Delete the project directory:
   ```bash
   rmdir /s pb-studio-rebuild
   ```

2. (Optional) Remove cached models:
   ```bash
   rmdir /s %USERPROFILE%\.cache\huggingface
   ```

3. (Optional) Remove Poetry:
   ```bash
   pip uninstall poetry
   ```

---

## Getting Help

If you encounter issues not covered here:

1. Check the [FAQ](faq.md)
2. Check the [Troubleshooting Guide](troubleshooting.md)
3. Review the log file at `logs\pb_studio.log`
4. Open a GitHub issue with:
   - Your GPU model and VRAM
   - The relevant section of `logs\pb_studio.log`
   - Steps to reproduce the issue

---

**Next:** [Getting Started](getting_started.md) — Create your first project

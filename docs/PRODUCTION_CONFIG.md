# PB Studio Production Configuration Guide

**Version:** 0.5.0  
**For:** System administrators and power users

---

## Overview

This guide covers advanced configuration options for production deployments of PB Studio, including model pre-caching, offline mode, multi-GPU setups, and enterprise environments.

---

## Configuration Locations

### User Configuration
- **Location:** `%USERPROFILE%\.pb_studio\config.env`
- **Purpose:** User-specific settings, API tokens
- **Created by:** `setup_environment.bat` or first launch

### Application Configuration
- **Location:** Embedded in application (read-only)
- **Override:** Use environment variables in `config.env`

### Model Cache
- **Default:** `%USERPROFILE%\.cache\huggingface\`
- **Override:** Set `HF_HOME` in `config.env`

---

## Environment Variables

### Required Variables

#### HUGGINGFACE_API_TOKEN
Hugging Face API token for downloading gated models.

```env
HUGGINGFACE_API_TOKEN=hf_YourTokenHere
```

**Get token:** https://huggingface.co/settings/tokens  
**Permissions:** Read access

---

### GPU Configuration

#### CUDA_VISIBLE_DEVICES
Specify which GPU(s) to use in multi-GPU systems.

```env
# Use first GPU only
CUDA_VISIBLE_DEVICES=0

# Use second GPU
CUDA_VISIBLE_DEVICES=1

# Use multiple GPUs (not fully supported yet)
CUDA_VISIBLE_DEVICES=0,1
```

**Note:** PB Studio currently optimizes for single-GPU use.

#### CUDA_DEVICE_ORDER
Control GPU ordering (advanced).

```env
# Use PCI bus order (recommended for multi-GPU)
CUDA_DEVICE_ORDER=PCI_BUS_ID
```

---

### Model Cache Configuration

#### HF_HOME
Override default model cache location.

```env
# Custom cache location (useful for shared network drives)
HF_HOME=D:\Models\huggingface

# Network share (requires proper permissions)
HF_HOME=\\NetworkServer\Models\huggingface
```

**Disk space required:** ~5 GB for all models

#### TRANSFORMERS_CACHE
Alternative cache location (legacy).

```env
TRANSFORMERS_CACHE=D:\Models\transformers
```

---

### Application Behavior

#### OFFLINE_MODE
Enable offline mode (requires pre-cached models).

```env
# Enable offline mode
OFFLINE_MODE=1

# Disable offline mode (default)
OFFLINE_MODE=0
```

#### LOG_LEVEL
Control application logging verbosity.

```env
# Options: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# For troubleshooting
LOG_LEVEL=DEBUG
```

#### LOG_FILE
Redirect logs to file.

```env
LOG_FILE=%USERPROFILE%\.pb_studio\logs\app.log
```

---

## Model Pre-Caching

For offline deployments or enterprise environments, pre-cache models before distribution.

### Manual Pre-Caching

```python
# pre_cache_models.py
import os
from huggingface_hub import snapshot_download

# Set token
os.environ["HUGGINGFACE_API_TOKEN"] = "hf_YourToken"

# Download Demucs
snapshot_download(
    "facebook/htdemucs",
    cache_dir=r"C:\Models\huggingface"
)

# Download Whisper
snapshot_download(
    "Systran/faster-whisper-large-v3",
    cache_dir=r"C:\Models\huggingface"
)

# Download SigLIP
snapshot_download(
    "google/siglip-so400m-patch14-384",
    cache_dir=r"C:\Models\huggingface"
)

# Download beat_this
snapshot_download(
    "CPJKU/beat_this",
    cache_dir=r"C:\Models\huggingface"
)

print("All models cached successfully!")
```

Run:
```bash
python pre_cache_models.py
```

### Bundling Models with Installer

To bundle models with the installer for offline installation:

1. **Cache models locally:**
   ```bash
   python pre_cache_models.py
   ```

2. **Modify NSIS script** to include cache directory:
   ```nsis
   ; In pb_studio.nsi, add:
   Section "AI Models (Recommended)"
     SetOutPath "$INSTDIR\models"
     File /r "C:\Models\huggingface\*"
   SectionEnd
   ```

3. **Set HF_HOME** in installer:
   ```nsis
   WriteRegStr HKCU "Environment" "HF_HOME" "$INSTDIR\models"
   ```

**Note:** This increases installer size by ~5 GB.

---

## Multi-User Deployments

### Shared Model Cache

For environments with multiple users, use a shared model cache:

1. **Create shared directory:**
   ```bash
   mkdir D:\Shared\PB_Studio_Models
   icacls D:\Shared\PB_Studio_Models /grant "Users:(OI)(CI)RX"
   ```

2. **Cache models to shared location:**
   ```bash
   set HF_HOME=D:\Shared\PB_Studio_Models
   python pre_cache_models.py
   ```

3. **Configure all users:**
   ```env
   # In each user's config.env
   HF_HOME=D:\Shared\PB_Studio_Models
   OFFLINE_MODE=1
   ```

### Read-Only Cache

For security, make cache read-only after initial setup:

```bash
icacls D:\Shared\PB_Studio_Models /inheritance:r
icacls D:\Shared\PB_Studio_Models /grant "Users:(OI)(CI)R"
icacls D:\Shared\PB_Studio_Models /grant "Administrators:(OI)(CI)F"
```

---

## Network Deployments

### Group Policy Deployment

Deploy via Active Directory Group Policy:

1. **Create MSI installer** (convert from EXE):
   ```bash
   # Use MSI Wrapper or similar tool
   msiexec /i pb_studio_v0.5.0.msi /qn
   ```

2. **Deploy via GPO:**
   - Computer Configuration → Policies → Software Settings → Software Installation
   - Add package: `pb_studio_v0.5.0.msi`

3. **Configure via GPO:**
   - User Configuration → Preferences → Windows Settings → Registry
   - Set `HKCU\Environment\HF_HOME` to shared cache

### SCCM/Intune Deployment

Create detection script:
```powershell
# detect_pb_studio.ps1
$installPath = "${env:ProgramFiles}\PB Studio\pb_studio.exe"
if (Test-Path $installPath) {
    $version = (Get-Item $installPath).VersionInfo.FileVersion
    if ($version -eq "0.5.0") {
        Write-Output "Installed"
        exit 0
    }
}
exit 1
```

---

## Performance Tuning

### GPU Memory Allocation

For systems with limited VRAM:

```env
# Limit PyTorch memory allocation (in GB)
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# Enable memory growth (slower but more stable)
CUDA_LAUNCH_BLOCKING=1
```

### FFmpeg Configuration

Custom FFmpeg binary location:

```env
FFMPEG_BINARY=C:\Tools\ffmpeg\bin\ffmpeg.exe
FFPROBE_BINARY=C:\Tools\ffmpeg\bin\ffprobe.exe
```

### Database Configuration

SQLite database location:

```env
PB_STUDIO_DB_PATH=%USERPROFILE%\.pb_studio\database.db
```

---

## Security Considerations

### API Token Storage

The Hugging Face token is stored in plain text in `config.env`. For enhanced security:

1. **Use Windows Credential Manager:**
   ```python
   # In application code
   import keyring
   token = keyring.get_password("pb_studio", "hf_token")
   ```

2. **Restrict file permissions:**
   ```bash
   icacls %USERPROFILE%\.pb_studio\config.env /inheritance:r
   icacls %USERPROFILE%\.pb_studio\config.env /grant "%USERNAME%:F"
   ```

### Network Firewall

Required network access for model downloads:

- **Hugging Face CDN:** `cdn-lfs.huggingface.co` (HTTPS)
- **Hugging Face API:** `huggingface.co` (HTTPS)

Whitelist these domains in corporate firewalls.

---

## Troubleshooting

### Models Won't Download

**Symptom:** Application hangs on "Downloading models..."

**Solutions:**
1. Verify HUGGINGFACE_API_TOKEN is correct
2. Check network connectivity to huggingface.co
3. Check proxy settings if behind corporate firewall
4. Use offline mode with pre-cached models

### Out of Memory Errors

**Symptom:** Application crashes with CUDA out of memory

**Solutions:**
1. Close other GPU-intensive applications
2. Reduce video resolution for processing
3. Enable memory growth: `CUDA_LAUNCH_BLOCKING=1`
4. Upgrade GPU RAM (16 GB recommended)

### Slow Performance

**Symptom:** Video processing is slower than expected

**Solutions:**
1. Verify GPU is being used: Check Task Manager → Performance → GPU
2. Update NVIDIA drivers
3. Check CUDA_VISIBLE_DEVICES is set to correct GPU
4. Close background GPU applications

---

## Monitoring and Logging

### Application Logs

Default log location:
```
%USERPROFILE%\.pb_studio\logs\app.log
```

Enable debug logging:
```env
LOG_LEVEL=DEBUG
LOG_FILE=%USERPROFILE%\.pb_studio\logs\debug.log
```

### Performance Metrics

Enable performance metrics:
```env
PB_STUDIO_METRICS=1
METRICS_FILE=%USERPROFILE%\.pb_studio\logs\metrics.json
```

---

## Backup and Recovery

### User Data Locations

**Configuration:**
```
%USERPROFILE%\.pb_studio\config.env
```

**Database:**
```
%USERPROFILE%\.pb_studio\database.db
```

**Projects:**
```
%USERPROFILE%\Documents\PB Studio Projects\
```

### Backup Script

```powershell
# backup_pb_studio.ps1
$backupDir = "$env:USERPROFILE\Backups\PB_Studio"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupPath = "$backupDir\backup_$timestamp"

New-Item -ItemType Directory -Path $backupPath -Force

# Backup configuration
Copy-Item "$env:USERPROFILE\.pb_studio\*" $backupPath -Recurse -Exclude "logs"

# Backup projects
Copy-Item "$env:USERPROFILE\Documents\PB Studio Projects\*" "$backupPath\Projects" -Recurse

Write-Output "Backup complete: $backupPath"
```

---

## Support and Contact

For production deployment support:
- Documentation: `docs/DEPLOYMENT.md`
- Troubleshooting: `docs/TROUBLESHOOTING.md`
- Issue tracker: [GitHub Issues]

---

**Last Updated:** 2026-04-07  
**Applies to:** PB Studio v0.5.0+

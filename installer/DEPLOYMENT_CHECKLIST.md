# PB Studio Deployment Checklist

**Version:** 0.5.0  
**Date:** 2026-04-07

Use this checklist when preparing a production deployment of PB Studio.

---

## Pre-Build Preparation

### Version Control
- [ ] Update version number in all files:
  - [ ] `pyproject.toml` → `version = "0.5.0"`
  - [ ] `pb_studio.spec` → Line 2 comment
  - [ ] `installer/build_installer.bat` → `APP_VERSION=0.5.0`
  - [ ] `installer/pb_studio.nsi` → `APP_VERSION "0.5.0"`
  - [ ] `installer/version_info.txt` → FileVersion and ProductVersion
  - [ ] `README.md` → Top header version
- [ ] Update CHANGELOG.md with release notes
- [ ] Commit all changes to git
- [ ] Create git tag: `git tag v0.5.0`

### Dependencies
- [ ] Run `poetry update` to update dependencies
- [ ] Export requirements: `poetry export -f requirements.txt --output requirements.txt --without-hashes`
- [ ] Test application with updated dependencies
- [ ] Run security audit: `poetry check`
- [ ] Scan for vulnerabilities (if vulnerability-scanner skill available)

### Code Quality
- [ ] Run tests: `pytest tests/`
- [ ] Check for linting issues
- [ ] Review TODO/FIXME comments
- [ ] Update documentation for any new features
- [ ] Verify all CLAUDE.md instructions are current

---

## Build Environment Setup

### System Preparation
- [ ] Clean Windows 11 build machine or VM
- [ ] Latest NVIDIA drivers installed
- [ ] CUDA Toolkit 12.4+ installed
- [ ] FFmpeg on PATH: `ffmpeg -version`
- [ ] NSIS 3.x installed and on PATH: `makensis /VERSION`
- [ ] Disk space: >50 GB free on build drive

### Python Environment
- [ ] Python 3.11 or 3.12 installed
- [ ] Poetry installed: `poetry --version`
- [ ] Virtual environment created: `poetry install`
- [ ] All dependencies installed without errors
- [ ] PyInstaller available: `pip install pyinstaller`

### Resources
- [ ] Icon file exists: `resources/pb_studio.ico`
- [ ] License file exists or will be auto-created
- [ ] All resource directories exist:
  - [ ] `resources/`
  - [ ] `styles/`
  - [ ] `knowledge/`

---

## Build Process

### PyInstaller Build
- [ ] Clean previous builds:
  - [ ] Delete `dist/pb_studio/` if exists
  - [ ] Delete `build/pb_studio/` if exists
- [ ] Run build script: `installer\build_installer.bat`
- [ ] Monitor build output for errors
- [ ] Verify build completed without warnings

### Build Verification
- [ ] Check executable exists: `dist/pb_studio/pb_studio.exe`
- [ ] Check build size: 8-20 GB range
- [ ] Verify CUDA DLLs included:
  - [ ] `cudart64_12.dll`
  - [ ] `cublas64_12.dll`
  - [ ] `cudnn64_9.dll`
- [ ] Verify PyTorch DLLs included:
  - [ ] `torch_cuda.dll`
  - [ ] `_C.pyd`
- [ ] Verify PySide6 DLLs included:
  - [ ] `Qt6Core.dll`
  - [ ] `Qt6Gui.dll`
  - [ ] `Qt6Widgets.dll`

### NSIS Installer Build
- [ ] NSIS script runs without errors
- [ ] Installer created: `dist/pb_studio_setup_v0.5.0.exe`
- [ ] Installer size reasonable: ~8-15 GB

---

## Testing

### Smoke Tests (Build Machine)
- [ ] Run smoke test script: `python installer/smoke_test.py`
- [ ] Launch executable directly: `dist/pb_studio/pb_studio.exe`
- [ ] Application starts without errors
- [ ] GPU detected and CUDA initialized
- [ ] Main window opens

### Clean VM Installation Test
- [ ] Prepare clean Windows 11 VM:
  - [ ] No Python installed
  - [ ] No development tools
  - [ ] NVIDIA drivers installed
  - [ ] 25+ GB free disk space
- [ ] Copy installer to VM
- [ ] Run installer as admin
- [ ] Verify installation completes
- [ ] Run environment setup script
- [ ] Launch application from Start Menu
- [ ] Complete first-time setup:
  - [ ] Enter Hugging Face token
  - [ ] Models download successfully
  - [ ] Application starts

### Functional Tests (VM)
- [ ] **Project Creation:**
  - [ ] Create new project
  - [ ] Set project name and location
  - [ ] Save project
- [ ] **Video Import:**
  - [ ] Import video file
  - [ ] Scene detection runs
  - [ ] Scenes appear in library
  - [ ] Preview keyframes generated
- [ ] **Audio Import:**
  - [ ] Import audio file
  - [ ] Waveform displays
  - [ ] Beat detection runs
  - [ ] Beatgrid visible
- [ ] **AI Analysis:**
  - [ ] Stem separation (Demucs) completes
  - [ ] Beat detection (beat_this) completes
  - [ ] Visual embeddings (SigLIP) generate
  - [ ] Motion analysis (RAFT) completes
- [ ] **Smart Director:**
  - [ ] Auto-edit generates scenes
  - [ ] Cuts align with beats
  - [ ] Preview playback works
- [ ] **Editing:**
  - [ ] Manual cut placement
  - [ ] Anchor creation
  - [ ] Scene reordering
  - [ ] Timeline scrubbing
- [ ] **Export:**
  - [ ] Export video
  - [ ] Audio normalization applied
  - [ ] Transitions rendered
  - [ ] Output file playable

### Performance Tests
- [ ] GPU utilization during processing (should be >80%)
- [ ] Memory usage acceptable (<80% of available RAM)
- [ ] VRAM usage within limits
- [ ] No memory leaks during extended use
- [ ] Response time acceptable for UI interactions

### Error Handling Tests
- [ ] Invalid file formats rejected gracefully
- [ ] Corrupted files handled without crash
- [ ] Out of disk space handled
- [ ] Network interruption during model download handled
- [ ] GPU unavailable error message clear

---

## Model Pre-Caching (Optional for Offline Deployment)

- [x] Run pre-cache script: `python installer/pre_cache_models.py` (Verified: includes htdemucs, whisper, siglip, moondream2, beat_this)
- [x] Integrate pre-caching into application CLI: `pb_studio.exe --pre-cache` (Implemented in main.py)
- [x] Integrate pre-caching into installer: Optional section in `pb_studio.nsi` (Implemented)
- [x] Verify all models downloaded:
  - [x] Demucs (~300 MB)
  - [x] Faster Whisper (~1.5 GB)
  - [x] SigLIP (~1.8 GB)
  - [x] Moondream2 (~1.7 GB)
  - [x] beat_this (~200 MB)
- [ ] Test offline mode with cached models
- [ ] Document cache location for deployment

---

## Documentation

### User Documentation
- [ ] Installation guide complete: `docs/user/INSTALLATION_GUIDE.md`
- [ ] Quick start guide updated
- [ ] FAQ updated with common issues
- [ ] Tutorial videos recorded (if applicable)

### Deployment Documentation
- [ ] Deployment guide complete: `docs/DEPLOYMENT.md`
- [ ] Production config guide complete: `docs/PRODUCTION_CONFIG.md`
- [ ] Troubleshooting guide updated
- [ ] Known issues documented

### Release Notes
- [ ] CHANGELOG.md updated with:
  - [ ] New features
  - [ ] Bug fixes
  - [ ] Breaking changes
  - [ ] Known issues
  - [ ] Upgrade notes

---

## Security

### Code Signing (Production Only)
- [ ] Obtain code signing certificate
- [ ] Sign installer executable:
  ```batch
  signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist\pb_studio_setup_v0.5.0.exe
  ```
- [ ] Verify signature: Right-click installer → Properties → Digital Signatures
- [ ] Test signed installer on clean VM

### Security Scan
- [ ] No sensitive data in build (API keys, passwords)
- [ ] No hardcoded credentials
- [ ] Environment variables used for secrets
- [ ] File permissions appropriate
- [ ] Network requests use HTTPS

---

## Distribution

### Package Preparation
- [ ] Rename installer with clear version: `pb_studio_setup_v0.5.0.exe`
- [ ] Generate checksums:
  ```powershell
  Get-FileHash dist\pb_studio_setup_v0.5.0.exe -Algorithm SHA256
  ```
- [ ] Create ZIP archive with installer + README
- [ ] Test ZIP extraction

### Release Artifacts
- [ ] Installer EXE
- [ ] SHA256 checksum file
- [ ] Installation guide (PDF or MD)
- [ ] Release notes
- [ ] License file

### Upload Locations
- [ ] GitHub Releases (if applicable)
- [ ] Company website/CDN
- [ ] Download links tested and working
- [ ] Download mirrors configured (if applicable)

### Communication
- [ ] Release announcement drafted
- [ ] Social media posts prepared
- [ ] Email to users (if applicable)
- [ ] Documentation website updated
- [ ] Version number visible on download page

---

## Post-Release

### Monitoring
- [ ] Download analytics set up
- [ ] Error reporting configured
- [ ] User feedback channel established
- [ ] Support ticket system ready

### Support Preparation
- [ ] Support team briefed on new version
- [ ] Known issues list shared
- [ ] Common troubleshooting steps documented
- [ ] Escalation path defined

### Backup
- [ ] Build artifacts backed up:
  - [ ] Source code (git tag)
  - [ ] Installer EXE
  - [ ] Build logs
  - [ ] Test results
- [ ] Store in version control and backup storage

---

## Rollback Plan

In case of critical issues after release:

- [ ] Previous version installer available
- [ ] Downgrade instructions documented
- [ ] Database migration rollback tested (if applicable)
- [ ] Communication plan for rollback announcement

---

## Sign-Off

### Technical Review
- [ ] CTO approval
- [ ] QA team sign-off
- [ ] Security review complete

### Business Review
- [ ] CEO approval (if required)
- [ ] Marketing approval
- [ ] Legal approval (licensing, EULA)

### Final Checklist
- [ ] All tests passed
- [ ] All documentation complete
- [ ] All stakeholders notified
- [ ] Support team ready
- [ ] Release approved

---

**Deployment Date:** _______________  
**Deployed By:** _______________  
**Version Released:** _______________  

---

**Notes:**

(Space for deployment-specific notes, issues encountered, or special considerations)

_______________________________________________________________

_______________________________________________________________

_______________________________________________________________

---

**Last Updated:** 2026-04-07  
**For Version:** 0.5.0+

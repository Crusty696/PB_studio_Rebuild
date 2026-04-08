# Backup & Google Drive Upload Guide

## Option 1: Windows Explorer (GUI)
1. **Right-click** `PB_studio_Rebuild` folder
2. Select **"Send to" → Compressed (zipped) folder**
3. Wait for ZIP creation (~2-3 min for 1.6 GB)
4. Open Google Drive in browser
5. **Drag & drop** the `.zip` file into Drive

## Option 2: PowerShell (Faster, shows progress)
```powershell
# In your Documents/App_Projekte directory:
Compress-Archive -Path "PB_studio_Rebuild" -DestinationPath "PB_studio_Rebuild_backup.zip" -CompressionLevel Optimal -Verbose

# Then upload to Google Drive
```

## Option 3: 7-Zip (Best compression, even faster)
```bash
# If you have 7-Zip installed:
7z a -tzip PB_studio_Rebuild_backup.zip PB_studio_Rebuild -xr"!.git"
```

## Upload to Google Drive
1. Open **drive.google.com**
2. Create folder: `PB_Studio_Backups` (optional, for organization)
3. Drag `.zip` file into the folder
4. Wait for upload to complete
5. Verify file integrity (size should be ~1.6 GB zipped → ~400-600 MB compressed)

## On Next Session (Resume Work)
```bash
# After extracting from Drive backup:
cd PB_studio_Rebuild

# Restore Python environment:
pip install -r requirements.txt

# Verify everything works:
python main.py  # or your entry point
```

## Troubleshooting
- **ZIP too large for Drive?** Upload in parts or use Google Drive's streaming upload
- **Missing dependencies?** `pip install -r requirements.txt` will restore them
- **Models missing?** App will auto-download Ollama models on first inference

---
**Estimated ZIP size**: 400-600 MB (compressed from 1.6 GB)
**Upload time**: Depends on internet (typically 5-30 min for 500 MB)


import os
from huggingface_hub import snapshot_download
from pathlib import Path

def download_beat_this():
    repo_id = "CPJKU/beat_this"
    target_dir = Path("bin/models/beat_this/final0")
    
    print(f"Starte Download von {repo_id} nach {target_dir}...")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            local_dir_use_symlinks=False
        )
        print("✅ Download erfolgreich!")
    except Exception as e:
        print(f"❌ Fehler beim Download: {e}")

if __name__ == "__main__":
    download_beat_this()

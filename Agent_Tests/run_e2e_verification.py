import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Config
PROJECT_ROOT = Path(r"C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild")
PYTHON_EXE = r"C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe"
HARNESS_SCRIPT = PROJECT_ROOT / "tests" / "gui_harness.py"

AUDIO_SRC = r"C:\Users\David_Lochmann\Music\drive-download-20260617T023341Z-3-001\Zyce,_Querox_-_Feel_Free_(Original)_142__(Trance_(Main_Floor))_Gb_Major_17_29.mp3"
VIDEO_SRC_DIR = r"C:\Users\David_Lochmann\Videos\Solo_Natur-20260406T220640Z-3-001\Solo_Natur"
TEST_VIDEOS_DIR = PROJECT_ROOT / "tests" / "qa_artifacts" / "test_videos"

os.environ["PB_PYTHON"] = PYTHON_EXE

def run_harness(cmd, **kwargs):
    args = [PYTHON_EXE, str(HARNESS_SCRIPT), cmd]
    for k, v in kwargs.items():
        if isinstance(v, bool):
            if v:
                args.append(f"--{k.replace('_', '-')}")
        else:
            args.extend([f"--{k.replace('_', '-')}", str(v)])
    
    print(f"Executing: {' '.join(args)}")
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stdout_strip = res.stdout.strip()
    if not stdout_strip:
        print(f"FAILED {cmd} {kwargs}: No stdout. Stderr: {res.stderr}", file=sys.stderr)
        return {"ok": False, "error": "No stdout", "stderr": res.stderr}
    
    try:
        # Finde die letzte JSON-Zeile
        lines = stdout_strip.split("\n")
        data = None
        for line in reversed(lines):
            if line.strip().startswith("{") and line.strip().endswith("}"):
                data = json.loads(line.strip())
                break
        if data is None:
            raise ValueError(f"No JSON found in output: {stdout_strip}")
        if not data.get("ok"):
            print(f"FAILED {cmd} {kwargs}: {data.get('error')}", file=sys.stderr)
        return data
    except Exception as e:
        print(f"FAILED {cmd} {kwargs}: JSON Parse error: {e}\nRaw Output:\n{stdout_strip}", file=sys.stderr)
        return {"ok": False, "error": str(e), "raw": stdout_strip}

def prepare_test_videos():
    if TEST_VIDEOS_DIR.exists():
        shutil.rmtree(TEST_VIDEOS_DIR)
    TEST_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Kopiere 3 kurze Videos
    video_files = [f for f in os.listdir(VIDEO_SRC_DIR) if f.endswith(".mp4")]
    video_files.sort()
    copied = 0
    for vf in video_files[:3]:  # nur 3 Videos fuer extrem schnellen E2E-Lauf
        src = os.path.join(VIDEO_SRC_DIR, vf)
        dst = TEST_VIDEOS_DIR / vf
        shutil.copy2(src, dst)
        print(f"Copied {src} -> {dst}")
        copied += 1
    print(f"Prepared {copied} test videos.")

def main():
    print("=== STARTING E2E STORAGE PROVENANCE VALIDATION ===")
    prepare_test_videos()
    
    # 0. Start App
    print("--> 0. Starting app...")
    start_res = run_harness("start", force=True)
    if not start_res.get("ok"):
        print("Could not start app!")
        sys.exit(1)
        
    print("Waiting for main window...")
    wait_res = run_harness("wait-window", timeout=30.0)
    if not wait_res.get("ok"):
        print("Window did not appear!")
        run_harness("kill", force=True)
        sys.exit(1)
        
    time.sleep(5)  # Init time
    
    # 1. Klicke Startup-Wizard / Checks weiter
    print("--> 1. Startup checks check...")
    run_harness("click_element", name_re="Weiter", control_type="Button")
    time.sleep(1)
    
    run_harness("screenshot", label="01_startup")
    
    # 2. Erstelle Project 1
    print("--> 2. Creating Project 1...")
    run_harness("click_element", name_re="Neues Projekt|\\+ Neues Projekt")
    time.sleep(2)
    
    # Tippe Name
    run_harness("type", text="E2E_PROV_1")
    time.sleep(1)
    run_harness("key", key="enter")
    time.sleep(3)
    
    run_harness("screenshot", label="02_project1_created")
    
    # 3. Audio Import
    print("--> 3. Importing Audio...")
    run_harness("click_element", name_re="AUDIO")
    time.sleep(1)
    run_harness("click_element", name_re="\\+ Audio|Audio importieren")
    time.sleep(2)
    
    run_harness("type", text=AUDIO_SRC)
    time.sleep(1)
    run_harness("key", key="enter")
    time.sleep(3)
    
    run_harness("screenshot", label="03_audio_imported")
    
    # 4. Video Import
    print("--> 4. Importing Videos...")
    run_harness("click_element", name_re="VIDEO")
    time.sleep(1)
    run_harness("click_element", name_re="\\+ Ordner|Ordner importieren")
    time.sleep(2)
    
    run_harness("type", text=str(TEST_VIDEOS_DIR))
    time.sleep(1)
    run_harness("key", key="enter")
    time.sleep(4)
    
    run_harness("screenshot", label="04_videos_imported")
    
    # 5. Audio-Analyse
    print("--> 5. Audio complete analysis (triggers stems, beatgrid, etc.)...")
    run_harness("click_element", name_re="AUDIO")
    time.sleep(1)
    run_harness("click_element", name_re="Audio komplett analysieren")
    
    print("Waiting for audio analysis to complete (90 seconds)...")
    time.sleep(90)
    
    run_harness("screenshot", label="05_audio_analyzed")
    
    # 6. Video-Analyse
    print("--> 6. Video complete analysis...")
    run_harness("click_element", name_re="VIDEO")
    time.sleep(1)
    run_harness("click_element", name_re="Alle Videos an-/abwaehlen")
    time.sleep(1)
    run_harness("click_element", name_re="Video komplett analysieren")
    
    print("Waiting for video analysis to complete (120 seconds)...")
    time.sleep(120)
    
    run_harness("screenshot", label="06_video_analyzed")
    
    # 7. Schnitt Workspace / Auto-Edit
    print("--> 7. Auto-Edit...")
    run_harness("click_element", name_re="EDIT Workspace")
    time.sleep(2)
    run_harness("click_element", name_re="Techno")
    time.sleep(2)
    run_harness("click_element", name_re="Auto-Edit|Timeline generieren")
    time.sleep(5)
    
    run_harness("screenshot", label="07_timeline_created")
    
    # 8. Export
    print("--> 8. Exporting...")
    run_harness("click_element", name_re="EXPORT Workspace|EXPORT")
    time.sleep(2)
    run_harness("click_element", name_re="Video exportieren")
    
    print("Waiting for export (40 seconds)...")
    time.sleep(40)
    
    run_harness("screenshot", label="08_export_done")
    
    # 9. Storage-Browser verifizieren
    print("--> 9. Checking Storage Browser...")
    run_harness("click_element", name_re="Einstellungen")
    time.sleep(2)
    run_harness("click_element", name_re="Storage-Browser")
    time.sleep(3)
    
    run_harness("screenshot", label="09_storage_browser")
    
    # Schliesse Dialoge
    run_harness("key", key="escape") # schliesst Browser
    time.sleep(1)
    run_harness("key", key="escape") # schliesst Settings
    time.sleep(1)
    
    # 10. (entfernt 2026-07-17) Project-Bundle-Export — ProjectBundleService
    # wurde im Altlast-Cleanup geloescht (war nie produktiv verdrahtet).

    # 11. Cross-Project Reuse verifizieren (Projekt 2)
    print("--> 11. Testing Cross-Project Reuse...")
    # Beende App
    run_harness("kill", force=True)
    time.sleep(2)
    
    # Starte App neu
    run_harness("start", force=True)
    time.sleep(5)
    run_harness("click_element", name_re="Weiter", control_type="Button")
    time.sleep(1)
    
    # Erstelle Project 2
    run_harness("click_element", name_re="Neues Projekt|\\+ Neues Projekt")
    time.sleep(2)
    run_harness("type", text="E2E_PROV_2")
    time.sleep(1)
    run_harness("key", key="enter")
    time.sleep(3)
    
    # Importiere dasselbe Video
    run_harness("click_element", name_re="VIDEO")
    time.sleep(1)
    run_harness("click_element", name_re="\\+ Ordner|Ordner importieren")
    time.sleep(2)
    run_harness("type", text=str(TEST_VIDEOS_DIR))
    time.sleep(1)
    run_harness("key", key="enter")
    time.sleep(4)
    
    # Hier sollte die Re-use Notice erscheinen!
    run_harness("screenshot", label="11_project2_reuse_notice")
    
    # Beende App
    print("--> Teardown...")
    run_harness("kill", force=True)
    print("=== E2E STORAGE PROVENANCE VALIDATION FINISHED ===")

if __name__ == "__main__":
    main()

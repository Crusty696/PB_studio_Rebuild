"""Dev-Tool: extrahiert die projekt-relevanten Frames aus faulthandler-Dumps."""
from pathlib import Path
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except: pass

log = Path("logs/freeze_stacks.log").read_text(encoding="utf-8", errors="replace")
blocks = log.split("Timeout (0:00:03)!")
print(f"Total Freeze-Dumps: {len(blocks)-1}")

PROJECT_MARKER = "PB_studio_Rebuild" + chr(92)

# Unique Blockers: welche Projekt-Frames waren an welcher Line
seen = set()
for i, b in enumerate(blocks[1:], 1):
    lines = b.splitlines()
    project_frames = [
        l.strip() for l in lines
        if PROJECT_MARKER in l
        and ".venv310" not in l
        and "handlers.py" not in l
        and "analyze_freezes" not in l
    ]
    if not project_frames:
        continue
    # Top-Frame (der konkrete Blocker)
    top = project_frames[0]
    if top in seen:
        continue
    seen.add(top)
    print(f"\n=== Dump #{i} — {len(project_frames)} project frames ===")
    for l in project_frames[:8]:
        print(" ", l[:160])

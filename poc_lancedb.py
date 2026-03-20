"""
PoC #2: LanceDB Machbarkeit — Wegwerf-Skript
Testet Insert, Query, Disk, RAM, Startup mit 10k synthetischen Eintraegen.
"""

import subprocess
import sys
import time
import os
import shutil
import tracemalloc
import numpy as np

# --- 1. Import-Check / Install ---
try:
    import lancedb
    import pyarrow as pa
    print(f"[OK] lancedb {lancedb.__version__} bereits installiert")
except ImportError:
    print("[INFO] lancedb nicht gefunden, installiere...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "lancedb", "-q"])
    import lancedb
    import pyarrow as pa
    print(f"[OK] lancedb {lancedb.__version__} installiert")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poc_lancedb_data")
N_ROWS = 10_000
VEC_DIM = 1152
N_QUERIES = 10
TOP_K = 5

# Cleanup
if os.path.exists(DB_PATH):
    shutil.rmtree(DB_PATH)

print(f"\n{'='*60}")
print(f"LanceDB PoC — {N_ROWS} rows, {VEC_DIM}-dim vectors")
print(f"{'='*60}\n")

# --- Start RAM tracking ---
tracemalloc.start()
ram_before = tracemalloc.get_traced_memory()[0]

# --- 2. Create DB ---
db = lancedb.connect(DB_PATH)

# --- 3+4. Create table with 10k synthetic entries ---
print("[1/6] Generating synthetic data...")
rng = np.random.default_rng(42)

data = []
for i in range(N_ROWS):
    data.append({
        "id": i,
        "video_path": f"/videos/project_{i % 100}/clip_{i}.mp4",
        "scene_start": float(rng.uniform(0, 3600)),
        "scene_end": float(rng.uniform(0, 3600)),
        "motion_score": float(rng.uniform(0, 1)),
        "description": f"Scene {i}: synthetic test entry with motion and cuts",
        "embedding": rng.standard_normal(VEC_DIM).astype(np.float32).tolist(),
    })

print("[2/6] Inserting 10,000 rows...")
t0 = time.perf_counter()
tbl = db.create_table("scenes", data=data)
insert_time = time.perf_counter() - t0
print(f"       Insert time: {insert_time:.3f}s ({N_ROWS/insert_time:.0f} rows/s)")

# --- 5a. Query: Nearest Neighbor ---
print("[3/6] Running 10 nearest-neighbor queries (top-5)...")
query_times = []
for _ in range(N_QUERIES):
    q_vec = rng.standard_normal(VEC_DIM).astype(np.float32).tolist()
    t0 = time.perf_counter()
    results = tbl.search(q_vec).limit(TOP_K).to_arrow()
    query_times.append(time.perf_counter() - t0)

avg_query = sum(query_times) / len(query_times)
min_query = min(query_times)
max_query = max(query_times)
print(f"       Avg query: {avg_query*1000:.1f}ms  (min {min_query*1000:.1f}ms, max {max_query*1000:.1f}ms)")

# --- 5b. Query with metadata filter ---
print("[4/6] Querying with metadata filter (motion_score > 0.5)...")
q_vec = rng.standard_normal(VEC_DIM).astype(np.float32).tolist()
t0 = time.perf_counter()
filtered = tbl.search(q_vec).where("motion_score > 0.5").limit(TOP_K).to_arrow()
filter_time = time.perf_counter() - t0
print(f"       Filtered query: {filter_time*1000:.1f}ms  ({filtered.num_rows} results)")

# --- 5a2. Query after warmup (exclude first cold query) ---
warm_queries = query_times[1:]  # skip first (cold) query
avg_warm = sum(warm_queries) / len(warm_queries)
print(f"       Avg warm query:  {avg_warm*1000:.1f}ms  (excluding cold start)")

# --- 5c. Disk footprint ---
def get_dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            total += os.path.getsize(os.path.join(dirpath, f))
    return total

disk_bytes = get_dir_size(DB_PATH)
disk_mb = disk_bytes / (1024 * 1024)
print(f"[5/6] Disk footprint: {disk_mb:.1f} MB")

# --- 5d. RAM ---
ram_after = tracemalloc.get_traced_memory()[0]
ram_peak = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
ram_delta_mb = (ram_after - ram_before) / (1024 * 1024)
ram_peak_mb = ram_peak / (1024 * 1024)
print(f"       RAM delta: {ram_delta_mb:.1f} MB  (peak traced: {ram_peak_mb:.1f} MB)")

# --- 6. Startup time ---
print("[6/6] Testing DB re-open + first query...")
del tbl
del db

t0 = time.perf_counter()
db2 = lancedb.connect(DB_PATH)
tbl2 = db2.open_table("scenes")
startup_time = time.perf_counter() - t0

q_vec = rng.standard_normal(VEC_DIM).astype(np.float32).tolist()
t0 = time.perf_counter()
_ = tbl2.search(q_vec).limit(TOP_K).to_arrow()
first_query_after_open = time.perf_counter() - t0
print(f"       Startup (connect+open): {startup_time*1000:.1f}ms")
print(f"       First query after open: {first_query_after_open*1000:.1f}ms")

# --- 7. Verdict ---
print(f"\n{'='*60}")
print("RESULTS SUMMARY")
print(f"{'='*60}")
print(f"  Insert 10k rows:        {insert_time:.3f}s")
print(f"  Avg NN query (top-5):   {avg_query*1000:.1f}ms  (warm: {avg_warm*1000:.1f}ms)")
print(f"  Filtered query:         {filter_time*1000:.1f}ms")
print(f"  Disk footprint:         {disk_mb:.1f} MB")
print(f"  RAM delta:              {ram_delta_mb:.1f} MB")
print(f"  RAM peak (traced):      {ram_peak_mb:.1f} MB")
print(f"  Startup time:           {startup_time*1000:.1f}ms")
print(f"  First query after open: {first_query_after_open*1000:.1f}ms")

# Decision criteria
issues = []
if insert_time > 30:
    issues.append(f"Insert too slow: {insert_time:.1f}s")
if avg_warm * 1000 > 500:
    issues.append(f"Warm query too slow: {avg_warm*1000:.0f}ms")
if disk_mb > 500:
    issues.append(f"Disk too large: {disk_mb:.0f}MB")
if ram_peak_mb > 2000:
    issues.append(f"RAM too high: {ram_peak_mb:.0f}MB")
if startup_time > 5:
    issues.append(f"Startup too slow: {startup_time:.1f}s")

print(f"\n{'='*60}")
if issues:
    print("VERDICT:  NO-GO")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("VERDICT:  GO")
    print("  LanceDB ist performant genug fuer PB Studio.")
    print("  10k Eintraege: schneller Insert, sub-second Queries,")
    print("  moderater Disk/RAM Footprint, schneller Startup.")
print(f"{'='*60}")

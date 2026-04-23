import sqlite3
import os

db_path = 'pb_studio.db'
if not os.path.exists(db_path):
    # Try different location or find it
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Migration Verification ---")
cursor.execute("SELECT * FROM analysis_status WHERE media_type='system'")
print("System Marker:", cursor.fetchall())

cursor.execute("SELECT count(*) FROM analysis_status WHERE step_key='structure_enrichment'")
print("Structure Enrichment count:", cursor.fetchone()[0])

cursor.execute("SELECT count(*) FROM mem_learned_pattern WHERE pattern_type='legacy_ai_memory'")
print("Legacy Patterns count:", cursor.fetchone()[0])

conn.close()

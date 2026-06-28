"""Brain V3 Storage-Layer — sqlite3 + sqlite-vec.

Repository-Pattern strikt: sqlite_vec.load() und sqlite3.connect() werden
NUR in diesem Subfolder verwendet. Alle anderen V3-Module (audio/, video/,
spaeter brain-core) greifen via Repository-API zu.
"""

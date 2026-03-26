# Technology Decisions Archive

> Warum haben wir X statt Y gewaehlt? Dieses Dokument bewahrt die Entscheidungsgruende
> auf, damit wir nicht dieselben Evaluierungen wiederholen.

---

## D-01: Beat-This statt Madmom

**Datum:** 2026-03-19 (Phase 1)
**Entscheidung:** `beat-this` (CPJKU) mit `dbn=False`
**Alternativen evaluiert:** madmom, librosa.beat

| Kriterium | beat-this | madmom | librosa.beat |
|-----------|-----------|--------|--------------|
| Python 3.11+ | Ja (dbn=False) | NEIN (np.float removed) | Ja |
| GPU-Support | CUDA | Nein | Nein |
| Genauigkeit | State-of-Art | Gut | Mittelmaessig |
| Downbeat-Detection | Ja | Ja | Nein |
| VRAM (30s Audio) | ~1.2 GB | N/A | N/A |

**Warum:** Madmom ist seit NumPy 1.24 kaputt (nutzt `np.float`). Beat-this
liefert Downbeats UND laeuft auf GPU. Mit `dbn=False` kein Madmom noetig.

**Risiko:** Beat-this ist ein Git-Dependency (nicht auf PyPI). Bei Breaking Changes
muessen wir den Commit pinnen.

---

## D-02: LanceDB statt ChromaDB / Pinecone

**Datum:** 2026-03-19 (Phase 1)
**Entscheidung:** LanceDB (embedded, lokal)
**Alternativen evaluiert:** ChromaDB, Pinecone, FAISS

| Kriterium | LanceDB | ChromaDB | Pinecone | FAISS |
|-----------|---------|----------|----------|-------|
| Embedded (kein Server) | Ja | Ja | Nein (Cloud) | Ja |
| Filtered Search | Ja (SQL-like) | Ja | Ja | Nein (nur Vektoren) |
| Disk-basiert | Ja (Arrow) | Ja (DuckDB) | Cloud | Nein (RAM) |
| Windows-Support | Gut | Problematisch | N/A | Gut |
| 10k Query Latenz | ~3ms | ~10ms | ~20ms | ~1ms |

**Warum:** Embedded (kein Server-Prozess), Arrow-basiert (effizient auf Disk),
Filtered Search fuer `motion_score > X`, und guter Windows-Support.
ChromaDB hatte File-Lock-Probleme unter Windows.

**Hinweis:** LanceDB ist auf Version 0.30.0 gepinnt wegen Breaking API-Changes
in neueren Versionen.

---

## D-03: NVENC statt Software-Encoding

**Datum:** 2026-03-19 (Phase 1)
**Entscheidung:** FFmpeg mit h264_nvenc (NVIDIA Hardware-Encoding)

**Warum:**
- Edit-Proxy (540p): ~50x schneller als libx264
- Master-Export (1080p): ~15x schneller
- CUDA Decode + NVENC Encode = Full HW Pipeline
- GTX 1060 unterstuetzt NVENC

**Fallback:** Software-Encoding (libx264) wenn keine NVIDIA GPU erkannt wird.
Implementiert in `services/convert_service.py`.

---

## D-04: OpenTimelineIO statt eigenes Timeline-Format

**Datum:** 2026-03-19 (Phase 1)
**Entscheidung:** OTIO als Timeline-Backend

**Warum:**
- Industriestandard (Pixar/Netflix)
- EDL + .otio Export fuer DaVinci Resolve Import
- Marker-System mit Custom Metadata (fuer Anchors)
- Multi-Track Support

**Bekannte Einschraenkung:** `AnyVector`/`AnyDictionary` Round-Trip erfordert
`safe_get_metadata()` Wrapper (siehe snippets.md #5).

---

## D-05: DuckDB — NICHT umgesetzt, entfernen

**Datum:** 2026-03-19 (ki_bauplan.txt)
**Urspruenglicher Plan:** DuckDB fuer Analytics neben SQLite
**Status:** NIE IMPLEMENTIERT

**Warum nicht:** SQLAlchemy + SQLite deckt alle aktuellen Anforderungen ab.
DuckDB war fuer OLAP-Queries auf grossen Clip-Datenbanken gedacht, aber
die Datenmengen sind zu klein fuer den Overhead.

**Aktion:** Dependency aus `pyproject.toml` entfernen (~50MB Ballast).

---

## D-06: PySide6 statt PyQt6

**Datum:** 2026-03-19 (Projektstart)
**Entscheidung:** PySide6 (Qt for Python, LGPL)

**Warum:** LGPL-Lizenz erlaubt kommerzielle Nutzung ohne Qt-Lizenzkosten.
PyQt6 waere GPL (oder kommerzielle Lizenz noetig). Funktional identisch.

**Hinweis:** Code-Kommentare und Skills referenzieren manchmal "PyQt6" —
das ist technisch falsch, wir nutzen PySide6. Die API ist nahezu identisch.

---

## D-07: Demucs htdemucs statt Open-Unmix / Spleeter

**Datum:** 2026-03-19
**Entscheidung:** Meta's Demucs (htdemucs Modell)

| Kriterium | Demucs htdemucs | Open-Unmix | Spleeter |
|-----------|-----------------|------------|----------|
| Qualitaet (SDR) | State-of-Art | Gut | Veraltet |
| 4-Stem Support | Ja | Ja | Ja |
| 6-Stem Support | Ja (htdemucs_6s) | Nein | Nein |
| GPU-Support | CUDA | CUDA | Nein |
| VRAM (3min Song) | ~3.5 GB | ~1.5 GB | ~0.5 GB |

**Warum:** Beste Trennungsqualitaet. VRAM-Verbrauch ist hoch, aber mit
sequentiellem Laden (siehe snippets.md #2) machbar auf GTX 1060.

---

## D-08: SigLIP statt CLIP fuer Video-Embeddings

**Datum:** 2026-03-20 (Phase 2)
**Entscheidung:** SigLIP (1152-dim) statt CLIP (512-dim)

**Warum:** SigLIP hat bessere Zero-Shot Accuracy und groessere Embedding-Dimension
(1152 vs 512). Der Text-to-Video Search profitiert von der hoeheren Aufloesung.
Laeuft ueber `transformers` Pipeline.

---

## D-09: Kein DaVinci-Style Color Grading (Feature Gap)

**Datum:** 2026-03-20 (feature_gap_analysis.md)
**Entscheidung:** NICHT implementieren

**Warum:** PB Studio ist ein *Pacing-Tool*, kein NLE. Color Grading gehoert
in DaVinci Resolve. Wir exportieren .otio/.edl fuer den Uebergang.
Focus auf das, was wir besser koennen: KI-gestuetztes Beat-Synchrones Editing.

# Legacy Snippets Archive

> Wichtige Code-Patterns und Erkenntnisse aus geloeschten POC-Dateien.
> Geloescht in Commit `7d95560` (2026-03-24). Hier archiviert fuer den Fall,
> dass wir diese Patterns erneut brauchen.

---

## 1. Beat-This: dbn=False ist Pflicht (poc_beat_this.py)

**Problem:** `beat-this` laedt standardmaessig `madmom` als DBN-Postprocessor.
Madmom ist inkompatibel mit Python 3.11+ (nutzt `np.float` alias, entfernt in NumPy 1.24).

**Loesung:**
```python
from beat_this.inference import Audio2Beats

model = Audio2Beats(device="cuda", dbn=False)  # KRITISCH: dbn=False!
beats, downbeats = model(audio_path)

# BPM aus Beat-Intervallen berechnen:
intervals = np.diff(beats)
median_interval = np.median(intervals)
bpm = 60.0 / median_interval
```

**Erkenntnis:** Mit `dbn=False` brauchen wir madmom nicht. Die Ergebnisse sind
trotzdem praezise genug fuer DJ-Pacing. Jetzt in `services/beat_analysis_service.py` produktiv.

---

## 2. VRAM-Budget: Sequentielles Laden auf GTX 1060 (poc_beat_this_test2.py)

**Getestete Konfiguration:** GTX 1060 6GB VRAM

| Modell | VRAM (idle) | VRAM (inference) | Max Duration |
|--------|-------------|------------------|--------------|
| Beat-This | ~800 MB | ~1.2 GB (30s) | ~300s bevor OOM |
| Demucs (htdemucs) | ~1.5 GB | ~3.5 GB | abhaengig von Chunk-Groesse |

**Pattern: Sequentielles GPU-Laden**
```python
# Erst Beat-This, dann entladen, dann Demucs
model_beat = Audio2Beats(device="cuda", dbn=False)
beats = model_beat(audio)
del model_beat
torch.cuda.empty_cache()  # VRAM freigeben

# Jetzt ist Platz fuer Demucs
separator = StemSeparator()
stems = separator.separate(audio)
```

**Erkenntnis:** Nie zwei grosse Modelle gleichzeitig auf der GPU. Der `ModelManager`
Singleton in `services/model_manager.py` erzwingt jetzt dieses Pattern.

---

## 3. LanceDB: 10k Vektoren in <2s, Query <5ms (poc_lancedb.py)

**Benchmark-Ergebnisse (1152-dim SigLIP Vektoren):**

| Operation | Ergebnis |
|-----------|----------|
| Bulk Insert (10k Eintraege) | ~1.8s |
| Warm Query (Top-10 NN) | ~2-4ms |
| Filtered Query (motion > 0.5) | ~3-6ms |
| Disk Footprint (10k) | ~85 MB |
| RAM Usage | ~180 MB |
| Cold-Start Reopen | ~0.3s |

**Entscheidung:** GO. LanceDB ist performant genug. Jetzt in `services/vector_db_service.py`.

**Wichtiges Pattern: Schema-Definition**
```python
import lancedb
from lancedb.pydantic import LanceModel, Vector

class ClipEmbedding(LanceModel):
    clip_id: int
    vector: Vector(1152)  # SigLIP embedding dimension
    motion_score: float
    scene_type: str
```

---

## 4. NVENC: 3 Export-Profile (poc_nvenc.py)

**Getestete Profile:**
```python
EXPORT_PROFILES = {
    "edit_proxy": {
        "resolution": "960x540",
        "preset": "p1",       # Schnellster NVENC Preset
        "cq": 28,             # Niedrige Qualitaet, schnell
    },
    "master_export": {
        "resolution": "1920x1080",
        "preset": "p4",       # Balanced
        "cq": 18,             # Hohe Qualitaet
    },
    "davinci_proxy": {
        "resolution": "1280x720",
        "codec": "dnxhd",     # DNxHR LB fuer DaVinci Import
        "profile": "dnxhr_lb",
    },
}
```

**Erkenntnis:** CUDA Decode + NVENC Encode funktioniert als Full-HW-Pipeline.
FFmpeg Progress-Parsing via `-progress pipe:1` liefert Frame-genauen Fortschritt.
Jetzt in `services/convert_service.py` und `services/export_service.py`.

---

## 5. OTIO: AnyVector Round-Trip Bug (poc_otio.py)

**Problem:** OpenTimelineIO speichert Python-Listen als `AnyVector` Objekte.
Nach Reload sind das keine normalen Listen mehr — `isinstance(x, list)` ist False.

**Loesung:**
```python
def safe_get_metadata(marker, namespace, key, default=None):
    """Sicherer Zugriff auf OTIO Marker-Metadaten mit AnyVector-Konvertierung."""
    try:
        md = marker.metadata.get(namespace, {})
        val = md.get(key, default)
        # AnyVector -> Python list konvertieren
        if hasattr(val, '__iter__') and not isinstance(val, (str, list)):
            return list(val)
        return val
    except Exception:
        return default
```

**Erkenntnis:** Immer `safe_get_metadata()` nutzen, nie direkt auf OTIO Metadaten
zugreifen. Pattern jetzt in `services/timeline_service.py`.

---

## 6. Librosa 0.11 BPM Scalar Bug (master_rebuild_bericht.md)

**Problem:** `librosa.beat.tempo()` gibt seit v0.11 ein `ndarray` statt `float` zurueck.

**Fix:**
```python
tempo = librosa.beat.tempo(y=y, sr=sr)
bpm = float(np.asarray(tempo).flat[0])  # Sicher: ndarray -> scalar
```

**Erkenntnis:** Librosa-API aendert sich oft. Immer defensiv casten.

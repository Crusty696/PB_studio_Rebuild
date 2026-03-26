# AI Stack Evaluation 2026 — PB Studio Rebuild

**Erstellt:** März 2026
**App:** PB_studio_Rebuild (PySide6, Windows, NVIDIA CUDA)
**Python-Version:** 3.11-3.12 | **CUDA (aktuell):** 12.1 (cu121)

---

## 1. Vollständige Bestandsaufnahme

### 1.1 Gesamtarchitektur

PB Studio Rebuild ist eine PySide6-Desktop-App für musiksynchrone Video-Produktion. Das KI-System:

- **ModelManager (Singleton):** Strenger VRAM-Manager – immer nur EIN Modell gleichzeitig im GPU-Speicher
- **5 KI-Agenten:** AudioAgent, VisionAgent, EditorAgent, PacingAgent, OrchestratorAgent
- **Ziel-Hardware:** NVIDIA GPU mit CUDA (entwickelt auf GTX 1060 6GB VRAM)

---

### 1.2 KI-Modell-Bestandsliste

| Modell | ID / Paket | Verwendet für | Datei |
|---|---|---|---|
| **Demucs htdemucs** | demucs PyPI | Stem-Trennung (Vocals/Drums/Bass/Other) | ai_audio_service.py |
| **faster-whisper base** | WhisperModel("base") | Audio-Transkription | model_manager.py |
| **Moondream2** | vikhyatk/moondream2 | Video-Inhaltsbeschreibung (Frames) | vision_agent.py |
| **SigLIP Base** | google/siglip-base-patch16-384 | Visual Embeddings für Vektorsuche | model_manager.py |
| **beat_this** | github.com/CPJKU/beat_this | Beat/Downbeat-Erkennung (GPU) | beat_analysis_service.py |

> ### ⚠️ KRITISCHER BUG GEFUNDEN
> In model_manager.py lädt load_siglip() standardmäßig google/siglip-base-patch16-384 (768-dim Output),
> aber vector_db_service.py erwartet EMBEDDING_DIM = 1152 Dimensionen.
> Das korrekte Modell für 1152-dim ist google/siglip-so400m-patch14-384.
> Dieser Dimensionsmismatch führt zu Fehlern beim Speichern von Embeddings!

---

### 1.3 ML-Bibliotheken-Bestandsliste

| Bibliothek | Version (pyproject.toml) | Verwendung |
|---|---|---|
| torch | >=2.5.0 | Basis ML-Framework |
| torchvision | >=0.20.0 | Bildverarbeitung |
| torchaudio | >=2.5.0 | Audio-Verarbeitung |
| transformers | >=4.47.0 | HuggingFace-Modelle (SigLIP, Moondream2) |
| accelerate | >=1.2.0 | HuggingFace-Beschleunigung |
| faster-whisper | >=1.1.0 | Whisper-Inference via CTranslate2 |
| demucs | >=4.0.1 | Stem-Separation |
| librosa | >=0.11.0 | Audio-Analyse, FFT, BPM (Frequenzanalyse) |
| beat-this | @main (GitHub) | Beat-Erkennung |
| opencv-python | >=4.10.0 | Video-Frame-Extraktion |
| scipy | >=1.14.0 | Audio-DSP, Auto-Ducking |
| einops | >=0.8.0 | Tensor-Operationen |
| lancedb | >=0.20.0 | Vector-Datenbank |
| pyarrow | >=18.0.0 | Spaltenformat fuer LanceDB |
| scenedetect | >=0.6.0 | Szenen-/Schnitterkennung |
| soundfile | >=0.12.0 | Audio I/O |
| numpy | >=2.1.0 | Numerische Berechnungen |


---

## 2. Alternativen-Analyse pro Kategorie

### 2.1 Stem-Separation (Demucs)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| htdemucs | v4.0.1 | htdemucs_ft (fine-tuned) | Moderat (+2-4% SDR) | Minimal (1 Parameter) | SOFORT UPGRADEN |
| htdemucs | v4.0.1 | htdemucs_6s (6-Stems) | Gleich + Piano/Guitar | Minimal | Piano-Qualitaet instabil |
| Demucs allgemein | v4 | Spleeter (Deezer) | Negativ (schlechter) | Mittel | NICHT empfohlen |

**Fazit Demucs:** htdemucs_ft ist der klare Gewinner im Open-Source-Bereich. Durch Aendern von
model="htdemucs" zu model="htdemucs_ft" in ai_audio_service.py ist der Upgrade in 2 Minuten erledigt.
Nachteil: 4x laengere Verarbeitungszeit. Fuer Produktionsqualitaet klar empfehlenswert.

---

### 2.2 Beat/Downbeat-Erkennung

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| beat_this | @main | madmom + DBN | Aehnlich, madmom besser bei Jazz | Mittel (Python 3.11 Fixes) | Nur wenn madmom-Kompatibilitaet geloest |
| beat_this | @main | BeatNet | Echtzeit-faehig, aehnliche Qualitaet | Mittel | Nur fuer Echtzeit |
| librosa.beat.beat_track (FrequencyAnalyzer) | 0.11 | beat_this (bereits vorhanden!) | Sehr stark (+15-20%) | Gering | SOFORT UMSTELLEN |

**Fazit beat_this:** beat_this ist eine ausgezeichnete Wahl (aktiv von CPJKU gewartet, GPU-first Design).
PROBLEM: FrequencyAnalyzer in ai_audio_service.py verwendet noch librosa.beat.beat_track fuer BPM –
das sollte auf den bereits vorhandenen BeatAnalysisService umgeleitet werden.

---

### 2.3 Audio-Transkription (Whisper)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| faster-whisper base | 1.1.0 | faster-whisper large-v3 | Sehr stark (WER 8% auf 2.5%) | Minimal (1 Parameter) | Fuer hoechste Qualitaet |
| faster-whisper base | 1.1.0 | distil-large-v3.5 | Stark (WER ~3%, 6.3x schneller) | Gering | BESTE BALANCE |
| faster-whisper base | 1.1.0 | whisper-large-v3-turbo | Aehnlich wie distil, multilingual | Gering | Gut |
| faster-whisper | 1.1.0 | WhisperX | + Diarisierung, Word-Timestamps | Mittel | Wartung eingeschraenkt |

**Fazit Whisper:** Das System verwendet "base" als Standardmodell – der schwaechste Whisper und fuer
professionellen Einsatz ungeeignet. distil-large-v3.5 bietet 6.3x hoehere Geschwindigkeit als large-v3
bei quasi gleicher Genauigkeit (<1.5% WER-Unterschied). Upgrade benoetigt nur eine Zeile Code.
Benoetigt ~2GB VRAM (statt 0.3GB fuer base). Auf GTX 1060: Modelle sequentiell laden, kein Problem.

---

### 2.4 Video-Inhaltsbeschreibung (VLM)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| moondream2 | 2025-06-21 | Qwen2.5-VL-3B-Instruct | Sehr stark (deutlich bessere Beschreibungen) | Mittel | Fuer RTX 3060+ empfohlen |
| moondream2 | – | SmolVLM2-2B | Moderat besser, video-faehig | Gering | Gute Alternative |
| moondream2 | – | Florence-2 (Microsoft) | Aehnliche Qualitaet, besser fuer OCR | Mittel | Fuer Detection besser |
| moondream2 | – | Qwen2.5-VL-7B-Instruct | Sehr stark | Hoch | VRAM-kritisch auf GTX 1060 |

**Fazit VLM:** Moondream2 ist auf dem neuesten Stand (Juni 2025) und fuer das VRAM-Budget einer
GTX 1060 gut geeignet (~1.5GB VRAM). Qwen2.5-VL-3B wuerde die Beschreibungsqualitaet deutlich
verbessern (~4-5GB VRAM). Auf RTX 3060+ klar zu empfehlen; GTX 1060: Moondream2 bleibt sicher.

---

### 2.5 Vision Embeddings (SigLIP)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| siglip-base-patch16-384 (768-dim Bug!) | 2023 | siglip-so400m-patch14-384 (korrekte 1152-dim) | Bug-Fix + Qualitaetsgewinn | Minimal | SOFORT FIXEN |
| siglip-so400m | 2023 | google/siglip2-so400m-patch14-384 | Stark (Feb 2025, besser Retrieval) | Gering | EMPFOHLEN |
| siglip-so400m | 2023 | Apple/DFN5B-CLIP-ViT-H-14 | Sehr stark (Top-Benchmark) | Hoch (DB-Migration) | Nur bei Neuaufbau |
| siglip-so400m | 2023 | OpenCLIP ViT-H-14-quickgelu | Aehnlich wie DFN5B | Hoch | DB-Migration noetig |

**Fazit SigLIP:** Zwei getrennte Massnahmen:
1. Bug-Fix (sofort): siglip-base → siglip-so400m (768-dim Bug → korrekte 1152-dim)
2. Quality-Upgrade: → siglip2-so400m (Feb 2025, besser bei Zero-Shot und Retrieval, gleiche Dims!)

SigLIP 2 (Februar 2025) erweitert das Training um: captioning-based pretraining,
self-distillation, masked prediction – deutlich bessere semantische Qualitaet.

---

### 2.6 Vektordatenbank (LanceDB)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| lancedb | >=0.20.0 | Qdrant (embedded mode) | Besser bei Filtering/Skalierung | Mittel | Nur bei Skalierungsbedarf |
| lancedb | >=0.20.0 | ChromaDB | Einfachere API | Mittel | Schlechtere Disk-Performance |
| lancedb | >=0.20.0 | FAISS (GPU) | Schneller bei reiner ANN-Suche | Hoch | Kein Metadata-Support |
| lancedb | >=0.20.0 | LanceDB (neueste Version) | Bugfixes, neue Features | Minimal | Version aktuell halten |

**Fazit LanceDB:** Fuer diese Anwendung (eingebettet, kein Server, Desktop-App) die BESTE WAHL.
Apache Arrow + Memory-Mapping = ideal fuer lokale Anwendungen. Keine Migration noetig.

---

### 2.7 Szenen-/Schnitterkennung (PySceneDetect)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| PySceneDetect | >=0.6.0 | TransNetV2 (Neural Net) | Stark bei komplexen Uebergaengen | Mittel | Ergaenzend hinzufuegen |
| PySceneDetect | >=0.6.0 | AutoShot (NAS-basiert) | Besser bei ungewoehnlichen Schnitten | Hoch | Wenig Community-Support |

**Fazit PySceneDetect:** Solid und gut wartbar. TransNetV2 als Ergaenzung fuer schwierige
Schnitte optional sinnvoll, aber kein dringender Handlungsbedarf.

---

### 2.8 Audio-Analyse (librosa)

| Aktuell | Version | Beste Alternative | Qualitaetsgewinn | Aufwand | Empfehlung |
|---|---|---|---|---|---|
| librosa (STFT/Spektrum) | 0.11 | torchaudio (GPU) | Stark bei GPU-beschleunigten Ops | Mittel | Fuer Mel-Spectrogramme |
| librosa.beat.beat_track | 0.11 | beat_this (bereits vorhanden) | Sehr stark | Gering | SOFORT UMSTELLEN |
| librosa allgemein | 0.11 | librosa (beibehalten) | Gut genug fuer Spektralanalyse | Keiner | Bleibt |

**Fazit librosa:** Gut fuer Spektral-Analyse (STFT, Frequenzbaender). Einziger kritischer Punkt:
FrequencyAnalyzer verwendet noch librosa.beat.beat_track fuer BPM – auf BeatAnalysisService umleiten.

---

### 2.9 ML-Infrastruktur (PyTorch/CUDA)

| Aktuell | Version | Stand 2026 | Empfehlung |
|---|---|---|---|
| torch | >=2.5.0 | 2.6+ verfuegbar | Upgrade auf 2.6+, CUDA 12.8 |
| CUDA | 12.1 (cu121) | CUDA 12.8 ist aktueller Stand | Upgrade auf cu128 fuer neue GPUs |
| transformers | >=4.47.0 | Aktiv entwickelt | Auf neueste Version pinnen |
| accelerate | >=1.2.0 | Aktiv | Gut |
| PySide6 | >=6.8.0 | Qt 6.9+ verfuegbar | Upgrade pruefen |


---

## 3. Top-5 Upgrade-Empfehlungen

### Rang 1 – BUG-FIX SigLIP-Dimensionsmismatch (KRITISCH)

**Problem:** model_manager.py laedt google/siglip-base-patch16-384 (768-dim),
aber vector_db_service.py erwartet EMBEDDING_DIM = 1152. Fehlende Konformitaet!

**Fix (1 Zeile):**
`python
# model_manager.py -> load_siglip() Standardwert aendern:
def load_siglip(self, model_id: str = "google/siglip-so400m-patch14-384") -> tuple:
`
Dann LanceDB-Tabelle loeschen und alle Videos neu embedden.

**Aufwand:** 1 Zeile Code + Neuindexierung der Videos
**Impact:** KRITISCH – ohne diesen Fix funktioniert die Vektorsuche nicht korrekt

---

### Rang 2 – SigLIP → SigLIP 2 (Hoher Qualitaetsgewinn, Geringer Aufwand)

**Upgrade:** google/siglip-so400m-patch14-384 -> google/siglip2-so400m-patch14-384

Vorteile:
- Gleiche Embedding-Dimensionen (1152-dim) -> keine DB-Schema-Aenderung
- Besser bei: Zero-Shot-Klassifizierung, Image-Text-Retrieval, Multilingual
- Veroeffentlicht: Februar 2025 (Paper: arXiv 2502.14786)
- Vollstaendig kompatibel mit HuggingFace Transformers >=4.49.0
- Verbesserte Objectives: captioning pretraining + self-distillation + masked prediction

**Fix:**
`python
# model_manager.py:
def load_siglip(self, model_id: str = "google/siglip2-so400m-patch14-384") -> tuple:
`

**Aufwand:** 1 Zeile + LanceDB neu-indexieren (alle Videos erneut embedden)
**Impact:** Deutlich bessere Clip-Suchqualitaet bei gleichem VRAM-Verbrauch

---

### Rang 3 – faster-whisper base -> distil-large-v3.5 (Sehr hoher Qualitaetsgewinn)

**Upgrade:** WhisperModel("base") -> WhisperModel("distil-large-v3.5")

Fakten:
- WER-Verbesserung: ~8% (base) -> ~3% (distil-large-v3.5)
- 6.3x schneller als large-v3 bei nur ~1.5% schlechterem WER
- distil-large-v3.5: 756M Parameter (statt 1.55B bei large-v3)
- Vollstaendig kompatibel mit faster-whisper API
- VRAM: ~2GB (statt 0.3GB fuer base) - auf GTX 1060 mit ModelManager OK

**Fix:**
`python
# model_manager.py -> load_whisper():
compute_type = "float16" if self.device == "cuda" else "int8"
self._model = WhisperModel(
    "distil-large-v3.5",   # <-- statt "base"
    device=self.device,
    compute_type=compute_type,
)
`

**Aufwand:** 1 Zeile + erster Download ~1.5GB
**Impact:** Professionell nutzbare Transkription (fuer DJ-Mix-Analyse sehr wichtig)

---

### Rang 4 – htdemucs -> htdemucs_ft (Moderat hoehere Stem-Qualitaet)

**Upgrade:** model="htdemucs" -> model="htdemucs_ft" in ai_audio_service.py

Vorteile:
- Fine-tuned Version von htdemucs (gleiche Architektur)
- Messbar bessere Vocal Isolation (+2-4% Signal-to-Distortion-Ratio)
- Nachteil: 4x laengere Verarbeitungszeit (30-Min-Mix: ~8min statt ~2min)
- Fuer DJ-Mix-Produktionen: Qualitaet vor Geschwindigkeit

**Fix:**
`python
# ai_audio_service.py -> StemSeparator.separate():
def separate(self, file_path: str, model: str = "htdemucs_ft", ...):
`

**Aufwand:** 1 Zeile
**Impact:** Spuerbar sauberere Vocals/Drums-Trennung fuer Pacing-Analyse

---

### Rang 5 – CUDA 12.1 -> CUDA 12.8 (Zukunftssicherung)

**Upgrade:** pytorch-cuda Source von cu121 -> cu128

Gruende:
- CUDA 12.1 wird von neueren PyTorch-Versionen deprioritisiert
- RTX 4000/5000-Serien benoetigen CUDA 12.6+ fuer volle Feature-Nutzung
- Alle aktuellen Bibliotheken (faster-whisper, demucs, beat_this) unterstuetzen CUDA 12.8

**Fix in pyproject.toml:**
`	oml
[[tool.poetry.source]]
name = "pytorch-cuda"
url = "https://download.pytorch.org/whl/cu128"
priority = "explicit"
`

Dann: poetry install (komplette Neuinstallation des PyTorch-Stacks)

**Aufwand:** Neuinstallation ~30 Minuten
**Impact:** Zukunftssicher, bessere Kompatibilitaet mit aktuellen + neuen GPUs

---

## 4. Gesamtbewertung – Was bleibt, was wird geaendert

| Komponente | Status | Begruendung |
|---|---|---|
| Demucs v4 | BLEIBT (Upgrade htdemucs_ft) | Best-in-class Open Source Stem-Separation |
| beat_this | BLEIBT | Beste GPU-Beat-Erkennung, aktiv von CPJKU gewartet |
| faster-whisper | BLEIBT (Modell upgraden) | Bibliothek ideal; Modell von base auf distil-large-v3.5 |
| LanceDB | BLEIBT | Perfekt fuer eingebettete Desktop-App ohne Server |
| ModelManager | BLEIBT | Exzellentes VRAM-Management fuer Single-GPU |
| librosa | BLEIBT (fuer Spektralanalyse) | BPM-Detection auf beat_this umleiten |
| PySceneDetect | BLEIBT | Gut genug; TransNetV2 optional ergaenzen |
| Moondream2 | BLEIBT (GTX 1060) | Auf RTX 3060+ -> Qwen2.5-VL-3B evaluieren |
| SigLIP Base | BUG-FIX + UPGRADE DRINGEND | Model-ID falsch (768-dim Bug) + SigLIP2-Upgrade |
| CUDA 12.1 | MITTELFRISTIG UPGRADEN | CUDA 12.8 fuer neue GPU-Kompatibilitaet |
| Whisper base | UPGRADE DRINGEND | Zu ungenau fuer professionellen Einsatz |
| FrequencyAnalyzer BPM | REFACTORING | librosa.beat_track -> BeatAnalysisService (beat_this) |

---

## 5. Weitere Optimierungspotentiale

### 5.1 RAFT Optical Flow (aktuell nicht implementiert)
Im Code nicht gefunden. Falls Motion-Score-Berechnung verbessert werden soll:
- RAFT (Princeton): State-of-the-art Optical Flow, GPU, via torchvision.models.optical_flow
- Aktuell: motion_score = 0.0 Default in vector_db_service.py (nicht berechnet)
- Aufwand: Mittel; Qualitaetsgewinn: Sehr hoch fuer Pacing-Entscheidungen

### 5.2 Multi-Frame Embedding Strategie
- Aktuell: SigLIP fuer einzelne Frames
- Besser: Mehrere Frames pro Szene embedden und mitteln (temporales Pooling)
- Verbesserung ohne Modellwechsel moeglich

### 5.3 FrequencyAnalyzer Doppelung entfernen
- FrequencyAnalyzer berechnet BPM via librosa.beat.beat_track
- BeatAnalysisService macht dasselbe via beat_this (deutlich besser)
- Refactoring: FrequencyAnalyzer soll BeatAnalysisService aufrufen

---

## 6. Massnahmenplan

### Sofort (< 1 Stunde, minimales Risiko)
1. SigLIP Bug-Fix: siglip-base-patch16-384 -> siglip-so400m-patch14-384 (1 Zeile)
2. Whisper-Upgrade: "base" -> "distil-large-v3.5" (1 Zeile)
3. Demucs-Upgrade: "htdemucs" -> "htdemucs_ft" (1 Zeile)

### Kurzfristig (< 1 Tag)
4. SigLIP2-Upgrade: siglip-so400m -> siglip2-so400m + Neuindexierung aller Videos
5. FrequencyAnalyzer: BPM-Berechnung auf BeatAnalysisService umleiten

### Mittelfristig (1-3 Tage)
6. CUDA 12.8 Migration: Neuinstallation PyTorch-Stack
7. Qwen2.5-VL-3B evaluieren (bei RTX 3060+ Hardware)
8. TransNetV2 ergaenzend fuer ML-basierte Szenerkennung hinzufuegen
9. RAFT Optical Flow fuer motion_score implementieren

---

## 7. Quellen

- Demucs GitHub: https://github.com/facebookresearch/demucs
- beat_this GitHub: https://github.com/CPJKU/beat_this
- faster-whisper GitHub: https://github.com/SYSTRAN/faster-whisper
- distil-whisper HuggingFace: https://huggingface.co/distil-whisper/distil-large-v3.5
- SigLIP 2 Paper: https://arxiv.org/abs/2502.14786
- SigLIP2 HuggingFace: https://huggingface.co/google/siglip2-so400m-patch14-384
- Moondream2 HuggingFace: https://huggingface.co/vikhyatk/moondream2
- LanceDB Docs: https://lancedb.github.io/lancedb/
- VLMs 2025 Uebersicht: https://huggingface.co/blog/vlms-2025
- Whisper Varianten-Vergleich: https://modal.com/blog/choosing-whisper-variants

---

*Report generiert: Maerz 2026 | PB_studio_Rebuild KI-Stack-Evaluation*

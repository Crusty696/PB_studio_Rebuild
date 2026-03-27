# Refactoring-Plan: Phase 4 Services sicher umbauen

**Erstellt**: 2026-03-27
**Status**: Geplant
**Ziel**: 4 aufgeschobene Refactorings sicher durchführen — testabgesichert, schrittweise, kein Risiko

---

## Kontext

Die Phase-4 Services (Key Detection, LUFS, Audio Classify, Spectral Analysis,
Structure Detection) und ihre Worker sind **funktional fertig**, haben aber:
- ~50 Magic Numbers (jetzt in `audio_constants.py` zentralisiert, aber noch nicht eingebaut)
- Duplizierter Code in Workers und Services
- Lange Methoden (bis 244 Zeilen)
- **0 Unit-Tests** — der Hauptgrund warum Refactorings verschoben wurden

---

## Reihenfolge (Abhängigkeiten beachten)

```
Phase A: Tests schreiben (BLOCKER für alles Weitere)
    ↓
Phase B: audio_constants.py einbauen (einfach, mechanisch)
    ↓
Phase C: Librosa Import-Guard vereinheitlichen
    ↓
Phase D: Lange Methoden aufsplitten
    ↓
Phase E: Worker Template-Method Pattern
```

---

## Phase A: Tests schreiben (BLOCKER)

**Warum zuerst?** Ohne Tests können wir nicht verifizieren dass Refactorings
die Logik nicht ändern. Tests sind das Sicherheitsnetz.

**Definition of Done:** Jeder Service hat ≥3 Unit-Tests die seine Kernlogik prüfen.

### A1: Test-Infrastruktur

- [ ] `tests/test_services/test_key_detection.py` erstellen
- [ ] `tests/test_services/test_lufs.py` erstellen
- [ ] `tests/test_services/test_audio_classify.py` erstellen
- [ ] `tests/test_services/test_spectral.py` erstellen
- [ ] `tests/test_services/test_structure_detection.py` erstellen
- [ ] `tests/test_workers/test_audio_analysis_workers.py` erstellen

### A2: Test-Strategie pro Service

**key_detection_service.py:**
- [ ] Test: Camelot Wheel hat alle 24+10 Einträge
- [ ] Test: _pearson() mit bekannten Vektoren
- [ ] Test: detect_key() mit Mock-librosa (chroma_cqt → bekanntes C-Major Profil)
- [ ] Test: detect_key() Fallback wenn librosa fehlt
- [ ] Test: get_compatible_keys() Wrapping-Logik (Key 1, Key 12, Flat-Notation)

**lufs_service.py:**
- [ ] Test: _safe_float() Edge Cases (-inf, "abc", None, 0.0)
- [ ] Test: _parse_loudnorm_json() mit echtem FFmpeg Output
- [ ] Test: _parse_loudnorm_json() mit kaputtem Output → None
- [ ] Test: analyze() mit Mock-subprocess (normaler Output)
- [ ] Test: analyze() Fallback bei FileNotFoundError
- [ ] Test: analyze() Timeout-Handling

**audio_classify_service.py:**
- [ ] Test: _classify_genre() BPM-Range Matching (140 BPM → Psytrance/Trance)
- [ ] Test: _classify_genre() Disambiguation via Centroid
- [ ] Test: _classify_mood() Threshold-Grenzen
- [ ] Test: _classify_energy() RMS-Grenzen
- [ ] Test: detect_dj_mix() unter 10 Min → False
- [ ] Test: detect_dj_mix() über 30 Min → True
- [ ] Test: classify() Fallback wenn librosa fehlt

**spectral_analysis_service.py:**
- [ ] Test: Band-Energie Berechnung mit synthetischem Sinus (500 Hz → "Mid" Band)
- [ ] Test: Normalisierung (alle Bands auf 0.0-1.0)
- [ ] Test: _detect_events() Drop-Erkennung mit künstlichem Energie-Sprung
- [ ] Test: _detect_events() leeres Array → keine Events
- [ ] Test: get_bands_json() JSON-Format

**structure_detection_service.py:**
- [ ] Test: detect() mit synthetischer Energie-Kurve (niedrig→steigend→hoch→fallend→niedrig)
- [ ] Test: detect() mit < 8 Beats → einzelnes VERSE Segment
- [ ] Test: detect() mit leerer energy_per_beat → Fallback
- [ ] Test: save_to_db() erstellt Segmente in DB
- [ ] Test: save_to_db() Rollback bei Fehler
- [ ] Test: _merge_consecutive() verschmilzt gleiche Labels
- [ ] Test: _remove_short_segments() entfernt kurze Segmente

### A3: Worker-Tests

- [ ] Test: KeyDetectionWorker emittiert finished Signal
- [ ] Test: LUFSAnalysisWorker speichert lufs in DB
- [ ] Test: Worker emittiert error bei kaputtem file_path
- [ ] Test: Worker setzt _errored korrekt zurück

**Geschätzter Aufwand:** ~200-300 Zeilen Testcode, ~2 Stunden

**Benötigte Skills:** `python-testing`

---

## Phase B: audio_constants.py einbauen

**Voraussetzung:** Phase A Tests bestanden (grüne Tests als Basis)

**Strategie:** Ein Service pro Commit, nach jedem Commit Tests laufen lassen.

### B1: key_detection_service.py

- [ ] `from services.audio_constants import DEFAULT_SR, MAX_DURATION_KEY, CHROMA_HOP_LENGTH, CONFIDENCE_EPSILON`
- [ ] Ersetze `sr=22050` → `sr=DEFAULT_SR`
- [ ] Ersetze `duration=120` → `duration=MAX_DURATION_KEY`
- [ ] Ersetze `hop_length=2048` → `hop_length=CHROMA_HOP_LENGTH`
- [ ] Ersetze `1e-9` → `CONFIDENCE_EPSILON`
- [ ] Tests laufen lassen → muss grün sein

### B2: lufs_service.py

- [ ] Import: `FFMPEG_TIMEOUT_SEC, MIN_LUFS_DB, MAX_LUFS_DB, ST_MAX_HEADROOM_DB`
- [ ] Ersetze `timeout=120` → `timeout=FFMPEG_TIMEOUT_SEC`
- [ ] Ersetze `-70.0` → `MIN_LUFS_DB`
- [ ] Ersetze `0.0` (inf clamp) → `MAX_LUFS_DB`
- [ ] Ersetze `true_peak + 3.0` → `true_peak + ST_MAX_HEADROOM_DB`
- [ ] Tests laufen lassen

### B3: audio_classify_service.py

- [ ] Import: Alle Classification Thresholds + DJ-Mix Konstanten
- [ ] Ersetze ~15 Magic Numbers
- [ ] Tests laufen lassen

### B4: spectral_analysis_service.py

- [ ] Import: STFT Parameter + Event Detection Thresholds
- [ ] Ersetze ~20 Magic Numbers
- [ ] Tests laufen lassen

### B5: structure_detection_service.py

- [ ] Import: Alle Structure Detection Konstanten
- [ ] Ersetze ~25 Magic Numbers
- [ ] Tests laufen lassen

**Geschätzter Aufwand:** ~1 Stunde (mechanisch, sicher)

---

## Phase C: Librosa Import-Guard vereinheitlichen

**Voraussetzung:** Phase B abgeschlossen, Tests grün

**Ziel-Pattern:** `_HAS_LIBROSA` Flag auf Modul-Ebene (wie key_detection_service.py)

### C1: Entscheidung

Gewähltes Pattern (wie key_detection_service.py):
```python
try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    _HAS_LIBROSA = False
```

### C2: Umsetzen

- [ ] audio_classify_service.py: Bereits `librosa = None` Pattern → umstellen auf `_HAS_LIBROSA`
- [ ] spectral_analysis_service.py: Inline import → Modul-Level mit Flag
- [ ] structure_detection_service.py: Inline import → Modul-Level mit Flag
- [ ] Tests laufen lassen nach jedem Service

**Geschätzter Aufwand:** ~30 Min

---

## Phase D: Lange Methoden aufsplitten

**Voraussetzung:** Phase C abgeschlossen, Tests grün

**Strategie:** Extract Method — NUR wenn Tests die Logik absichern.

### D1: structure_detection_service.detect() (244 Zeilen → ~5 Methoden)

- [ ] Extrahiere `_label_intro_outro(labels, energy_norm, n_beats) -> None`
- [ ] Tests laufen lassen
- [ ] Extrahiere `_label_buildups(labels, gradient, energy_norm, n_beats) -> None`
- [ ] Tests laufen lassen
- [ ] Extrahiere `_label_drops(labels, energy_norm, n_beats) -> None`
- [ ] Tests laufen lassen
- [ ] Extrahiere `_label_breakdowns(labels, energy_norm, n_beats) -> None`
- [ ] Tests laufen lassen
- [ ] Extrahiere `_form_segments(labels, beats, energy_norm) -> list[StructureSegmentResult]`
- [ ] Tests laufen lassen

### D2: spectral_analysis_service._detect_events() (142 Zeilen → ~4 Methoden)

- [ ] Extrahiere `_detect_drops(energies_norm, window_duration) -> list[SpectralEvent]`
- [ ] Extrahiere `_detect_buildups(energies_norm, window_duration) -> list[SpectralEvent]`
- [ ] Extrahiere `_detect_breakdowns(energies_norm, window_duration) -> list[SpectralEvent]`
- [ ] Extrahiere `_deduplicate_events(events, min_distance) -> list[SpectralEvent]`
- [ ] Tests laufen lassen

### D3: lufs_service.analyze() (112 Zeilen → ~3 Methoden)

- [ ] Extrahiere `_run_ffmpeg(file_path) -> str` (returns stderr)
- [ ] Extrahiere `_extract_values(data: dict) -> LUFSResult`
- [ ] Tests laufen lassen

### D4: Entferne unused `beats` Parameter aus `_remove_short_segments()`

- [ ] Parameter entfernen
- [ ] Alle Aufrufe prüfen (nur 1 Stelle)
- [ ] Tests laufen lassen

**Geschätzter Aufwand:** ~2 Stunden (wegen test-after-each-step)

---

## Phase E: Worker Template-Method Pattern

**Voraussetzung:** Phase D abgeschlossen, Tests grün

**Ziel:** 5 Worker mit ~30 Zeilen identischem Boilerplate → 1 Basis-Klasse + 5 schlanke Worker

### E1: BaseAnalysisWorker erstellen

```python
class BaseAnalysisWorker(QObject, CancellableMixin):
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, audio_track_id: int, file_path: str, **kwargs):
        super().__init__()
        CancellableMixin.__init__(self)
        self.audio_track_id = audio_track_id
        self.file_path = file_path

    def run(self) -> None:
        self._errored = False
        try:
            self.progress.emit(10, self._start_message())
            result = self._analyze()
            self.progress.emit(80, self._done_message(result))
            self._save_to_db(result)
            self.progress.emit(100, "Fertig")
            self._ok = True
            self.finished.emit(result)
        except Exception as e:
            self._errored = True
            logger.error("...", exc_info=True)
            self.error.emit(str(e))
        finally:
            if not self._errored and not self._ok:
                self.finished.emit(None)

    # Abstrakte Methoden — jeder Worker implementiert diese
    def _start_message(self) -> str: ...
    def _analyze(self) -> object: ...
    def _done_message(self, result) -> str: ...
    def _save_to_db(self, result) -> None: ...
```

### E2: Worker umstellen

- [ ] KeyDetectionWorker → erbt von BaseAnalysisWorker
- [ ] Tests laufen lassen
- [ ] LUFSAnalysisWorker → erbt
- [ ] Tests laufen lassen
- [ ] AudioClassifyWorker → erbt
- [ ] Tests laufen lassen
- [ ] SpectralAnalysisWorker → erbt
- [ ] Tests laufen lassen
- [ ] StructureDetectionWorker → erbt (Sonderfall: extra kwargs)
- [ ] Tests laufen lassen

**Geschätzter Aufwand:** ~1.5 Stunden

---

## Risiko-Matrix

| Phase | Risiko | Mitigation |
|-------|--------|-----------|
| A (Tests) | NIEDRIG | Nur neue Dateien, berührt nichts |
| B (Constants) | NIEDRIG | Mechanisch, 1:1 Ersetzung |
| C (Import-Guard) | MITTEL | Könnte Import-Reihenfolge ändern → Tests fangen das |
| D (Split Methods) | MITTEL | Extract Method kann Parameter-Fehler einführen → Tests fangen das |
| E (Template Pattern) | HOCH | Ändert Vererbungshierarchie → braucht Worker-Integration-Tests |

---

## Gesamt-Zeitschätzung

| Phase | Aufwand |
|-------|---------|
| A: Tests | ~2h |
| B: Constants | ~1h |
| C: Import-Guard | ~30min |
| D: Split Methods | ~2h |
| E: Template Pattern | ~1.5h |
| **Gesamt** | **~7h** |

---

## Nächster Schritt

**Phase A starten** — Tests für die 5 neuen Services schreiben.
Skill: `/python-testing`
Dateien: `tests/test_services/test_key_detection.py` etc.

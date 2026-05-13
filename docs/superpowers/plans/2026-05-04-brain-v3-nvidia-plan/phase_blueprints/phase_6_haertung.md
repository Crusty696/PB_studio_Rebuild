# Phase 6 Blueprint — Härtung (Backup, Recovery, Lizenz, NVENC-Fix)

> **🔴 STATUS 2026-05-05: TODO — BUILD-FROM-SCRATCH-MODE**
>
> Vor Beginn prüfen:
> 1. `services/brain_v3/storage/{backup,recovery}.py` sollten **NICHT
>    existieren** (sonst → Verify-Mode statt Build).
> 2. Phase 5 muss DONE sein.
> 3. NVENC-Test-Skript-Bug aus `outputs/spike_brain_v3_open_points/<ts>/`
>    bekannt: `-preset p4` ist Turing+, Pascal braucht `-preset slow`.

## 1. Ziel + Erfolgsdefinition

**Ziel:** Brain V3 produktiv-tauglich. Wöchentliches Backup läuft
automatisch. Korrupter Hirn-Store crasht App nicht. Lizenz-Compliance
dokumentiert. NVENC-Coexistenz-Test mit korrekten Pascal-Parametern.
Optionale ONNX/TensorRT-Eval. R18-HNSW-Workaround validiert.

**Erfolg = wahr wenn:** alle Recovery-Tests grün, LICENSES.md vollständig,
Pacing-Latenz mit Brain V3 <800 ms verifiziert, NVENC + Brain
parallel-Test ohne OOM/Race.

**Aufwand-Schätzung:** laufend — typische Tasks 4–6 Stunden je.

---

## 2. Voraussetzungen

| Voraussetzung | Status erwartet |
|---|---|
| Phase 3, 4, 5 DONE | ✓ Vorbedingung |
| `BrainStore` existiert + 3 V3-DBs in `%APPDATA%\PB_Studio\brain_v3\` | aus Phase 3 |
| `services/brain_v3/brain_v3_service.py` mit `BrainV3Service` aktiv | aus Phase 4 |
| FFmpeg + NVENC verfügbar | aus Phase-0-Spike + open-points-Spike (h264_nvenc bestätigt) |

---

## 3. Architektur

```text
services/brain_v3/storage/
├── backup.py                       ←── VACUUM INTO atomar, Retention
├── recovery.py                     ←── open_with_recovery + corrupt-handling

services/brain_v3/
├── nvenc_coexistence.py            ←── (optional) Pascal-Pre-Sets dokumentieren
└── onnx_export.py                  ←── (optional) CLAP+SigLIP nach ONNX

scripts/
├── spike_brain_v3_pacing_latency.py     ←── 100 Cuts mit/ohne Brain V3
├── spike_brain_v3_nvenc_corrected.py    ←── NVENC mit Pascal-Parametern
├── spike_brain_v3_recovery.py           ←── Korrupte DB simulieren

LICENSES.md                          ←── Workspace-Root, alle Komponenten
docs/USER/brain_v3_user_guide.md     ←── Was ist Cold-Start, Lern-Session etc.

services/brain_v3/brain_v3_service.py ←── +1 Methode: BrainV3Service.health()
                                          (in-process, keine REST-Schicht)
```

---

## 4. Datei-für-Datei-Spezifikation

### 4.1 `services/brain_v3/storage/backup.py`

```python
import sqlite3
from datetime import datetime
from pathlib import Path

class BrainV3Backup:
    """VACUUM INTO atomare Backups aller 3 Hirn-Store-DBs.

    SQLite-Doc bestätigt: VACUUM INTO ist online + transaktional.
    """
    def __init__(self, brain_dir: Path, backup_dir: Path,
                 retention_count: int = 4):
        self.brain_dir = brain_dir
        self.backup_dir = backup_dir
        self.retention_count = retention_count

    def create_backup(self) -> Path:
        """Erstellt atomares Backup aller weights.db + patterns.db +
        embedding_cache.db.

        Returns: Pfad zum erstellten Backup-Verzeichnis
                 (brain_v3_backup_<YYYYMMDD_HHMMSS>/)
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.backup_dir / f"brain_v3_backup_{ts}"
        target.mkdir(parents=True, exist_ok=True)
        for db_name in ("weights.db", "patterns.db", "embedding_cache.db"):
            src = self.brain_dir / db_name
            if not src.exists():
                continue
            dst = target / db_name
            conn = sqlite3.connect(str(src))
            try:
                conn.execute("VACUUM INTO ?", (str(dst),))
            finally:
                conn.close()
        self._enforce_retention()
        return target

    def _enforce_retention(self):
        """Behält nur die N neuesten Backups, löscht ältere."""
        ...

    def list_backups(self) -> list[Path]:
        """Liste aller Backups, sortiert neuestes zuerst."""
        ...
```

### 4.2 `services/brain_v3/storage/recovery.py`

```python
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class BrainV3Recovery:
    """Graceful Fallback bei korruptem Hirn-Store.

    Strategie:
    1. Versuche zu öffnen + integrity_check
    2. Bei Fehler: aus letztem Backup wiederherstellen
    3. Bei keinem Backup: löschen + frisch initialisieren (Cold-Start)
    """
    def __init__(self, brain_dir: Path, backup: BrainV3Backup): ...

    def open_with_recovery(self, db_name: str) -> sqlite3.Connection:
        """Öffnet eine V3-DB mit Recovery-Fallback."""
        db_path = self.brain_dir / db_name
        try:
            conn = sqlite3.connect(str(db_path))
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity == "ok":
                return conn
            conn.close()
            raise sqlite3.DatabaseError(f"integrity_check failed: {integrity}")
        except sqlite3.DatabaseError as e:
            logger.error("DB %s korrupt: %s — versuche Backup-Restore", db_name, e)
            if self._restore_latest_backup(db_name):
                return sqlite3.connect(str(db_path))
            logger.warning("Kein Backup verfügbar — frische DB anlegen")
            db_path.unlink(missing_ok=True)
            from services.brain_v3.storage.brain_store import BrainStore
            BrainStore()  # legt frische Tabellen via Migration an
            return sqlite3.connect(str(db_path))

    def _restore_latest_backup(self, db_name: str) -> bool: ...
```

### 4.3 `LICENSES.md` (Workspace-Root)

```markdown
# Lizenz-Übersicht — PB Studio + Brain V3

## ML-Modelle

| Komponente | HuggingFace-ID | Lizenz | Konsequenz |
|---|---|---|---|
| CLAP Audio-Modell | `laion/larger_clap_music` | Apache-2.0 | uneingeschränkt, KEINE Attribution-Pflicht |
| SigLIP-2 Vision (Brain V3) | `google/siglip2-base-patch16-384` | Apache-2.0 | uneingeschränkt |
| SigLIP-1 Vision (Bestand V1/V2) | `google/siglip-so400m-patch14-384` | Apache-2.0 | uneingeschränkt |

## Python-Dependencies (V3-relevant)

| Paket | Lizenz | Kommentar |
|---|---|---|
| torch / torchvision / torchaudio | BSD-3 / MIT | uneingeschränkt |
| transformers | Apache-2.0 | uneingeschränkt |
| accelerate | Apache-2.0 | uneingeschränkt |
| librosa | ISC | uneingeschränkt |
| scipy / numpy | BSD-3 | uneingeschränkt |
| sqlite-vec | Apache-2.0 / MIT | uneingeschränkt |
| sqlite3 | Public Domain | uneingeschränkt |
| opencv-python | Apache-2.0 | uneingeschränkt |
| Pillow | HPND | uneingeschränkt |
| pydantic | MIT | uneingeschränkt |
| PySide6 | LGPL-3 | dynamisch linken |

## Externe Tools

| Tool | Lizenz | Konsequenz |
|---|---|---|
| ffmpeg / ffprobe | LGPL/GPL | dynamisch linken (bestehender Stack) |
| UVR-MDX-NET-Inst_HQ_3.onnx | MIT | uneingeschränkt |
| NVIDIA Driver / CUDA Toolkit | proprietär | EULA |

**WICHTIG:** Frueherer Plan behauptete CLAP unter CC-BY-4.0 mit
Attribution-Pflicht. HF Hub Verify bestätigt **Apache-2.0** — Splash-Screen-
Attribution NICHT nötig. Diese LICENSES.md genügt für Compliance.
```

### 4.4 `scripts/spike_brain_v3_nvenc_corrected.py`

```python
"""Korrigierter NVENC-Test für Pascal (GTX 1060) mit kompatiblen Parametern.

Open-Points-Spike (2026-05-04) hatte `-preset p4 -rc vbr -b:v 5M` benutzt
und Invalid-Argument-Crash bekommen. Pascal NVENC unterstützt nicht alle
modernen Presets (p1-p7 sind Turing+).

Pascal-kompatible Parameter:
    -preset slow       (statt p4)
    -rc cbr            (statt vbr — vbr funktioniert auch, aber cbr ist sicher)
    -b:v 5M
    -profile:v high
    -level 4.1
"""
# Implementation analog scripts/spike_brain_v3_open_points.py:step_nvenc()
# aber mit korrekten Parametern.
```

### 4.5 `scripts/spike_brain_v3_pacing_latency.py`

```python
"""Misst Pacing-Run-Latenz mit/ohne Brain V3 für Plan-DoD <800 ms."""

# 1. Pacing-Run mit use_brain_v3=False, 100 Cuts, 5 Wiederholungen
# 2. Pacing-Run mit use_brain_v3=True, 100 Cuts, 5 Wiederholungen
# 3. Differenz = Brain-Overhead, sollte <800 ms median bei 100 Cuts
```

### 4.6 `scripts/spike_brain_v3_recovery.py`

```python
"""Recovery-Test für 3 Korruptionsszenarien.

1. weights.db löschen (file fehlt) → frischer Cold-Start
2. weights.db mit 0-Byte-Datei ersetzen → Backup-Restore
3. weights.db mit garbage-Bytes ersetzen → integrity_check fail → Backup
4. Kein Backup verfügbar → frische DB
5. App-Boot mit jedem Szenario darf nicht crashen
"""
```

### 4.7 `docs/USER/brain_v3_user_guide.md`

User-orientierte Doku:
- Was ist Cold-Start? (1.2 = TriggerSettings-Default, kein "schlecht")
- Wann lohnt eine Lern-Session? (nach 50+ Klicks Diversität)
- Was bedeuten die Confidence-Balken? (Farb-Skala)
- Was passiert bei Reset?
- Plan-Doc 02 #24-Hinweis: V1+V2 sind unabhängig vom V3-Reset

### 4.8 `services/brain_v3/onnx_export.py` (optional)

```python
"""ONNX-Export für CLAP + SigLIP-2 — Pascal-Optimierung.

LIMITS:
- Pascal hat keine Tensor Cores → kein FP16-Speedup
- Optimierungs-Headroom kleiner als auf Ampere/Ada
- Optional: TensorRT-Engine kompilieren wenn verfügbar

Vor Implementation: Eval-Spike laufen lassen um zu messen ob lohnt.
"""
```

### 4.9 `services/brain_v3/brain_v3_service.py` — `health()`-Methode (in-process)

```python
class BrainV3Service:
    # ... bestehende Methoden ...

    def health(self) -> BrainV3HealthResponse:
        """Diagnostik (in-process Aufruf, kein REST):
        - V3-DBs erreichbar?
        - Total-Klicks
        - Pfad-Konsistenz (V3 nicht in V1/V2-Subfolder)
        - Letzte Backup-Zeit
        - Disk-Space verbleibend
        """
```

Aufruf aus PySide6: `service.health()` direkt im Slot oder im
QThread-Worker — wie alle anderen `BrainV3Service`-Methoden.

---

## 5. SQL-Migrations

**Keine neuen.** Bestehende Schemas bleiben.

---

## 6. App-Eingriffspunkte

| Datei | Was | Risk |
|---|---|---|
| `LICENSES.md` (Workspace-Root) | NEU oder ergänzen | niedrig |
| `services/brain_v3/brain_v3_service.py` | +`health()`-Methode | niedrig (additiv) |
| App-Boot-Script (Pfad per Grep verifizieren) | optional: Backup-Trigger via QTimer / `threading.Timer` (in-process, **kein** FastAPI-Lifespan) | mittel |

**KEINE** Änderungen an V1/V2-Code.

---

## 7. Test-Spezifikation

### Backup-Tests `tests/test_services/test_brain_v3_backup.py`

- `test_backup_creates_atomic_copy_of_three_dbs` — alle 3 DBs in target
- `test_backup_handles_missing_db_gracefully` — wenn weights.db fehlt, skip
- `test_retention_keeps_only_n_newest`
- `test_list_backups_returns_sorted_newest_first`
- `test_vacuum_into_during_active_writes_is_consistent` (WAL-Concurrency)

### Recovery-Tests `tests/test_services/test_brain_v3_recovery.py`

- `test_open_with_recovery_intact_db` — happy path
- `test_recovery_from_zero_byte_corrupt_db` — Backup-Restore
- `test_recovery_no_backup_creates_fresh_db` — Cold-Start
- `test_recovery_garbage_bytes_triggers_integrity_check_fail`
- `test_app_boot_survives_corrupt_brain_v3_db` (Integration)

### NVENC-Test `tests/test_services/test_brain_v3_nvenc.py`

- `test_pascal_preset_slow_works` — h264_nvenc -preset slow läuft durch
- `test_nvenc_with_clap_inference_does_not_oom` — gleichzeitig

### Performance-Spike (skript-basiert)

- `spike_brain_v3_pacing_latency.py` — DoD <800 ms verifiziert

### Manuelle Recovery-Tests (siehe Sektion 4.6 spike_brain_v3_recovery.py)

```text
☐ Hirn-Store löschen (rm weights.db) → App starten → Cold-Start aktiv
☐ weights.db mit 0-Byte-Datei ersetzen → App starten → Backup-Restore
☐ Kein Backup vorhanden → App starten → frische DB, Cold-Start
☐ Pacing-Latenz mit Brain V3 <800 ms bei 100 Cuts (gemessen mit Spike)
☐ Wöchentliches Backup läuft (Background-Task verifiziert via /brain_v3/health)
```

---

## 8. Definition of Done

```text
☐ BrainV3Backup erstellt + 5 Tests grün
☐ BrainV3Recovery erstellt + 5 Tests grün
☐ Recovery-Spike-Skript läuft alle 4 Szenarien grün
☐ NVENC-Korrektur-Skript läuft erfolgreich (h264_nvenc -preset slow)
☐ NVENC + Brain-Inferenz parallel: kein OOM (verifiziert)
☐ Pacing-Latenz <800 ms median bei 100 Cuts (Spike-Output)
☐ LICENSES.md vollständig + im Workspace-Root
☐ docs/USER/brain_v3_user_guide.md geschrieben
☐ BrainV3Service.health() liefert validen Status (in-process Aufruf)
☐ ONNX-Export-Eval optional: Latenz-Vergleich CLAP/SigLIP nativ vs ONNX
☐ Alle V3-Tests (Phase 1-6) zusammen grün (~120+ Tests)
☐ Synthesis-Doc Phase 6
```

---

## 9. Risiken + Mitigationen

| Risiko | Mitigation |
|---|---|
| VACUUM INTO bricht ab bei aktiven Writes | WAL-Mode + transaktional, SQLite-Doc bestätigt Sicherheit |
| Backup-Verzeichnis volläuft Disk | retention_count konfigurierbar, default 4 |
| Recovery aus 0-Byte-Backup → frischer Cold-Start statt Restore | integrity_check vor Use, nur valide Backups nutzen |
| NVENC-Pascal-Preset ändert sich in zukünftigen FFmpeg-Versions | Test-Skript mit aktueller Version prüfen, vor Deploy |
| ONNX-Export für CLAP/SigLIP scheitert (Vision-Tower-only ist tricky) | optional, vor Implementation Eval-Spike. Wenn zu komplex: skip. |
| Pacing-Latenz >800 ms wegen 102 SELECTs pro Cut (R18) | WeightStore-Connection cachen, ggf. Read-only-Memory-Cache der Top-Buckets |

---

## 10. Verifikations-Strategie

- **Unit-Tests:** ~10 in test_brain_v3_backup + test_brain_v3_recovery + test_brain_v3_nvenc
- **Spike-Skripte:** 3 (pacing_latency, nvenc_corrected, recovery)
- **Manuelle Tests:** 5 Recovery-Szenarien (siehe Sektion 7)
- **Final-Check:** `run_pytest_brain_v3.bat` muss alle ~120+ Tests grün haben
  (Phase 1-6 zusammen)
- **Performance-Verify:** `outputs/spike_brain_v3_pacing_latency/<ts>/report.md`
  muss <800 ms median ausweisen

---

## 11. Reihenfolge der Implementation

```text
1. backup.py + 5 Tests (1.5 h)
2. recovery.py + 5 Tests + Recovery-Spike-Skript (2 h)
3. NVENC-Korrektur-Skript + 2 Tests (1 h)
4. spike_brain_v3_pacing_latency.py + Lauf (1 h)
5. /brain_v3/health Endpoint + Test (30 Min)
6. LICENSES.md (45 Min)
7. docs/USER/brain_v3_user_guide.md (1 h)
8. ONNX-Eval optional (3-5 h, kann skipped werden)
9. Background-Backup-Task in App-Boot (1 h)
10. Final-Run aller V3-Tests + Synthesis-Doc

Total: ~10-12 Stunden + optional ONNX (3-5 h).
```

---

## Hinweis für Claude Code

- **NVENC-Test:** vor Implementation in einem isolierten cmd manuell testen
  welche Pascal-Parameter funktionieren. FFmpeg-Versionen variieren in
  Preset-Support.
- **Backup-Verzeichnis:** Default `%APPDATA%\PB_Studio\brain_v3\backups\`,
  konfigurierbar via Config-Datei.
- **Background-Task für Backup:** schedule via Windows Task Scheduler
  (per `schtasks` CLI) ODER in-process via `QTimer` im PySide6-Boot
  bzw. `threading.Timer` — **kein** FastAPI-Lifespan (User-Direktive
  2026-05-05 F1: keine REST-Schicht).
- **ONNX-Export ist optional** — vor Implementation Cost/Benefit prüfen.
  Pascal hat kein Tensor-Core-FP16-Speedup, daher Headroom klein.

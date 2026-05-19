# 03 — Quality-Profiles Video (Spec)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 1 Foundation
> Status: spec · 2026-05-19

## Ziel

Drei vordefinierte Profile fuer Video-Analyse — User waehlt im Settings-Dialog, App kann pro Job ueberschreiben. **Default = Maximum Quality** (Hartregel User-Anweisung 2026-05-19).

## Profile-Definition

Jedes Profil ist ein Dataclass-Bundle pro Pipeline-Stage. Konstanten in `services/video_pipeline/profiles.py`.

### Maximum Quality (Default)

| Stage | Parameter | Wert |
|---|---|---|
| Scene-Detect | `ContentDetector(threshold=...)` | `threshold=27.0` (sensitiv) |
| Scene-Detect | `min_scene_len_s` | `1.0` |
| Keyframe-Selector | `mode` | `anchors_3` (Anfang/Mitte/Ende pro Szene) |
| Keyframe-Selector | `+ uniform_every_s` | `2.0` (Coverage-Anker) |
| Keyframe-Encode | `JPEG quality` | `95` |
| SigLIP-Embed | `model_id` | `google/siglip-so400m-patch14-384` |
| SigLIP-Embed | `image_size` | `384` (native) |
| SigLIP-Embed | `batch_size` | `8` |
| SigLIP-Embed | `dtype` | `float16` (auf disk) |
| RAFT-Motion | `model` | `raft_large` |
| RAFT-Motion | `resolution_scale` | `1.0` (Original) |
| RAFT-Motion | `iter_count` | `12` |
| VLM-Caption | `frequenz` | `pro Scene-Keyframe` |
| VLM-Caption | `modell` | aus Plan-B Auto-Selector (Default `minicpm-v:8b-q4`) |
| Proxy-Gen | `codec` | `h264_nvenc` |
| Proxy-Gen | `bitrate` | `6M` |
| Proxy-Gen | `max_width` | `1280` |
| Cross-Modal | `model` | aus Plan-B `reasoning_heavy` |

### Balanced

| Stage | Parameter | Wert |
|---|---|---|
| Scene-Detect | `threshold` | `30.0` |
| Scene-Detect | `min_scene_len_s` | `1.5` |
| Keyframe-Selector | `mode` | `mid` (1 Frame pro Szene) |
| Keyframe-Selector | `+ uniform_every_s` | `4.0` |
| Keyframe-Encode | `JPEG quality` | `90` |
| SigLIP-Embed | `model_id` | `google/siglip-so400m-patch14-384` |
| SigLIP-Embed | `image_size` | `384` |
| SigLIP-Embed | `batch_size` | `16` |
| RAFT-Motion | `model` | `raft_small` |
| RAFT-Motion | `resolution_scale` | `0.5` |
| RAFT-Motion | `iter_count` | `8` |
| VLM-Caption | `frequenz` | `jede 2. Szene` |
| VLM-Caption | `modell` | `moondream:1.8b` (kleiner) |
| Proxy-Gen | `bitrate` | `3M` |
| Proxy-Gen | `max_width` | `960` |
| Cross-Modal | `model` | `reasoner` (statt heavy) |

### Fast Preview

| Stage | Parameter | Wert |
|---|---|---|
| Scene-Detect | `threshold` | `35.0` |
| Scene-Detect | `min_scene_len_s` | `2.0` |
| Keyframe-Selector | `mode` | `mid` |
| Keyframe-Selector | `+ uniform_every_s` | `8.0` (sparse) |
| Keyframe-Encode | `JPEG quality` | `80` |
| SigLIP-Embed | `model_id` | `google/siglip2-base-patch16-384` (kleiner, 768-dim) |
| SigLIP-Embed | `image_size` | `384` |
| SigLIP-Embed | `batch_size` | `16` |
| RAFT-Motion | `model` | `raft_small` |
| RAFT-Motion | `resolution_scale` | `0.25` (480p) |
| RAFT-Motion | `iter_count` | `4` |
| VLM-Caption | `frequenz` | `jede 4. Szene` |
| VLM-Caption | `modell` | `moondream:1.8b` |
| Proxy-Gen | `bitrate` | `1M` |
| Proxy-Gen | `max_width` | `720` |
| Cross-Modal | heuristisch | kein LLM-Call |

## VRAM-Budget pro Profile (Schaetzung, Verifizierung Pflicht Tier-2)

| Profile | SigLIP-VRAM | RAFT-VRAM | VLM-VRAM | Gesamt-Peak (sequentiell) |
|---|---|---|---|---|
| Maximum | ~1.5 GB | ~1.5 GB | bis 5.5 GB | ~5.5 GB (VLM dominiert) |
| Balanced | ~1.5 GB | ~0.5 GB | ~2 GB | ~2 GB |
| Fast | ~0.5 GB | ~0.3 GB | ~2 GB | ~2 GB |

GTX 1060 6 GB Budget: alle Profile passen sequentiell. Parallel mit Audio-V2/Brain V3 verboten (siehe `18_GPU_LOCK_AWARENESS.md`).

## Laufzeit-Schaetzung (Verifizierung Pflicht — heutige Schaetzung)

| Profile | 1 min Video | 1 h Video | 4 h Video |
|---|---|---|---|
| Maximum | ~3 min | ~3 h | ~12 h |
| Balanced | ~1 min | ~1 h | ~4 h |
| Fast | ~20 s | ~20 min | ~80 min |

Realistische Messung wird in Tier-2 Phase 11 (Smoke-Test) hinterlegt.

## Profile-Wahl

### Global-Setting

`settings.json`:
```json
"video_pipeline": {
  "default_quality_profile": "maximum",
  "balanced_threshold_minutes": null,   // nicht autom. wechseln
  "fast_for_long_files_threshold_minutes": null
}
```

Default: `maximum`. Kein automatischer Profile-Wechsel.

### Per-Job-Override

```python
pipeline.run(
    track_id=42,
    source_path=...,
    quality_profile="balanced",   # ueberschreibt Default
)
```

### Per-Stage-Override (Advanced)

```python
pipeline.run(
    quality_profile="maximum",
    stage_overrides={
        "raft_motion": "balanced",     # einzelne Stage langsamer machen
    },
)
```

## DB-Erweiterung (kommt **nicht** in Phase 01)

Future Plan C `analysis_jobs.quality_profile` (siehe Plan C `01_DB_PROVENANCE_TABLES.md`). Solange Plan C nicht implementiert: kein DB-Spalte fuer Profile pro Job.

Hier Phase 03: nur Code-Konstanten, kein DB-Touch.

## Dataclass-Spec (Tier-2-Implementation)

```python
# services/video_pipeline/profiles.py — Phase-3-Stub, ausimplementiert in Tier 2
@dataclass(frozen=True)
class SceneDetectParams:
    threshold: float = 27.0
    min_scene_len_s: float = 1.0

@dataclass(frozen=True)
class KeyframeParams:
    mode: str = "anchors_3"
    uniform_every_s: float = 2.0
    jpeg_quality: int = 95

# ... pro Stage ein Dataclass

@dataclass(frozen=True)
class QualityProfile:
    name: str
    scene_detect: SceneDetectParams
    keyframe: KeyframeParams
    siglip: SigLipParams
    raft: RaftParams
    vlm: VlmParams
    proxy: ProxyParams
    cross_modal: CrossModalParams

MAXIMUM = QualityProfile(name="maximum", ...)
BALANCED = QualityProfile(name="balanced", ...)
FAST = QualityProfile(name="fast", ...)

PROFILES = {"maximum": MAXIMUM, "balanced": BALANCED, "fast": FAST}
```

## Verifikation (Phase-3-Acceptance)

- [x] Profil-Tabelle pro Stage konkretisiert
- [x] VRAM + Laufzeit-Schaetzung dokumentiert (Verifizierung Pflicht Tier 2)
- [x] Default = `maximum` (User-Hartregel)
- [x] Per-Job + Per-Stage-Override-Pattern beschrieben
- [ ] Dataclass-Implementation in Tier-2 Phase 10+ (kein Code in Phase 03)

## Offene Klaerungs-Punkte

- [ ] `siglip2-base` (768-dim) vs `siglip-so400m` (1152-dim) — Mix in Fast vs Max ist problematisch fuer Aehnlichkeitssuche. Soll Fast einen separaten Embedding-Slot bekommen oder Mix akzeptieren?
- [ ] VLM-Modell-Wahl per Profile bindet Plan B vs Auto-Selector — pruefen ob hard-pin gewuenscht
- [ ] Bei Profile-Wechsel auf bereits analysierter Datei: nur fehlende Stages mit neuem Profil ODER alles neu?

## Naechster Schritt

Phase 03 done. Phase 03 ist reine Doku — kein Code-Touch, kein RED-Test noetig.

Naechste Phase: **Tier 2 Phase 10** (Video-Decoder-Primitive) — erstes echtes Building-Block-Modul.

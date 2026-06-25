# 13 — Scene-Detect-Primitive (PySceneDetect-Wrapper)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Cuts/Scenes erkennen.

## Scope

```python
def detect_scenes(path: Path, *, threshold: float = 27.0) -> list[Scene]:
    """
    Returns list of Scene(start_s, end_s, duration_s).
    PySceneDetect ContentDetector mit threshold (Quality-Profile-abhaengig).
    Wahlweise auf Proxy fuer Speed (Cuts aendern sich nicht durch Aufloesung).
    """
```

- Lange Videos: Stream-Mode, kein Full-Load.
- Coverage-Garantie: jede Sekunde liegt in einer Szene.

## Verifikation

- Solo_Natur-Clips bekannte Cut-Anzahl
- Lange Test-Datei → kein Stream-OOM
- `pytest tests/test_services/test_scene_detect.py -v` gruen

"""services/enrichment/visual_metrics.py
==========================================

Bildmetriken pro Szene aus den BEREITS vorhandenen Keyframe-JPEGs.

Hintergrund
-----------
Die Clip-Auswahl (``services/brain/bridge_dimensions.py``) bewertet u.a.
``brightness_match_weight`` und ``color_temp_match_weight`` ueber
``ClipCandidate.brightness`` / ``.saturation`` / ``.color_temp``. Fuer diese
drei Felder gab es bis dato KEINE Datenquelle. Ohne reale Messwerte blieben
beide Achsen fuer alle Kandidaten identisch und damit wirkungslos.

WICHTIG — Abgrenzung: ``timeline_entries.brightness`` ist ein
Farbkorrektur-REGLER (User-Eingabe), KEIN Messwert. Er wird hier weder
gelesen noch geschrieben.

Datenquelle
-----------
``services/video_analysis_service.extract_keyframes`` schreibt pro Szene ein
JPEG nach ``<APP_ROOT>/storage/keyframes/<proxy_stem>_scene%04d.jpg``
(1 Frame aus der Szenen-Mitte, skaliert auf 384x384 mit
``force_original_aspect_ratio=decrease`` + ``pad``).

Letterbox-Warnung
-----------------
Durch das ``pad``-Filter sind 16:9-Frames in einem 384x384-Quadrat
zentriert — real gemessen tragen nur ~222 von 384 Zeilen Bildinhalt, der Rest
ist schwarz. Ohne Crop waere die gemessene Helligkeit systematisch um ~42 %
zu niedrig und die Saettigung verwaessert. ``_crop_letterbox`` entfernt die
schwarzen Raender deshalb vor jeder Messung.

Metriken (alle CPU, kein GPU — Hartregel GTX-1060-only bleibt unberuehrt)
------------------------------------------------------------------------
brightness : 0..1   mittlere Rec.709-Luma
saturation : 0..1   mittlere HSV-Saettigung ``(max-min)/max``
color_temp : -1..+1 ``(R-B)/(R+B)``, positiv = warm, negativ = kalt
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Versions-Tag, das mit den Werten persistiert wird. Bei Aenderung der
# Berechnung hochzaehlen, damit Alt-Werte erkennbar bleiben.
VISUAL_METRICS_VERSION: str = "vm1"

# Analyse-Aufloesung: Keyframes sind 384x384; auf 192 herunterrechnen ist
# fuer Mittelwerte mehr als ausreichend und halbiert die Rechenzeit.
_ANALYSIS_MAX_SIDE: int = 192

# Luma-Schwelle, ab der eine Zeile/Spalte als "hat Bildinhalt" gilt.
# JPEG-Artefakte an der Padding-Kante liegen deutlich darunter.
_LETTERBOX_LUMA_THRESHOLD: float = 0.02

_EPS: float = 1e-6


@dataclass(frozen=True)
class VisualMetrics:
    """Aggregierte Bildmetriken einer Szene."""

    brightness: float  # 0..1
    saturation: float  # 0..1
    color_temp: float  # -1..+1  (warm positiv)
    frame_count: int  # wie viele Keyframes real eingeflossen sind
    version: str = VISUAL_METRICS_VERSION

    def as_row(self) -> dict[str, float | int | str]:
        """Dict fuer den DB-Insert (Spaltennamen von struct_clip_tags)."""
        return {
            "avg_brightness": self.brightness,
            "avg_saturation": self.saturation,
            "color_temp": self.color_temp,
            "visual_frame_count": self.frame_count,
            "visual_metrics_version": self.version,
        }


# ---------------------------------------------------------------------------
# Bildverarbeitung
# ---------------------------------------------------------------------------
def _luma(arr: np.ndarray) -> np.ndarray:
    """Rec.709-Luma aus einem float-RGB-Array (H, W, 3) in 0..1."""
    return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]


def _crop_letterbox(arr: np.ndarray) -> np.ndarray:
    """Entfernt schwarze Pad-Raender (oben/unten bzw. links/rechts).

    Gibt das Original zurueck, wenn nichts (oder alles) als Rand erkannt wird
    — ein komplett schwarzer Frame soll als schwarz gemessen werden, nicht
    auf 0x0 zusammenfallen.
    """
    lum = _luma(arr)
    row_has = lum.max(axis=1) > _LETTERBOX_LUMA_THRESHOLD
    col_has = lum.max(axis=0) > _LETTERBOX_LUMA_THRESHOLD
    if not row_has.any() or not col_has.any():
        return arr
    r0, r1 = int(np.argmax(row_has)), int(len(row_has) - np.argmax(row_has[::-1]))
    c0, c1 = int(np.argmax(col_has)), int(len(col_has) - np.argmax(col_has[::-1]))
    cropped = arr[r0:r1, c0:c1, :]
    if cropped.size == 0:
        return arr
    return cropped


def compute_image_metrics(image_path: str | Path) -> VisualMetrics:
    """Metriken eines einzelnen Keyframe-Bildes.

    Raises
    ------
    FileNotFoundError
        Wenn die Datei nicht existiert.
    OSError / ValueError
        Wenn PIL das Bild nicht dekodieren kann.
    """
    from PIL import Image  # lazy: haelt Import-Kosten aus dem Worker-Start

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    with Image.open(path) as im:
        im = im.convert("RGB")
        if max(im.size) > _ANALYSIS_MAX_SIDE:
            im.thumbnail((_ANALYSIS_MAX_SIDE, _ANALYSIS_MAX_SIDE))
        arr = np.asarray(im, dtype=np.float32) / 255.0

    arr = _crop_letterbox(arr)

    brightness = float(np.clip(_luma(arr).mean(), 0.0, 1.0))

    ch_max = arr.max(axis=2)
    ch_min = arr.min(axis=2)
    sat_px = np.where(ch_max > _EPS, (ch_max - ch_min) / np.maximum(ch_max, _EPS), 0.0)
    saturation = float(np.clip(sat_px.mean(), 0.0, 1.0))

    r = arr[..., 0]
    b = arr[..., 2]
    temp_px = (r - b) / np.maximum(r + b, _EPS)
    color_temp = float(np.clip(temp_px.mean(), -1.0, 1.0))

    return VisualMetrics(
        brightness=brightness,
        saturation=saturation,
        color_temp=color_temp,
        frame_count=1,
    )


def compute_scene_metrics(image_paths: Sequence[str | Path]) -> VisualMetrics | None:
    """Mittelt die Metriken ueber alle lesbaren Keyframes einer Szene.

    Returns ``None``, wenn KEIN einziges Bild gelesen werden konnte — bewusst
    kein stiller 0.5-Default, damit "nicht gemessen" von "gemessen = 0.5"
    unterscheidbar bleibt.
    """
    per_frame: list[VisualMetrics] = []
    for p in image_paths:
        try:
            per_frame.append(compute_image_metrics(p))
        except (FileNotFoundError, OSError, ValueError) as exc:
            logger.debug("visual_metrics: Keyframe unlesbar (%s): %s", p, exc)
    if not per_frame:
        return None
    n = len(per_frame)
    return VisualMetrics(
        brightness=float(sum(m.brightness for m in per_frame) / n),
        saturation=float(sum(m.saturation for m in per_frame) / n),
        color_temp=float(sum(m.color_temp for m in per_frame) / n),
        frame_count=n,
    )


# ---------------------------------------------------------------------------
# Keyframe-Aufloesung
# ---------------------------------------------------------------------------
def _stem_candidates(video_path: str | None, proxy_path: str | None) -> list[str]:
    """Moegliche Datei-Stems, unter denen Keyframes abgelegt wurden.

    ``extract_keyframes`` benutzt ``Path(video_path).stem`` des Videos, das
    die Pipeline analysiert hat — real ist das der PROXY (``*_edit_proxy``
    bzw. ``*_proxy``). Alt-Projekte ohne ``proxy_path`` deckt der aus
    ``scripts/diag/fixplan_reanalyze_motion_captions.py`` bekannte
    ``<original_stem>_proxy`` / ``<original_stem>_edit_proxy`` ab.
    """
    stems: list[str] = []
    if proxy_path:
        stems.append(Path(proxy_path).stem)
    if video_path:
        base = Path(video_path).stem
        stems += [f"{base}_edit_proxy", f"{base}_proxy", base]
    # Reihenfolge erhalten, Duplikate raus
    seen: set[str] = set()
    out: list[str] = []
    for s in stems:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def resolve_scene_keyframes(
    *,
    keyframe_dir: str | Path,
    scene_index: int,
    stored_paths: Iterable[str] | None = None,
    video_path: str | None = None,
    proxy_path: str | None = None,
) -> list[Path]:
    """Findet die Keyframe-Dateien einer Szene.

    Prioritaet:
      1. ``scenes.keyframe_paths`` (JSON-Liste), sofern gesetzt UND existent.
      2. Ableitung ``<stem>_scene%04d.jpg`` im Keyframe-Verzeichnis, ueber die
         Stem-Kandidaten aus :func:`_stem_candidates`.

    Gibt eine (moeglicherweise leere) Liste existierender Pfade zurueck.
    """
    found: list[Path] = []
    if stored_paths:
        for raw in stored_paths:
            if not raw:
                continue
            p = Path(raw)
            if not p.is_absolute():
                p = Path(keyframe_dir).parent.parent / raw
            if p.exists():
                found.append(p)
    if found:
        return found

    kf_dir = Path(keyframe_dir)
    if not kf_dir.is_dir():
        return []
    for stem in _stem_candidates(video_path, proxy_path):
        cand = kf_dir / f"{stem}_scene{scene_index:04d}.jpg"
        if cand.exists():
            return [cand]
    return []

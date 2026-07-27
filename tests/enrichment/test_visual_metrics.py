"""tests/enrichment/test_visual_metrics.py

Beweispflicht: die Werte muessen ueber Clips VARIIEREN, nicht nur gesetzt
sein. Ein reiner Existenztest haette den urspruenglichen Bug (konstante
0.5 / 0.5 / 0.0 fuer alle Kandidaten) nicht gefangen.

Run:
    python -m pytest tests/enrichment/test_visual_metrics.py -p no:randomly -q
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from services.enrichment.visual_metrics import (
    VISUAL_METRICS_VERSION,
    VisualMetrics,
    compute_image_metrics,
    compute_scene_metrics,
    resolve_scene_keyframes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write(path, rgb, size=(64, 48), letterbox_rows: int = 0):
    """Schreibt ein JPEG in Volltonfarbe, optional mit schwarzen Balken."""
    w, h = size
    arr = np.zeros((h + 2 * letterbox_rows, w, 3), dtype=np.uint8)
    arr[letterbox_rows : letterbox_rows + h, :, :] = np.array(rgb, dtype=np.uint8)
    Image.fromarray(arr).save(path, quality=95)
    return path


# ---------------------------------------------------------------------------
# Einzelbild-Metriken
# ---------------------------------------------------------------------------
def test_brightness_orders_dark_mid_bright(tmp_path):
    dark = compute_image_metrics(_write(tmp_path / "d.jpg", (20, 20, 20)))
    mid = compute_image_metrics(_write(tmp_path / "m.jpg", (128, 128, 128)))
    bright = compute_image_metrics(_write(tmp_path / "b.jpg", (240, 240, 240)))

    assert dark.brightness < mid.brightness < bright.brightness
    assert 0.0 <= dark.brightness <= 1.0
    assert 0.0 <= bright.brightness <= 1.0
    # Varianz explizit: nicht nur "gesetzt", sondern spannend weit auseinander
    vals = [dark.brightness, mid.brightness, bright.brightness]
    assert max(vals) - min(vals) > 0.5
    assert len({round(v, 4) for v in vals}) == 3


def test_saturation_grey_vs_colour(tmp_path):
    grey = compute_image_metrics(_write(tmp_path / "g.jpg", (128, 128, 128)))
    vivid = compute_image_metrics(_write(tmp_path / "v.jpg", (255, 0, 0)))

    assert grey.saturation < 0.1
    assert vivid.saturation > 0.9
    assert vivid.saturation - grey.saturation > 0.8


def test_color_temp_warm_positive_cold_negative_neutral_zero(tmp_path):
    warm = compute_image_metrics(_write(tmp_path / "w.jpg", (220, 140, 40)))
    cold = compute_image_metrics(_write(tmp_path / "c.jpg", (40, 140, 220)))
    neutral = compute_image_metrics(_write(tmp_path / "n.jpg", (128, 128, 128)))

    assert warm.color_temp > 0.2
    assert cold.color_temp < -0.2
    assert abs(neutral.color_temp) < 0.05
    assert -1.0 <= cold.color_temp <= 1.0 and -1.0 <= warm.color_temp <= 1.0


def test_letterbox_padding_is_cropped_before_measuring(tmp_path):
    """Ohne Crop wuerde das ffmpeg-``pad``-Filter die Helligkeit verfaelschen.

    Real gemessen an den Projekt-Keyframes: nur ~222 von 384 Zeilen tragen
    Bildinhalt (384x384 mit force_original_aspect_ratio=decrease + pad).
    """
    plain = compute_image_metrics(_write(tmp_path / "p.jpg", (200, 200, 200)))
    boxed = compute_image_metrics(
        _write(tmp_path / "lb.jpg", (200, 200, 200), letterbox_rows=40)
    )
    # Der schwarze Rand macht ~62 % der Flaeche aus; ohne Crop laege boxed
    # bei ~0.3 statt ~0.78.
    assert boxed.brightness == pytest.approx(plain.brightness, abs=0.05)


def test_all_black_frame_is_measured_as_black_not_crashed(tmp_path):
    black = compute_image_metrics(_write(tmp_path / "k.jpg", (0, 0, 0)))
    assert black.brightness < 0.05


# ---------------------------------------------------------------------------
# Szenen-Aggregation
# ---------------------------------------------------------------------------
def test_scene_metrics_averages_and_counts_frames(tmp_path):
    a = _write(tmp_path / "a.jpg", (0, 0, 0))
    b = _write(tmp_path / "b.jpg", (255, 255, 255))
    vm = compute_scene_metrics([a, b])
    assert isinstance(vm, VisualMetrics)
    assert vm.frame_count == 2
    assert 0.3 < vm.brightness < 0.7
    assert vm.version == VISUAL_METRICS_VERSION


def test_scene_metrics_returns_none_when_nothing_readable(tmp_path):
    """Kein stiller 0.5-Default — ``None`` heisst ehrlich 'nicht gemessen'."""
    assert compute_scene_metrics([tmp_path / "does_not_exist.jpg"]) is None
    assert compute_scene_metrics([]) is None


def test_scene_metrics_skips_unreadable_but_uses_the_rest(tmp_path):
    good = _write(tmp_path / "good.jpg", (200, 100, 50))
    vm = compute_scene_metrics([tmp_path / "missing.jpg", good])
    assert vm is not None and vm.frame_count == 1


def test_metrics_vary_across_a_simulated_clip_library(tmp_path):
    """Kernbeweis: ueber mehrere 'Clips' entstehen distinkte Werte."""
    palette = [
        (10, 10, 30),
        (200, 60, 20),
        (30, 90, 210),
        (240, 235, 220),
        (90, 160, 70),
        (150, 20, 160),
    ]
    metrics = [
        compute_image_metrics(_write(tmp_path / f"c{i}.jpg", rgb))
        for i, rgb in enumerate(palette)
    ]
    brights = [m.brightness for m in metrics]
    sats = [m.saturation for m in metrics]
    temps = [m.color_temp for m in metrics]

    for label, vals in (("brightness", brights), ("saturation", sats), ("color_temp", temps)):
        assert max(vals) - min(vals) > 0.0, f"{label} ist konstant"
        assert len({round(v, 4) for v in vals}) == len(palette), (
            f"{label} hat nur {len({round(v, 4) for v in vals})} distinkte Werte"
        )
    assert max(brights) - min(brights) > 0.5
    assert max(temps) - min(temps) > 0.5


# ---------------------------------------------------------------------------
# Keyframe-Aufloesung
# ---------------------------------------------------------------------------
def test_resolve_prefers_stored_paths(tmp_path):
    kf_dir = tmp_path / "storage" / "keyframes"
    kf_dir.mkdir(parents=True)
    stored = _write(tmp_path / "stored.jpg", (1, 2, 3))
    found = resolve_scene_keyframes(
        keyframe_dir=kf_dir, scene_index=0, stored_paths=[str(stored)]
    )
    assert found == [stored]


def test_resolve_derives_from_proxy_stem(tmp_path):
    """Muster aus ``extract_keyframes``: ``<proxy_stem>_scene%04d.jpg``."""
    kf_dir = tmp_path / "storage" / "keyframes"
    kf_dir.mkdir(parents=True)
    target = _write(kf_dir / "movie_edit_proxy_scene0003.jpg", (5, 5, 5))
    found = resolve_scene_keyframes(
        keyframe_dir=kf_dir,
        scene_index=3,
        stored_paths=None,
        video_path=r"C:\videos\movie.mp4",
        proxy_path=r"C:\proj\storage\proxies\movie_edit_proxy.mp4",
    )
    assert found == [target]


def test_resolve_falls_back_to_original_stem_pattern(tmp_path):
    """Alt-Projekte ohne ``proxy_path`` (Muster aus dem Diag-Skript)."""
    kf_dir = tmp_path / "storage" / "keyframes"
    kf_dir.mkdir(parents=True)
    target = _write(kf_dir / "movie_proxy_scene0000.jpg", (5, 5, 5))
    found = resolve_scene_keyframes(
        keyframe_dir=kf_dir,
        scene_index=0,
        stored_paths=None,
        video_path=r"C:\videos\movie.mp4",
        proxy_path=None,
    )
    assert found == [target]


def test_resolve_returns_empty_when_nothing_found(tmp_path):
    kf_dir = tmp_path / "storage" / "keyframes"
    kf_dir.mkdir(parents=True)
    assert (
        resolve_scene_keyframes(
            keyframe_dir=kf_dir, scene_index=7, video_path="x.mp4"
        )
        == []
    )

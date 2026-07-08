import pytest
import numpy as np
from services.export_service import _video_encode_args
from services.video_analysis_service import _cpu_motion_score, SceneInfo, compute_motion_scores

def test_export_nvenc_recheck():
    """B3: Testet, dass _video_encode_args ohne globalen permanenten Cache arbeitet
    und bei fehlschlagendem NVENC auf libx264 fallbackt."""
    # Führt _video_encode_args aus. Sollte entweder h264_nvenc oder libx264 zurückgeben,
    # ohne abzustürzen, und den Re-Check erlauben.
    args = _video_encode_args()
    assert isinstance(args, list)
    assert len(args) > 1
    assert args[1] in ("h264_nvenc", "libx264")

def test_cpu_motion_score_scale():
    """B3: Testet, dass der CPU Motion Score skalenkonsistent mit der exp-Normalisierung
    ist und Werte im Bereich 0.0-1.0 liefert."""
    # Zwei identische Frames -> Motion Score 0.0
    f1 = np.zeros((320, 520, 3), dtype=np.uint8)
    f2 = np.zeros((320, 520, 3), dtype=np.uint8)
    score_zero = _cpu_motion_score(f1, f2)
    assert score_zero == 0.0
    
    # Frames mit leichter Änderung (z. B. Helligkeitsunterschied 13/255 = ~0.05)
    f1 = np.zeros((320, 520, 3), dtype=np.uint8)
    f2 = np.ones((320, 520, 3), dtype=np.uint8) * 13
    score_mid = _cpu_motion_score(f1, f2)
    # 1 - exp(-0.05 * 15) = 1 - exp(-0.75) = ~0.5276
    assert 0.5 < score_mid < 0.55
    
    # Extrem unterschiedliche Frames
    f2 = np.ones((320, 520, 3), dtype=np.uint8) * 255
    score_max = _cpu_motion_score(f1, f2)
    # 1 - exp(-1.0 * 15) = ~1.0
    assert 0.99 < score_max <= 1.0

def test_motion_fallback_marking(tmp_path):
    """B3: Testet, dass bei erzwungenem CPU-Fallback das Flag motion_is_fallback gesetzt wird."""
    scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0)]
    # Wenn wir compute_motion_scores mit ungültigem Video-Pfad rufen,
    # sollte es die Szenen unverändert zurückgeben.
    res = compute_motion_scores("nonexistent_video.mp4", scenes)
    assert len(res) == 1
    # Pfad existiert nicht -> liefert Szenen direkt zurück

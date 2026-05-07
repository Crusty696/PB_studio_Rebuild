from __future__ import annotations

from pathlib import Path


def test_licenses_covers_phase6_required_components():
    path = Path("LICENSES.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8").lower()

    required_components = [
        "laion/larger_clap_music",
        "google/siglip2-base-patch16-384",
        "google/siglip-so400m-patch14-384",
        "demucs",
        "beat_this",
        "sqlite-vec",
        "sqlite3",
        "librosa",
        "transformers",
        "accelerate",
        "torch",
        "torchvision",
        "torchaudio",
        "scipy",
        "numpy",
        "opencv-python",
        "pillow",
        "pydantic",
        "pyside6",
        "ffmpeg",
        "ffprobe",
        "uvr-mdx-net-inst_hq_3.onnx",
        "nvidia driver",
        "cuda toolkit",
    ]

    missing = [needle for needle in required_components if needle not in text]
    assert missing == []


def test_licenses_documents_clap_without_cc_by_requirement():
    text = Path("LICENSES.md").read_text(encoding="utf-8").lower()

    assert "clap" in text
    assert "apache-2.0" in text
    assert "cc-by-4.0" in text
    assert "widerlegt" in text or "nicht" in text

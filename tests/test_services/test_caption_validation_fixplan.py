"""Fixplan 2026-07-07 Schritt 2: Vision-Caption-Validierung.

Die Junk-Beispiele stammen 1:1 aus der realen Projekt-DB
outputs/final-check/pb_studio.db (scenes.ai_caption, Stand 2026-07-07).
"""
from services.video_analysis_service import (
    _caption_text_is_plausible,
    _validate_caption_dict,
)


REAL_JUNK_DICTS = [
    # Metadaten-Echo ohne description
    {"type": "image/jpeg", "url": "file:///path/to/your/image.jpeg",
     "size": "large", "height": "0.12", "width": "0.13", "depth": 0,
     "timestamp": 0},
    {"type": "image/jpeg", "url": "https://www.pixabay.com/photo/1/12/2013/",
     "size": "large", "format": "JPEG", "quality": "low"},
    # Koordinaten-Dict
    {"x": 0.17, "y": 0.64, "w": 1.0, "h": 0.86},
    # description enthaelt JSON-Array-Echo
    {"description": '[{"type": "person", "x": 0.46, "y": 0.5, "w": 0.6}]'},
    {"description": '[{"type": "image/jpeg", "url": "file:///path/to/your/picture", "size": "large"}]'},
]

GOOD_DICTS = [
    {"description": "A mysterious woman dances slowly in a bioluminescent "
                    "jungle at night, surrounded by glowing plants.",
     "mood": "mystical", "tags": ["jungle", "dance"]},
    {"description": "Slow tracking shot through a green forest with soft "
                    "morning light.", "mood": None, "tags": []},
]


class TestValidateCaptionDict:
    def test_real_junk_from_db_rejected(self):
        for junk in REAL_JUNK_DICTS:
            assert _validate_caption_dict(junk) is None, junk

    def test_good_captions_accepted(self):
        for good in GOOD_DICTS:
            assert _validate_caption_dict(good) == good

    def test_non_dict_rejected(self):
        assert _validate_caption_dict(None) is None
        assert _validate_caption_dict("some text") is None
        assert _validate_caption_dict([1, 2]) is None
        assert _validate_caption_dict({}) is None


class TestCaptionTextPlausible:
    def test_prose_accepted(self):
        assert _caption_text_is_plausible(
            "A dancer moves through glowing plants in the dark jungle.")

    def test_short_or_empty_rejected(self):
        assert not _caption_text_is_plausible("")
        assert not _caption_text_is_plausible("ok")
        assert not _caption_text_is_plausible(None)

    def test_json_echo_rejected(self):
        assert not _caption_text_is_plausible('{"type": "image/jpeg"}')
        assert not _caption_text_is_plausible('[{"x": 0.1, "y": 0.2}]')
        assert not _caption_text_is_plausible(
            'the file is at file:///path/to/your/image.jpeg size large')

    def test_numbers_only_rejected(self):
        assert not _caption_text_is_plausible("0.1 0.2 0.3 0.4 0.5 0.6")

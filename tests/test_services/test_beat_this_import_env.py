def test_beat_this_importable_in_active_env():
    import beat_this

    assert beat_this is not None

"""Regression tests for Ollama cold-load request timeouts."""

from __future__ import annotations

import inspect

from services.ollama_service import OllamaService


def test_chat_and_vision_do_not_use_bounded_read_timeout_for_inference() -> None:
    """B-242: cold model load must not be cut off by httpx read timeout."""
    chat_src = inspect.getsource(OllamaService.chat)
    vision_src = inspect.getsource(OllamaService.vision)

    assert "timeout=120.0" not in chat_src
    assert "timeout=60.0" not in vision_src
    assert "_inference_timeout()" in chat_src
    assert "_inference_timeout()" in vision_src


def test_vision_has_generate_fallback_for_empty_chat_content() -> None:
    """B-249: moondream returns empty content via /api/chat, but works via /api/generate."""
    vision_src = inspect.getsource(OllamaService.vision)

    assert '"/api/generate"' in vision_src
    assert "if not content" in vision_src or "if content" in vision_src

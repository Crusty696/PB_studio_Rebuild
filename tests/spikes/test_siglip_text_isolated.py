"""PRE-4 Spike: SigLIP-Text-Tower as isolated slice.

Tests the assumption from D-024 that the SigLIP text encoder can be loaded
WITHOUT the vision tower, sharing the model_id but only instantiating the
text path. If true: caption embeddings cost +0..0.5 GB VRAM (vs ~3 GB for
the full vision+text model).
"""
import pytest


@pytest.fixture(scope="module")
def siglip_text_model():
    """Load only the text encoder of SigLIP-so400m. Cached for module scope."""
    from transformers import SiglipTextModel, AutoTokenizer

    model_id = "google/siglip-so400m-patch14-384"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = SiglipTextModel.from_pretrained(model_id)
    model.eval()
    return model, tokenizer


def test_text_model_loads_without_vision(siglip_text_model):
    """The text-only slice can be instantiated by class-name."""
    model, _ = siglip_text_model
    assert model is not None
    # Should have text_model layers but NOT vision_model
    assert hasattr(model, "text_model") or hasattr(model, "encoder")
    assert not hasattr(model, "vision_model")


def test_text_embedding_shape_is_1152(siglip_text_model):
    """Output dim must match D-024 spec: 1152-dim (matches image tower)."""
    import torch

    model, tokenizer = siglip_text_model
    inputs = tokenizer(
        ["a person looking at the camera"],
        padding="max_length",
        max_length=64,
        return_tensors="pt",
    )
    with torch.inference_mode():
        out = model(**inputs)
    # SiglipTextModel returns BaseModelOutputWithPooling with pooler_output
    pooled = out.pooler_output
    assert pooled.shape == (1, 1152), f"expected (1, 1152), got {pooled.shape}"


def test_text_embedding_is_finite(siglip_text_model):
    """No NaN/Inf in output (sanity check)."""
    import torch

    model, tokenizer = siglip_text_model
    inputs = tokenizer(
        ["bear looking into the camera", "wide cinematic landscape"],
        padding="max_length",
        max_length=64,
        return_tensors="pt",
    )
    with torch.inference_mode():
        out = model(**inputs)
    assert torch.isfinite(out.pooler_output).all()
    assert out.pooler_output.shape == (2, 1152)

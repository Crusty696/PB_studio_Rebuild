"""services.agent — Aggregator-Index für KI-Agent-Domain Services.

Cycle 14 / Option C: Logische Gruppierung der Agent-Services ohne
physische Moves. Vorhandene Imports bleiben kompatibel.
"""
from __future__ import annotations

from services.action_registry import (  # noqa: F401
    ActionDef,
    ActionRegistry,
    action_registry,
)
from services.local_agent_service import LocalAgentService  # noqa: F401
from services.ollama_client import OllamaClient  # noqa: F401

__all__ = [
    "ActionDef",
    "ActionRegistry",
    "action_registry",
    "LocalAgentService",
    "OllamaClient",
]

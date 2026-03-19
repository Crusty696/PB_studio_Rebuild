"""
Multi-Agenten System für PB Studio.

Enthält spezialisierte Agenten (Vision, Audio, Editor) sowie einen
Orchestrator, der Anfragen an den richtigen Agenten weiterleitet.
"""

from agents.base_agent import BaseAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.vision_agent import VisionAgent
from agents.audio_agent import AudioAgent
from agents.editor_agent import EditorAgent

__all__ = [
    "BaseAgent",
    "OrchestratorAgent",
    "VisionAgent",
    "AudioAgent",
    "EditorAgent",
]

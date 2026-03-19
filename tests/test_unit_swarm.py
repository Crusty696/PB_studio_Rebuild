"""Unit-Tests für das 3-Agenten Swarm System (ohne ML-Modelle)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.model_manager import ModelManager

# Test 1: Singleton
mm1 = ModelManager()
mm2 = ModelManager()
assert mm1 is mm2
print("OK1: ModelManager Singleton")

# Test 2: Action Registry
import services.register_actions
from services.action_registry import action_registry
actions = action_registry.list_actions()
assert "transcribe_audio" in actions
assert "analyze_video_content" in actions
print(f"OK2: Actions = {actions}")

# Test 3: Agent Routing
from agents.orchestrator_agent import OrchestratorAgent
from agents.audio_agent import AudioAgent
from agents.vision_agent import VisionAgent
orch = OrchestratorAgent()
a = orch._route_to_agent("Transkribiere Audio Track 1")
assert isinstance(a, AudioAgent), f"Got {type(a)}"
v = orch._route_to_agent("Was passiert visuell im Video?")
assert isinstance(v, VisionAgent), f"Got {type(v)}"
print("OK3: Agent Routing")

# Test 4: Multi-Step Detection
assert orch._detect_multi_step("Analysiere Bild und Ton von Video 1")
assert orch._detect_multi_step("Was passiert im Video und was wird gesagt?")
assert not orch._detect_multi_step("Analysiere das Audio")
print("OK4: Multi-Step Detection")

# Test 5: LocalAgentService uses Singleton
from services.local_agent_service import LocalAgentService
agent = LocalAgentService()
assert agent.model_manager is mm1
print("OK5: LocalAgentService uses Singleton ModelManager")

print("\nALLE UNIT-TESTS BESTANDEN!")

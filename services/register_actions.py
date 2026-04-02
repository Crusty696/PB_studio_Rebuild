"""Entry-point: imports all action modules so their @action_registry.register
decorators run at startup.

Add new domains by importing the corresponding module in services/actions/.
"""

from services.actions import audio_actions  # noqa: F401
from services.actions import video_actions  # noqa: F401
from services.actions import edit_actions   # noqa: F401
from services.actions import ai_actions     # noqa: F401

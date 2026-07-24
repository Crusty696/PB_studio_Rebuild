"""B-685: Ein PBStudioError (z.B. OllamaError) aus einem synchronen Action-Handler
muss in _execute_single_action als strukturierte Per-Aktion-Fehlermeldung gefangen
werden — sonst entkommt er dem except-Tupel und reisst den Multi-Action-Loop ab.
"""

from services.errors import DatabaseError, OllamaError
from services.local_agent_service import LocalAgentService


class _Def:
    def __init__(self, name):
        self.name = name


def _service_with_raising_registry(exc):
    class _Registry:
        def resolve(self, name):
            return _Def(name)

        def execute(self, name, params):
            raise exc

    svc = object.__new__(LocalAgentService)  # __init__ umgehen (kein Modell-Load)
    svc.registry = _Registry()
    return svc


def test_ollama_error_is_caught_per_action():
    svc = _service_with_raising_registry(
        OllamaError("HTTP-Fehler 500", model="m", http_code=500)
    )

    result = svc._execute_single_action({"action": "ask_ai", "params": {}})

    # B-685: kein Escape — strukturierte Per-Aktion-Meldung.
    assert result["error"] is not None
    assert "ask_ai" in result["error"]
    assert "500" in result["error"] or "HTTP" in result["error"]


def test_other_pbstudioerror_also_caught():
    svc = _service_with_raising_registry(DatabaseError("locked"))

    result = svc._execute_single_action({"action": "import_file", "params": {}})

    assert result["error"] is not None
    assert "import_file" in result["error"]


def test_successful_action_not_falsely_caught():
    class _Registry:
        def resolve(self, name):
            return _Def(name)

        def execute(self, name, params):
            return {"status": "ok", "value": 42}

    svc = object.__new__(LocalAgentService)
    svc.registry = _Registry()

    result = svc._execute_single_action({"action": "list_actions", "params": {}})

    assert result["error"] is None
    assert result["result"] == {"status": "ok", "value": 42}

from __future__ import annotations

import threading


class _FakeRegistry:
    def execute(self, _name, _params):
        return {"status": "ok"}


class _RacingAgent:
    def __init__(self):
        self.registry = _FakeRegistry()
        self.first_started = threading.Event()
        self.second_entered = threading.Event()
        self.release_first = threading.Event()
        self.release_second = threading.Event()
        self.seen: dict[str, object] = {}

    def process(self, text):
        if text == "first":
            self.seen["first_start"] = self.registry
            self.first_started.set()
            assert self.release_first.wait(timeout=3)
            self.seen["first_after_release"] = self.registry
            return {"action": "none", "message": "first"}

        self.seen["second_start"] = self.registry
        self.second_entered.set()
        assert self.release_second.wait(timeout=3)
        self.seen["second_after_wait"] = self.registry
        return {"action": "none", "message": "second"}


def test_b410_agent_worker_holds_registry_stable_during_process_call():
    from ui.chat_dock import AIAgentWorker

    agent = _RacingAgent()
    first = AIAgentWorker(agent, "first")
    second = AIAgentWorker(agent, "second")

    t1 = threading.Thread(target=first.run)
    t2 = threading.Thread(target=second.run)

    t1.start()
    assert agent.first_started.wait(timeout=3)
    t2.start()
    assert not agent.second_entered.wait(timeout=0.2)

    agent.release_first.set()
    t1.join(timeout=3)
    assert agent.second_entered.wait(timeout=3)
    agent.release_second.set()
    t2.join(timeout=3)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert agent.seen["first_start"] is agent.seen["first_after_release"]

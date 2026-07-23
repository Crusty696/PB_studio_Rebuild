"""B-669: harte Wall-Clock-Grenze fuer die generierenden OllamaClient-Methoden.

Hintergrund: ``urllib.request.urlopen(timeout=self.timeout)`` ist ein
Socket-INAKTIVITAETS-Timeout pro Read, keine Gesamtlaufzeit-Grenze. Solange
Ollama periodisch Bytes liefert (Streaming, langsamer Modell-Load), wird der
Timeout staendig zurueckgesetzt und der Call laeuft praktisch unbegrenzt —
live gemessen ~50 Min (B-666). Der Worker-Thread haengt dabei in einem
blockierenden C-Call und ist nicht unterbrechbar.

Diese Tests pinnen, dass jede generierende Methode nach der Wall-Clock-Grenze
zurueckkehrt, statt am Inaktivitaets-Timeout haengen zu bleiben.
"""

import time

import pytest

from services.errors import OllamaError, OllamaTimeoutError


# Alle generierenden Methoden + Aufrufargumente. `_generate_text` ist privat,
# wird aber von `chat` als Fallback genutzt (Modell ohne /api/chat-Support)
# und blockiert genauso.
GENERATING_CALLS = [
    ("chat", dict(model="m", user_message="hi")),
    ("chat_with_history", dict(model="m", messages=[{"role": "user", "content": "hi"}])),
    ("_generate_text", dict(model="m", user_message="hi")),
    ("chat_vision", dict(model="m", user_message="hi", images_base64=["Zm9v"])),
    ("chat_with_tools", dict(model="m", user_message="hi", tools=[])),
]


class _HangingResponse:
    """urlopen-Ersatz, der wie ein streamendes Ollama nie fertig wird."""

    def __init__(self, *_a, **_kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self):
        # Simuliert den blockierenden, nicht unterbrechbaren Call. Deutlich
        # laenger als die Test-Deadline, aber endlich, damit ein Fehlschlag
        # die Suite nicht aufhaengt.
        time.sleep(30)
        return b'{"message": {"content": "zu spaet"}}'


@pytest.fixture
def hanging_client(monkeypatch):
    """Client mit sehr kurzer Wall-Clock-Grenze und haengendem HTTP-Call."""
    import services.ollama_client as oc

    monkeypatch.setattr(oc.urllib.request, "urlopen", _HangingResponse)
    return oc.OllamaClient(wall_clock_timeout=0.4)


@pytest.mark.parametrize("method_name,kwargs", GENERATING_CALLS,
                         ids=[c[0] for c in GENERATING_CALLS])
def test_generating_call_is_wall_clock_bounded(hanging_client, method_name, kwargs):
    """Jede generierende Methode kehrt an der Wall-Clock-Grenze zurueck."""
    started = time.monotonic()
    with pytest.raises(OllamaTimeoutError):
        getattr(hanging_client, method_name)(**kwargs)
    elapsed = time.monotonic() - started

    # Grosszuegige Obergrenze: entscheidend ist, dass NICHT die vollen 30 s
    # des haengenden Calls abgewartet werden.
    assert elapsed < 10.0, (
        f"{method_name} kehrte erst nach {elapsed:.1f}s zurueck — "
        "Wall-Clock-Grenze greift nicht"
    )


def test_timeout_error_is_ollama_error_subclass():
    """Bestehende ``except OllamaError``-Pfade fangen den Timeout weiterhin.

    Wichtig fuer die Fallback-Logik in pacing_strategist (B-666), die
    ``except (RuntimeError, OSError, OllamaError)`` nutzt.
    """
    assert issubclass(OllamaTimeoutError, OllamaError)


def test_timeout_is_labelled_honestly(hanging_client):
    """Timeout darf nicht als 'nicht erreichbar' fehletikettiert werden.

    B-666-Lehre: ein Timeout ist ein eigener degraded_reason, kein
    ``OllamaNotAvailableError`` — sonst zeigt die Diagnose auf die falsche
    Ursache.
    """
    from services.errors import OllamaNotAvailableError

    with pytest.raises(OllamaTimeoutError) as excinfo:
        hanging_client.chat(model="m", user_message="hi")

    assert not isinstance(excinfo.value, OllamaNotAvailableError)
    assert "timeout" in str(excinfo.value).lower()


def test_successful_call_is_unaffected(monkeypatch):
    """Der Bound darf den normalen Erfolgsfall nicht veraendern."""
    import services.ollama_client as oc

    class _OkResponse:
        def __init__(self, *_a, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return b'{"message": {"content": "  hallo  "}}'

    monkeypatch.setattr(oc.urllib.request, "urlopen", _OkResponse)
    client = oc.OllamaClient(wall_clock_timeout=5.0)

    assert client.chat(model="m", user_message="hi") == "hallo"


def test_nested_fallback_does_not_stack_deadlines(monkeypatch):
    """Interner Modell-Fallback darf keine zweite Deadline aufspannen.

    ``chat`` ruft sich bei "memory layout"-HTTPError rekursiv mit einem
    Fallback-Modell auf. Wuerde dabei eine neue Wall-Clock-Grenze gesetzt,
    verdoppelte sich die maximale Gesamtlaufzeit.
    """
    import services.ollama_client as oc

    depths = []

    class _Client(oc.OllamaClient):
        def _wall_clock_deadline_active(self):
            active = super()._wall_clock_deadline_active()
            depths.append(active)
            return active

    client = _Client(wall_clock_timeout=5.0)

    calls = {"n": 0}

    class _Resp:
        def __init__(self, *_a, **_kw):
            calls["n"] += 1

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return b'{"message": {"content": "ok"}}'

    monkeypatch.setattr(oc.urllib.request, "urlopen", _Resp)
    monkeypatch.setattr(_Client, "_find_fallback_model", lambda self, m: "fallback:1b")

    # Direkter rekursiver Aufruf im gebundenen Kontext: der zweite Eintritt
    # muss die bestehende Deadline sehen und keine neue oeffnen.
    assert client.chat(model="m", user_message="hi", _in_fallback=True) == "ok"
    assert depths, "Deadline-Kontext wurde nicht geprueft"
    assert depths[0] is False, "erster Eintritt darf noch keine Deadline sehen"

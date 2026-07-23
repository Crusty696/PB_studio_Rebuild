"""B-670: ein abgekoppelter LLM-Call darf den Prozess-Exit nicht aufhalten.

Der B-669-Bound gibt dem Aufrufer nach der Wall-Clock-Grenze die Kontrolle
zurueck. Mit ``ThreadPoolExecutor`` blieb der Prozess trotzdem haengen:
``concurrent.futures.thread._python_exit`` ist als atexit-Hook registriert und
macht ``t.join()`` OHNE Timeout auf jeden Worker-Thread. Der Hang wanderte
damit nur von der Laufzeit in den Shutdown — bei einem streamenden Ollama
potenziell unbegrenzt (genau der B-666-Ausgangsbefund).

Gemessen wird deshalb die Zeit bis zum **echten Prozessende**, nicht die
Rueckkehr des Aufrufers. Das geht nur im Subprozess.
"""

import subprocess
import sys
import textwrap
import time

import pytest


# Der Stub blockiert so lange; der Prozess muss deutlich frueher enden.
_BLOCK_SEC = 8
_DEADLINE_SEC = 0.4
# Grosszuegig: Interpreter-Start + Imports (torch etc.) kosten hier real ~5-7s.
# Entscheidend ist der Abstand zu _BLOCK_SEC, nicht ein knapper Absolutwert.
_MAX_OVERHEAD_SEC = 4.0


def _run_probe(body: str) -> float:
    """Fuehrt ``body`` im Subprozess aus, liefert die Gesamt-Prozesslaufzeit."""
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {repr(str(__import__('pathlib').Path(__file__).resolve().parents[2]))})

        class _Blocking:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                time.sleep({_BLOCK_SEC})
                return b'{{"message": {{"content": "zu spaet"}}}}'

        {textwrap.indent(textwrap.dedent(body), "        ").strip()}
    """)

    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=_BLOCK_SEC * 4,
    )
    elapsed = time.monotonic() - started
    assert proc.returncode == 0, (
        f"Probe-Subprozess scheiterte:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr[-1500:]}"
    )
    assert "TIMEOUT_OK" in proc.stdout, (
        f"Wall-Clock-Grenze griff nicht:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr[-800:]}"
    )
    return elapsed


@pytest.mark.slow
def test_ollama_client_timeout_does_not_delay_process_exit():
    elapsed = _run_probe(f"""
        import services.ollama_client as oc
        oc.urllib.request.urlopen = _Blocking
        client = oc.OllamaClient(wall_clock_timeout={_DEADLINE_SEC})
        try:
            client.chat(model="m", user_message="hi")
        except oc.OllamaTimeoutError:
            print("TIMEOUT_OK", flush=True)
    """)

    assert elapsed < _BLOCK_SEC, (
        f"Prozess brauchte {elapsed:.1f}s — er wartet auf den abgekoppelten "
        f"Call ({_BLOCK_SEC}s). Der Shutdown ist blockiert (B-670)."
    )


@pytest.mark.slow
def test_pacing_strategist_timeout_does_not_delay_process_exit():
    """Gleiches Muster im B-666-Fix des PacingStrategist."""
    elapsed = _run_probe(f"""
        import services.ollama_client as oc
        import services.pacing_strategist as ps
        oc.urllib.request.urlopen = _Blocking
        # Modul-Global, wird in _chat_with_deadline als future.result(timeout=...)
        # gelesen — sonst wartet der Test die vollen 120 s.
        ps.HTTP_OLLAMA_PACING_TIMEOUT_SEC = {_DEADLINE_SEC}

        client = oc.OllamaClient(wall_clock_timeout=600)  # innerer Bound darf nicht greifen
        strategist = ps.PacingStrategist()
        try:
            strategist._chat_with_deadline(client, "m", "hi", 64)
        except Exception as exc:
            if "timeout" in str(exc).lower() or "Timeout" in type(exc).__name__:
                print("TIMEOUT_OK", flush=True)
            else:
                raise
    """)

    assert elapsed < _BLOCK_SEC, (
        f"Prozess brauchte {elapsed:.1f}s — PacingStrategist haelt den Exit auf (B-670)."
    )

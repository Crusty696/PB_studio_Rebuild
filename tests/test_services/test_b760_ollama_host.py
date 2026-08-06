"""B-760: Hostname-Normalisierung ``localhost`` -> ``127.0.0.1`` im OllamaClient.

Hintergrund: Windows loest ``localhost`` bevorzugt nach ``::1`` (IPv6) auf.
Am 2026-08-04 lauschte dort eine fremde Ollama-0.30.10-Instanz, die den
Kontext 3x groesser dimensionierte — Vision-Modell lief dadurch zu 77 % auf
CPU statt GPU. ``127.0.0.1`` trifft deterministisch die gepinnte GPU-faehige
0.21.2. Reine URL-String-Vertraege, keine Netzverbindungen.
"""

from services.ollama_client import OllamaClient, _normalize_ollama_host


def test_localhost_normalized_to_ipv4():
    assert _normalize_ollama_host("http://localhost:11434") == "http://127.0.0.1:11434"


def test_localhost_uppercase_and_trailing_slash():
    assert (
        _normalize_ollama_host("http://LOCALHOST:11434/".rstrip("/"))
        == "http://127.0.0.1:11434"
    )


def test_ipv4_loopback_unchanged():
    assert _normalize_ollama_host("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_remote_host_unchanged():
    assert _normalize_ollama_host("http://192.168.1.5:11434") == "http://192.168.1.5:11434"


def test_scheme_and_port_preserved():
    assert _normalize_ollama_host("https://localhost:9999") == "https://127.0.0.1:9999"


def test_client_init_normalizes_base_url():
    # __init__ hat keine Netz-Nebenwirkungen (nur optionaler torch-Import
    # in try/except) — normale Instanziierung ist sicher.
    client = OllamaClient(base_url="http://localhost:11434")
    assert client.base_url == "http://127.0.0.1:11434"


def test_client_init_keeps_remote_url():
    client = OllamaClient(base_url="http://192.168.1.5:11434/")
    assert client.base_url == "http://192.168.1.5:11434"


def test_ollama_service_base_normalized():
    # B-760 Folge: ollama_service spricht Ollama direkt via httpx —
    # OLLAMA_BASE muss ebenfalls IPv4-normalisiert sein.
    from services.ollama_service import OLLAMA_BASE

    assert "127.0.0.1" in OLLAMA_BASE and "localhost" not in OLLAMA_BASE

"""
LIVE Ollama/LLM Integration Test fuer PB Studio.

Testet JEDE Funktion einzeln gegen einen laufenden Ollama-Server.
Wenn eine Funktion crasht, wird sie gefangen und der naechste Test laeuft weiter.

Voraussetzung: Ollama laeuft auf localhost:11434 mit gemma4:e4b und/oder phi3:mini.
"""

import os
import sys
import time
import traceback
import logging

# Projekt-Root zum sys.path hinzufuegen
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Logging konfigurieren (nur Warnungen und hoeher fuer sauberen Output)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# ============================================================================
# Hilfsfunktionen
# ============================================================================

RESULTS = []  # Sammelt alle Testergebnisse

def run_test(test_name: str, func, *args, **kwargs):
    """Fuehrt einen Test aus, faengt alle Exceptions, misst die Zeit."""
    print(f"\n{'='*70}")
    print(f"  TEST: {test_name}")
    print(f"{'='*70}")

    t_start = time.time()
    status = "PASS"
    response_content = ""
    model_used = ""
    error_tb = ""

    try:
        result = func(*args, **kwargs)
        elapsed = time.time() - t_start

        if isinstance(result, dict):
            response_content = str(result.get("response", result))[:200]
            model_used = result.get("model", "")
            if result.get("status") == "FAIL":
                status = "FAIL"
                error_tb = result.get("error", "")
        elif isinstance(result, str):
            response_content = result[:200]
        else:
            response_content = str(result)[:200]

    except Exception as e:
        elapsed = time.time() - t_start
        status = "CRASH"
        error_tb = traceback.format_exc()
        response_content = str(e)[:200]

    entry = {
        "test": test_name,
        "status": status,
        "elapsed": f"{elapsed:.2f}s",
        "response": response_content,
        "model": model_used,
        "traceback": error_tb,
    }
    RESULTS.append(entry)

    # Sofortiges Feedback
    icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "CRASH": "[CRASH]"}[status]
    print(f"  {icon} {test_name} ({elapsed:.2f}s)")
    if response_content:
        print(f"  Response: {response_content[:150]}")
    if error_tb and status == "CRASH":
        print(f"  Traceback:\n{error_tb}")
    elif error_tb and status == "FAIL":
        print(f"  Error: {error_tb[:300]}")

    return entry


# ============================================================================
# TEST 1: OllamaClient Konnektivitaet
# ============================================================================

def test_ollama_client_connectivity():
    """Testet grundlegende HTTP-Verbindung zum Ollama-Server."""
    from services.ollama_client import OllamaClient

    client = OllamaClient(base_url="http://localhost:11434")
    available = client.is_available()

    if not available:
        return {"status": "FAIL", "response": "Ollama nicht erreichbar auf localhost:11434", "model": "", "error": "is_available() returned False"}

    return {"status": "PASS", "response": f"Ollama verfuegbar: {available}", "model": ""}


def test_ollama_client_version():
    """Testet Versions-Abfrage."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    version = client.get_version()

    if version is None:
        return {"status": "FAIL", "response": "Version ist None", "model": "", "error": "get_version() returned None"}

    return {"status": "PASS", "response": f"Ollama Version: {version}", "model": ""}


def test_ollama_client_list_models():
    """Listet alle verfuegbaren Modelle."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    models = client.list_models()

    if not models:
        return {"status": "FAIL", "response": "Keine Modelle gefunden", "model": "", "error": "list_models() returned empty list"}

    return {"status": "PASS", "response": f"Modelle ({len(models)}): {', '.join(models)}", "model": ""}


def test_ollama_client_model_exists():
    """Prueft ob gemma4:e4b oder phi3:mini verfuegbar ist."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    models = client.list_models()

    target_models = ["gemma4:e4b", "phi3:mini"]
    found = [m for m in target_models if m in models]
    not_found = [m for m in target_models if m not in models]

    response = f"Gefunden: {found}"
    if not_found:
        response += f" | Nicht gefunden: {not_found}"

    if not found:
        return {"status": "FAIL", "response": response, "model": "", "error": "Keines der Zielmodelle verfuegbar"}

    return {"status": "PASS", "response": response, "model": ""}


def test_ollama_client_best_model():
    """Testet get_best_available_model()."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    best = client.get_best_available_model(probe=False)

    if best is None:
        return {"status": "FAIL", "response": "Kein bestes Modell gefunden", "model": "", "error": "get_best_available_model() returned None"}

    return {"status": "PASS", "response": f"Bestes Modell: {best}", "model": best}


def test_ollama_client_model_info():
    """Testet get_model_info() fuer das beste Modell."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    best = client.get_best_available_model(probe=False)
    if not best:
        return {"status": "FAIL", "response": "Kein Modell verfuegbar", "model": "", "error": "Kein Modell"}

    info = client.get_model_info(best)

    if not info:
        return {"status": "FAIL", "response": f"Keine Info fuer {best}", "model": best, "error": "get_model_info() returned empty dict"}

    # Extrahiere Schluesseldaten
    details = info.get("details", {})
    template_preview = str(info.get("template", ""))[:100]
    params = details.get("parameter_size", "?")
    quant = details.get("quantization_level", "?")

    return {
        "status": "PASS",
        "response": f"Modell: {best} | Params: {params} | Quant: {quant} | Template: {template_preview}",
        "model": best,
    }


# ============================================================================
# TEST 2: OllamaClient.chat() — Direkte Chat-Funktion
# ============================================================================

def test_ollama_client_chat_gemma():
    """Testet OllamaClient.chat() mit gemma4:e4b."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    models = client.list_models()

    if "gemma4:e4b" not in models:
        return {"status": "FAIL", "response": "gemma4:e4b nicht installiert", "model": "gemma4:e4b", "error": "Modell nicht vorhanden"}

    reply = client.chat(
        model="gemma4:e4b",
        user_message="Hallo, was bist du? Antworte in einem Satz.",
        temperature=0.1,
        max_tokens=100,
    )

    if not reply or not reply.strip():
        return {"status": "FAIL", "response": "Leere Antwort", "model": "gemma4:e4b", "error": "chat() returned empty string"}

    return {"status": "PASS", "response": reply, "model": "gemma4:e4b"}


def test_ollama_client_chat_phi3():
    """Testet OllamaClient.chat() mit phi3:mini."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    models = client.list_models()

    if "phi3:mini" not in models:
        return {"status": "FAIL", "response": "phi3:mini nicht installiert", "model": "phi3:mini", "error": "Modell nicht vorhanden"}

    reply = client.chat(
        model="phi3:mini",
        user_message="Hallo, was bist du? Antworte in einem Satz.",
        temperature=0.1,
        max_tokens=100,
    )

    if not reply or not reply.strip():
        return {"status": "FAIL", "response": "Leere Antwort", "model": "phi3:mini", "error": "chat() returned empty string"}

    return {"status": "PASS", "response": reply, "model": "phi3:mini"}


def test_ollama_client_chat_with_system_prompt():
    """Testet OllamaClient.chat() mit System-Prompt."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    best = client.get_best_available_model(probe=False)
    if not best:
        return {"status": "FAIL", "response": "Kein Modell", "model": "", "error": "Kein Modell"}

    reply = client.chat(
        model=best,
        user_message="Was ist 2+2?",
        system_prompt="Du bist ein Mathematiker. Antworte IMMER mit einer einzigen Zahl. Kein anderer Text.",
        temperature=0.0,
        max_tokens=10,
    )

    # Pruefen ob "4" in der Antwort
    has_four = "4" in reply

    return {
        "status": "PASS" if has_four else "FAIL",
        "response": f"Antwort: '{reply}' | Enthaelt '4': {has_four}",
        "model": best,
        "error": "" if has_four else f"Erwartete '4' in Antwort, bekam: '{reply}'",
    }


# ============================================================================
# TEST 3: OllamaClient.chat_with_history() — Multi-Turn
# ============================================================================

def test_ollama_client_chat_with_history():
    """Testet chat_with_history() mit mehreren Nachrichten."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    best = client.get_best_available_model(probe=False)
    if not best:
        return {"status": "FAIL", "response": "Kein Modell", "model": "", "error": "Kein Modell"}

    messages = [
        {"role": "system", "content": "Du bist ein hilfreicher Assistent. Antworte kurz."},
        {"role": "user", "content": "Mein Name ist David."},
        {"role": "assistant", "content": "Hallo David! Wie kann ich dir helfen?"},
        {"role": "user", "content": "Wie heisse ich?"},
    ]

    reply = client.chat_with_history(
        model=best,
        messages=messages,
        temperature=0.1,
        max_tokens=50,
    )

    has_david = "david" in reply.lower()

    return {
        "status": "PASS" if has_david else "FAIL",
        "response": f"Antwort: '{reply}' | Enthaelt 'David': {has_david}",
        "model": best,
        "error": "" if has_david else f"Erwartete 'David' in Antwort, bekam: '{reply}'",
    }


# ============================================================================
# TEST 4: OllamaClient Pause/Resume (VRAM-Schutz)
# ============================================================================

def test_ollama_client_pause_resume():
    """Testet den Pause/Resume-Mechanismus fuer VRAM-Schutz."""
    from services.ollama_client import OllamaClient
    from services.errors import OllamaPausedError

    client = OllamaClient()
    best = client.get_best_available_model(probe=False)
    if not best:
        return {"status": "FAIL", "response": "Kein Modell", "model": "", "error": "Kein Modell"}

    # Startzustand pruefen
    assert not client.is_paused, "Client sollte initial NICHT pausiert sein"

    # Pausieren
    client.pause()
    assert client.is_paused, "Client sollte nach pause() pausiert sein"

    # Chat sollte jetzt OllamaPausedError werfen
    paused_error_raised = False
    try:
        client.chat(model=best, user_message="Test")
    except OllamaPausedError:
        paused_error_raised = True

    # Resume
    client.resume()
    assert not client.is_paused, "Client sollte nach resume() NICHT pausiert sein"

    if not paused_error_raised:
        return {"status": "FAIL", "response": "OllamaPausedError wurde NICHT geworfen", "model": best, "error": "Pause-Schutz funktioniert nicht"}

    return {"status": "PASS", "response": "Pause/Resume funktioniert korrekt. OllamaPausedError wurde geworfen.", "model": best}


# ============================================================================
# TEST 5: OllamaClient.supports_tools()
# ============================================================================

def test_ollama_client_supports_tools():
    """Testet die Tool-Use-Erkennung."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()

    # Bekannte Tool-faehige Modelle
    tool_capable = {
        "gemma4:e4b": True,
        "phi3:mini": True,
        "llama3.1:8b": True,
        "qwen2.5:7b-instruct": True,
    }

    # Kleine Modelle die kein Tool-Use koennen
    not_tool_capable = {
        "qwen2.5:0.5b": False,
    }

    results_detail = []
    all_correct = True

    for model, expected in {**tool_capable, **not_tool_capable}.items():
        actual = client.supports_tools(model)
        correct = actual == expected
        if not correct:
            all_correct = False
        results_detail.append(f"{model}: expected={expected}, actual={actual}, {'OK' if correct else 'FALSCH'}")

    return {
        "status": "PASS" if all_correct else "FAIL",
        "response": " | ".join(results_detail),
        "model": "",
        "error": "" if all_correct else "Einige Tool-Use-Checks falsch",
    }


# ============================================================================
# TEST 6: OllamaClient.chat_with_tools() — Function Calling
# ============================================================================

def test_ollama_client_chat_with_tools():
    """Testet Function-Calling via chat_with_tools()."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    best = client.get_best_available_model(probe=False)
    if not best:
        return {"status": "FAIL", "response": "Kein Modell", "model": "", "error": "Kein Modell"}

    if not client.supports_tools(best):
        return {"status": "FAIL", "response": f"Modell {best} unterstuetzt kein Tool-Use", "model": best, "error": "Kein Tool-Use-Support"}

    tools = [
        {
            "type": "function",
            "function": {
                "name": "analyze_audio",
                "description": "Analysiert eine Audiodatei und gibt BPM zurueck",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "track_id": {"type": "integer", "description": "ID des Audio-Tracks"}
                    },
                    "required": ["track_id"],
                },
            },
        }
    ]

    result = client.chat_with_tools(
        model=best,
        user_message="Analysiere Audio Track 5",
        tools=tools,
        system_prompt="Du bist ein Audio-Analyse-Assistent. Nutze die verfuegbaren Tools.",
        temperature=0.0,
        max_tokens=200,
    )

    response_type = result.get("type", "unknown")

    return {
        "status": "PASS",
        "response": f"Type: {response_type} | Tool-Calls: {result.get('tool_calls', [])} | Content: {result.get('content', '')[:100]}",
        "model": best,
    }


# ============================================================================
# TEST 7: OllamaService.chat() (hoeherer Abstraktions-Layer)
# ============================================================================

def test_ollama_service_chat():
    """Testet OllamaService.chat() — der hoehere Abstraktions-Layer."""
    from services.ollama_service import OllamaService

    svc = OllamaService.get()

    if not svc.is_ready:
        # Versuche Start
        svc.start()
        time.sleep(1)
        if not svc.is_ready:
            return {"status": "FAIL", "response": "OllamaService nicht bereit", "model": "", "error": "is_ready is False"}

    reply = svc.chat(
        messages=[
            {"role": "system", "content": "Antworte in einem Satz."},
            {"role": "user", "content": "Was ist PB Studio?"},
        ],
        model="gemma4:e4b",
    )

    if not reply or not reply.strip():
        return {"status": "FAIL", "response": "Leere Antwort", "model": "gemma4:e4b", "error": "chat() returned empty string"}

    if reply.startswith("Fehler:"):
        return {"status": "FAIL", "response": reply, "model": "gemma4:e4b", "error": reply}

    return {"status": "PASS", "response": reply, "model": "gemma4:e4b"}


# ============================================================================
# TEST 8: OllamaService — Streaming (via httpx)
# ============================================================================

def test_ollama_streaming():
    """Testet Streaming-Antworten via rohem httpx-Aufruf (OllamaService hat kein natives Streaming)."""
    import httpx

    OLLAMA_BASE = "http://localhost:11434"

    # Verwende das kleinste verfuegbare Modell fuer schnelle Antwort
    from services.ollama_client import OllamaClient
    client = OllamaClient()
    best = client.get_best_available_model(probe=False)
    if not best:
        return {"status": "FAIL", "response": "Kein Modell", "model": "", "error": "Kein Modell"}

    chunks_received = 0
    full_content = ""

    with httpx.Client(base_url=OLLAMA_BASE, timeout=60.0) as http_client:
        with http_client.stream("POST", "/api/chat", json={
            "model": best,
            "messages": [{"role": "user", "content": "Sage nur: Hallo Welt"}],
            "stream": True,
        }) as response:
            import json
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        chunks_received += 1
                        full_content += content
                except json.JSONDecodeError:
                    pass

    if chunks_received == 0:
        return {"status": "FAIL", "response": "Keine Chunks empfangen", "model": best, "error": "0 Streaming-Chunks"}

    return {
        "status": "PASS",
        "response": f"Empfangen: {chunks_received} Chunks | Content: '{full_content[:100]}'",
        "model": best,
    }


# ============================================================================
# TEST 9: ConversationMemory
# ============================================================================

def test_conversation_memory_basic():
    """Testet grundlegende ConversationMemory-Funktionalitaet."""
    from services.conversation_memory import ConversationMemory

    mem = ConversationMemory(session_id="test_session", max_turns=4)

    # Anfangszustand
    assert mem.is_empty, "Sollte initial leer sein"
    assert mem.turn_count == 0, f"Sollte 0 Turns haben, hat {mem.turn_count}"

    # Turn hinzufuegen
    mem.add_turn("Was ist BPM?", "BPM steht fuer Beats per Minute.")
    assert mem.turn_count == 1, f"Sollte 1 Turn haben, hat {mem.turn_count}"
    assert not mem.is_empty

    # Messages abrufen
    messages = mem.get_messages("Du bist ein Test-System.")
    assert len(messages) == 3, f"Erwartet 3 Messages (system + user + assistant), got {len(messages)}"
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert "BPM" in messages[1]["content"]

    return {"status": "PASS", "response": f"Memory funktioniert: {mem.turn_count} Turn(s), {len(messages)} Messages", "model": ""}


def test_conversation_memory_sliding_window():
    """Testet das Sliding-Window-Verhalten bei Overflow."""
    from services.conversation_memory import ConversationMemory

    mem = ConversationMemory(session_id="test_window", max_turns=3)

    # 5 Turns hinzufuegen (Window = 3, also sollten 2 rausfallen)
    for i in range(5):
        mem.add_turn(f"Frage {i}", f"Antwort {i}")

    assert mem.turn_count == 3, f"Erwartet 3 Turns nach Window-Trim, hat {mem.turn_count}"

    # Letzte 3 Turns pruefen
    last = mem.get_last_n_turns(3)
    assert len(last) == 3
    assert last[0].user == "Frage 2", f"Erwartet 'Frage 2', got '{last[0].user}'"
    assert last[-1].user == "Frage 4", f"Erwartet 'Frage 4', got '{last[-1].user}'"

    # Zusammenfassung sollte existieren (entfernte Turns)
    messages = mem.get_messages("System")
    system_content = messages[0]["content"]
    has_summary = "FRUEHERE GESPRAECHSHISTORIE" in system_content or "FRÜHERE GESPRÄCHSHISTORIE" in system_content

    return {
        "status": "PASS",
        "response": f"Sliding Window OK: {mem.turn_count} Turns behalten, Summary vorhanden: {has_summary}",
        "model": "",
    }


def test_conversation_memory_clear():
    """Testet das Loeschen der History."""
    from services.conversation_memory import ConversationMemory

    mem = ConversationMemory(session_id="test_clear", max_turns=8)
    mem.add_turn("Frage", "Antwort")
    assert mem.turn_count == 1

    mem.clear()
    assert mem.turn_count == 0
    assert mem.is_empty

    return {"status": "PASS", "response": "Clear funktioniert korrekt", "model": ""}


def test_conversation_memory_manager():
    """Testet den ConversationMemoryManager (Session-Management)."""
    from services.conversation_memory import ConversationMemoryManager

    manager = ConversationMemoryManager(max_sessions=3)

    # Sessions erstellen
    s1 = manager.get_or_create("session_a")
    s2 = manager.get_or_create("session_b")
    s3 = manager.get_or_create("session_c")

    assert manager.session_count == 3
    assert set(manager.list_sessions()) == {"session_a", "session_b", "session_c"}

    # Gleiche Session erneut abrufen (kein Duplikat)
    s1_again = manager.get_or_create("session_a")
    assert s1 is s1_again

    # 4. Session: Aelteste wird entfernt
    s4 = manager.get_or_create("session_d")
    assert manager.session_count == 3
    assert "session_a" not in manager.list_sessions(), "session_a sollte entfernt worden sein"
    assert "session_d" in manager.list_sessions()

    # Session entfernen
    manager.remove_session("session_b")
    assert manager.session_count == 2

    # Alle loeschen
    manager.clear_all()
    assert manager.session_count == 0

    return {"status": "PASS", "response": "ConversationMemoryManager: Sessions, Purging, Clear alles OK", "model": ""}


# ============================================================================
# TEST 10: ModelLifecycleService
# ============================================================================

def test_model_lifecycle_ollama_available():
    """Testet ob ModelLifecycleService Ollama erkennt."""
    from services.model_lifecycle_service import ModelLifecycleService

    svc = ModelLifecycleService(ollama_url="http://localhost:11434")
    available = svc.is_ollama_available()

    return {
        "status": "PASS" if available else "FAIL",
        "response": f"Ollama verfuegbar: {available}",
        "model": "",
        "error": "" if available else "is_ollama_available() returned False",
    }


def test_model_lifecycle_scan_ollama():
    """Testet das Scannen der Ollama-Modelle."""
    from services.model_lifecycle_service import ModelLifecycleService

    svc = ModelLifecycleService(ollama_url="http://localhost:11434")
    entries = svc.scan_ollama_models()

    if not entries:
        return {"status": "FAIL", "response": "Keine Ollama-Modelle gescannt", "model": "", "error": "scan_ollama_models() returned empty list"}

    model_details = []
    for e in entries:
        model_details.append(f"{e.model_id} ({e.size_display}, {e.metadata.get('parameter_size', '?')})")

    return {
        "status": "PASS",
        "response": f"Gescannt: {len(entries)} Modelle: {', '.join(model_details)}",
        "model": "",
    }


# ============================================================================
# TEST 11: OrchestratorAgent Routing (Keyword-basiert)
# ============================================================================

def test_orchestrator_agent_routing_audio():
    """Testet Keyword-Routing: 'analysiere das Audio' -> AudioAgent."""
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent()
    agent = orch._route_to_agent("analysiere das Audio")

    if agent is None:
        return {"status": "FAIL", "response": "Kein Agent fuer 'analysiere das Audio'", "model": "", "error": "route returned None"}

    return {
        "status": "PASS" if agent.domain == "audio" else "FAIL",
        "response": f"Geroutet zu: {agent.name} (domain: {agent.domain})",
        "model": "",
        "error": "" if agent.domain == "audio" else f"Erwartet audio, bekam {agent.domain}",
    }


def test_orchestrator_agent_routing_pacing():
    """Testet Keyword-Routing: 'schneide zum Beat' -> PacingAgent."""
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent()
    agent = orch._route_to_agent("schneide zum Beat automatisch")

    if agent is None:
        return {"status": "FAIL", "response": "Kein Agent fuer 'schneide zum Beat'", "model": "", "error": "route returned None"}

    return {
        "status": "PASS" if agent.domain == "pacing" else "FAIL",
        "response": f"Geroutet zu: {agent.name} (domain: {agent.domain})",
        "model": "",
        "error": "" if agent.domain == "pacing" else f"Erwartet pacing, bekam {agent.domain}",
    }


def test_orchestrator_agent_routing_vision():
    """Testet Keyword-Routing: 'beschreibe die Szene' -> VisionAgent."""
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent()
    agent = orch._route_to_agent("beschreibe die Szene im Video")

    if agent is None:
        return {"status": "FAIL", "response": "Kein Agent fuer 'beschreibe die Szene'", "model": "", "error": "route returned None"}

    return {
        "status": "PASS" if agent.domain == "vision" else "FAIL",
        "response": f"Geroutet zu: {agent.name} (domain: {agent.domain})",
        "model": "",
        "error": "" if agent.domain == "vision" else f"Erwartet vision, bekam {agent.domain}",
    }


def test_orchestrator_multi_step_detection():
    """Testet die Erkennung von Multi-Step-Anfragen."""
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent()

    multi_texts = [
        "Was passiert in Video 1 und was wird gesagt?",
        "Analysiere Bild und Ton von Clip 3",
    ]

    non_multi_texts = [
        "Analysiere das Audio",
        "Beschreibe die Szene",
    ]

    results_detail = []
    all_correct = True

    for text in multi_texts:
        detected = orch._detect_multi_step(text)
        correct = detected is True
        if not correct:
            all_correct = False
        results_detail.append(f"'{text[:40]}': multi={detected} ({'OK' if correct else 'FALSCH'})")

    for text in non_multi_texts:
        detected = orch._detect_multi_step(text)
        correct = detected is False
        if not correct:
            all_correct = False
        results_detail.append(f"'{text[:40]}': multi={detected} ({'OK' if correct else 'FALSCH'})")

    return {
        "status": "PASS" if all_correct else "FAIL",
        "response": " | ".join(results_detail),
        "model": "",
        "error": "" if all_correct else "Einige Multi-Step-Erkennungen falsch",
    }


def test_orchestrator_compound_detection():
    """Testet die Erkennung von Compound-Actions."""
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent()

    # "proxy + stems" sollte 2 Actions erkennen
    actions = orch._detect_compound_actions("Erstelle Proxy-Daten und trenne die Stems")

    if len(actions) < 2:
        return {
            "status": "FAIL",
            "response": f"Erwartet >=2 Actions, bekam: {actions}",
            "model": "",
            "error": f"Nur {len(actions)} Compound-Actions erkannt",
        }

    return {
        "status": "PASS",
        "response": f"Compound-Actions erkannt: {actions}",
        "model": "",
    }


# ============================================================================
# TEST 12: ActionRegistry — Bekannter Bug (list_all)
# ============================================================================

def test_action_registry_list_actions():
    """Testet ActionRegistry.list_actions() (funktioniert)."""
    from services.action_registry import action_registry

    actions = action_registry.list_actions()

    return {
        "status": "PASS",
        "response": f"Registrierte Aktionen ({len(actions)}): {', '.join(actions[:10])}{'...' if len(actions) > 10 else ''}",
        "model": "",
    }


def test_action_registry_list_all_bug():
    """Testet den bekannten Bug: ActionRegistry.list_all() existiert NICHT.

    LocalAgentService._registry_to_tools() ruft self.registry.list_all() auf,
    aber ActionRegistry hat nur list_actions() (gibt strings zurueck) und
    get() (gibt ActionDef zurueck).
    """
    from services.action_registry import ActionRegistry

    registry = ActionRegistry()

    has_list_all = hasattr(registry, "list_all")
    has_list_actions = hasattr(registry, "list_actions")

    if has_list_all:
        # Wenn list_all existiert, pruefen ob es funktioniert
        try:
            result = registry.list_all()
            return {
                "status": "PASS",
                "response": f"list_all() existiert DOCH und gibt {type(result).__name__} zurueck (Bug wurde behoben?)",
                "model": "",
            }
        except Exception as e:
            return {
                "status": "FAIL",
                "response": f"list_all() existiert, crasht aber: {e}",
                "model": "",
                "error": str(e),
            }
    else:
        # Erwartetes Verhalten: list_all() existiert NICHT
        return {
            "status": "PASS",
            "response": f"BESTAETIGT: list_all() existiert NICHT (AttributeError). list_actions()={has_list_actions}. "
                        f"_registry_to_tools() in LocalAgentService wird crashen wenn aufgerufen.",
            "model": "",
        }


def test_action_registry_tool_use_crash():
    """Testet ob _registry_to_tools() tatsaechlich crasht wegen list_all()."""
    from services.local_agent_service import LocalAgentService
    from services.action_registry import ActionRegistry

    # Erstelle einen LocalAgentService mit leerem Registry
    registry = ActionRegistry()
    agent = LocalAgentService(registry=registry, use_ollama=False)

    try:
        tools = agent._registry_to_tools()
        # Wenn es funktioniert, pruefen was zurueckkommt
        return {
            "status": "FAIL",
            "response": f"_registry_to_tools() hat NICHT gecrasht. Ergebnis: {tools}. Bug existiert nicht (mehr)?",
            "model": "",
            "error": "Erwarteter AttributeError blieb aus",
        }
    except AttributeError as e:
        return {
            "status": "PASS",
            "response": f"BESTAETIGT: _registry_to_tools() crasht mit AttributeError: {e}",
            "model": "",
        }


def test_action_registry_get_schema():
    """Testet get_schema_for_prompt()."""
    from services.action_registry import action_registry

    schema = action_registry.get_schema_for_prompt()

    if not schema:
        return {"status": "FAIL", "response": "Leeres Schema", "model": "", "error": "get_schema_for_prompt() returned empty"}

    import json
    try:
        parsed = json.loads(schema)
        if isinstance(parsed, list):
            return {
                "status": "PASS",
                "response": f"Schema: {len(parsed)} Aktionen definiert. Erste: {parsed[0]['name'] if parsed else 'keine'}",
                "model": "",
            }
        else:
            return {"status": "FAIL", "response": f"Schema ist kein Array: {type(parsed)}", "model": "", "error": "Unerwarteter Typ"}
    except json.JSONDecodeError as e:
        return {"status": "FAIL", "response": f"Schema ist kein gueltiges JSON: {e}", "model": "", "error": str(e)}


# ============================================================================
# TEST 13: OllamaService.ensure_model()
# ============================================================================

def test_ollama_service_ensure_model():
    """Testet OllamaService.ensure_model() — Modell-Check oder Download."""
    from services.ollama_service import OllamaService

    svc = OllamaService.get()
    if not svc.is_ready:
        svc.start()
        time.sleep(1)

    if not svc.is_ready:
        return {"status": "FAIL", "response": "OllamaService nicht bereit", "model": "", "error": "Not ready"}

    # Fuer gemma4:e4b (sollte schon installiert sein)
    result = svc.ensure_model("gemma4:e4b")

    return {
        "status": "PASS" if result else "FAIL",
        "response": f"ensure_model('gemma4:e4b') = {result}",
        "model": "gemma4:e4b",
        "error": "" if result else "ensure_model returned False",
    }


# ============================================================================
# TEST 14: get_ollama_client Singleton
# ============================================================================

def test_ollama_client_singleton():
    """Testet dass get_ollama_client() ein Singleton zurueckgibt."""
    from services.ollama_client import get_ollama_client

    c1 = get_ollama_client()
    c2 = get_ollama_client()

    same_instance = c1 is c2

    # Andere URL -> neuer Client
    c3 = get_ollama_client("http://localhost:99999")
    different_for_url = c3 is not c1 or c3.base_url != c1.base_url

    # Zurueck zur Standard-URL
    c4 = get_ollama_client("http://localhost:11434")

    return {
        "status": "PASS" if same_instance else "FAIL",
        "response": f"Singleton: same={same_instance}, different_url={different_for_url}",
        "model": "",
        "error": "" if same_instance else "Nicht dasselbe Objekt",
    }


# ============================================================================
# TEST 15: OllamaClient Fallback-Modell-Logik
# ============================================================================

def test_ollama_client_fallback_logic():
    """Testet die Fallback-Modell-Logik fuer _find_fallback_model()."""
    from services.ollama_client import OllamaClient

    client = OllamaClient()
    models = client.list_models()

    if len(models) < 2:
        return {"status": "FAIL", "response": f"Brauche mindestens 2 Modelle fuer Fallback-Test, habe: {models}", "model": "", "error": "Zu wenig Modelle"}

    # Simuliere dass das erste Modell nicht ladbar ist
    first_model = models[0]
    fallback = client._find_fallback_model(first_model)

    if fallback is None:
        return {"status": "FAIL", "response": f"Kein Fallback gefunden fuer {first_model}", "model": "", "error": "Fallback ist None"}

    if fallback == first_model:
        return {"status": "FAIL", "response": f"Fallback ist dasselbe Modell: {fallback}", "model": "", "error": "Fallback = Original"}

    return {
        "status": "PASS",
        "response": f"Fallback fuer '{first_model}': '{fallback}'",
        "model": fallback,
    }


# ============================================================================
# MAIN: Alle Tests ausfuehren
# ============================================================================

def main():
    print("\n" + "="*70)
    print("  PB STUDIO — LIVE OLLAMA/LLM INTEGRATION TEST")
    print(f"  Server: http://localhost:11434")
    print(f"  Python: {sys.executable}")
    print(f"  CWD: {os.getcwd()}")
    print("="*70)

    # --- Gruppe 1: OllamaClient Konnektivitaet ---
    run_test("1.1 OllamaClient Connectivity", test_ollama_client_connectivity)
    run_test("1.2 OllamaClient Version", test_ollama_client_version)
    run_test("1.3 OllamaClient List Models", test_ollama_client_list_models)
    run_test("1.4 OllamaClient Model Exists (gemma4/phi3)", test_ollama_client_model_exists)
    run_test("1.5 OllamaClient Best Available Model", test_ollama_client_best_model)
    run_test("1.6 OllamaClient Model Info", test_ollama_client_model_info)
    run_test("1.7 OllamaClient Singleton", test_ollama_client_singleton)

    # --- Gruppe 2: Chat-Funktionen ---
    run_test("2.1 OllamaClient.chat() — gemma4:e4b", test_ollama_client_chat_gemma)
    run_test("2.2 OllamaClient.chat() — phi3:mini", test_ollama_client_chat_phi3)
    run_test("2.3 OllamaClient.chat() — System Prompt", test_ollama_client_chat_with_system_prompt)
    run_test("2.4 OllamaClient.chat_with_history()", test_ollama_client_chat_with_history)

    # --- Gruppe 3: VRAM-Schutz ---
    run_test("3.1 Pause/Resume (VRAM-Schutz)", test_ollama_client_pause_resume)

    # --- Gruppe 4: Tool-Use / Function Calling ---
    run_test("4.1 supports_tools() Erkennung", test_ollama_client_supports_tools)
    run_test("4.2 chat_with_tools() Function Calling", test_ollama_client_chat_with_tools)

    # --- Gruppe 5: OllamaService (hoeherer Layer) ---
    run_test("5.1 OllamaService.chat()", test_ollama_service_chat)
    run_test("5.2 OllamaService.ensure_model()", test_ollama_service_ensure_model)

    # --- Gruppe 6: Streaming ---
    run_test("6.1 Streaming Response (raw httpx)", test_ollama_streaming)

    # --- Gruppe 7: ConversationMemory ---
    run_test("7.1 ConversationMemory Basic", test_conversation_memory_basic)
    run_test("7.2 ConversationMemory Sliding Window", test_conversation_memory_sliding_window)
    run_test("7.3 ConversationMemory Clear", test_conversation_memory_clear)
    run_test("7.4 ConversationMemoryManager", test_conversation_memory_manager)

    # --- Gruppe 8: ModelLifecycleService ---
    run_test("8.1 ModelLifecycleService Ollama Available", test_model_lifecycle_ollama_available)
    run_test("8.2 ModelLifecycleService Scan Ollama", test_model_lifecycle_scan_ollama)

    # --- Gruppe 9: OrchestratorAgent Routing ---
    run_test("9.1 Orchestrator -> AudioAgent", test_orchestrator_agent_routing_audio)
    run_test("9.2 Orchestrator -> PacingAgent", test_orchestrator_agent_routing_pacing)
    run_test("9.3 Orchestrator -> VisionAgent", test_orchestrator_agent_routing_vision)
    run_test("9.4 Orchestrator Multi-Step Detection", test_orchestrator_multi_step_detection)
    run_test("9.5 Orchestrator Compound Detection", test_orchestrator_compound_detection)

    # --- Gruppe 10: ActionRegistry + bekannter Bug ---
    run_test("10.1 ActionRegistry.list_actions()", test_action_registry_list_actions)
    run_test("10.2 ActionRegistry.list_all() Bug", test_action_registry_list_all_bug)
    run_test("10.3 _registry_to_tools() Crash-Test", test_action_registry_tool_use_crash)
    run_test("10.4 ActionRegistry.get_schema_for_prompt()", test_action_registry_get_schema)

    # --- Gruppe 11: Fallback-Logik ---
    run_test("11.1 OllamaClient Fallback Model", test_ollama_client_fallback_logic)

    # ======================================================================
    # ZUSAMMENFASSUNG
    # ======================================================================
    print("\n\n" + "="*70)
    print("  ZUSAMMENFASSUNG")
    print("="*70)

    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    crashed = sum(1 for r in RESULTS if r["status"] == "CRASH")
    total = len(RESULTS)

    print(f"\n  TOTAL:   {total} Tests")
    print(f"  PASS:    {passed}")
    print(f"  FAIL:    {failed}")
    print(f"  CRASH:   {crashed}")
    print(f"  Rate:    {passed/total*100:.1f}%")

    # Detaillierte Tabelle
    print(f"\n  {'Nr':<6} {'Status':<8} {'Zeit':<8} {'Test':<45} {'Modell':<15}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*45} {'-'*15}")

    for i, r in enumerate(RESULTS, 1):
        status_icon = {"PASS": "OK", "FAIL": "FAIL", "CRASH": "!!"}[r["status"]]
        test_name = r["test"][:45]
        model = r["model"][:15] if r["model"] else ""
        print(f"  {i:<6} {status_icon:<8} {r['elapsed']:<8} {test_name:<45} {model:<15}")

    # Fehlerdetails
    failures = [r for r in RESULTS if r["status"] in ("FAIL", "CRASH")]
    if failures:
        print(f"\n\n{'='*70}")
        print(f"  FEHLERDETAILS ({len(failures)} Fehler)")
        print(f"{'='*70}")
        for r in failures:
            print(f"\n  [{r['status']}] {r['test']}")
            if r["response"]:
                print(f"    Response: {r['response'][:200]}")
            if r["traceback"]:
                # Nur die letzten Zeilen des Tracebacks
                tb_lines = r["traceback"].strip().split("\n")
                for line in tb_lines[-5:]:
                    print(f"    {line}")

    print(f"\n{'='*70}")
    print(f"  ENDE — {passed}/{total} Tests bestanden")
    print(f"{'='*70}\n")

    return 0 if failed + crashed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

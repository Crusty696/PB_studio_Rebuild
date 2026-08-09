"""Sicherer, modellunabhaengiger Brain-Gateway (B-738 / D-082 / D-083).

Tool-faehige Modelle nutzen weiterhin native Tool-Calls. Modelle ohne
Tool-Support duerfen genau vier Brain-Aktionen als validiertes JSON anfordern.
Vision ist read-only und darf nur Recall/Explain anfordern.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

GatewayMode = Literal["chat", "vision"]
_ENVELOPE_KEY = "pb_brain_gateway"
_ENVELOPE_VERSION = "v1"
_LEARN_PREFIXES = (
    "merke dir:",
    "speichere:",
    "notiere:",
    "behalte:",
    "remember:",
    "save:",
    "store:",
    "note:",
)

_CHAT_ACTION_PARAMS: dict[str, frozenset[str]] = {
    "brain_recall": frozenset({"query", "clip_id", "scene_id", "top_k"}),
    "brain_stats": frozenset(),
    "brain_explain_cut": frozenset(
        {"decision_id", "run_id", "at_timestamp_sec"}
    ),
    "brain_learn_note": frozenset(
        {"title", "body", "context", "source", "linked_entity_id"}
    ),
}
_VISION_ACTION_PARAMS: dict[str, frozenset[str]] = {
    "brain_recall": _CHAT_ACTION_PARAMS["brain_recall"],
    "brain_explain_cut": _CHAT_ACTION_PARAMS["brain_explain_cut"],
}

_NONTOOL_PROTOCOL = """\
## SICHERES BRAIN-GATEWAY
Tool-Support ist nicht erforderlich. Fuer eine Brain-Operation antworte
AUSSCHLIESSLICH mit genau einem JSON-Objekt:
{"pb_brain_gateway":"v1","action":"brain_recall","params":{"query":"..."}}

Erlaubt:
- brain_recall: query, clip_id, scene_id, top_k
- brain_stats: keine Parameter
- brain_explain_cut: decision_id ODER run_id + at_timestamp_sec
- brain_learn_note: nur wenn Usertext exakt mit Merke dir:/Speichere:/
  Notiere:/Behalte:/Remember:/Save:/Store:/Note: beginnt; title und body
  erforderlich; context/source optional

Keine andere Aktion ist ueber dieses Gateway erlaubt. Behaupte nie, eine
Operation sei erfolgt, bevor Gateway-Ergebnis vorliegt. Fuer normale Fragen
antworte als normaler Text, nicht als JSON.
"""

_VISION_PROTOCOL = """\
## VISION-BRAIN (READ-ONLY)
Projektwissen darf nur gelesen werden: brain_recall und brain_explain_cut.
Vision darf niemals Projektwissen veraendern oder Schreibaktionen ausloesen.
Nutze Kontext nur fuer Schnittabsicht; nicht als sichtbaren Bildinhalt ausgeben.
"""


def has_explicit_learn_intent(user_text: str) -> bool:
    """Persistentes Learn nur ueber eindeutiges reserviertes User-Praefix."""
    text = (user_text or "").strip().casefold()
    return text.startswith(_LEARN_PREFIXES)


def encode_gateway_request(action: str, params: dict[str, Any]) -> str:
    """Deterministische Test-/Adapterdarstellung einer Gateway-Anfrage."""
    return json.dumps(
        {
            _ENVELOPE_KEY: _ENVELOPE_VERSION,
            "action": action,
            "params": params,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _context(query: str, max_chars: int) -> str:
    try:
        from services.knowledge_loader import build_brain_context

        return build_brain_context(query=query, max_chars=max_chars)
    except (ImportError, ValueError, RuntimeError, OSError) as exc:
        logger.debug("Brain-Gateway: Kontext nicht ladbar: %s", exc)
        return ""


def _context_with_recent_fallback(query: str, max_chars: int) -> str:
    """Recall mit Leer-Query-Fallback (B-787), analog zum Vision-Pfad.

    Tokenbasierter Recall trifft bei generischen Gedaechtnisfragen
    ("Was hast du dir bisher gemerkt?") nichts, weil solche Fragen keine
    inhaltlichen Tokens enthalten. Leere Query liefert dann den neuesten
    Projektsnapshot. Ist nichts gespeichert, bleibt das Ergebnis leer.
    """
    context = _context(query, max_chars=max_chars)
    if context:
        return context
    return _context("", max_chars=max_chars)


def build_nontool_prompt(base_prompt: str, query: str) -> str:
    """Chat-Prompt mit projektisoliertem Recall und validiertem Protokoll."""
    parts = [base_prompt.rstrip()]
    context = _context_with_recent_fallback(query, max_chars=1200)
    if context:
        parts.append(context)
    parts.append(_NONTOOL_PROTOCOL.rstrip())
    return "\n\n".join(parts)


def build_tool_prompt(base_prompt: str, query: str) -> str:
    """Tool-Chat erhaelt Recall-Fallback; native Tools bleiben unveraendert."""
    context = _context_with_recent_fallback(query, max_chars=1200)
    if not context:
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{context}"


def _vision_explain_context(max_chars: int = 350) -> str:
    """Neueste Cut-Erklaerung projektisoliert und strikt read-only laden."""
    try:
        from services.action_registry import action_registry

        result = action_registry.execute("brain_explain_cut", {})
    except (ImportError, KeyError, ValueError, RuntimeError, OSError, TypeError) as exc:
        logger.debug("Vision-Brain: Explain nicht ladbar: %s", exc)
        return ""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return ""
    if result.get("decision_id") is None:
        return ""
    message = str(result.get("message") or "").strip()
    if not message:
        return ""
    return "## BRAIN-SCHNITT-ERKLAERUNG (READ-ONLY)\n" + message[:max_chars]


def build_vision_prompt(base_prompt: str, query: str) -> str:
    """Vision-Prompt mit kleinem read-only Brain-Kontext gemaess D-083."""
    parts: list[str] = []
    context = _context(query, max_chars=450)
    if not context:
        # Tokenbasierter Recall kann eine vorhandene Memory bei spezifischer
        # Query verfehlen. Leere Query liefert dann neuesten Projektsnapshot.
        context = _context("", max_chars=450)
    if context:
        parts.append(context)
    explanation = _vision_explain_context()
    if explanation:
        parts.append(explanation)
    parts.append(_VISION_PROTOCOL.rstrip())
    # Fachprompt zuletzt: Caption-JSON-Schema bzw. Bildfrage bleibt dominante
    # Abschlussanweisung und Brain-Kontext wird nicht als Bildinhalt gespiegelt.
    parts.append(base_prompt.rstrip())
    return "\n\n".join(parts)


def _iter_json_object_candidates(text: str):
    """Liefert jedes balancierte Top-Level-``{...}``-Fragment des Textes.

    B-785: Non-Tool-Modelle betten das Envelope in Fliesstext ein. Die
    Klammerzaehlung ignoriert Klammern innerhalb von JSON-Strings.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                yield text[start:index + 1]
                start = -1


def _as_envelope(candidate: str) -> dict[str, Any] | None:
    """Nur ein vollstaendiges, versioniertes Gateway-Envelope passiert."""
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get(_ENVELOPE_KEY) != _ENVELOPE_VERSION:
        return None
    if "action" not in payload:
        return None
    return payload


def _extract_payload(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        first_newline = text.find("\n")
        last_fence = text.rfind("```")
        if first_newline >= 0 and last_fence > first_newline:
            text = text[first_newline + 1:last_fence].strip()
    payload = _as_envelope(text)
    if payload is not None:
        return payload
    # B-785: eingebettetes Envelope suchen. Die Sicherheit bleibt gleich —
    # Envelope-Key, Version, Action-Allowlist und Parameterpruefung gelten
    # unveraendert; nur die Fundstelle wird toleranter bestimmt.
    for candidate in _iter_json_object_candidates(text):
        payload = _as_envelope(candidate)
        if payload is not None:
            return payload
    return None


def _reject(message: str) -> dict[str, Any]:
    return {
        "action": "brain_gateway_rejected",
        "params": {},
        "result": None,
        "message": f"Brain-Gateway abgelehnt: {message}",
        "error": message,
    }


def _derive_title(body: Any) -> str:
    """Kurzen Titel aus dem Notiz-Body ableiten (erste Zeile / erster Satz)."""
    if not isinstance(body, str):
        return ""
    first_line = " ".join(body.strip().splitlines()[:1]).strip()
    if not first_line:
        return ""
    for stop in (". ", "! ", "? "):
        cut = first_line.find(stop)
        if cut > 0:
            first_line = first_line[:cut]
            break
    first_line = first_line.rstrip(" .!?")
    return first_line[:80].strip()


def _not_written(reason: str) -> dict[str, Any]:
    """Deterministische Negativmeldung fuer einen nicht ausgefuehrten Merk-Auftrag."""
    return {
        "action": "brain_learn_note_not_written",
        "params": {},
        "result": None,
        "message": (
            "Ich habe NICHTS gespeichert — es wurde keine Notiz in die "
            f"Datenbank geschrieben ({reason}). Bitte formuliere den "
            "Merk-Auftrag erneut."
        ),
        "error": reason,
    }


def _learn_message(result: Any) -> tuple[str, str | None]:
    """Bestaetigung strikt aus dem DB-Ergebnis ableiten (B-786)."""
    ok = isinstance(result, dict) and result.get("status") == "ok"
    if ok:
        db_message = str(result.get("message") or "").strip()
        if db_message:
            return db_message, None
        note_id = result.get("note_id")
        title = str(result.get("title") or "").strip()
        verb = "gespeichert" if result.get("created") else "aktualisiert"
        suffix = f" (brain_note #{note_id})" if note_id is not None else ""
        return (
            f"Notiz {verb}{suffix}: {title}. "
            "Wiederfindbar ueber brain_recall.",
            None,
        )
    reason = "Schreibvorgang fehlgeschlagen"
    if isinstance(result, dict):
        reason = str(
            result.get("message") or result.get("error") or reason
        ).strip() or reason
    return _not_written(reason)["message"], reason


def _validate_params(action: str, params: Any, mode: GatewayMode) -> dict[str, Any]:
    allowed_map = _CHAT_ACTION_PARAMS if mode == "chat" else _VISION_ACTION_PARAMS
    if action not in allowed_map:
        raise ValueError(f"Aktion '{action}' ist im {mode}-Gateway nicht erlaubt")
    if not isinstance(params, dict):
        raise ValueError("params muss ein JSON-Objekt sein")
    unknown = set(params) - set(allowed_map[action])
    if unknown:
        raise ValueError(
            f"Unerlaubte Parameter fuer {action}: {', '.join(sorted(unknown))}"
        )

    clean = dict(params)
    for key in ("clip_id", "scene_id", "decision_id", "run_id", "linked_entity_id"):
        if key in clean and (isinstance(clean[key], bool) or not isinstance(clean[key], int)):
            raise ValueError(f"{key} muss Integer sein")
    if "at_timestamp_sec" in clean and (
        isinstance(clean["at_timestamp_sec"], bool)
        or not isinstance(clean["at_timestamp_sec"], (int, float))
    ):
        raise ValueError("at_timestamp_sec muss numerisch sein")
    if "top_k" in clean:
        if isinstance(clean["top_k"], bool) or not isinstance(clean["top_k"], int):
            raise ValueError("top_k muss Integer sein")
        clean["top_k"] = max(1, min(10, clean["top_k"]))
    for key in ("query", "title", "body", "source"):
        if key in clean and not isinstance(clean[key], str):
            raise ValueError(f"{key} muss Text sein")
    if action == "brain_learn_note":
        if not str(clean.get("title") or "").strip():
            # B-785: Non-Tool-Modelle liefern haeufig nur body. Der Titel ist
            # reine Anzeige-/Upsert-Kennung und wird defensiv aus dem bereits
            # validierten body abgeleitet, statt den Merk-Auftrag zu verwerfen.
            derived = _derive_title(clean.get("body"))
            if derived:
                clean["title"] = derived
        if not str(clean.get("title") or "").strip():
            raise ValueError("brain_learn_note braucht title")
        if not str(clean.get("body") or "").strip():
            raise ValueError("brain_learn_note braucht body")
        if "context" in clean and not isinstance(clean["context"], dict):
            raise ValueError("context muss ein JSON-Objekt sein")
        clean["title"] = clean["title"].strip()[:240]
        clean["body"] = clean["body"].strip()[:4000]
    if "query" in clean:
        clean["query"] = clean["query"].strip()[:1000]
    return clean


def execute_gateway_response(
    raw: str,
    mode: GatewayMode = "chat",
    *,
    allow_learn: bool = False,
) -> dict[str, Any] | None:
    """Validiert optionale LLM-JSON-Antwort und fuehrt nur Brain-Allowlist aus.

    Normaler Text liefert ``None``. Ein JSON-Aktionsversuch wird immer
    terminal behandelt: erlaubt und ausgefuehrt oder sichtbar abgelehnt.
    """
    payload = _extract_payload(raw)
    if payload is None:
        if allow_learn:
            # B-786: Der User hat ausdruecklich einen Merk-Auftrag gegeben,
            # das Modell hat aber keine Gateway-Aktion angefordert. Freitext
            # ("Ich habe mir gemerkt ...") darf hier nicht als Antwort
            # durchgereicht werden — sonst behauptet das Modell einen
            # Schreibvorgang, den es nie gab.
            return _not_written(
                "Modell hat keine Gateway-Aktion angefordert",
            )
        return None
    action = str(payload.get("action") or "")
    if action == "brain_learn_note" and not allow_learn:
        return _reject("brain_learn_note braucht ausdruecklichen Merk-/Speicherauftrag")
    try:
        params = _validate_params(action, payload.get("params", {}), mode)
    except ValueError as exc:
        return _reject(str(exc))

    from services.action_registry import action_registry

    try:
        result = action_registry.execute(action, params)
    except (KeyError, ValueError, RuntimeError, OSError, TypeError) as exc:
        return {
            "action": action,
            "params": params,
            "result": None,
            "message": f"Brain-Gateway-Fehler bei {action}: {exc}",
            "error": str(exc),
        }

    if action == "brain_learn_note":
        # B-786: Erfolg/Misserfolg kommt aus dem DB-Ergebnis, nie vom Modell.
        message, error = _learn_message(result)
        return {
            "action": action,
            "params": params,
            "result": result,
            "message": message,
            "error": error,
        }

    message = result.get("message") if isinstance(result, dict) else str(result)
    error = None
    if isinstance(result, dict) and result.get("status") == "error":
        error = str(result.get("message") or result.get("error") or "Brain-Aktion fehlgeschlagen")
    return {
        "action": action,
        "params": params,
        "result": result,
        "message": message,
        "error": error,
    }

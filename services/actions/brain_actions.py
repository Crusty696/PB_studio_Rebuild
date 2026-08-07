"""Brain-Lese-/Schreib-Actions: macht das gelernte Wissen der App fuer
JEDES Modell ueber das Action-Registry abrufbar.

Vier Actions:
  - ``brain_recall``      — Suche in gespeicherten Erkenntnissen/Entscheidungen
  - ``brain_stats``       — was hat die App bisher gelernt (inkl. Luecken)
  - ``brain_explain_cut`` — warum wurde an dieser Stelle dieser Clip gewaehlt
  - ``brain_learn_note``  — Modell/App legt selbst eine Erkenntnis ab

Alle vier laufen rein synchron ueber Service-/DB-Zugriff — KEIN Qt, KEIN
TaskManager, KEIN Worker-Spawn. Damit sind sie headless nutzbar
(``action_registry.execute("brain_stats", {})`` genuegt) und brauchen
keinen Eintrag in ``workers/registry.py``.

Datenquellen (alles bereits vorhanden, nichts neu erfunden):
  - ``mem_pacing_run`` / ``mem_decision`` / ``mem_user_feedback_event``
    ueber ``services.brain.legacy_sqlite.BrainService`` (der lebende
    Read-Aggregator, der auch die Studio-Brain-Tabs speist).
  - ``mem_learned_pattern`` (PatternAggregator-Output, Konsument ist
    ``services.pacing.pattern_lookup.LearnedPatternLookup``).
  - ``brain_note`` (Alembic-Revision c3d4e5f6a7b8) als Ablage fuer
    frei formulierte Erkenntnisse — KEINE neue Migration noetig.
  - ``services.brain.weight_store.WeightStore`` (Beta-Bernoulli-Gewichte
    ueber die Brain-Bridge-Achsen) — nur lesend.
  - ``services.vector_db_service.VectorDBService`` (SigLIP-Clip-Embeddings,
    1152d, Cosine) — nur Vektor-zu-Vektor, es wird KEIN Modell geladen.

Ehrlichkeits-Vertrag: leere Quelle -> ``"noch keine Daten"`` plus die
Angabe WELCHE Quelle leer ist. Niemals Platzhalterwerte.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
from typing import Any, Callable, Optional

from sqlalchemy import text

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Pattern-Kinds, die der PacingScorer ueber ``pattern_lookup`` abfragt.
# Nur ``context_preference`` wird vom PatternAggregator geschrieben — die
# drei String-Kinds haben (noch) keine Datenbasis und liefern im Scorer
# ehrlich Wilson-neutral 0.5 (siehe services/pacing/pattern_lookup.py
# Modul-Docstring). ``brain_stats`` meldet sie als ``no_signal_kinds``.
KNOWN_PATTERN_KINDS: tuple[str, ...] = (
    "context_preference",
    "genre",
    "key",
    "spectral",
)

# Ab wieviel Wilson-Confidence ein gelerntes Pattern als "konfident" gilt.
# Rein fuer die Stats-Aufbereitung — beeinflusst kein Scoring.
PATTERN_CONFIDENCE_THRESHOLD = 0.6

# Quelle-Default fuer selbst abgelegte Erkenntnisse. ``brain_note`` hat
# UNIQUE(title, source), d.h. (Titel, Quelle) ist der Upsert-Schluessel.
DEFAULT_NOTE_SOURCE = "agent"

# Stoppwoerter fuer das Token-Matching in ``brain_recall``. Bewusst klein
# gehalten (DE + EN), das Ranking ist eine Token-Ueberlappung, keine
# Embedding-Suche.
_STOPWORDS: frozenset[str] = frozenset({
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "und", "oder", "aber", "ist", "sind", "war", "waren", "wie", "was", "wer",
    "wo", "wann", "warum", "welche", "welcher", "welches", "fuer", "für",
    "von", "mit", "bei", "auf", "aus", "zum", "zur", "im", "in", "an", "am",
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "how", "what",
    "why", "which", "for", "of", "with", "at", "on", "in", "to", "from",
    "ich", "du", "wir", "sie", "es", "man", "sich", "nicht", "kein", "keine",
})


# ---------------------------------------------------------------------------
# Session-/DB-Helfer
# ---------------------------------------------------------------------------

def _session_factory() -> Callable[[], Any]:
    """Liefert eine Session-Fabrik auf der AKTUELLEN Projekt-Engine.

    ``database.session.engine`` wird zur Aufrufzeit gelesen (nicht beim
    Import), damit Projektwechsel (``set_project``) und Test-Monkeypatches
    greifen. Rueckgabe erfuellt den ``BrainService``-Vertrag.
    """
    from sqlalchemy.orm import Session as SASession
    import database.session as _dbs

    return lambda: SASession(_dbs.engine)


def _brain_service():
    """Frische ``BrainService``-Instanz (eigene lru_caches, keine Stale-Reads)."""
    from services.brain.legacy_sqlite import BrainService

    return BrainService(_session_factory())


def _table_exists(session: Any, name: str) -> bool:
    """True wenn die Tabelle in der aktuellen SQLite-DB existiert.

    Die ``mem_*``/``brain_*``-Tabellen entstehen ausschliesslich per Alembic,
    NICHT per ``Base.metadata.create_all``. Eine frisch angelegte Projekt-DB
    ohne Migrations-Lauf hat sie also nicht — das ist ein legitimer Zustand
    und darf keinen Traceback erzeugen, sondern ein ehrliches "leer".
    """
    row = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :n"),
        {"n": name},
    ).first()
    return row is not None


def _scalar(session: Any, sql: str, params: Optional[dict] = None) -> Any:
    return session.execute(text(sql), params or {}).scalar()


def _tokens(value: str) -> set[str]:
    """Kleingeschriebene Wort-Tokens ohne Stoppwoerter, min. 3 Zeichen."""
    raw = re.findall(r"[\wÀ-ɏ]+", (value or "").lower())
    return {t for t in raw if len(t) >= 3 and t not in _STOPWORDS}


def _match_score(query_tokens: set[str], haystack: str) -> float:
    """Token-Ueberlappung query -> haystack, normalisiert auf 0..1.

    Bewusst simpel und deterministisch. Volltext-Substring-Treffer werden
    zusaetzlich belohnt, damit exakte Begriffe vorne landen.
    """
    if not query_tokens:
        return 0.0
    hay = (haystack or "").lower()
    hay_tokens = _tokens(hay)
    if not hay_tokens:
        return 0.0
    hits = query_tokens & hay_tokens
    score = len(hits) / len(query_tokens)
    # Substring-Bonus fuer mehrteilige Begriffe ("style bucket", "dark psy")
    for tok in query_tokens:
        if tok not in hits and tok in hay:
            score += 0.25 / len(query_tokens)
    return min(1.0, score)


def _fmt_time(secs: Optional[float]) -> str:
    if secs is None:
        return "?"
    total = int(secs)
    hours, rem = divmod(total, 3600)
    mins, sec = divmod(rem, 60)
    return f"{hours:d}h{mins:02d}m{sec:02d}s" if hours else f"{mins:02d}:{sec:02d}"


# ---------------------------------------------------------------------------
# 1. brain_recall — Suche in gespeicherten Erkenntnissen/Entscheidungen
# ---------------------------------------------------------------------------

@action_registry.register(
    name="brain_recall",
    description=(
        "Durchsucht das Gedaechtnis von PB Studio: selbst abgelegte "
        "Erkenntnisse (brain_note), gelernte Muster (mem_learned_pattern) "
        "und getroffene Schnitt-Entscheidungen (mem_decision). Optional "
        "zusaetzlich aehnliche Video-Szenen ueber die gespeicherten "
        "SigLIP-Embeddings (Vektor-Nachbarschaft, kein Modell-Load). "
        "Nutze diese Aktion bei 'Was weisst du ueber X?', 'Was haben wir "
        "gelernt?', 'Erinnerst du dich an ...', 'aehnliche Clips zu #12'."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Frage oder Suchbegriff, z.B. 'psytrance drop' oder "
                    "'welche Rolle funktioniert im Breakdown'."
                ),
            },
            "clip_id": {
                "type": "integer",
                "description": (
                    "Optional: VideoClip-ID. Liefert die Entscheidungs-Historie "
                    "zu diesem Clip plus visuell aehnliche Szenen aus der VectorDB."
                ),
            },
            "scene_id": {
                "type": "integer",
                "description": "Optional: Scene-ID fuer die Entscheidungs-Historie.",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximale Treffer pro Quelle (default: 5).",
            },
        },
        "required": [],
    },
)
def brain_recall(
    query: str = "",
    clip_id: Optional[int] = None,
    scene_id: Optional[int] = None,
    top_k: int = 5,
) -> dict:
    """Sucht in Notizen, gelernten Mustern, Entscheidungen und Embeddings."""
    action = "brain_recall"
    try:
        limit = max(1, int(top_k or 5))
        q_tokens = _tokens(query)
        results: list[dict[str, Any]] = []
        empty_sources: list[str] = []
        missing_tables: list[str] = []

        factory = _session_factory()
        session = factory()
        try:
            # -- a) brain_note: selbst abgelegte Erkenntnisse ----------------
            if not _table_exists(session, "brain_note"):
                missing_tables.append("brain_note")
            else:
                rows = session.execute(
                    text(
                        "SELECT id, title, body_md, source, linked_entity_id, "
                        "       created_at, updated_at "
                        "FROM brain_note ORDER BY updated_at DESC, id DESC "
                        "LIMIT 500"
                    )
                ).mappings().all()
                if not rows:
                    empty_sources.append("brain_note")
                for r in rows:
                    hay = f"{r['title']} {r['body_md']} {r['source']}"
                    score = _match_score(q_tokens, hay) if q_tokens else 1.0
                    if score <= 0.0:
                        continue
                    results.append({
                        "source": "brain_note",
                        "score": round(float(score), 4),
                        "note_id": int(r["id"]),
                        "title": r["title"],
                        "body": r["body_md"],
                        "note_source": r["source"],
                        "linked_entity_id": r["linked_entity_id"],
                        "updated_at": str(r["updated_at"]),
                    })

            # -- b) mem_learned_pattern: aggregierte Muster ------------------
            if not _table_exists(session, "mem_learned_pattern"):
                missing_tables.append("mem_learned_pattern")
            else:
                rows = session.execute(
                    text(
                        "SELECT id, pattern_type, context_fingerprint, target_ref, "
                        "       stat_accept_count, stat_reject_count, "
                        "       stat_sample_size, confidence, last_updated "
                        "FROM mem_learned_pattern "
                        "ORDER BY confidence DESC, last_updated DESC LIMIT 500"
                    )
                ).mappings().all()
                if not rows:
                    empty_sources.append("mem_learned_pattern")
                for r in rows:
                    hay = (
                        f"{r['pattern_type']} {r['context_fingerprint']} "
                        f"{r['target_ref']}"
                    )
                    score = _match_score(q_tokens, hay) if q_tokens else float(
                        r["confidence"] or 0.0
                    )
                    if score <= 0.0:
                        continue
                    results.append({
                        "source": "mem_learned_pattern",
                        "score": round(float(score), 4),
                        "pattern_id": int(r["id"]),
                        "pattern_type": r["pattern_type"],
                        "context_fingerprint": _json_or_raw(r["context_fingerprint"]),
                        "target_ref": _json_or_raw(r["target_ref"]),
                        "accepts": int(r["stat_accept_count"] or 0),
                        "rejects": int(r["stat_reject_count"] or 0),
                        "samples": int(r["stat_sample_size"] or 0),
                        "confidence": float(r["confidence"] or 0.0),
                    })

            # -- c) mem_decision: konkrete Schnitt-Entscheidungen ------------
            if not _table_exists(session, "mem_decision"):
                missing_tables.append("mem_decision")
            else:
                total_decisions = int(
                    _scalar(session, "SELECT COUNT(*) FROM mem_decision") or 0
                )
                if total_decisions == 0:
                    empty_sources.append("mem_decision")
                else:
                    results.extend(
                        _recall_decisions(
                            session, q_tokens, clip_id, scene_id, limit
                        )
                    )
        finally:
            _close(session)

        # -- d) VectorDB: visuell aehnliche Szenen (nur Vektor-Mathematik) --
        vector_note: Optional[str] = None
        if clip_id is not None or scene_id is not None:
            similar, vector_note = _similar_scenes(clip_id, scene_id, limit)
            results.extend(similar)
            if vector_note:
                empty_sources.append("vector_db")

        results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        trimmed = results[: limit * 4]

        if not trimmed:
            reasons: list[str] = []
            if missing_tables:
                reasons.append(
                    "Tabellen fehlen (DB ohne Alembic-Migration): "
                    + ", ".join(sorted(set(missing_tables)))
                )
            if empty_sources:
                reasons.append(
                    "leere Quellen: " + ", ".join(sorted(set(empty_sources)))
                )
            if not reasons:
                reasons.append("keine Quelle passte zur Anfrage")
            return {
                "status": "ok",
                "action": action,
                "query": query,
                "clip_id": clip_id,
                "scene_id": scene_id,
                "result_count": 0,
                "results": [],
                "empty_sources": sorted(set(empty_sources)),
                "missing_tables": sorted(set(missing_tables)),
                "message": (
                    "Noch keine Daten im Brain zu dieser Anfrage — "
                    + "; ".join(reasons)
                    + ". Erkenntnisse lassen sich mit `brain_learn_note` ablegen."
                ),
            }

        lines = [f"Brain-Recall ({len(trimmed)} Treffer)"]
        if query:
            lines[0] += f' zu "{query}"'
        lines.append("=" * min(len(lines[0]), 70))
        for item in trimmed:
            lines.append(_render_recall_item(item))
        if empty_sources:
            lines.append(
                "Hinweis — leere Quellen: " + ", ".join(sorted(set(empty_sources)))
            )
        if missing_tables:
            lines.append(
                "Hinweis — fehlende Tabellen: "
                + ", ".join(sorted(set(missing_tables)))
            )

        return {
            "status": "ok",
            "action": action,
            "query": query,
            "clip_id": clip_id,
            "scene_id": scene_id,
            "result_count": len(trimmed),
            "results": trimmed,
            "empty_sources": sorted(set(empty_sources)),
            "missing_tables": sorted(set(missing_tables)),
            "message": "\n".join(lines),
        }
    except Exception as exc:  # broad catch intentional — DB/VectorDB/JSON errors
        _logger.error("%s fehlgeschlagen: %s", action, exc, exc_info=True)
        return {"status": "error", "action": action, "message": str(exc)}


def _json_or_raw(raw: Any) -> Any:
    """JSON-Spalten kommen je nach Treiber als str oder bereits geparst."""
    if raw is None or isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _close(session: Any) -> None:
    try:
        close = getattr(session, "close", None)
        if callable(close):
            close()
    except Exception:  # best-effort cleanup
        pass


def _recall_decisions(
    session: Any,
    q_tokens: set[str],
    clip_id: Optional[int],
    scene_id: Optional[int],
    limit: int,
) -> list[dict[str, Any]]:
    """Entscheidungs-Treffer: gezielt per scene_id/clip_id, sonst per Text."""
    sql = (
        "SELECT d.id, d.run_id, d.sequence_idx, d.at_timestamp_sec, "
        "       d.at_genre, d.at_sub_genre, d.at_section_type, d.at_bpm, "
        "       d.at_mood_audio, d.scene_id, d.clip_role, "
        "       d.clip_mood_refined, d.agent_score, d.user_verdict, "
        "       s.video_clip_id AS video_clip_id "
        "FROM mem_decision d "
        "LEFT JOIN scenes s ON s.id = d.scene_id "
    )
    params: dict[str, Any] = {"lim": limit}
    if scene_id is not None:
        sql += "WHERE d.scene_id = :sid ORDER BY d.id DESC LIMIT :lim"
        params["sid"] = int(scene_id)
    elif clip_id is not None:
        sql += "WHERE s.video_clip_id = :cid ORDER BY d.id DESC LIMIT :lim"
        params["cid"] = int(clip_id)
    else:
        # Text-Pfad: nur Zeilen mit Kontext-Text, sonst gibt es nichts zu matchen.
        sql += (
            "WHERE d.at_genre IS NOT NULL OR d.at_section_type IS NOT NULL "
            "OR d.clip_role IS NOT NULL OR d.clip_mood_refined IS NOT NULL "
            "ORDER BY d.id DESC LIMIT 800"
        )
        params.pop("lim")

    rows = session.execute(text(sql), params).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        hay = " ".join(
            str(r[k] or "")
            for k in (
                "at_genre", "at_sub_genre", "at_section_type",
                "at_mood_audio", "clip_role", "clip_mood_refined",
                "user_verdict",
            )
        )
        if scene_id is not None or clip_id is not None:
            score = 1.0 if not q_tokens else max(0.5, _match_score(q_tokens, hay))
        else:
            score = _match_score(q_tokens, hay)
            if score <= 0.0:
                continue
        out.append({
            "source": "mem_decision",
            "score": round(float(score), 4),
            "decision_id": int(r["id"]),
            "run_id": int(r["run_id"]),
            "at_timestamp_sec": float(r["at_timestamp_sec"] or 0.0),
            "at_genre": r["at_genre"],
            "at_section_type": r["at_section_type"],
            "at_bpm": float(r["at_bpm"]) if r["at_bpm"] is not None else None,
            "scene_id": int(r["scene_id"]) if r["scene_id"] is not None else None,
            "video_clip_id": (
                int(r["video_clip_id"]) if r["video_clip_id"] is not None else None
            ),
            "clip_role": r["clip_role"],
            "clip_mood_refined": r["clip_mood_refined"],
            "agent_score": float(r["agent_score"] or 0.0),
            "user_verdict": r["user_verdict"],
        })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out[:limit]


def _similar_scenes(
    clip_id: Optional[int],
    scene_id: Optional[int],
    limit: int,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Nachbarn eines gespeicherten Clip-Embeddings via VectorDB.

    Reine Vektor-zu-Vektor-Suche gegen bereits persistierte SigLIP-Vektoren —
    es wird KEIN Modell geladen und keine GPU angefasst. Gibt
    ``(treffer, hinweis_wenn_leer)`` zurueck.
    """
    target_clip = clip_id
    try:
        if target_clip is None and scene_id is not None:
            from sqlalchemy.orm import Session as SASession
            import database.session as _dbs

            with SASession(_dbs.engine) as s:
                row = s.execute(
                    text("SELECT video_clip_id FROM scenes WHERE id = :sid"),
                    {"sid": int(scene_id)},
                ).first()
            if row is None:
                return [], "vector_db: scene_id unbekannt"
            target_clip = int(row[0])

        if target_clip is None:
            return [], None

        from services.vector_db_service import VectorDBService

        vdb = VectorDBService()
        matrix, metadata = vdb.get_all_embeddings()
        if len(metadata) == 0:
            return [], "vector_db: keine Embeddings gespeichert"

        # F-043: composite_id = clip_id * 1_000_000 + scene_index
        idx = next(
            (
                i for i, m in enumerate(metadata)
                if int(m["id"]) // 1_000_000 == int(target_clip)
            ),
            None,
        )
        if idx is None:
            return [], f"vector_db: kein Embedding fuer Clip #{target_clip}"

        hits = vdb.search(matrix[idx], top_k=limit + 1)
        out: list[dict[str, Any]] = []
        for h in hits:
            if int(h.get("id", -1)) // 1_000_000 == int(target_clip):
                continue  # Selbsttreffer
            dist = h.get("_distance")
            out.append({
                "source": "vector_db",
                "score": round(float(1.0 - float(dist)), 4) if dist is not None else 0.0,
                "video_path": h.get("video_path"),
                "scene_index": h.get("scene_index"),
                "scene_start": h.get("scene_start"),
                "scene_end": h.get("scene_end"),
                "motion_score": h.get("motion_score"),
                "distance": dist,
            })
        return out[:limit], None
    except Exception as exc:  # broad catch — VectorDB darf recall nicht kippen
        _logger.warning("brain_recall: VectorDB-Nachbarsuche fehlgeschlagen: %s", exc)
        return [], f"vector_db: nicht verfuegbar ({exc})"


def _render_recall_item(item: dict[str, Any]) -> str:
    src = item.get("source")
    if src == "brain_note":
        body = (item.get("body") or "").replace("\n", " ")
        if len(body) > 220:
            body = body[:220] + "..."
        return (
            f"  [Notiz #{item['note_id']} | {item['note_source']} | "
            f"score={item['score']}] {item['title']}: {body}"
        )
    if src == "mem_learned_pattern":
        return (
            f"  [Muster #{item['pattern_id']} | {item['pattern_type']} | "
            f"score={item['score']}] fingerprint={item['context_fingerprint']} "
            f"target={item['target_ref']} "
            f"accept={item['accepts']}/{item['samples']} "
            f"conf={item['confidence']:.3f}"
        )
    if src == "mem_decision":
        return (
            f"  [Cut #{item['decision_id']} | run {item['run_id']} @ "
            f"{_fmt_time(item['at_timestamp_sec'])} | score={item['score']}] "
            f"genre={item['at_genre']} section={item['at_section_type']} "
            f"role={item['clip_role']} mood={item['clip_mood_refined']} "
            f"agent_score={item['agent_score']:.3f} "
            f"verdict={item['user_verdict'] or 'kein Verdikt'}"
        )
    if src == "vector_db":
        path = str(item.get("video_path") or "?")
        short = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        return (
            f"  [Aehnliche Szene | score={item['score']}] {short} "
            f"[{_fmt_time(item.get('scene_start'))}-"
            f"{_fmt_time(item.get('scene_end'))}]"
        )
    return f"  {item}"


# ---------------------------------------------------------------------------
# 2. brain_stats — was hat die App bisher gelernt (inkl. Luecken)
# ---------------------------------------------------------------------------

@action_registry.register(
    name="brain_stats",
    description=(
        "Zeigt, was PB Studio bisher gelernt hat: Anzahl Pacing-Runs und "
        "Schnitt-Entscheidungen, Verteilung des User-Feedbacks, konfidente "
        "gelernte Muster, Zustand der Brain-Bridge-Achsen-Gewichte und "
        "abgelegte Notizen. Meldet ausdruecklich die LUECKEN "
        "(no_signal_kinds / no_signal_axes), also wo noch kein Signal "
        "vorliegt. Nutze diese Aktion bei 'Was hast du gelernt?', "
        "'Brain-Status', 'Lernfortschritt', 'wie gut ist das Modell schon?'."
    ),
    param_schema={"type": "object", "properties": {}, "required": []},
)
def brain_stats() -> dict:
    """Aggregiert den Lernstand aus mem_*, brain_note und weights.db."""
    action = "brain_stats"
    try:
        result: dict[str, Any] = {"status": "ok", "action": action}
        no_signal_kinds: list[str] = []
        missing_tables: list[str] = []

        factory = _session_factory()
        session = factory()
        try:
            # -- Runs + Decisions ------------------------------------------
            if _table_exists(session, "mem_pacing_run"):
                result["run_count"] = int(
                    _scalar(session, "SELECT COUNT(*) FROM mem_pacing_run") or 0
                )
                result["rated_run_count"] = int(
                    _scalar(
                        session,
                        "SELECT COUNT(*) FROM mem_pacing_run "
                        "WHERE user_rating IS NOT NULL",
                    ) or 0
                )
            else:
                missing_tables.append("mem_pacing_run")
                result["run_count"] = 0
                result["rated_run_count"] = 0

            if _table_exists(session, "mem_decision"):
                result["decision_count"] = int(
                    _scalar(session, "SELECT COUNT(*) FROM mem_decision") or 0
                )
                verdicts = session.execute(
                    text(
                        "SELECT user_verdict, COUNT(*) AS n FROM mem_decision "
                        "GROUP BY user_verdict"
                    )
                ).all()
                result["verdict_distribution"] = {
                    (v[0] if v[0] is not None else "kein_verdikt"): int(v[1])
                    for v in verdicts
                }
                result["decisions_with_verdict"] = sum(
                    n for k, n in result["verdict_distribution"].items()
                    if k != "kein_verdikt"
                )
                result["distinct_genres"] = [
                    r[0] for r in session.execute(
                        text(
                            "SELECT DISTINCT at_genre FROM mem_decision "
                            "WHERE at_genre IS NOT NULL ORDER BY at_genre"
                        )
                    ).all()
                ]
                result["distinct_sections"] = [
                    r[0] for r in session.execute(
                        text(
                            "SELECT DISTINCT at_section_type FROM mem_decision "
                            "WHERE at_section_type IS NOT NULL "
                            "ORDER BY at_section_type"
                        )
                    ).all()
                ]
            else:
                missing_tables.append("mem_decision")
                result["decision_count"] = 0
                result["verdict_distribution"] = {}
                result["decisions_with_verdict"] = 0
                result["distinct_genres"] = []
                result["distinct_sections"] = []

            if _table_exists(session, "mem_user_feedback_event"):
                result["feedback_event_count"] = int(
                    _scalar(
                        session, "SELECT COUNT(*) FROM mem_user_feedback_event"
                    ) or 0
                )
            else:
                missing_tables.append("mem_user_feedback_event")
                result["feedback_event_count"] = 0

            # -- Gelernte Muster + no_signal_kinds -------------------------
            if _table_exists(session, "mem_learned_pattern"):
                result["pattern_count"] = int(
                    _scalar(session, "SELECT COUNT(*) FROM mem_learned_pattern") or 0
                )
                by_type = {
                    r[0]: int(r[1]) for r in session.execute(
                        text(
                            "SELECT pattern_type, COUNT(*) FROM mem_learned_pattern "
                            "GROUP BY pattern_type"
                        )
                    ).all()
                }
                result["patterns_by_type"] = by_type
                result["confident_pattern_count"] = int(
                    _scalar(
                        session,
                        "SELECT COUNT(*) FROM mem_learned_pattern "
                        "WHERE confidence >= :thr",
                        {"thr": PATTERN_CONFIDENCE_THRESHOLD},
                    ) or 0
                )
                no_signal_kinds = [
                    k for k in KNOWN_PATTERN_KINDS if by_type.get(k, 0) == 0
                ]
            else:
                missing_tables.append("mem_learned_pattern")
                result["pattern_count"] = 0
                result["patterns_by_type"] = {}
                result["confident_pattern_count"] = 0
                no_signal_kinds = list(KNOWN_PATTERN_KINDS)

            # -- Selbst abgelegte Erkenntnisse -----------------------------
            if _table_exists(session, "brain_note"):
                result["note_count"] = int(
                    _scalar(session, "SELECT COUNT(*) FROM brain_note") or 0
                )
                result["note_sources"] = {
                    r[0]: int(r[1]) for r in session.execute(
                        text(
                            "SELECT source, COUNT(*) FROM brain_note GROUP BY source"
                        )
                    ).all()
                }
            else:
                missing_tables.append("brain_note")
                result["note_count"] = 0
                result["note_sources"] = {}
        finally:
            _close(session)

        result["no_signal_kinds"] = no_signal_kinds
        result["missing_tables"] = sorted(set(missing_tables))

        # -- Bridge-Achsen-Gewichte (weights.db, read-only) ----------------
        result.update(_weights_summary())

        # -- Ehrliche Zusammenfassung --------------------------------------
        lines = ["Brain-Lernstand", "=" * 40]
        lines.append(
            f"Pacing-Runs: {result['run_count']} "
            f"({result['rated_run_count']} mit User-Rating)"
        )
        lines.append(
            f"Schnitt-Entscheidungen: {result['decision_count']} "
            f"({result['decisions_with_verdict']} mit Verdikt, "
            f"{result['feedback_event_count']} Feedback-Events)"
        )
        if result["verdict_distribution"]:
            lines.append(
                "Verdikt-Verteilung: "
                + ", ".join(
                    f"{k}={v}" for k, v in sorted(
                        result["verdict_distribution"].items()
                    )
                )
            )
        lines.append(
            f"Gelernte Muster: {result['pattern_count']} "
            f"(davon konfident >= {PATTERN_CONFIDENCE_THRESHOLD}: "
            f"{result['confident_pattern_count']})"
        )
        lines.append(f"Abgelegte Erkenntnisse (brain_note): {result['note_count']}")
        lines.append(
            f"Bridge-Achsen mit Signal: {result['axes_with_signal']}/"
            f"{result['total_axes']} "
            f"(konfident >= {result['min_confident_samples']} Samples: "
            f"{result['confident_axes']})"
        )

        gaps: list[str] = []
        if result["decision_count"] == 0:
            gaps.append("noch keine Schnitt-Entscheidungen aufgezeichnet")
        elif result["decisions_with_verdict"] == 0:
            gaps.append(
                "Entscheidungen vorhanden, aber KEIN einziges User-Verdikt — "
                "ohne Verdikte kann der Pattern-Aggregator nichts lernen"
            )
        if no_signal_kinds:
            gaps.append(
                "Pattern-Kinds ohne Datenbasis: " + ", ".join(no_signal_kinds)
            )
        if result["no_signal_axes"]:
            gaps.append(
                f"{len(result['no_signal_axes'])} von {result['total_axes']} "
                "Bridge-Achsen ohne jedes Signal"
            )
        if result["missing_tables"]:
            gaps.append(
                "Tabellen fehlen in dieser DB (keine Alembic-Migration): "
                + ", ".join(result["missing_tables"])
            )
        if result.get("weights_error"):
            gaps.append(f"weights.db nicht lesbar: {result['weights_error']}")

        if gaps:
            lines.append("")
            lines.append("LUECKEN (ehrlich):")
            for g in gaps:
                lines.append(f"  - {g}")
        else:
            lines.append("")
            lines.append("Keine offensichtlichen Luecken in den gelesenen Quellen.")

        result["gaps"] = gaps
        result["message"] = "\n".join(lines)
        return result
    except Exception as exc:  # broad catch intentional — DB + weights errors
        _logger.error("%s fehlgeschlagen: %s", action, exc, exc_info=True)
        return {"status": "error", "action": action, "message": str(exc)}


def _weights_summary() -> dict[str, Any]:
    """Liest weights.db read-only aus (Beta-Bernoulli-Gewichte, Brain-Achsen)."""
    from services.brain.cold_start import BRIDGE_AXES

    out: dict[str, Any] = {
        "total_axes": len(BRIDGE_AXES),
        "axes_with_signal": 0,
        "confident_axes": 0,
        "cold_start_axes": len(BRIDGE_AXES),
        "no_signal_axes": list(BRIDGE_AXES),
        "total_weight_clicks": 0.0,
        "top_positive_buckets": [],
        "min_confident_samples": 0,
        "weights_error": None,
    }
    store = None
    try:
        from services.brain import paths
        from services.brain.weight_store import WeightStore, MIN_CONFIDENT_SAMPLES

        out["min_confident_samples"] = MIN_CONFIDENT_SAMPLES
        weights_path = paths.weights_db_path(create_dir=False)
        if not weights_path.exists():
            # Kein Anlegen einer leeren weights.db als Seiteneffekt einer
            # reinen Diagnose-Abfrage — ehrlich "noch nicht vorhanden".
            out["weights_error"] = f"weights.db existiert noch nicht ({weights_path})"
            return out
        store = WeightStore(weights_path)
        conn = store._get_conn()  # noqa: SLF001 — read-only Diagnose, kein Write
        rows = conn.execute(
            "SELECT DISTINCT axis FROM axis_weights "
            "WHERE positive_count + negative_count > 0"
        ).fetchall()
        with_signal = {r[0] for r in rows} & set(BRIDGE_AXES)
        out["axes_with_signal"] = len(with_signal)
        out["no_signal_axes"] = sorted(set(BRIDGE_AXES) - with_signal)
        cold = store.cold_start_status()
        out["confident_axes"] = int(cold.get("confident_axes", 0))
        out["cold_start_axes"] = int(cold.get("cold_start_axes", len(BRIDGE_AXES)))
        out["total_weight_clicks"] = float(store.total_clicks())
        out["top_positive_buckets"] = store.top_buckets(n=5, by="positive")
    except Exception as exc:  # broad catch — weights.db darf stats nicht kippen
        _logger.warning("brain_stats: weights.db nicht lesbar: %s", exc)
        out["weights_error"] = str(exc)
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:  # best-effort
                pass
    return out


# ---------------------------------------------------------------------------
# 3. brain_explain_cut — warum wurde hier dieser Clip gewaehlt
# ---------------------------------------------------------------------------

@action_registry.register(
    name="brain_explain_cut",
    description=(
        "Erklaert eine einzelne Schnitt-Entscheidung: welcher Clip wurde "
        "warum gewaehlt, welche Score-Terme haben beigetragen, welche "
        "Alternativen waren knapp dahinter, und wie lautet das User-Verdikt. "
        "Quelle ist mem_decision (agent_rationale). Angabe entweder per "
        "decision_id oder per run_id + Zeitpunkt. "
        "Nutze diese Aktion bei 'Warum dieser Schnitt?', 'Erklaere Cut X', "
        "'Warum wurde der Clip gewaehlt?', 'Begruendung fuer den Schnitt'."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "decision_id": {
                "type": "integer",
                "description": "ID der Entscheidung (mem_decision.id).",
            },
            "run_id": {
                "type": "integer",
                "description": (
                    "Optional statt decision_id: Pacing-Run. Ohne Angabe wird "
                    "der neueste Run genommen."
                ),
            },
            "at_timestamp_sec": {
                "type": "number",
                "description": (
                    "Optional mit run_id: Zeitpunkt im Mix in Sekunden. Es wird "
                    "die zeitlich naechste Entscheidung erklaert."
                ),
            },
        },
        "required": [],
    },
)
def brain_explain_cut(
    decision_id: Optional[int] = None,
    run_id: Optional[int] = None,
    at_timestamp_sec: Optional[float] = None,
) -> dict:
    """Liefert Score-Beitraege, Alternativen und Verdikt zu einer Entscheidung."""
    action = "brain_explain_cut"
    try:
        factory = _session_factory()
        session = factory()
        try:
            if not _table_exists(session, "mem_decision"):
                return {
                    "status": "ok",
                    "action": action,
                    "decision_id": None,
                    "message": (
                        "Noch keine Daten: Tabelle 'mem_decision' existiert in "
                        "dieser Projekt-DB nicht (keine Alembic-Migration gelaufen)."
                    ),
                }

            resolved_id, resolve_note = _resolve_decision_id(
                session, decision_id, run_id, at_timestamp_sec
            )
            if resolved_id is None:
                return {
                    "status": "ok",
                    "action": action,
                    "decision_id": None,
                    "message": f"Noch keine Daten: {resolve_note}",
                }

            row = session.execute(
                text(
                    "SELECT d.id, d.run_id, d.sequence_idx, d.at_timestamp_sec, "
                    "       d.at_beat_idx, d.at_bpm, d.at_energy, "
                    "       d.at_section_type, d.at_key, d.at_mood_audio, "
                    "       d.at_genre, d.at_sub_genre, d.at_lufs, "
                    "       d.at_enricher_version, d.scene_id, d.clip_role, "
                    "       d.clip_mood_refined, d.clip_style_bucket_id, "
                    "       d.clip_motion_score, d.agent_score, "
                    "       d.user_verdict, d.user_verdict_at, d.user_rating, "
                    "       s.video_clip_id AS video_clip_id, "
                    "       v.file_path     AS video_file_path "
                    "FROM mem_decision d "
                    "LEFT JOIN scenes s      ON s.id = d.scene_id "
                    "LEFT JOIN video_clips v ON v.id = s.video_clip_id "
                    "WHERE d.id = :did"
                ),
                {"did": int(resolved_id)},
            ).mappings().first()
        finally:
            _close(session)

        if row is None:
            return {
                "status": "ok",
                "action": action,
                "decision_id": resolved_id,
                "message": f"Entscheidung #{resolved_id} nicht gefunden.",
            }

        # Rationale-Aufbereitung ueber den lebenden Read-Aggregator, damit
        # Chat und Audit-Tab identisch interpretieren.
        detail = _brain_service().get_decision_detail(int(resolved_id)) or {}
        terms: dict[str, float] = detail.get("rationale_terms") or {}
        alternatives: list[dict] = detail.get("alternatives") or []

        video_path = row["video_file_path"]
        clip_name = (
            str(video_path).rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            if video_path else None
        )

        context = {
            "at_timestamp_sec": float(row["at_timestamp_sec"] or 0.0),
            "at_beat_idx": row["at_beat_idx"],
            "at_bpm": float(row["at_bpm"]) if row["at_bpm"] is not None else None,
            "at_energy": (
                float(row["at_energy"]) if row["at_energy"] is not None else None
            ),
            "at_section_type": row["at_section_type"],
            "at_key": row["at_key"],
            "at_mood_audio": row["at_mood_audio"],
            "at_genre": row["at_genre"],
            "at_sub_genre": row["at_sub_genre"],
            "at_lufs": float(row["at_lufs"]) if row["at_lufs"] is not None else None,
            "at_enricher_version": row["at_enricher_version"],
        }
        chosen = {
            "scene_id": int(row["scene_id"]) if row["scene_id"] is not None else None,
            "video_clip_id": (
                int(row["video_clip_id"]) if row["video_clip_id"] is not None else None
            ),
            "clip_name": clip_name,
            "clip_role": row["clip_role"],
            "clip_mood_refined": row["clip_mood_refined"],
            "clip_style_bucket_id": row["clip_style_bucket_id"],
            "clip_motion_score": (
                float(row["clip_motion_score"])
                if row["clip_motion_score"] is not None else None
            ),
            "agent_score": float(row["agent_score"] or 0.0),
        }
        verdict = {
            "user_verdict": row["user_verdict"],
            "user_verdict_at": (
                str(row["user_verdict_at"]) if row["user_verdict_at"] else None
            ),
            "user_rating": row["user_rating"],
        }

        # Text-Aufbereitung analog ui/studio_brain/audit_tab.py
        lines = [
            f"Cut #{row['id']} (Run {row['run_id']}, Sequenz "
            f"{row['sequence_idx']}) @ {_fmt_time(context['at_timestamp_sec'])}"
        ]
        lines.append("=" * min(len(lines[0]), 70))
        if resolve_note:
            lines.append(f"({resolve_note})")
        lines.append(
            "Audio-Kontext: "
            f"genre={context['at_genre'] or '?'}, "
            f"section={context['at_section_type'] or '?'}, "
            f"bpm={context['at_bpm'] if context['at_bpm'] is not None else '?'}, "
            f"energy={context['at_energy'] if context['at_energy'] is not None else '?'}, "
            f"mood={context['at_mood_audio'] or '?'}"
        )
        clip_label = clip_name or f"scene #{chosen['scene_id']}"
        lines.append(
            "Gewaehlter Clip: "
            f"{clip_label} "
            f"(scene_id={chosen['scene_id']}, role={chosen['clip_role']}, "
            f"mood={chosen['clip_mood_refined']}, "
            f"motion={chosen['clip_motion_score']}) "
            f"-> Score {chosen['agent_score']:.4f}"
        )

        if terms:
            lines.append("Score-Beitraege:")
            for name, value in sorted(
                terms.items(), key=lambda kv: abs(kv[1]), reverse=True
            ):
                lines.append(f"  {name:<28} {value:+.4f}")
        else:
            lines.append(
                "Score-Beitraege: keine — agent_rationale enthaelt kein "
                "'contribs'-Feld fuer diese Entscheidung."
            )

        if alternatives:
            lines.append("Knappste Alternativen:")
            for i, alt in enumerate(alternatives, 1):
                lines.append(
                    f"  {i}. clip_id={alt.get('clip_id')} "
                    f"score={float(alt.get('score') or 0.0):.4f} "
                    f"role={alt.get('role') or '-'}"
                )
        else:
            lines.append(
                "Alternativen: keine — agent_rationale enthaelt keine "
                "bewerteten stage_results."
            )

        lines.append(
            "Verdikt: "
            + (verdict["user_verdict"] or "noch kein User-Verdikt")
            + (
                f" (Rating {verdict['user_rating']})"
                if verdict["user_rating"] is not None else ""
            )
        )
        if detail.get("fallback"):
            lines.append(
                "Hinweis: Fallback-Pfad aktiv (stage1_softened / stage2_forced / "
                "forced_negative) — die Wahl war erzwungen, nicht frei gescored."
            )
        if detail.get("budget_state"):
            lines.append(f"Budget-State: {detail['budget_state']}")

        return {
            "status": "ok",
            "action": action,
            "decision_id": int(row["id"]),
            "run_id": int(row["run_id"]),
            "sequence_idx": int(row["sequence_idx"] or 0),
            "context": context,
            "chosen": chosen,
            "score_contributions": terms,
            "alternatives": alternatives,
            "budget_state": detail.get("budget_state") or {},
            "fallback": bool(detail.get("fallback")),
            "verdict": verdict,
            "resolved_by": resolve_note or "decision_id",
            "message": "\n".join(lines),
        }
    except Exception as exc:  # broad catch intentional — DB + JSON errors
        _logger.error("%s fehlgeschlagen: %s", action, exc, exc_info=True)
        return {"status": "error", "action": action, "message": str(exc)}


def _resolve_decision_id(
    session: Any,
    decision_id: Optional[int],
    run_id: Optional[int],
    at_timestamp_sec: Optional[float],
) -> tuple[Optional[int], Optional[str]]:
    """Findet die zu erklaerende decision_id. Gibt (id, hinweis) zurueck."""
    if decision_id is not None:
        return int(decision_id), None

    rid = run_id
    note_parts: list[str] = []
    if rid is None:
        row = session.execute(
            text(
                "SELECT run_id FROM mem_decision "
                "ORDER BY run_id DESC, id DESC LIMIT 1"
            )
        ).first()
        if row is None:
            return None, "es existiert noch keine einzige Entscheidung (mem_decision leer)"
        rid = int(row[0])
        note_parts.append(f"neuester Run #{rid}")

    if at_timestamp_sec is None:
        row = session.execute(
            text(
                "SELECT id FROM mem_decision WHERE run_id = :rid "
                "ORDER BY sequence_idx ASC, id ASC LIMIT 1"
            ),
            {"rid": int(rid)},
        ).first()
        if row is None:
            return None, f"Run #{rid} hat keine Entscheidungen"
        note_parts.append("erste Entscheidung des Runs")
        return int(row[0]), ", ".join(note_parts)

    row = session.execute(
        text(
            "SELECT id, at_timestamp_sec FROM mem_decision WHERE run_id = :rid "
            "ORDER BY ABS(at_timestamp_sec - :ts) ASC, id ASC LIMIT 1"
        ),
        {"rid": int(rid), "ts": float(at_timestamp_sec)},
    ).first()
    if row is None:
        return None, f"Run #{rid} hat keine Entscheidungen"
    note_parts.append(
        f"naechste Entscheidung zu {_fmt_time(at_timestamp_sec)} "
        f"(tatsaechlich {_fmt_time(float(row[1] or 0.0))})"
    )
    return int(row[0]), ", ".join(note_parts)


# ---------------------------------------------------------------------------
# 4. brain_learn_note — Modell/App legt selbst eine Erkenntnis ab
# ---------------------------------------------------------------------------

@action_registry.register(
    name="brain_learn_note",
    description=(
        "Legt eine Erkenntnis dauerhaft im Brain ab, damit sie spaeter ueber "
        "`brain_recall` wiedergefunden wird. Freier Text plus optionaler "
        "Kontext und Quellenangabe. Nutze diese Aktion wenn etwas gelernt "
        "wurde, das kuenftige Entscheidungen verbessern soll — z.B. "
        "'merke dir, dass ...', 'notiere die Erkenntnis ...', "
        "'speichere das fuer spaeter'."
    ),
    param_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Kurzer, sprechender Titel der Erkenntnis.",
            },
            "body": {
                "type": "string",
                "description": "Die Erkenntnis als freier Text (Markdown erlaubt).",
            },
            "context": {
                "type": "object",
                "description": (
                    "Optionaler Kontext als Objekt, z.B. "
                    "{\"genre\": \"psytrance\", \"section\": \"drop\"}. Wird "
                    "mitgespeichert und ist ueber brain_recall mitdurchsuchbar."
                ),
            },
            "source": {
                "type": "string",
                "description": (
                    "Herkunft der Erkenntnis (default 'agent'), z.B. 'user', "
                    "'orchestrator', 'pacing'. Zusammen mit dem Titel der "
                    "Upsert-Schluessel."
                ),
            },
            "linked_entity_id": {
                "type": "integer",
                "description": "Optionale brain_entity-ID als Verknuepfung.",
            },
        },
        "required": ["title", "body"],
    },
)
def brain_learn_note(
    title: str,
    body: str,
    context: Optional[dict] = None,
    source: str = DEFAULT_NOTE_SOURCE,
    linked_entity_id: Optional[int] = None,
) -> dict:
    """Schreibt eine Erkenntnis nach ``brain_note`` (Upsert auf title+source)."""
    action = "brain_learn_note"
    try:
        clean_title = (title or "").strip()
        clean_body = (body or "").strip()
        clean_source = (source or DEFAULT_NOTE_SOURCE).strip() or DEFAULT_NOTE_SOURCE
        if not clean_title:
            return {
                "status": "error",
                "action": action,
                "message": "title darf nicht leer sein.",
            }
        if not clean_body:
            return {
                "status": "error",
                "action": action,
                "message": "body darf nicht leer sein.",
            }

        # Kontext wird an den Markdown-Body angehaengt. brain_note hat keine
        # eigene Kontext-Spalte; so bleibt der Kontext im Volltext und damit
        # ueber brain_recall auffindbar — ohne neue Migration.
        stored_body = clean_body
        if context:
            try:
                ctx_json = json.dumps(context, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError):
                ctx_json = str(context)
            stored_body = f"{clean_body}\n\nKontext: {ctx_json}"

        now = _dt.datetime.utcnow()
        factory = _session_factory()
        session = factory()
        try:
            if not _table_exists(session, "brain_note"):
                return {
                    "status": "error",
                    "action": action,
                    "message": (
                        "Tabelle 'brain_note' existiert in dieser Projekt-DB "
                        "nicht. Alembic-Migration c3d4e5f6a7b8 (add_brain_v2_tables) "
                        "muss gelaufen sein."
                    ),
                }

            existing = session.execute(
                text(
                    "SELECT id FROM brain_note WHERE title = :t AND source = :s"
                ),
                {"t": clean_title, "s": clean_source},
            ).first()

            if existing is None:
                session.execute(
                    text(
                        "INSERT INTO brain_note "
                        "(title, body_md, source, linked_entity_id, "
                        " created_at, updated_at) "
                        "VALUES (:t, :b, :s, :l, :c, :u)"
                    ),
                    {
                        "t": clean_title,
                        "b": stored_body,
                        "s": clean_source,
                        "l": linked_entity_id,
                        "c": now,
                        "u": now,
                    },
                )
                session.commit()
                note_id = int(
                    _scalar(
                        session,
                        "SELECT id FROM brain_note WHERE title = :t AND source = :s",
                        {"t": clean_title, "s": clean_source},
                    )
                )
                created = True
            else:
                note_id = int(existing[0])
                session.execute(
                    text(
                        "UPDATE brain_note SET body_md = :b, "
                        "linked_entity_id = :l, updated_at = :u WHERE id = :i"
                    ),
                    {
                        "b": stored_body,
                        "l": linked_entity_id,
                        "u": now,
                        "i": note_id,
                    },
                )
                session.commit()
                created = False
        finally:
            _close(session)

        return {
            "status": "ok",
            "action": action,
            "note_id": note_id,
            "created": created,
            "updated": not created,
            "title": clean_title,
            "source": clean_source,
            "context": context or {},
            "message": (
                f"Erkenntnis {'gespeichert' if created else 'aktualisiert'} "
                f"(brain_note #{note_id}, Quelle '{clean_source}'): "
                f"{clean_title}. Wiederfindbar ueber `brain_recall`."
            ),
        }
    except Exception as exc:  # broad catch intentional — DB write errors
        _logger.error("%s fehlgeschlagen: %s", action, exc, exc_info=True)
        return {"status": "error", "action": action, "message": str(exc)}

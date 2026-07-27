"""Beweis-Tests fuer die Brain-Lese-/Schreib-Actions (services/actions/brain_actions.py).

Jeder Test ruft die Action ueber ``action_registry.execute(...)`` auf — NICHT
die Python-Funktion direkt. Damit ist bewiesen, dass die Action ueber das
Registry (den Mechanismus, ueber den jedes Modell Faehigkeiten aufruft)
wirklich erreichbar und ausfuehrbar ist.

Alle Tests laufen ohne QApplication, ohne TaskManager, ohne Worker, ohne
GPU und ohne LLM-Call — reiner Service-/DB-Zugriff.

Die DB wird ueber den PRODUKTIVEN Fresh-DB-Pfad aufgebaut
(``database.session.set_project`` + ``database.migrations.init_db``), damit
die ``mem_*``/``brain_*``-Tabellen genauso entstehen wie in einer echten
Projekt-DB — sie stammen ausschliesslich aus Alembic, nicht aus
``Base.metadata.create_all``.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

import database.session as dbs
from database.models import AudioTrack, Project, Scene, VideoClip
from services.action_registry import action_registry

# Import registriert die vier Actions als Side-Effect.
import services.actions.brain_actions as brain_actions  # noqa: F401


BRAIN_ACTION_NAMES = (
    "brain_recall",
    "brain_stats",
    "brain_explain_cut",
    "brain_learn_note",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def migrated_project(tmp_path, monkeypatch):
    """Frische Projekt-DB inkl. Alembic-Head (mem_* + brain_* existieren).

    Baut das Schema exakt wie der produktive Fresh-DB-Pfad in
    ``database.migrations.init_db``: ``create_all`` fuer die ORM-Tabellen,
    dann Alembic-Baseline stempeln und auf Head migrieren — denn die
    ``mem_*``/``brain_*``-Tabellen entstehen NUR durch Alembic.

    Der Aufbau laeuft in einer eigenen Engine, die danach entsorgt wird;
    erst dann wird ``database.session.engine`` fuer den Test umgebogen.
    So bleibt keine offene Schreib-Transaktion aus dem Migrationslauf
    zurueck (sonst: "database is locked").
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from database.migrations import _ALEMBIC_BASELINE_REV, _REPO_ROOT
    from database.models import Base

    db_path = tmp_path / "pb_studio.db"
    url = f"sqlite:///{db_path.as_posix()}"

    boot = create_engine(url, future=True)
    Base.metadata.create_all(boot)
    boot.dispose()

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "database" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.stamp(cfg, _ALEMBIC_BASELINE_REV)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    monkeypatch.setattr(dbs, "engine", engine)

    # Sanity: die Alembic-only-Tabellen muessen wirklich da sein, sonst
    # testet der Rest gegen ein Phantom.
    with SASession(engine) as s:
        for table in ("mem_pacing_run", "mem_decision", "mem_learned_pattern",
                      "brain_note"):
            assert s.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": table},
            ).first() is not None, f"{table} fehlt nach der Migration"

    yield tmp_path

    engine.dispose()


@pytest.fixture
def seeded_brain(migrated_project):
    """Legt Projekt/Audio/Video/Scene + einen Pacing-Run mit 3 Cuts an.

    Rueckgabe: dict mit den erzeugten IDs.
    """
    now = dt.datetime(2026, 7, 20, 12, 0, 0)

    with SASession(dbs.engine) as s:
        project = Project(name="BrainTest", path=str(migrated_project))
        s.add(project)
        s.flush()

        track = AudioTrack(
            project_id=project.id,
            file_path=str(migrated_project / "mix.mp3"),
            title="Testmix",
            bpm=142.0,
            genre="psytrance",
        )
        clip = VideoClip(
            project_id=project.id,
            file_path=str(migrated_project / "jungle.mp4"),
            duration=60.0,
        )
        s.add_all([track, clip])
        s.flush()

        scenes = []
        for i in range(3):
            sc = Scene(
                video_clip_id=clip.id,
                start_time=float(i * 5),
                end_time=float(i * 5 + 5),
                scene_index=i,
            )
            scenes.append(sc)
        s.add_all(scenes)
        s.flush()

        scene_ids = [sc.id for sc in scenes]
        track_id, clip_id, project_id = track.id, clip.id, project.id

        # -- mem_pacing_run + mem_decision (raw SQL: keine ORM-Models) ------
        s.execute(
            text(
                "INSERT INTO mem_pacing_run "
                "(id, audio_track_id, started_at, completed_at, is_dj_mix, "
                " total_duration_sec, total_cuts, agent_version, weights_profile) "
                "VALUES (1, :tid, :st, :ct, 1, 300.0, 3, 'test-1.0', 'default')"
            ),
            {"tid": track_id, "st": now, "ct": now},
        )

        rationale_rich = json.dumps({
            "chosen_clip_id": clip_id,
            "chosen_scene_id": scene_ids[0],
            "chosen_score": 0.82,
            "contribs": {"energy": 0.31, "role": 0.25, "freshness": -0.04},
            "stage_results": [
                {"clip_id": clip_id, "soft_score": 0.82},
                {"clip_id": 99, "soft_score": 0.79},
                {"clip_id": 98, "soft_score": 0.71},
            ],
            "stage1_softened": False,
            "stage2_forced": False,
        })
        rationale_plain = json.dumps({"chosen_clip_id": clip_id, "chosen_score": 0.4})

        rows = [
            (1, 0, 10.0, "drop", 0.82, rationale_rich, "accept", scene_ids[0]),
            (2, 1, 42.5, "breakdown", 0.55, rationale_plain, None, scene_ids[1]),
            (3, 2, 90.0, "drop", 0.61, rationale_plain, "reject", scene_ids[2]),
        ]
        for did, seq, ts, section, score, rationale, verdict, sid in rows:
            s.execute(
                text(
                    "INSERT INTO mem_decision "
                    "(id, run_id, sequence_idx, at_timestamp_sec, at_bpm, "
                    " at_energy, at_section_type, at_mood_audio, at_genre, "
                    " at_sub_genre, at_enricher_version, scene_id, clip_role, "
                    " clip_mood_refined, clip_style_bucket_id, clip_motion_score, "
                    " agent_score, agent_rationale, user_verdict) "
                    "VALUES (:id, 1, :seq, :ts, 142.0, 0.7, :section, 'energetic', "
                    " 'psytrance', 'dark_psy', 'v1', :sid, 'hero', 'euphoric', "
                    " 2, 0.66, :score, :rationale, :verdict)"
                ),
                {
                    "id": did, "seq": seq, "ts": ts, "section": section,
                    "sid": sid, "score": score, "rationale": rationale,
                    "verdict": verdict,
                },
            )

        s.execute(
            text(
                "INSERT INTO mem_learned_pattern "
                "(id, pattern_type, context_fingerprint, target_ref, "
                " stat_accept_count, stat_reject_count, stat_sample_size, "
                " confidence, last_updated) "
                "VALUES (1, 'context_preference', :fp, :tr, 8, 2, 10, 0.72, :lu)"
            ),
            {
                "fp": json.dumps({
                    "genre": "psytrance", "section_type": "drop", "bpm_bucket": 142
                }),
                "tr": json.dumps({"scene_id": scene_ids[0]}),
                "lu": now,
            },
        )
        s.commit()

    return {
        "project_id": project_id,
        "track_id": track_id,
        "clip_id": clip_id,
        "scene_ids": scene_ids,
    }


# ---------------------------------------------------------------------------
# Erreichbarkeit im Registry / headless Ausfuehrbarkeit
# ---------------------------------------------------------------------------

def test_all_brain_actions_are_registered():
    """Die vier Actions sind im globalen Registry auffindbar."""
    registered = set(action_registry.list_actions())
    for name in BRAIN_ACTION_NAMES:
        assert name in registered, f"{name} nicht im action_registry"
        assert action_registry.get(name) is not None


def test_brain_actions_reachable_via_register_actions_entrypoint():
    """Der Produktions-Entrypoint ``services.register_actions`` zieht das Modul."""
    import services.register_actions as ra

    src = ra.__file__
    with open(src, "r", encoding="utf-8") as fh:
        content = fh.read()
    assert "brain_actions" in content, (
        "services/register_actions.py importiert brain_actions nicht — "
        "die Actions waeren in der App nie registriert."
    )


def test_brain_actions_need_no_worker_registration():
    """Kein Worker-/Qt-Pfad: die Handler emittieren keine agent_command_signal.

    Genau das war die Fehlerklasse 'Action meldet Erfolg, aber es ist nie
    ein Worker registriert' — diese vier laufen komplett synchron.
    """
    import inspect

    for name in BRAIN_ACTION_NAMES:
        handler = action_registry.get(name).handler
        src = inspect.getsource(handler)
        assert "agent_command_signal" not in src, (
            f"{name} nutzt einen Worker-Spawn, braucht dann aber einen "
            f"Eintrag in workers/registry.py"
        )
        assert "GlobalTaskManager" not in src, f"{name} koppelt an den TaskManager"


def test_brain_actions_execute_headless_via_registry(seeded_brain):
    """Alle vier laufen ueber action_registry.execute ohne GUI durch."""
    calls = {
        "brain_stats": {},
        "brain_recall": {"query": "psytrance drop"},
        "brain_explain_cut": {"decision_id": 1},
        "brain_learn_note": {"title": "Headless", "body": "Ohne GUI abgelegt."},
    }
    for name, params in calls.items():
        result = action_registry.execute(name, params)
        assert isinstance(result, dict), f"{name} liefert kein dict"
        assert result.get("status") == "ok", f"{name}: {result.get('message')}"
        assert result.get("action") == name


# ---------------------------------------------------------------------------
# brain_stats
# ---------------------------------------------------------------------------

def test_brain_stats_reports_real_counts(seeded_brain):
    result = action_registry.execute("brain_stats", {})

    assert result["status"] == "ok"
    assert result["run_count"] == 1
    assert result["decision_count"] == 3
    assert result["decisions_with_verdict"] == 2
    assert result["verdict_distribution"]["accept"] == 1
    assert result["verdict_distribution"]["reject"] == 1
    assert result["verdict_distribution"]["kein_verdikt"] == 1
    assert result["pattern_count"] == 1
    assert result["confident_pattern_count"] == 1
    assert "psytrance" in result["distinct_genres"]
    assert set(result["distinct_sections"]) == {"drop", "breakdown"}
    assert "Schnitt-Entscheidungen: 3" in result["message"]


def test_brain_stats_reports_no_signal_kinds(seeded_brain):
    """Nur context_preference hat Daten — die drei String-Kinds sind leer."""
    result = action_registry.execute("brain_stats", {})

    assert "context_preference" not in result["no_signal_kinds"]
    for kind in ("genre", "key", "spectral"):
        assert kind in result["no_signal_kinds"]
    assert any("Pattern-Kinds ohne Datenbasis" in g for g in result["gaps"])


def test_brain_stats_empty_db_is_honest(migrated_project):
    """Leere (aber migrierte) DB: ehrliche Nullen statt Platzhalter."""
    result = action_registry.execute("brain_stats", {})

    assert result["status"] == "ok"
    assert result["run_count"] == 0
    assert result["decision_count"] == 0
    assert result["pattern_count"] == 0
    assert result["note_count"] == 0
    assert result["verdict_distribution"] == {}
    assert any("noch keine Schnitt-Entscheidungen" in g for g in result["gaps"])
    assert result["no_signal_kinds"] == list(brain_actions.KNOWN_PATTERN_KINDS)


def test_brain_stats_reports_axes_gap(migrated_project, monkeypatch, tmp_path):
    """Ohne weights.db wird die Achsen-Luecke gemeldet, nicht erfunden."""
    from services.brain import paths

    missing = tmp_path / "nowhere" / "weights.db"
    monkeypatch.setattr(paths, "weights_db_path", lambda create_dir=True: missing)

    result = action_registry.execute("brain_stats", {})

    assert result["status"] == "ok"
    assert result["weights_error"] is not None
    assert result["axes_with_signal"] == 0
    assert len(result["no_signal_axes"]) == result["total_axes"] == 17
    assert any("weights.db" in g for g in result["gaps"])


# ---------------------------------------------------------------------------
# brain_explain_cut
# ---------------------------------------------------------------------------

def test_brain_explain_cut_returns_contributions_and_alternatives(seeded_brain):
    result = action_registry.execute("brain_explain_cut", {"decision_id": 1})

    assert result["status"] == "ok"
    assert result["decision_id"] == 1
    assert result["run_id"] == 1

    contribs = result["score_contributions"]
    assert contribs["energy"] == pytest.approx(0.31)
    assert contribs["role"] == pytest.approx(0.25)
    assert contribs["freshness"] == pytest.approx(-0.04)

    # Alternativen = bewertete stage_results ohne den gewaehlten Clip
    alt_ids = {a["clip_id"] for a in result["alternatives"]}
    assert alt_ids == {99, 98}

    assert result["context"]["at_genre"] == "psytrance"
    assert result["context"]["at_section_type"] == "drop"
    assert result["chosen"]["scene_id"] == seeded_brain["scene_ids"][0]
    assert result["chosen"]["clip_role"] == "hero"
    assert result["verdict"]["user_verdict"] == "accept"
    assert result["fallback"] is False
    assert "Score-Beitraege" in result["message"]
    assert "energy" in result["message"]


def test_brain_explain_cut_is_honest_when_rationale_has_no_terms(seeded_brain):
    """Cut #2 hat keine contribs — das wird gesagt, nicht erfunden."""
    result = action_registry.execute("brain_explain_cut", {"decision_id": 2})

    assert result["status"] == "ok"
    assert result["score_contributions"] == {}
    assert result["alternatives"] == []
    assert "keine" in result["message"]
    assert "contribs" in result["message"]


def test_brain_explain_cut_resolves_by_run_and_timestamp(seeded_brain):
    """Ohne decision_id wird ueber run_id + Zeitpunkt aufgeloest."""
    result = action_registry.execute(
        "brain_explain_cut", {"run_id": 1, "at_timestamp_sec": 88.0}
    )

    assert result["status"] == "ok"
    assert result["decision_id"] == 3  # naechster Cut zu 88s liegt bei 90s
    assert result["verdict"]["user_verdict"] == "reject"
    assert "naechste Entscheidung" in result["resolved_by"]


def test_brain_explain_cut_defaults_to_newest_run(seeded_brain):
    result = action_registry.execute("brain_explain_cut", {})

    assert result["status"] == "ok"
    assert result["run_id"] == 1
    assert result["decision_id"] == 1  # erste Entscheidung des Runs
    assert "neuester Run" in result["resolved_by"]


def test_brain_explain_cut_empty_db_is_honest(migrated_project):
    result = action_registry.execute("brain_explain_cut", {})

    assert result["status"] == "ok"
    assert result["decision_id"] is None
    assert "Noch keine Daten" in result["message"]


# ---------------------------------------------------------------------------
# brain_recall
# ---------------------------------------------------------------------------

def test_brain_recall_finds_decisions_and_patterns(seeded_brain):
    result = action_registry.execute(
        "brain_recall", {"query": "psytrance drop", "top_k": 5}
    )

    assert result["status"] == "ok"
    assert result["result_count"] > 0
    sources = {r["source"] for r in result["results"]}
    assert "mem_decision" in sources
    assert "mem_learned_pattern" in sources

    pattern_hit = next(
        r for r in result["results"] if r["source"] == "mem_learned_pattern"
    )
    assert pattern_hit["accepts"] == 8
    assert pattern_hit["samples"] == 10
    assert pattern_hit["context_fingerprint"]["genre"] == "psytrance"


def test_brain_recall_by_scene_id_returns_decision_history(seeded_brain):
    scene_id = seeded_brain["scene_ids"][2]
    result = action_registry.execute("brain_recall", {"scene_id": scene_id})

    assert result["status"] == "ok"
    hits = [r for r in result["results"] if r["source"] == "mem_decision"]
    assert hits, "keine Entscheidungs-Historie zur Scene gefunden"
    assert all(h["scene_id"] == scene_id for h in hits)
    assert any(h["user_verdict"] == "reject" for h in hits)


def test_brain_recall_empty_db_is_honest(migrated_project):
    result = action_registry.execute("brain_recall", {"query": "irgendwas"})

    assert result["status"] == "ok"
    assert result["result_count"] == 0
    assert result["results"] == []
    assert "Noch keine Daten" in result["message"]
    assert set(result["empty_sources"]) >= {
        "brain_note", "mem_learned_pattern", "mem_decision"
    }


# ---------------------------------------------------------------------------
# brain_learn_note + der geschlossene Kreis
# ---------------------------------------------------------------------------

def test_brain_learn_note_persists_to_brain_note(migrated_project):
    result = action_registry.execute("brain_learn_note", {
        "title": "Breakdowns vertragen lange Clips",
        "body": "Im Breakdown wirken Schnitte ueber 4 Sekunden ruhiger.",
        "context": {"section": "breakdown"},
        "source": "pacing",
    })

    assert result["status"] == "ok"
    assert result["created"] is True
    note_id = result["note_id"]

    with SASession(dbs.engine) as s:
        row = s.execute(
            text("SELECT title, body_md, source FROM brain_note WHERE id = :i"),
            {"i": note_id},
        ).first()
    assert row is not None
    assert row[0] == "Breakdowns vertragen lange Clips"
    assert "4 Sekunden" in row[1]
    assert "breakdown" in row[1]  # Kontext landet im Volltext
    assert row[2] == "pacing"


def test_brain_learn_note_upserts_on_same_title_and_source(migrated_project):
    first = action_registry.execute("brain_learn_note", {
        "title": "Gleiche Notiz", "body": "Erste Fassung.", "source": "agent",
    })
    second = action_registry.execute("brain_learn_note", {
        "title": "Gleiche Notiz", "body": "Zweite Fassung.", "source": "agent",
    })

    assert first["created"] is True
    assert second["created"] is False
    assert second["updated"] is True
    assert second["note_id"] == first["note_id"]

    with SASession(dbs.engine) as s:
        count = s.execute(text("SELECT COUNT(*) FROM brain_note")).scalar()
        body = s.execute(
            text("SELECT body_md FROM brain_note WHERE id = :i"),
            {"i": first["note_id"]},
        ).scalar()
    assert count == 1
    assert body == "Zweite Fassung."


def test_brain_learn_note_rejects_empty_input(migrated_project):
    assert action_registry.execute(
        "brain_learn_note", {"title": "  ", "body": "x"}
    )["status"] == "error"
    assert action_registry.execute(
        "brain_learn_note", {"title": "x", "body": "   "}
    )["status"] == "error"


def test_learn_note_is_found_again_by_recall(migrated_project):
    """DER KREIS: geschrieben mit brain_learn_note, gefunden mit brain_recall."""
    # Vorher: nichts da — ehrliche Leermeldung.
    before = action_registry.execute(
        "brain_recall", {"query": "hero clips im drop"}
    )
    assert before["result_count"] == 0
    assert "brain_note" in before["empty_sources"]

    write = action_registry.execute("brain_learn_note", {
        "title": "Hero-Clips gehoeren in den Drop",
        "body": (
            "Clips mit role=hero funktionieren im Drop am besten, "
            "im Breakdown wirken sie ueberladen."
        ),
        "context": {"genre": "psytrance", "section": "drop", "role": "hero"},
        "source": "orchestrator",
    })
    assert write["status"] == "ok"

    after = action_registry.execute(
        "brain_recall", {"query": "hero clips im drop", "top_k": 5}
    )
    assert after["status"] == "ok"

    notes = [r for r in after["results"] if r["source"] == "brain_note"]
    assert notes, "brain_recall findet die eben abgelegte Erkenntnis nicht"
    hit = notes[0]
    assert hit["note_id"] == write["note_id"]
    assert hit["title"] == "Hero-Clips gehoeren in den Drop"
    assert "role=hero" in hit["body"]
    assert hit["note_source"] == "orchestrator"
    assert "Hero-Clips gehoeren in den Drop" in after["message"]


def test_learn_note_context_is_searchable_by_recall(migrated_project):
    """Der mitgegebene Kontext ist ueber brain_recall auffindbar."""
    action_registry.execute("brain_learn_note", {
        "title": "Kontext-Test",
        "body": "Kurzer Text ohne Suchbegriff.",
        "context": {"groove_template": "fotf", "sub_genre": "darkpsy"},
    })

    result = action_registry.execute("brain_recall", {"query": "darkpsy"})

    notes = [r for r in result["results"] if r["source"] == "brain_note"]
    assert notes, "Kontext-Feld wird von brain_recall nicht durchsucht"
    assert notes[0]["title"] == "Kontext-Test"


def test_brain_stats_counts_notes_after_learning(migrated_project):
    """brain_stats sieht die selbst abgelegten Erkenntnisse."""
    assert action_registry.execute("brain_stats", {})["note_count"] == 0

    action_registry.execute("brain_learn_note", {
        "title": "Notiz A", "body": "Text A", "source": "agent",
    })
    action_registry.execute("brain_learn_note", {
        "title": "Notiz B", "body": "Text B", "source": "user",
    })

    stats = action_registry.execute("brain_stats", {})
    assert stats["note_count"] == 2
    assert stats["note_sources"] == {"agent": 1, "user": 1}

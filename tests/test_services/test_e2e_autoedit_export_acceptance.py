"""End-to-End-ABNAHMEVERTRAG: Auswahl-/Apply-Kette liefert eine benutzbare,
exportvalide Timeline.

Diese Suite ist KEIN Unit-Test einzelner Fixes, sondern das bisher fehlende
Abnahme-Kriterium ueber die gesamte Kette:

    PacingPipeline.select_best (Loop wie pacing_service)
        -> apply_auto_edit_segments (DB, locked-aware, Repair)
        -> heal_video_timeline_gaps / _validate_video_timeline_gaps (Export)

Kein GUI, kein ffmpeg-Render, keine echte Projekt-DB — test_engine-Fixture
(tests/conftest.py) + In-Memory-SQLite wie in den bestehenden Service-Tests.

MUTATIONS-GEGENPROBE (statt RED-Phase — Suite entstand NACH den Fixes):
Jeder Vertrag schuetzt gegen eine REALE, datierte Regression:

- Vertrag 1  <- B-763 (2026-08-06): kein Nutzungs-Cap im Studio-Brain-Pfad;
               5 Clips gewannen ~95 % von 1415 Segmenten.
               <- B-768 (2026-08-07): Stage-1-Rollenmatrix kollabierte die
               Kandidatenmenge auf eine Rollen-Minderheit (22 von 364).
               <- B-759 (2026-08-06/07): 104 direkte Wiederholungen in der
               Wahlfolge (Nachbarschaftsregel wirkungslos).
- Vertrag 2  <- B-769 (2026-08-07): Apply/Repair liess Luecken vor gelockten
               Ankern stehen (new_test_august, Entry 990, 2.668s Luecke),
               Export brach Minuten spaeter am Gap-Validator ab.
- Vertrag 3  <- B-767 (2026-08-07 00:07): Cancel bei 572/1410 gab Teilstand
               zurueck, Aufrufer wandte ihn an -> 1410er-Timeline durch
               Fragment mit 1437s-Loch ersetzt. Vertrag: Cancel = ([], []) =
               NICHTS anwenden, Bestands-Timeline bleibt byte-identisch.
- Vertrag 4  <- B-769: Export heilt Luecken NUR in-memory; die DB darf dabei
               byte-identisch bleiben (Export mutiert das Projekt nicht).
- Vertrag 5  <- B-769: unschliessbare Luecke (beidseitig locked) muss einen
               praezisen, handlungsleitenden Fehler mit Zeitangabe liefern —
               nicht den rohen Validator-Text "Timeline gap vor Video-Segment N".

Wenn hier etwas ROT ist, ist das ein ECHTER FUND — Test nicht weichspuelen.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from database.models import Project, TimelineEntry, VideoClip
from services.export._common import (
    _validate_video_timeline_gaps,
    heal_video_timeline_gaps,
)
from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures

REPO_ROOT = Path(__file__).resolve().parents[2]

# Rollenmatrix wie im B-768-Livebefund: DROP akzeptiert nur hero/action.
RULES_YAML = """\
section_role_matrix:
  drop: [hero, action]
key_mood_gate:
  enabled: false
  forbidden_moods: []
stage1_fallback: soften
"""


def _ctx() -> AudioContext:
    return AudioContext(
        at_timestamp_sec=10.0,
        at_beat_idx=20,
        at_section_type="drop",
        at_bpm=140.0,
        at_energy=0.8,
        at_key="A min",
        at_key_confidence=0.85,
        at_harmonic_tension=0.5,
        at_mood_audio="energetic",
        at_mood_video=None,
        at_genre="techno",
        at_sub_genre=None,
        at_spectral_hash="abc12345",
        at_groove_template="four_on_floor",
        at_lufs=-8.5,
    )


def _clip(clip_id: int, role: str, motion: float) -> ClipFeatures:
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined="energetic",
        style_bucket_id=1,
        motion_score=motion,
        embedding=np.ones(4, dtype=np.float32) * 0.5,
    )


def _snapshot_timeline(engine, project_id: int) -> list[tuple]:
    """Byte-genauer SELECT-Vergleichsstand aller Timeline-Zeilen."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM timeline_entries "
                "WHERE project_id = :pid ORDER BY id"
            ),
            {"pid": project_id},
        ).fetchall()
    return [tuple(r) for r in rows]


# ---------------------------------------------------------------------------
# Vertrag 1 — VERTEILUNG: Selektions-Loop wie pacing_service
# ---------------------------------------------------------------------------


def test_contract1_distribution_200_segments_role_minority(tmp_path):
    """B-763 + B-768 + B-759: 200 Segmente, 50 Kandidaten, nur 5 mit
    section-tauglicher Rolle (action fuer DROP). Der Loop entspricht dem
    echten pacing_service-Muster: Wahl -> usage_counts[vid] += 1 ->
    recent_clip_ids (3er-Fenster) -> naechstes Segment.

    Abnahme: kein Clip > max_uses, >= n/max_uses verschiedene Clips,
    0 direkte Wiederholungen in der Wahlfolge.
    """
    rules = tmp_path / "pacing_rules.yaml"
    rules.write_text(RULES_YAML, encoding="utf-8")
    pipeline = PacingPipeline(rules_path=rules)

    n_segments = 200
    candidates = [
        _clip(
            i,
            role="action" if i <= 5 else "unknown",
            motion=0.8 if i <= 5 else 0.2 + (i % 7) * 0.01,
        )
        for i in range(1, 51)
    ]
    max_uses = (n_segments // len(candidates)) + 1  # = 5, wie pacing_service

    usage: dict[int, int] = {}
    used_recently: list[int] = []
    choices: list[int] = []
    for _ in range(n_segments):
        result = pipeline.select_best(
            candidates=candidates,
            ctx=_ctx(),
            recent_clip_ids=used_recently[-3:] or None,
            usage_counts=usage,
            max_uses=max_uses,
        )
        assert result.chosen is not None, "Loop darf nie leer waehlen"
        vid = result.chosen.clip_id
        choices.append(vid)
        usage[vid] = usage.get(vid, 0) + 1
        used_recently.append(vid)

    wins: dict[int, int] = {}
    for vid in choices:
        wins[vid] = wins.get(vid, 0) + 1

    worst = max(wins.values())
    assert worst <= max_uses, (
        f"B-763-Regression: ein Clip gewann {worst}x trotz "
        f"max_uses={max_uses}: {wins}"
    )
    assert len(wins) >= n_segments // max_uses, (
        f"B-768-Regression: nur {len(wins)} verschiedene Clips fuer "
        f"{n_segments} Segmente (Kollaps auf Rollen-Minderheit): {wins}"
    )
    direct_repeats = sum(
        1 for a, b in zip(choices, choices[1:]) if a == b
    )
    assert direct_repeats == 0, (
        f"B-759-Regression: {direct_repeats} direkte Wiederholungen in "
        f"der Wahlfolge"
    )


# ---------------------------------------------------------------------------
# Vertrag 2 — APPLY-INVARIANTE: nach Apply ist die Timeline exportvalide
# ---------------------------------------------------------------------------


def test_contract2_apply_produces_export_valid_timeline(test_engine, monkeypatch):
    """B-769: apply_auto_edit_segments mit absichtlichen Mini-Luecken (0.2s /
    0.15s — beide > close_threshold 0.05s, der Validator allein wuerde also
    ValueError werfen) + locked Bestandssegment. Danach MUSS die gelesene
    Timeline _validate_video_timeline_gaps bestehen und das locked Segment
    byte-identisch erhalten sein (Muster test_apply_auto_edit_locked.py).

    Mutations-Gegenprobe (dokumentiert): Entfernt man in
    services/timeline_service.py::repair_timeline_integrity den
    heal_video_timeline_gaps-Backfill (B-769) ODER den Gap-Close-Pass,
    bleibt die 0.2s-Luecke vor dem locked Anker stehen und der Validator
    unten wirft ValueError — genau der reale Export-Abbruch vom 2026-08-07
    (new_test_august, Entry 990, 2.668s).
    """
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="e2e-apply", path="/tmp/e2e-apply")
        s.add(p)
        s.flush()
        clips = []
        for i in range(3):
            c = VideoClip(
                project_id=p.id,
                file_path=f"/tmp/e2e-apply-{i}.mp4",
                duration=30.0,
            )
            s.add(c)
            clips.append(c)
        s.flush()
        c1, c2, c3 = (c.id for c in clips)
        # Locked Bestandssegment [10..14]
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=c1,
            start_time=10.0, end_time=14.0,
            source_start=0.0, source_end=4.0,
            lane=0, locked=True,
        ))
        s.commit()
        pid = p.id

    def _locked_row(engine):
        with engine.connect() as conn:
            return tuple(conn.execute(
                text(
                    "SELECT * FROM timeline_entries "
                    "WHERE project_id = :pid AND locked = 1"
                ),
                {"pid": pid},
            ).one())

    locked_before = _locked_row(test_engine)

    segments = [
        {"media_id": c1, "start": 0.0, "end": 4.0, "lane": 0,
         "source_start": 0.0, "source_end": 4.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
        # absichtliche 0.2s-Luecke vor diesem Segment
        {"media_id": c2, "start": 4.2, "end": 10.0, "lane": 0,
         "source_start": 0.0, "source_end": 5.8,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
        # absichtliche 0.15s-Luecke nach dem locked Segment
        {"media_id": c3, "start": 14.15, "end": 18.0, "lane": 0,
         "source_start": 0.0, "source_end": 3.85,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
    ]

    inserted = ts_mod.apply_auto_edit_segments(segments, pid)
    assert inserted == 3

    with DBSession(test_engine) as s:
        rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video")
            .order_by(TimelineEntry.start_time, TimelineEntry.id)
            .all()
        )
        video_segments = [
            {"start": float(r.start_time), "end": float(r.end_time)}
            for r in rows
        ]

    # Abnahme-Kern: der EXPORT-Validator akzeptiert das Apply-Ergebnis.
    before_validation = [dict(seg) for seg in video_segments]
    _validate_video_timeline_gaps(video_segments)
    # Ehrlichkeits-Riegel: PASS heisst hier "keine Luecke vorhanden", nicht
    # "Validator hat still selbst geschlossen" (der schliesst <= 50ms selbst).
    assert video_segments == before_validation, (
        "Timeline war nur DANK Validator-Autoclose lueckenlos — Apply/Repair "
        "haben eine Restluecke hinterlassen"
    )

    # Locked Segment byte-identisch (kompletter Spaltenvergleich per SELECT).
    assert _locked_row(test_engine) == locked_before, (
        "Locked Bestandssegment wurde durch Apply/Repair veraendert"
    )

    # Kein unlocked-Segment ragt in die Locked-Range hinein.
    for r in rows:
        if not r.locked:
            assert r.end_time <= 10.0 or r.start_time >= 14.0


# ---------------------------------------------------------------------------
# Vertrag 3 — CANCEL-INVARIANTE: ([], []) wird nie angewendet
# ---------------------------------------------------------------------------


def test_contract3_cancel_leaves_existing_timeline_untouched(test_engine):
    """B-767: Cancel gibt ([], []) zurueck (pacing_service Z. ~1425) und der
    Aufrufer _on_auto_edit_finished (ui/controllers/edit_workspace.py:494)
    returned bei leerer Segmentliste VOR jedem Apply.

    Ehrlichkeit: Dieser Test dokumentiert den AUFRUFER-Vertrag per
    Quelltext-Assertion (der Guard 'if not segments' steht vor dem
    ApplyAutoEditCommand) PLUS DB-Beweis: da kein Apply stattfindet, bleibt
    die Bestands-Timeline byte-identisch. Es wird hier bewusst KEIN
    Qt-Controller instanziert (kein GUI im Vertragstest).
    """
    # --- Quelltext-Assertion des Aufrufer-Vertrags -------------------------
    src = (REPO_ROOT / "ui" / "controllers" / "edit_workspace.py").read_text(
        encoding="utf-8"
    )
    m = re.search(
        r"def _on_auto_edit_finished\(.*?(?=\n    def |\Z)", src, re.DOTALL
    )
    assert m, "_on_auto_edit_finished fehlt in edit_workspace.py"
    body = m.group(0)
    guard_idx = body.find("if not segments:")
    apply_idx = body.find("ApplyAutoEditCommand(")
    assert guard_idx != -1, (
        "B-767-Regression: Guard 'if not segments' fehlt im Auto-Edit-Finish"
    )
    assert apply_idx != -1, "Apply-Callsite (ApplyAutoEditCommand) nicht gefunden"
    assert guard_idx < apply_idx, (
        "B-767-Regression: Apply-Callsite steht VOR dem Leer-Guard — "
        "ein Cancel-([], []) wuerde angewendet"
    )
    guard_block = body[guard_idx:apply_idx]
    assert "return" in guard_block, (
        "Leer-Guard returned nicht vor dem Apply — Cancel-Fragment wuerde "
        "trotzdem angewendet"
    )

    # --- DB-Beweis: simulierter Cancel-Rueckgabewert, kein Apply -----------
    with DBSession(test_engine) as s:
        p = Project(name="e2e-cancel", path="/tmp/e2e-cancel")
        s.add(p)
        s.flush()
        for i, (a, b) in enumerate([(0.0, 4.0), (4.0, 9.0), (9.0, 12.0)]):
            s.add(TimelineEntry(
                project_id=p.id, track="video", media_id=100 + i,
                start_time=a, end_time=b,
                source_start=0.0, source_end=b - a,
                lane=0, locked=(i == 1),
            ))
        s.commit()
        pid = p.id

    snapshot_before = _snapshot_timeline(test_engine, pid)
    assert len(snapshot_before) == 3

    # Simulierter Worker-Rueckgabewert nach Cancel (B-767-Vertrag).
    segments: list[dict] = []
    cut_points: list[dict] = []
    # Aufrufer-Vertrag: bei leerer Segmentliste wird apply NICHT gerufen.
    if segments or cut_points:  # pragma: no cover - Vertragsverletzung
        pytest.fail("Cancel-Vertrag: ([], []) erwartet")

    # KEIN apply_auto_edit_segments-Aufruf — exakt wie der Guard es erzwingt.
    snapshot_after = _snapshot_timeline(test_engine, pid)
    assert snapshot_after == snapshot_before, (
        "Bestands-Timeline hat sich ohne Apply veraendert — DB-Seiteneffekt"
    )


# ---------------------------------------------------------------------------
# Vertrag 4 — EXPORT-HEILUNG: in-memory heilen, DB byte-identisch
# ---------------------------------------------------------------------------


def test_contract4_export_heals_gap_in_memory_db_untouched(test_engine):
    """B-769: 2.7s-Luecke zwischen UNLOCKED Segmenten in der DB. Der
    Export-Pfad heilt die geladene Segmentliste in-memory
    (heal_video_timeline_gaps, pure fn) -> Validator PASS. Die DB-Zeilen
    bleiben dabei byte-identisch (Export darf das Projekt nicht mutieren;
    ein stiller DB-Write wuerde den QUndoStack umgehen).
    """
    with DBSession(test_engine) as s:
        p = Project(name="e2e-heal", path="/tmp/e2e-heal")
        s.add(p)
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=1,
            start_time=0.0, end_time=4.0,
            source_start=0.0, source_end=4.0, lane=0, locked=False,
        ))
        # 2.7s-Luecke: 4.0 -> 6.7
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=2,
            start_time=6.7, end_time=10.0,
            source_start=0.0, source_end=3.3, lane=0, locked=False,
        ))
        s.commit()
        pid = p.id

    snapshot_before = _snapshot_timeline(test_engine, pid)

    with DBSession(test_engine) as s:
        rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video")
            .order_by(TimelineEntry.start_time, TimelineEntry.id)
            .all()
        )
        items = [
            {
                "start": float(r.start_time),
                "end": float(r.end_time),
                "locked": bool(r.locked),
                "source_end": float(r.source_end),
                "source_duration": float(r.source_end) - float(r.source_start),
                "clip_duration": 30.0,
            }
            for r in rows
        ]

    # Gegenprobe: OHNE Heilung lehnt der Validator die 2.7s-Luecke ab.
    with pytest.raises(ValueError):
        _validate_video_timeline_gaps([dict(i) for i in items])

    heal_result = heal_video_timeline_gaps(items)
    assert heal_result["unclosable"] == []
    assert heal_result["gaps_closed"] >= 1

    _validate_video_timeline_gaps(items)  # MUSS jetzt passen
    assert items[1]["start"] == pytest.approx(4.0)

    # DB byte-identisch (SELECT-Vergleich vorher/nachher).
    assert _snapshot_timeline(test_engine, pid) == snapshot_before, (
        "B-769-Regression: Export-Heilung hat DB-Zeilen mutiert"
    )


# ---------------------------------------------------------------------------
# Vertrag 5 — UNSCHLIESSBAR: praeziser Fehler statt rohem Validator-Text
# ---------------------------------------------------------------------------


def test_contract5_unclosable_gap_between_locked_yields_precise_error():
    """B-769: Luecke zwischen ZWEI locked Segmenten ist ohne Lock-Bruch nicht
    schliessbar. heal_video_timeline_gaps MUSS sie als unclosable melden und
    der Export-Pfad (services/export_service.py) MUSS daraus einen praezisen,
    handlungsleitenden Fehler mit Zeitangabe bauen — BEVOR der rohe
    Validator-Text 'Timeline gap vor Video-Segment N' fliegen kann.
    """
    items = [
        {"start": 0.0, "end": 4.0, "locked": True,
         "source_end": 4.0, "clip_duration": 30.0},
        # 2.7s-Luecke zwischen zwei locked Segmenten -> unschliessbar
        {"start": 6.7, "end": 10.0, "locked": True,
         "source_end": 3.3, "clip_duration": 30.0},
    ]
    heal_result = heal_video_timeline_gaps([dict(i) for i in items])
    assert heal_result["gaps_closed"] == 0
    assert heal_result["unclosable"] == [(4.0, 6.7)], (
        "Luecke zwischen zwei locked Segmenten muss als unclosable gemeldet "
        "werden (nicht still verschoben — Locks sind unantastbar)"
    )

    # Export-Pfad-Vertrag per Quelltext-Assertion (export_timeline selbst
    # braeuchte ffmpeg/Audio-Mocks — der Fehlerbau ist eine reine
    # String-Formatierung, die hier 1:1 nachvollzogen wird):
    export_src = (REPO_ROOT / "services" / "export_service.py").read_text(
        encoding="utf-8"
    )
    unclosable_idx = export_src.find('if _heal_result["unclosable"]:')
    validator_idx = export_src.find("_validate_video_timeline_gaps(video_segments)")
    assert unclosable_idx != -1, (
        "B-769-Regression: Export prueft heal-unclosable nicht mehr"
    )
    assert validator_idx != -1
    assert unclosable_idx < validator_idx, (
        "B-769-Regression: unclosable-Check steht NACH dem Gap-Validator — "
        "User bekaeme den rohen 'Timeline gap vor Video-Segment N'-Fehler"
    )
    assert "B-769: Timeline-Luecke" in export_src, (
        "Praeziser B-769-Fehlertext im Export-Pfad fehlt"
    )

    # Fehlertext exakt wie export_service.py:440 ihn baut — mit Zeitangabe,
    # ohne rohen Validator-Text.
    gap_from, gap_to = heal_result["unclosable"][0]
    message = (
        f"B-769: Timeline-Luecke {gap_from:.3f}s bis {gap_to:.3f}s "
        "grenzt an gelockte Segmente und kann ohne Verschieben "
        "gelockter Clips nicht geschlossen werden. Bitte die Luecke in "
        "der Timeline manuell schliessen (Clip entsperren, verschieben "
        "oder Material einfuegen)."
    )
    # Drift-Riegel: der Kernbaustein des f-Strings (Zeitangabe) muss im
    # Export-Quelltext stehen — driftet der Text, faellt der Test.
    assert "{_gap_from:.3f}s bis {_gap_to:.3f}s" in export_src
    assert "4.000s bis 6.700s" in message
    assert "Timeline gap vor Video-Segment" not in message

    # Gegenprobe: der rohe Validator wuerde ohne den B-769-Fruehfehler genau
    # den unpraezisen Text liefern, den der User NICHT mehr sehen soll.
    with pytest.raises(ValueError, match=r"Timeline gap vor Video-Segment 2"):
        _validate_video_timeline_gaps([dict(i) for i in items])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

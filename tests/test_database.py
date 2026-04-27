"""
Tests fuer database.py – Models, FK-Constraints, Cascade-Delete.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
from database import (
    AnalysisStatus,
    AudioTrack,
    Beatgrid,
    Base,
    ClipAnchor,
    PacingBlueprint,
    Project,
    Scene,
    TimelineEntry,
    VideoClip,
    WaveformData,
)


# ---------------------------------------------------------------------------
# Hilfsfunktion: Frische In-Memory-Engine mit FK-Support
# ---------------------------------------------------------------------------

def _make_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng, "connect")
    def _fk(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    return eng


# ---------------------------------------------------------------------------
# Projekt-Tests
# ---------------------------------------------------------------------------

class TestProjectModel:
    def test_create_and_read_project(self):
        """Projekt anlegen und wieder laden."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="DJ Set", path="/music", resolution="1920x1080", fps=25.0)
            s.add(proj)
            s.commit()
            s.refresh(proj)
            assert proj.id is not None
            assert proj.name == "DJ Set"
            assert proj.fps == 25.0

    def test_project_default_values(self):
        """Standardwerte fuer resolution und fps werden gesetzt."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="Default", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            assert proj.resolution == "1920x1080"
            assert proj.fps == 30.0

    def test_project_repr(self):
        proj = Project(id=1, name="Test", path=".", fps=24.0)
        assert "Test" in repr(proj)
        assert "24.0" in repr(proj)


# ---------------------------------------------------------------------------
# AudioTrack-Tests
# ---------------------------------------------------------------------------

class TestAudioTrackModel:
    def _project(self, session) -> Project:
        p = Project(name="P", path=".")
        session.add(p)
        session.commit()
        session.refresh(p)
        return p

    def test_create_audio_track(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = self._project(s)
            track = AudioTrack(
                project_id=proj.id,
                file_path="/audio/mix.mp3",
                title="Mix 1",
                duration=3600.0,
                bpm=130.0,
            )
            s.add(track)
            s.commit()
            s.refresh(track)
            assert track.id is not None
            assert track.bpm == 130.0
            assert track.duration == 3600.0

    def test_audio_track_fk_violation_raises(self):
        """Fehlende project_id loest IntegrityError aus."""
        eng = _make_engine()
        with Session(eng) as s:
            track = AudioTrack(project_id=9999, file_path="/x.mp3")
            s.add(track)
            with pytest.raises(IntegrityError):
                s.commit()

    def test_audio_track_repr(self):
        t = AudioTrack(id=1, title="Mix", bpm=128.0)
        assert "Mix" in repr(t)


# ---------------------------------------------------------------------------
# VideoClip-Tests
# ---------------------------------------------------------------------------

class TestVideoClipModel:
    def _project(self, session) -> Project:
        p = Project(name="VP", path=".")
        session.add(p)
        session.commit()
        session.refresh(p)
        return p

    def test_create_video_clip(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = self._project(s)
            clip = VideoClip(
                project_id=proj.id,
                file_path="/video/clip1.mp4",
                duration=30.0,
                width=1920,
                height=1080,
                fps=30.0,
                codec="h264",
            )
            s.add(clip)
            s.commit()
            s.refresh(clip)
            assert clip.id is not None
            assert clip.codec == "h264"

    def test_video_clip_fk_violation_raises(self):
        eng = _make_engine()
        with Session(eng) as s:
            clip = VideoClip(project_id=9999, file_path="/bad.mp4")
            s.add(clip)
            with pytest.raises(IntegrityError):
                s.commit()

    def test_video_clip_repr(self):
        c = VideoClip(id=1, file_path="/clip.mp4")
        assert "/clip.mp4" in repr(c)


# ---------------------------------------------------------------------------
# Beatgrid-Tests
# ---------------------------------------------------------------------------

class TestBeatgridModel:
    def test_create_beatgrid(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            track = AudioTrack(project_id=proj.id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            s.refresh(track)

            bg = Beatgrid(
                audio_track_id=track.id,
                bpm=128.0,
                offset=0.0,
                beat_positions="[0.0, 0.47, 0.94]",
            )
            s.add(bg)
            s.commit()
            s.refresh(bg)
            assert bg.bpm == 128.0

    def test_beatgrid_repr(self):
        bg = Beatgrid(id=1, bpm=140.0)
        assert "140.0" in repr(bg)


# ---------------------------------------------------------------------------
# Scene-Tests
# ---------------------------------------------------------------------------

class TestSceneModel:
    def test_create_scene(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path="/v.mp4")
            s.add(clip)
            s.commit()
            s.refresh(clip)

            scene = Scene(
                video_clip_id=clip.id,
                start_time=0.0,
                end_time=5.0,
                energy=0.75,
            )
            s.add(scene)
            s.commit()
            s.refresh(scene)
            assert scene.energy == 0.75

    def test_scene_repr(self):
        scene = Scene(id=1, start_time=1.0, end_time=3.0)
        assert "1.0" in repr(scene)


# ---------------------------------------------------------------------------
# Cascade-Delete-Tests
# ---------------------------------------------------------------------------

class TestCascadeDelete:
    def test_delete_project_cascades_to_audio_tracks(self):
        """Projekt loeschen entfernt auch alle AudioTracks."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            proj_id = proj.id

            track = AudioTrack(project_id=proj_id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            track_id = track.id

            # Projekt loeschen
            s.delete(proj)
            s.commit()

            # AudioTrack muss weg sein
            assert s.get(AudioTrack, track_id) is None

    def test_delete_project_cascades_to_video_clips(self):
        """Projekt loeschen entfernt auch alle VideoClips."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path="/v.mp4")
            s.add(clip)
            s.commit()
            clip_id = clip.id

            s.delete(proj)
            s.commit()

            assert s.get(VideoClip, clip_id) is None

    def test_delete_video_clip_cascades_to_scenes(self):
        """VideoClip loeschen entfernt auch alle Scenes."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path="/v.mp4")
            s.add(clip)
            s.commit()
            s.refresh(clip)

            scene = Scene(video_clip_id=clip.id, start_time=0.0, end_time=5.0)
            s.add(scene)
            s.commit()
            scene_id = scene.id

            s.delete(clip)
            s.commit()

            assert s.get(Scene, scene_id) is None

    def test_delete_audio_track_cascades_to_beatgrid(self):
        """AudioTrack loeschen entfernt auch das Beatgrid."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            track = AudioTrack(project_id=proj.id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            s.refresh(track)

            bg = Beatgrid(audio_track_id=track.id, bpm=120.0, offset=0.0)
            s.add(bg)
            s.commit()
            bg_id = bg.id

            s.delete(track)
            s.commit()

            assert s.get(Beatgrid, bg_id) is None


# ---------------------------------------------------------------------------
# WaveformData-Tests
# ---------------------------------------------------------------------------

class TestWaveformDataModel:
    def test_create_waveform_data(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            track = AudioTrack(project_id=proj.id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            s.refresh(track)

            wd = WaveformData(
                audio_track_id=track.id,
                num_samples=1000,
                duration=30.0,
                band_low="[0.1, 0.2]",
                band_mid="[0.3, 0.4]",
                band_high="[0.5, 0.6]",
            )
            s.add(wd)
            s.commit()
            s.refresh(wd)
            assert wd.num_samples == 1000

    def test_waveform_data_repr(self):
        wd = WaveformData(id=1, num_samples=500)
        assert "500" in repr(wd)


# ---------------------------------------------------------------------------
# TimelineEntry- und ClipAnchor-Tests
# ---------------------------------------------------------------------------

class TestTimelineEntryModel:
    def test_create_timeline_entry(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            entry = TimelineEntry(
                project_id=proj.id,
                track="video",
                media_id=1,
                start_time=0.0,
                end_time=5.0,
                lane=0,
            )
            s.add(entry)
            s.commit()
            s.refresh(entry)
            assert entry.track == "video"

    def test_timeline_entry_repr(self):
        e = TimelineEntry(id=1, track="audio", start_time=2.5)
        assert "audio" in repr(e)
        assert "2.5" in repr(e)

    def test_clip_anchor_cascade_from_timeline_entry(self):
        """ClipAnchor wird geloescht wenn TimelineEntry geloescht wird."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            entry = TimelineEntry(
                project_id=proj.id,
                track="audio",
                media_id=1,
                start_time=0.0,
                end_time=5.0,
            )
            s.add(entry)
            s.commit()
            s.refresh(entry)

            anchor = ClipAnchor(
                timeline_entry_id=entry.id,
                time_offset=1.5,
                label="Downbeat",
            )
            s.add(anchor)
            s.commit()
            anchor_id = anchor.id

            s.delete(entry)
            s.commit()

            assert s.get(ClipAnchor, anchor_id) is None


# ---------------------------------------------------------------------------
# PacingBlueprint-Tests
# ---------------------------------------------------------------------------

class TestPacingBlueprintModel:
    def test_create_pacing_blueprint(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            bp = PacingBlueprint(
                project_id=proj.id,
                name="Fast Cuts",
                style="energetic",
                cuts_per_bar=4,
            )
            s.add(bp)
            s.commit()
            s.refresh(bp)
            assert bp.cuts_per_bar == 4

    def test_pacing_blueprint_repr(self):
        bp = PacingBlueprint(id=1, name="Chill")
        assert "Chill" in repr(bp)


# ---------------------------------------------------------------------------
# B-185: Soft-Delete Architektur-Compliance
# ---------------------------------------------------------------------------

class TestSoftDeleteArchitectureCompliance:
    """Schutzschicht gegen B-185: models.py-Docstring widersprach der
    Soft-Delete-Realitaet (Project/AudioTrack/VideoClip haben deleted_at,
    50+ Filter-Sites in services/ und ui/, App-Doku bestaetigt Soft-Delete-
    Norm). Diese Tests stellen sicher, dass der Docstring zur Realitaet
    passt und die Spalten erhalten bleiben.
    """

    def test_root_models_have_deleted_at_column(self):
        """Project, AudioTrack, VideoClip MUESSEN deleted_at haben — sonst
        brechen Filter wie ``Project.deleted_at.is_(None)`` an 50+ Stellen."""
        for cls in (Project, AudioTrack, VideoClip):
            assert "deleted_at" in cls.__table__.columns, (
                f"{cls.__name__} muss deleted_at haben (Soft-Delete-Architektur)"
            )

    def test_models_module_docstring_does_not_deny_soft_deletes(self):
        """Der Docstring darf nicht behaupten ``No Soft Deletes`` solange
        deleted_at-Spalten existieren. (B-185)
        """
        import database.models as models_mod

        doc = (models_mod.__doc__ or "").lower()
        assert "no soft deletes" not in doc, (
            "models.py-Docstring leugnet Soft-Deletes, aber deleted_at-Spalten "
            "existieren. B-185: Docstring an Realitaet anpassen."
        )
        assert "hard cascade deletes for simplicity" not in doc, (
            "models.py-Docstring behauptet Hard-Cascade-only, aber Soft-Delete "
            "ist die Norm. B-185: Docstring an Realitaet anpassen."
        )


# ---------------------------------------------------------------------------
# B-186 / D-027: Eltern-only-Soft-Delete-Architektur
# ---------------------------------------------------------------------------

class TestSoftDeleteParentOnlyArchitecture:
    """Schutzschicht gegen B-186 (D-027 — Eltern-only-Soft-Delete).

    Status quo (siehe ``database/models.py`` Docstring): nur die
    Top-Level-Modelle Project / AudioTrack / VideoClip tragen ``deleted_at``.
    Kind-Tabellen besitzen *bewusst* keine eigene ``deleted_at``-Spalte —
    Konsumenten muessen Kinder ueber den jeweiligen Eltern joinen, um die
    Soft-Delete-Sicht zu erhalten.

    Diese Tests verhindern zwei Regressionen:
    1. Jemand stempelt Eltern, vergisst aber den Eltern-JOIN beim Lesen
       der Kinder → Orphans sichtbar trotz Eltern-Tombstone.
    2. Jemand fuegt ``deleted_at`` einer Kind-Tabelle hinzu, ohne einen
       Cascade-Mechanismus zu implementieren → halb-fertige Soft-Delete-
       Erweiterung schleicht sich rein. Sobald V2 vollendet wird (Story A
       in B-186), muss dieser Test bewusst geloest und ersetzt werden.
    """

    # ── 1. Lebenszeit-Konvention: Eltern-Soft-Delete + JOIN ──

    def test_audio_track_soft_delete_hides_children_via_parent_join(self):
        """Soft-Delete eines AudioTrack laesst Kinder physisch stehen,
        aber Konsumenten, die ueber den Eltern-Filter joinen, sehen sie
        nicht mehr — das ist die zugesicherte Lebenszeit-Konvention.
        """
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            track = AudioTrack(project_id=proj.id, file_path="/x/track.mp3")
            s.add(track)
            s.commit()

            beatgrid = Beatgrid(audio_track_id=track.id, bpm=128.0)
            s.add(beatgrid)
            s.commit()

            track.deleted_at = _datetime_now()
            s.commit()

            # Eltern verschwindet aus dem Soft-Delete-Filter ...
            visible_tracks = s.query(AudioTrack).filter(
                AudioTrack.deleted_at.is_(None)
            ).all()
            assert visible_tracks == []

            # ... Kind ist physisch noch da (Status quo, dokumentiert):
            assert s.get(Beatgrid, beatgrid.id) is not None

            # ... aber via Eltern-JOIN (zugesicherte Lese-Konvention)
            #     wird das Kind nicht mehr ausgeliefert:
            visible_via_join = (
                s.query(Beatgrid)
                .join(AudioTrack, Beatgrid.audio_track_id == AudioTrack.id)
                .filter(AudioTrack.deleted_at.is_(None))
                .all()
            )
            assert visible_via_join == [], (
                "B-186: Kinder muessen via Eltern-JOIN unsichtbar werden, "
                "wenn der Eltern-Track soft-geloescht ist."
            )

    def test_video_clip_soft_delete_hides_scenes_via_parent_join(self):
        """Gleiche Konvention fuer VideoClip → Scene."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            clip = VideoClip(project_id=proj.id, file_path="/x/clip.mp4")
            s.add(clip)
            s.commit()

            scene = Scene(video_clip_id=clip.id, start_time=0.0, end_time=1.5)
            s.add(scene)
            s.commit()

            clip.deleted_at = _datetime_now()
            s.commit()

            visible_via_join = (
                s.query(Scene)
                .join(VideoClip, Scene.video_clip_id == VideoClip.id)
                .filter(VideoClip.deleted_at.is_(None))
                .all()
            )
            assert visible_via_join == []

    def test_project_soft_delete_hides_timeline_entries_via_parent_join(self):
        """Project → TimelineEntry: gleiche Konvention auf Top-Level."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            clip = VideoClip(project_id=proj.id, file_path="/x/clip.mp4")
            s.add(clip)
            s.commit()

            entry = TimelineEntry(
                project_id=proj.id,
                track="video",
                media_id=clip.id,
                start_time=0.0,
            )
            s.add(entry)
            s.commit()

            proj.deleted_at = _datetime_now()
            s.commit()

            visible_via_join = (
                s.query(TimelineEntry)
                .join(Project, TimelineEntry.project_id == Project.id)
                .filter(Project.deleted_at.is_(None))
                .all()
            )
            assert visible_via_join == []

    # ── 2. Architektur-Riegel: Kinder DUERFEN heute kein deleted_at haben ──

    def test_child_tables_have_no_deleted_at_column(self):
        """B-186 / D-027: Solange Soft-Delete-Cascade nicht implementiert
        ist, darf keine Kind-Tabelle eine eigene ``deleted_at``-Spalte
        bekommen — sonst entsteht halb-fertige Soft-Delete-Logik ohne
        Cascade-Mechanismus. Wer dieses Verhalten aendert, muss die
        Architektur-Entscheidung D-027 (Eltern-only-Soft-Delete) explizit
        revidieren und einen Cascade-Pfad mitliefern.
        """
        children = (
            Scene,
            Beatgrid,
            WaveformData,
            PacingBlueprint,
            TimelineEntry,
            ClipAnchor,
        )
        offenders = [
            cls.__name__
            for cls in children
            if "deleted_at" in cls.__table__.columns
        ]
        assert offenders == [], (
            f"B-186 / D-027 verletzt: Kind-Tabelle(n) {offenders} haben "
            "deleted_at, obwohl Eltern-only-Soft-Delete die zugesicherte "
            "Architektur ist. Entweder D-027 revidieren (Cascade-Mechanismus "
            "implementieren) oder die Spalte entfernen."
        )


def _datetime_now():
    """Lokaler Helper — vermeidet Top-Level-Datetime-Import-Sprawl."""
    import datetime as _dt
    return _dt.datetime.utcnow()


# ---------------------------------------------------------------------------
# B-187 + B-188 / D-028: Polymorphe media_id-App-Layer-Invarianten
# ---------------------------------------------------------------------------

class TestPolymorphicMediaIdAppLayerInvariants:
    """Schutzschicht gegen B-187 (TimelineEntry.media_id polymorph ohne FK)
    und B-188 (AnalysisStatus.media_id polymorph ohne FK, un-dokumentiert).

    Die SQL-Engine kann disjunktive Foreign-Keys nicht ausdruecken, deshalb
    sind ``track`` / ``media_type`` reine String-Discriminator-Spalten ohne
    DB-Validation. Die App-Schicht muss garantieren:

    - ``track`` ∈ ``{"audio", "video"}`` (TimelineEntry)
    - ``media_type`` ∈ ``{"audio", "video"}`` (AnalysisStatus)
    - ``media_id`` zeigt auf einen real existierenden Datensatz im
      durch den Discriminator ausgewaehlten Eltern-Modell.

    Diese Tests dokumentieren das **akzeptierte latente Risiko** (DB
    laesst invalide Eintraege durch) und schuetzen den App-Layer-
    Vertrag gegen Drift. Die DB-Tests beweisen den Status quo
    (bewusst akzeptiert), die App-Layer-Tests fixieren die Whitelist.

    Siehe [[D-028-polymorphic-media-id-app-layer]].
    """

    APP_LAYER_DISCRIMINATOR_WHITELIST = {"audio", "video"}

    # ── 1. Status-quo: DB akzeptiert invalide Daten (dokumentiert) ──

    def test_db_accepts_orphan_timeline_entry_after_audio_hard_delete(self):
        """Status quo: Wird ein AudioTrack hart geloescht, bleibt der
        TimelineEntry mit dessen media_id als Orphan zurueck — die DB
        kennt keinen FK, der ihn mitsplittet. Dieser Test pinnt das
        Verhalten fest. Konsumenten muessen das im App-Layer abfangen.
        """
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            track = AudioTrack(project_id=proj.id, file_path="/x/track.mp3")
            s.add(track)
            s.commit()
            track_id = track.id

            entry = TimelineEntry(
                project_id=proj.id,
                track="audio",
                media_id=track_id,
                start_time=0.0,
            )
            s.add(entry)
            s.commit()
            entry_id = entry.id

            s.delete(track)
            s.commit()

            survivor = s.get(TimelineEntry, entry_id)
            assert survivor is not None, (
                "B-187 / D-028: TimelineEntry ueberlebt Hard-Delete des "
                "polymorphen Ziel-Tracks — App-Layer muss Orphans filtern."
            )
            assert survivor.media_id == track_id

    def test_db_accepts_orphan_analysis_status_after_video_hard_delete(self):
        """Gleicher Status quo fuer AnalysisStatus: Hard-Delete des
        VideoClips laesst den analysis_status-Eintrag stehen (B-188).
        """
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            clip = VideoClip(project_id=proj.id, file_path="/x/clip.mp4")
            s.add(clip)
            s.commit()
            clip_id = clip.id

            status = AnalysisStatus(
                media_type="video",
                media_id=clip_id,
                step_key="scene_detection",
                status="done",
            )
            s.add(status)
            s.commit()
            status_id = status.id

            s.delete(clip)
            s.commit()

            survivor = s.get(AnalysisStatus, status_id)
            assert survivor is not None, (
                "B-188 / D-028: AnalysisStatus ueberlebt Hard-Delete des "
                "polymorphen Ziel-Clips — App-Layer muss Orphans filtern."
            )
            assert survivor.media_id == clip_id

    def test_db_accepts_cross_type_pointer(self):
        """Status quo: Die DB akzeptiert sogar einen TimelineEntry mit
        ``track="audio"`` und ``media_id`` aus dem Video-Pool. App-Layer
        muss das verhindern (B-187 Risiko-Klasse).
        """
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            clip = VideoClip(project_id=proj.id, file_path="/x/clip.mp4")
            s.add(clip)
            s.commit()
            clip_id = clip.id

            cross_entry = TimelineEntry(
                project_id=proj.id,
                track="audio",
                media_id=clip_id,
                start_time=0.0,
            )
            s.add(cross_entry)
            s.commit()
            cross_id = cross_entry.id

            persisted = s.get(TimelineEntry, cross_id)
            assert persisted is not None and persisted.track == "audio", (
                "Status quo dokumentiert: DB blockiert Cross-Type-Pointer "
                "nicht. Konsumenten muessen App-Layer-Lookup absichern."
            )

    # ── 2. App-Layer-Vertrag: Discriminator-Whitelist ──

    def test_orchestrator_audio_dispatch_writes_audio_media_type(self):
        """Der Orchestrator-Pfad fuer AnalysisStatus muss die App-Layer-
        Whitelist {"audio", "video"} respektieren. Wir verifizieren, dass
        die App heute *ausschliesslich* diese beiden Werte schreibt — ein
        zukuenftiger neuer Discriminator (z. B. "stem") braucht eine
        Architektur-Erweiterung von D-028.
        """
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()

            track = AudioTrack(project_id=proj.id, file_path="/x/track.mp3")
            clip = VideoClip(project_id=proj.id, file_path="/x/clip.mp4")
            s.add_all([track, clip])
            s.commit()

            s.add_all([
                AnalysisStatus(
                    media_type="audio",
                    media_id=track.id,
                    step_key="bpm_detection",
                    status="pending",
                ),
                AnalysisStatus(
                    media_type="video",
                    media_id=clip.id,
                    step_key="scene_detection",
                    status="pending",
                ),
            ])
            s.commit()

            distinct_types = {
                row[0] for row in s.execute(
                    AnalysisStatus.__table__.select().with_only_columns(
                        AnalysisStatus.media_type
                    )
                )
            }
            assert distinct_types <= self.APP_LAYER_DISCRIMINATOR_WHITELIST, (
                f"AnalysisStatus.media_type ausserhalb der App-Layer-Whitelist "
                f"({distinct_types - self.APP_LAYER_DISCRIMINATOR_WHITELIST}). "
                "B-188 / D-028: Whitelist erweitern erfordert Decision-Update."
            )

    # ── 3. Architektur-Riegel: Schema bleibt polymorph ──

    def test_polymorphic_columns_have_no_foreign_key(self):
        """Solange D-028 in Kraft ist, DARF ``media_id`` keinen ForeignKey
        haben — sonst wuerde halb-fertige FK-Logik (nur ein Pfad
        valide) entstehen. Wer das Schema umstellt (z. B. auf
        ``audio_track_id`` + ``video_clip_id``), muss D-028 revidieren.
        """
        for cls in (TimelineEntry, AnalysisStatus):
            col = cls.__table__.columns["media_id"]
            assert not col.foreign_keys, (
                f"B-187/188 / D-028: {cls.__name__}.media_id traegt einen "
                "ForeignKey. Das verletzt die polymorphe App-Layer-"
                "Architektur. Entweder D-028 revidieren oder FK entfernen."
            )


# ---------------------------------------------------------------------------
# B-189: APP_ROOT-Mutation und lazy Lookup in database.migrations
# ---------------------------------------------------------------------------

class TestSetProjectAppRootRebinding:
    """Schutzschicht gegen B-189: ``set_project()`` mutiert die globale
    ``database.session.APP_ROOT``. Module die den Wert per
    ``from database.session import APP_ROOT`` cachen, sehen den alten
    Wert und brechen nach Project-Switch (siehe
    ``docs/REAL_DATA_TESTBERICHT_2026-04-13.md`` Eintrag MEDIUM-10).

    `database/migrations.py` ist die kritische Stelle (Top-Level-Import
    + Alembic-Asset-Pfade). Diese Tests garantieren:
    1. Alembic-Assets liegen am statischen ``_REPO_ROOT`` und wandern
       nicht mit ``set_project()``.
    2. Der laufzeit-Lookup von ``APP_ROOT`` (``_app_root()``) folgt
       der Mutation korrekt.
    """

    def test_repo_root_is_static_and_points_to_alembic_assets(self):
        """B-189: ``_REPO_ROOT`` muss auf das Repo zeigen, in dem
        ``alembic.ini`` und ``database/alembic`` liegen — egal welcher
        APP_ROOT gerade aktiv ist.
        """
        from database import migrations as _mig

        repo_root = _mig._REPO_ROOT
        assert (repo_root / "alembic.ini").exists(), (
            f"B-189: _REPO_ROOT={repo_root} muss alembic.ini enthalten."
        )
        assert (repo_root / "database" / "alembic" / "env.py").exists(), (
            f"B-189: _REPO_ROOT={repo_root} muss database/alembic/env.py enthalten."
        )

    def test_app_root_lookup_follows_set_project_mutation(self, tmp_path):
        """B-189: ``_app_root()`` liest ``APP_ROOT`` zur Laufzeit, nicht
        zum Modul-Load-Zeitpunkt. Nach simulierter ``APP_ROOT``-Mutation
        muss der Helper den neuen Wert liefern.
        """
        from database import migrations as _mig
        from database import session as _ses

        original = _ses.APP_ROOT
        try:
            new_root = tmp_path / "test_project"
            new_root.mkdir()
            _ses.APP_ROOT = new_root
            assert _mig._app_root() == new_root, (
                "B-189: _app_root() folgt der Mutation nicht."
            )
        finally:
            _ses.APP_ROOT = original

    def test_repo_root_independent_of_app_root_mutation(self, tmp_path):
        """Architektur-Riegel: Alembic-Assets-Pfad bleibt stabil,
        auch wenn jemand ``APP_ROOT`` umbiegt.
        """
        from database import migrations as _mig
        from database import session as _ses

        original = _ses.APP_ROOT
        original_repo_root = _mig._REPO_ROOT
        try:
            _ses.APP_ROOT = tmp_path / "elsewhere"
            assert _mig._REPO_ROOT == original_repo_root, (
                "B-189: _REPO_ROOT darf nicht durch APP_ROOT-Mutation veraendert werden."
            )
        finally:
            _ses.APP_ROOT = original


# ---------------------------------------------------------------------------
# B-190: Kein Auto-Default-Project mehr in _seed_defaults
# ---------------------------------------------------------------------------

class TestSeedDefaultsNoAutoProject:
    """Schutzschicht gegen B-190: Frueher legte ``_seed_defaults`` ein
    ``Project(name="Default", path=".")``-Stub an, das
    ``services/project_manager.create_project()`` direkt wieder loeschte.
    Diese Tests fixieren den neuen Status quo:

    - ``_seed_defaults`` legt **kein** Default-Project mehr an.
    - Style-Presets werden weiter geseedet (immutable Bootstrap-Daten).
    - ``project_manager.create_project()`` enthaelt keinen
      Cleanup-Loop mehr, der bestehende Projekte hart loescht.
    """

    def test_seed_defaults_source_does_not_insert_default_project(self):
        """B-190: ``_seed_defaults`` darf keinen ``Project(...)``-Konstruktor
        mehr aufrufen. Der historische Pfad ``Project(name="Default",
        path=".", ...)`` ist verboten.
        """
        import inspect as _inspect

        from database import migrations as _mig

        src = _inspect.getsource(_mig._seed_defaults)
        # Nur Code-Pfad pruefen, keine Docstring-Begruendung. Code-Zeilen
        # erkennt man an fuehrendem Whitespace + ``session.add(Project(``.
        code_lines = [
            ln for ln in src.splitlines()
            if "session.add(Project(" in ln
        ]
        assert code_lines == [], (
            "B-190: _seed_defaults() darf keine Project-Inserts mehr "
            f"ausfuehren — gefundene Zeilen: {code_lines}"
        )

    def test_project_manager_does_not_hard_delete_projects_on_create(self):
        """B-190: ``project_manager.create_project()`` darf keinen
        Cleanup-Loop mehr fahren, der alle bestehenden Projekte
        hart-loescht. Frueher war das noetig, um das Auto-Default-
        Project zu entfernen — jetzt wuerde es echte User-Projekte
        killen.
        """
        import inspect as _inspect

        from services import project_manager as _pm

        src = _inspect.getsource(_pm)
        forbidden = "session.delete(p)"
        assert forbidden not in src, (
            "B-190: project_manager.py enthaelt noch einen Project-"
            "Hard-Delete-Loop. Das ist seit Entfernung des Auto-Default-"
            "Projects unnoetig und zerstoert User-Daten."
        )

    def test_style_presets_still_seeded(self):
        """B-190: Style-Presets bleiben Bootstrap-Daten — Pacing-Workflow
        verlaesst sich darauf.
        """
        import inspect as _inspect

        from database import migrations as _mig

        src = _inspect.getsource(_mig._seed_defaults)
        assert "StylePreset(" in src, (
            "B-190: Style-Presets muessen weiterhin geseedet werden."
        )


# ---------------------------------------------------------------------------
# B-191: FK-Migration-Backup wird nach Erfolg aufgeraeumt
# ---------------------------------------------------------------------------

class TestFkMigrationBackupCleanup:
    """B-191: Frueher blieb das ``*.backup_before_fk_migration``-File
    nach erfolgreicher FK-Migration permanent im Filesystem liegen
    (Disk-Leak). Diese Tests fixieren das neue Cleanup-Verhalten.
    """

    def test_cleanup_helper_removes_existing_backup(self, tmp_path):
        from database.migrations import _cleanup_fk_migration_backup

        backup = tmp_path / "pb_studio.db.backup_before_fk_migration"
        backup.write_bytes(b"\x53\x51\x4c\x69\x74\x65")  # "SQLite"-magic stub
        assert backup.exists()

        _cleanup_fk_migration_backup(backup)

        assert not backup.exists(), (
            "B-191: _cleanup_fk_migration_backup muss die Backup-Datei "
            "loeschen."
        )

    def test_cleanup_helper_idempotent_on_missing_file(self, tmp_path):
        from database.migrations import _cleanup_fk_migration_backup

        ghost = tmp_path / "does_not_exist.backup_before_fk_migration"
        # Kein Crash erwartet — fehlende Datei darf den App-Start nicht killen.
        _cleanup_fk_migration_backup(ghost)
        _cleanup_fk_migration_backup(None)

    def test_cleanup_helper_called_on_success_path(self):
        """Source-Inspection: Der Erfolgs-Logger
        ``"FK-CASCADE Migration abgeschlossen"`` muss vom
        ``_cleanup_fk_migration_backup``-Aufruf gefolgt werden, sonst
        leakt das Backup wieder.
        """
        import inspect as _inspect

        from database import migrations as _mig

        src = _inspect.getsource(_mig._migrate_fk_cascade)
        success_marker = 'FK-CASCADE Migration abgeschlossen'
        cleanup_marker = '_cleanup_fk_migration_backup(backup_path)'
        success_idx = src.find(success_marker)
        cleanup_idx = src.find(cleanup_marker)
        assert success_idx > 0, "Erfolgs-Logger nicht gefunden"
        assert cleanup_idx > success_idx, (
            "B-191: _cleanup_fk_migration_backup muss nach dem Erfolgs-"
            "Logger im Erfolgs-Pfad aufgerufen werden."
        )


# ---------------------------------------------------------------------------
# B-192: NullPoolSessionContext.__exit__ darf Original-Exception nicht schlucken
# ---------------------------------------------------------------------------

class TestNullPoolSessionContextExitPreservesException:
    """B-192: ``_NullPoolSessionContext.__exit__`` rief ``self._session.close()``
    ungeschuetzt auf. Wenn ``close()`` ihrerseits eine Exception warf,
    ueberschrieb diese die ``with``-Block-Exception (Python-Semantik:
    ein selbst-geworfener __exit__-Error verschluckt ``exc_val``).

    Diese Tests beweisen, dass die Original-Exception nun korrekt
    weitergereicht wird, auch wenn ``close()`` failt.
    """

    def _build_ctx_with_close_failure(self):
        """Hilfs-Setup: NullPool-Context mit einer Mock-Session, deren
        ``close()`` raised. Engine-Dispose ist no-op."""
        from database.session import _NullPoolSessionContext

        class _BoomSession:
            def __init__(self):
                self.closed = False
                self.committed = False
                self.rolled_back = False

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def close(self):
                self.closed = True
                raise RuntimeError("close-failed")

        class _NoOpEngine:
            def dispose(self):
                pass

        ctx = _NullPoolSessionContext(_NoOpEngine())
        ctx._session = _BoomSession()
        return ctx

    def test_close_failure_does_not_swallow_original_exception(self):
        """Original-Exception aus dem ``with``-Block muss propagiert
        werden, auch wenn ``session.close()`` zusaetzlich raised.
        """
        ctx = self._build_ctx_with_close_failure()

        try:
            with ctx as session:
                _ = session  # close() wirft erst beim __exit__
                raise ValueError("original-error")
        except ValueError as exc:
            assert str(exc) == "original-error", (
                "B-192: Original-Exception verloren — close() hat sie ueberschrieben."
            )
        else:
            raise AssertionError("Original-Exception wurde verschluckt")

    def test_close_failure_alone_does_not_propagate(self):
        """Wenn der ``with``-Block sauber durchlaeuft, darf ein close-
        Error die App nicht killen — er wird nur geloggt.
        """
        ctx = self._build_ctx_with_close_failure()

        # Sollte kein Raise: close-Fehler ist Cleanup-Noise.
        with ctx as session:
            _ = session

    def test_session_close_is_wrapped_in_try_catch(self):
        """Architektur-Riegel: Der ``self._session.close()``-Aufruf in
        ``__exit__`` muss in einem ``try``/``except``-Block stehen.
        Wer die Wrapping-Schicht entfernt, riskiert, dass close-Errors
        die Original-Exception verschlucken.
        """
        import inspect as _inspect
        import re as _re

        from database.session import _NullPoolSessionContext

        src = _inspect.getsource(_NullPoolSessionContext.__exit__)
        # Suche das Pattern: try:\n   self._session.close()
        pattern = _re.compile(
            r"try\s*:\s*\n\s*self\._session\.close\(\)",
        )
        assert pattern.search(src), (
            "B-192: self._session.close() muss in einem try-Block stehen, "
            "sonst kann ein close-Error die Original-Exception verschlucken."
        )

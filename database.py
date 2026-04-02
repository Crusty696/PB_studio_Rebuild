import datetime as _datetime
import logging
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, event, Column, Integer, String, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Session, relationship

logger = logging.getLogger(__name__)

# Zentraler Projektpfad — alle Services importieren APP_ROOT statt relative Pfade zu nutzen
# F-019: .resolve() stellt sicher dass der Pfad immer absolut ist (unabhaengig von CWD)
APP_ROOT = Path(__file__).resolve().parent


# ======================================================================
# EngineProxy — transparenter Wrapper um die echte SQLAlchemy Engine.
# Ermoeglicht atomaren Engine-Swap bei Projektwechsel, ohne dass
# Module die ``from database import engine`` gemacht haben neu
# importiert werden muessen.
# ======================================================================

class EngineProxy:
    """Transparent proxy that forwards all attribute access to the real engine.

    Call ``swap(new_engine)`` to atomically replace the inner engine and
    dispose the old one.  All existing references (``Session(engine)``,
    ``Base.metadata.create_all(engine)``) keep working because they go
    through this proxy.
    """

    def __init__(self, real_engine):
        object.__setattr__(self, '_engine', real_engine)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_engine'), name)

    def swap(self, new_engine):
        """Atomically replace the wrapped engine; dispose the old one."""
        old = object.__getattribute__(self, '_engine')
        object.__setattr__(self, '_engine', new_engine)
        try:
            old.dispose()
        except Exception as e:
            logger.warning("EngineProxy.swap() — old.dispose() fehlgeschlagen: %s", e)

    # Explicit delegates needed for SQLAlchemy internals that bypass __getattr__:
    def connect(self, *a, **kw):
        return object.__getattribute__(self, '_engine').connect(*a, **kw)

    def begin(self, *a, **kw):
        return object.__getattribute__(self, '_engine').begin(*a, **kw)

    def dispose(self, *a, **kw):
        return object.__getattribute__(self, '_engine').dispose(*a, **kw)

    @property
    def dialect(self):
        return object.__getattribute__(self, '_engine').dialect

    @property
    def url(self):
        return object.__getattribute__(self, '_engine').url

    @property
    def pool(self):
        return object.__getattribute__(self, '_engine').pool


def _make_engine(db_path: Path):
    """Create a configured SQLAlchemy engine with FK/WAL/sync pragmas.

    The pragma setup is done via an event listener attached to each new
    engine instance (not a global decorator).
    """
    eng = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 60},
        # Pool fuer schnelle Reads. Worker nutzen nullpool_session() fuer Writes.
        # pool_size=5 idle Connections, max_overflow=15 Burst-Kapazitaet fuer
        # Batch-Operationen (z.B. 10+ Video-Clips gleichzeitig laden).
        pool_size=5,
        max_overflow=15,
        pool_timeout=60,
        pool_recycle=300,
    )

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # WAL-optimiert: fsync nur bei Checkpoint
        cursor.execute("PRAGMA busy_timeout=120000")  # 120s warten bei locked DB (Multi-Worker + lange Analyse)
        cursor.close()

    return eng


# Datenbank-Engine: SQLite-Datei im Projektordner
# check_same_thread=False ist ZWINGEND noetig, weil QThread-Workers
# auf dieselbe Engine zugreifen (SQLite verbietet sonst Cross-Thread-Zugriff).
engine = EngineProxy(_make_engine(APP_ROOT / 'pb_studio.db'))


def get_raw_engine():
    """Return the ACTUAL SQLAlchemy engine (not the proxy).

    Needed for ``sqlalchemy.inspect()`` which requires a real engine instance.
    """
    return object.__getattribute__(engine, '_engine')


def nullpool_session():
    """Erzeugt eine SQLAlchemy Session mit NullPool-Engine (frische Connection).

    Verwendung fuer Worker-Threads die in die DB schreiben und dabei
    "database is locked" Fehler durch den Connection Pool bekommen.
    Die NullPool-Engine erstellt eine frische Connection pro Session und
    schliesst sie sofort nach dem Commit — kein Pooling, kein Lock-Halten.

    Muster (identisch mit timeline_service._do_apply_segments):
        with nullpool_session() as session:
            track = session.get(AudioTrack, track_id)
            track.bpm = 120.0
            session.commit()

    Die Engine wird automatisch disposed wenn der Context-Manager endet.
    """
    from sqlalchemy import create_engine as _ce, event as _ev
    from sqlalchemy.pool import NullPool

    db_path = APP_ROOT / 'pb_studio.db'
    _eng = _ce(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )

    @_ev.listens_for(_eng, "connect")
    def _set_pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.close()

    return _NullPoolSessionContext(_eng)


class _NullPoolSessionContext:
    """Context-Manager fuer NullPool-Sessions. Disposed die Engine beim Verlassen."""

    def __init__(self, eng):
        self._eng = eng
        self._session = None

    def __enter__(self):
        self._session = Session(self._eng)
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._session is not None:
                self._session.close()
        finally:
            self._eng.dispose()
        return False


def get_active_project_id() -> int:
    """Gibt die ID des aktiven Projekts zurueck (erstes in der DB, Default=1)."""
    try:
        from sqlalchemy.orm import Session as _S
        with _S(engine) as s:
            proj = s.query(Project).first()
            return proj.id if proj else 1
    except Exception:
        return 1


def _patch_service_paths(project_path: Path):
    """Patch module-level path constants in service modules to point at the
    new project folder.  Uses ``sys.modules`` so already-imported modules
    get updated in-place.
    """
    patches = {
        "services.video_service": {"PROXY_DIR": project_path / "storage" / "proxies"},
        "services.ai_audio_service": {"STEMS_DIR": project_path / "storage" / "stems"},
        "services.export_service": {"EXPORT_DIR": project_path / "exports"},
        "services.convert_service": {"PROXY_DIR": project_path / "storage" / "proxies"},
        "services.video_analysis_service": {"KEYFRAME_DIR": project_path / "storage" / "keyframes"},
        "services.vector_db_service": {
            "DB_DIR": project_path / "data" / "vector",
            "DB_FILE": project_path / "data" / "vector" / "embeddings.db",
            "_instance": None,  # F-030: Singleton reset on project switch
        },
    }
    for mod_name, attrs in patches.items():
        mod = sys.modules.get(mod_name)
        if mod is not None:
            for attr, value in attrs.items():
                setattr(mod, attr, value)
                logger.debug("Patched %s.%s -> %s", mod_name, attr, value)


def set_project(project_path: Path):
    """Switch the active project to *project_path*.

    - Creates a new engine via ``_make_engine``
    - Atomically swaps it into the global ``engine`` proxy
    - Updates ``APP_ROOT``
    - Patches service module-level path constants
    """
    global APP_ROOT
    project_path = Path(project_path)
    db_file = project_path / "pb_studio.db"

    new_engine = _make_engine(db_file)
    engine.swap(new_engine)
    APP_ROOT = project_path
    _patch_service_paths(project_path)
    logger.info("Projekt gewechselt: %s", project_path)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    resolution = Column(String, nullable=False, default="1920x1080")
    fps = Column(Float, nullable=False, default=30.0)

    # Relationships
    audio_tracks = relationship("AudioTrack", back_populates="project", cascade="all, delete-orphan", passive_deletes=True)
    video_clips = relationship("VideoClip", back_populates="project", cascade="all, delete-orphan", passive_deletes=True)
    # Bug-20 Fix: fehlende back_populates ergänzt
    pacing_blueprints = relationship("PacingBlueprint", back_populates="project", cascade="all, delete-orphan", passive_deletes=True)
    timeline_entries = relationship("TimelineEntry", back_populates="project", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', fps={self.fps})>"


class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    title = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    sample_rate = Column(Integer, nullable=True, default=44100)
    bpm = Column(Float, nullable=True)
    key = Column(String, nullable=True)
    energy_curve = Column(Text, nullable=True)

    # Stem-Pfade (Phase 1: AI Stem Separation)
    stem_vocals_path = Column(String, nullable=True)
    stem_drums_path = Column(String, nullable=True)
    stem_bass_path = Column(String, nullable=True)
    stem_other_path = Column(String, nullable=True)

    # Phase 4: Erweiterte Audio-Analyse
    key_confidence = Column(Float, nullable=True)       # 0.0-1.0 Confidence der Key-Erkennung
    lufs = Column(Float, nullable=True)                 # EBU R128 Integrated Loudness (dB)
    mood = Column(String, nullable=True)                # "energetic", "melancholic", "dark", ...
    genre = Column(String, nullable=True)               # "Psytrance", "Techno", "House", ...
    is_dj_mix = Column(Boolean, nullable=True, default=False)  # DJ-Mix erkannt?
    spectral_bands = Column(Text, nullable=True)        # JSON: 8-Band Frequenz-Energien

    project = relationship("Project", back_populates="audio_tracks")
    beatgrid = relationship("Beatgrid", back_populates="audio_track", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    waveform_data = relationship("WaveformData", back_populates="audio_track", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    structure_segments = relationship("StructureSegment", back_populates="audio_track", cascade="all, delete-orphan", passive_deletes=True)
    hotcues = relationship("HotCue", back_populates="audio_track", cascade="all, delete-orphan", passive_deletes=True)
    audio_video_anchors = relationship("AudioVideoAnchor", back_populates="audio_track", foreign_keys="AudioVideoAnchor.audio_track_id", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<AudioTrack(id={self.id}, title='{self.title}', bpm={self.bpm})>"


class VideoClip(Base):
    __tablename__ = "video_clips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    proxy_path = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    codec = Column(String, nullable=True)

    project = relationship("Project", back_populates="video_clips")
    scenes = relationship("Scene", back_populates="video_clip", cascade="all, delete-orphan", passive_deletes=True)
    audio_video_anchors = relationship("AudioVideoAnchor", back_populates="video_clip", foreign_keys="AudioVideoAnchor.video_clip_id", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<VideoClip(id={self.id}, path='{self.file_path}')>"


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    label = Column(String, nullable=True)
    energy = Column(Float, nullable=True)

    video_clip = relationship("VideoClip", back_populates="scenes")

    def __repr__(self):
        return f"<Scene(id={self.id}, start={self.start_time}, end={self.end_time})>"


class Beatgrid(Base):
    __tablename__ = "beatgrids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    bpm = Column(Float, nullable=False)
    offset = Column(Float, nullable=False, default=0.0)
    beat_positions = Column(Text, nullable=True)
    downbeat_positions = Column(Text, nullable=True)   # Phase 3: JSON list of downbeat timestamps
    energy_per_beat = Column(Text, nullable=True)       # Phase 3: JSON list of RMS energy per beat [0.0-1.0]

    audio_track = relationship("AudioTrack", back_populates="beatgrid")

    def __repr__(self):
        return f"<Beatgrid(id={self.id}, bpm={self.bpm})>"


class WaveformData(Base):
    """Frequenz-basierte Wellenform-Daten (Rekordbox-Style) pro Audio-Track."""
    __tablename__ = "waveform_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)

    # Anzahl der Samples (Zeitschritte) — typisch 1 pro ~23ms (hop_length=512 bei sr=22050)
    num_samples = Column(Integer, nullable=False, default=0)
    duration = Column(Float, nullable=False, default=0.0)

    # JSON-Arrays mit Amplituden [0.0 .. 1.0] pro Zeitschritt
    band_low = Column(Text, nullable=False)    # Bass: 20-250 Hz (blau)
    band_mid = Column(Text, nullable=False)    # Mitten: 250-4000 Hz (rosa/rot)
    band_high = Column(Text, nullable=False)   # Höhen: 4000-20000 Hz (weiß/gelb)

    audio_track = relationship("AudioTrack", back_populates="waveform_data")

    def __repr__(self):
        return f"<WaveformData(id={self.id}, samples={self.num_samples})>"


class PacingBlueprint(Base):
    __tablename__ = "pacing_blueprints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    style = Column(String, nullable=True)
    cuts_per_bar = Column(Integer, nullable=True, default=1)
    energy_curve = Column(Text, nullable=True)

    # Bug-20 Fix: back_populates ergänzt
    project = relationship("Project", back_populates="pacing_blueprints")

    def __repr__(self):
        return f"<PacingBlueprint(id={self.id}, name='{self.name}')>"


class AudioVideoAnchor(Base):
    __tablename__ = "audio_video_anchors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id", ondelete="CASCADE"), nullable=False)
    audio_time = Column(Float, nullable=False)
    video_time = Column(Float, nullable=False)
    anchor_type = Column(String, nullable=True, default="beat")

    # Bug-20 Fix: fehlende Relationships ergänzt + DB-19 Fix: back_populates
    audio_track = relationship("AudioTrack", back_populates="audio_video_anchors", foreign_keys=[audio_track_id])
    video_clip = relationship("VideoClip", back_populates="audio_video_anchors", foreign_keys=[video_clip_id])

    def __repr__(self):
        return f"<AudioVideoAnchor(id={self.id}, type='{self.anchor_type}')>"


class ClipAnchor(Base):
    """Ein manueller Anker-Marker auf einem Timeline-Clip (Audio oder Video).

    Wird fuer die manuelle Synchronisation genutzt: Wenn ein Audio- und ein
    Video-Clip jeweils einen Anker haben, koennen sie exakt aufeinander
    ausgerichtet werden.
    """
    __tablename__ = "clip_anchors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timeline_entry_id = Column(Integer, ForeignKey("timeline_entries.id", ondelete="CASCADE"), nullable=False)
    time_offset = Column(Float, nullable=False)  # Offset in Sekunden relativ zum Clip-Start
    label = Column(String, nullable=True, default="")
    color = Column(String, nullable=True, default="#FF3333")

    # Bug-20 Fix: Rückbeziehung zu TimelineEntry ergänzt
    timeline_entry = relationship("TimelineEntry", back_populates="anchors")

    def __repr__(self):
        return f"<ClipAnchor(id={self.id}, entry={self.timeline_entry_id}, offset={self.time_offset})>"


class AIPacingMemory(Base):
    """KI-Langzeitgedaechtnis: Speichert manuelle Schnitt-Entscheidungen fuer zukuenftige Auto-Edits.

    Wird befuellt wenn der User auf 'Als KI-Regel lernen' klickt. Die Kombination
    aus Audio-Kontext und Video-Entscheidung beeinflusst kuenftige Auto-Edits.
    """
    __tablename__ = "ai_pacing_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(String, nullable=True, default=lambda: _datetime.datetime.utcnow().isoformat())

    # ── Audio-Kontext ──
    bpm = Column(Float, nullable=True)
    bass_energy = Column(Float, nullable=True)    # 0.0-1.0
    drum_energy = Column(Float, nullable=True)    # 0.0-1.0
    overall_energy = Column(Float, nullable=True) # 0.0-1.0
    mood = Column(String, nullable=True)          # "drop", "peak", "buildup", "breakdown", "warmup"
    audio_time = Column(Float, nullable=True)     # Zeitstempel im Audio (Sekunden)

    # ── Video-Entscheidung ──
    raft_motion = Column(Float, nullable=True)       # RAFT motion score (0.0-1.0)
    siglip_tags = Column(Text, nullable=True)        # JSON: ["outdoor", "energetic", ...]
    cut_type = Column(String, nullable=True)         # "hard_cut", "crossfade", "loop", "trim"
    crossfade_duration = Column(Float, nullable=True, default=0.0)
    section_type = Column(String, nullable=True)     # "DROP", "BUILDUP", "BREAKDOWN", ...

    # ── Referenz ──
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=True)
    label = Column(String, nullable=True)

    def __repr__(self):
        return f"<AIPacingMemory(id={self.id}, bpm={self.bpm}, mood='{self.mood}')>"


class StructureSegment(Base):
    """Song-Struktur Segment (INTRO, BUILDUP, DROP, BREAKDOWN, OUTRO etc.)."""
    __tablename__ = "structure_segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)          # Sekunden
    end_time = Column(Float, nullable=False)             # Sekunden
    label = Column(String, nullable=False)               # "INTRO", "BUILDUP", "DROP", "BREAKDOWN", "OUTRO"
    energy = Column(Float, nullable=True)                # Durchschnittliche Energie 0.0-1.0
    confidence = Column(Float, nullable=True)            # Erkennungs-Confidence 0.0-1.0

    audio_track = relationship("AudioTrack", back_populates="structure_segments")

    def __repr__(self):
        return f"<StructureSegment(id={self.id}, label='{self.label}', {self.start_time:.1f}-{self.end_time:.1f})>"


class HotCue(Base):
    """Manueller Marker auf einem Audio-Track (wie Rekordbox HotCues)."""
    __tablename__ = "hotcues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    time = Column(Float, nullable=False)                 # Zeitposition in Sekunden
    label = Column(String, nullable=True, default="")    # z.B. "Drop 1", "Breakdown"
    color = Column(String, nullable=True, default="#FF3333")  # Hex-Farbe
    cue_type = Column(String, nullable=True, default="cue")   # "cue", "loop", "fade"

    audio_track = relationship("AudioTrack", back_populates="hotcues")

    def __repr__(self):
        return f"<HotCue(id={self.id}, time={self.time:.2f}, label='{self.label}')>"


class ModelRegistry(Base):
    """Registry aller installierten KI-Modelle (Ollama + HuggingFace).

    Verfolgt: Name, Quelle, Größe, letzte Nutzung, Installationsdatum, Status.
    Basis für Auto-Cleanup-Vorschläge (ungenutzte Modelle nach X Tagen).
    """
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, nullable=False, unique=True)   # "qwen2.5:7b" | "openai/whisper-large-v3"
    source = Column(String, nullable=False)                   # "ollama" | "huggingface"
    display_name = Column(String, nullable=True)
    size_mb = Column(Float, nullable=True)
    installed_at = Column(String, nullable=True)              # ISO datetime
    last_used_at = Column(String, nullable=True)              # ISO datetime
    status = Column(String, nullable=False, default="installed")  # "installed" | "downloading" | "error"
    local_path = Column(String, nullable=True)                # HF-Cache-Pfad
    metadata_json = Column(Text, nullable=True)               # JSON: Parameter, Tags, Quantisierung

    def __repr__(self):
        return f"<ModelRegistry(model_id='{self.model_id}', source='{self.source}', size={self.size_mb})>"


class AgentFeedback(Base):
    """Nutzerfeedback auf KI-Agenten-Antworten — AP-5 (AUD-12).

    Basis fuer Auto-Prompt-Optimization: Positive Beispiele werden als
    Few-Shot-Beispiele in den System-Prompt injiziert, negative werden gefiltert.

    rating:  1 = positiv (Daumen hoch), -1 = negativ (Daumen runter), 0 = neutral
    """
    __tablename__ = "agent_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(String, nullable=True, default=lambda: _datetime.datetime.utcnow().isoformat())

    # ── Kontext ──
    session_id = Column(String, nullable=True)           # Chat-Session-ID
    model_id = Column(String, nullable=True)             # "qwen2.5:7b" oder "Qwen/Qwen2.5-0.5B"
    backend = Column(String, nullable=True, default="ollama")  # "ollama" | "huggingface"

    # ── Query + Antwort ──
    user_query = Column(Text, nullable=False)            # Ursprüngliche Benutzeranfrage
    ai_response = Column(Text, nullable=False)           # KI-Antwort (JSON oder Text)
    action_name = Column(String, nullable=True)          # Erkannte Aktion (z.B. "analyze_audio")

    # ── Feedback ──
    rating = Column(Integer, nullable=False, default=0)  # 1=positiv, -1=negativ, 0=neutral
    user_comment = Column(Text, nullable=True)           # Optionaler Kommentar

    def __repr__(self):
        return f"<AgentFeedback(id={self.id}, action='{self.action_name}', rating={self.rating})>"


class StylePreset(Base):
    """Pacing Style-Preset (Techno, House, D&B etc.) mit Standard-Parametern."""
    __tablename__ = "style_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)   # "Techno", "House", etc.
    cut_rate = Column(Float, nullable=True, default=1.0)
    energy_reactivity = Column(Float, nullable=True, default=0.7)
    breakdown_behavior = Column(String, nullable=True, default="halve")  # "halve", "16beat", "none"
    min_clip_duration = Column(Float, nullable=True, default=1.0)
    max_clip_duration = Column(Float, nullable=True, default=8.0)
    beat_weight = Column(Float, nullable=True, default=1.0)
    kick_weight = Column(Float, nullable=True, default=1.0)
    snare_weight = Column(Float, nullable=True, default=0.8)
    hihat_weight = Column(Float, nullable=True, default=0.3)
    description = Column(String, nullable=True)

    def __repr__(self):
        return f"<StylePreset(id={self.id}, name='{self.name}')>"


class TimelineEntry(Base):
    """Ein Clip auf der Timeline mit Position und Spur."""
    __tablename__ = "timeline_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    track = Column(String, nullable=False)          # "audio" oder "video"
    media_id = Column(Integer, nullable=False)       # AudioTrack.id oder VideoClip.id
    start_time = Column(Float, nullable=False, default=0.0)
    end_time = Column(Float, nullable=True)
    lane = Column(Integer, nullable=False, default=0)

    # Phase 3: Crossfade-Dauer in Sekunden (0 = harter Cut)
    crossfade_duration = Column(Float, nullable=True, default=0.0)

    # Source-Offsets: Position im Quell-Video (fuer korrekten Export-Schnitt)
    source_start = Column(Float, nullable=True, default=0.0)  # Sekunden im Quell-Video
    source_end = Column(Float, nullable=True)                  # Sekunden im Quell-Video

    # Phase 3: Crossfade-Dauer und Farbkorrektur-Parameter (FFmpeg-Filter)
    brightness = Column(Float, nullable=True, default=0.0)   # -1.0 bis 1.0
    contrast = Column(Float, nullable=True, default=1.0)     # 0.0 bis 3.0

    # Bug-20 Fix: Rückbeziehungen zu Project und ClipAnchor ergänzt
    project = relationship("Project", back_populates="timeline_entries")
    anchors = relationship("ClipAnchor", back_populates="timeline_entry", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<TimelineEntry(id={self.id}, track='{self.track}', start={self.start_time})>"


def _needs_fk_cascade_migration(insp) -> bool:
    """Prüft ob ON DELETE CASCADE in den Child-Tabellen fehlt.

    Bug-16 Fix: Prüft ALLE Child-Tabellen, nicht nur 'scenes'.
    Vorher wurde nur scenes geprüft — beatgrids, waveform_data, timeline_entries
    usw. wurden nie kontrolliert, was zu verwaisten Datensätzen führte.
    """
    from sqlalchemy import text
    # Alle Child-Tabellen die ON DELETE CASCADE benötigen
    child_tables = [
        "scenes", "beatgrids", "waveform_data", "pacing_blueprints",
        "audio_video_anchors", "clip_anchors", "timeline_entries",
        "structure_segments", "hotcues",
    ]
    existing_tables = set(insp.get_table_names())
    try:
        with engine.connect() as conn:
            for tname in child_tables:
                if tname not in existing_tables:
                    continue
                result = conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE name=:tname"),
                    {"tname": tname},
                )
                row = result.fetchone()
                # Wenn sql vorhanden aber kein CASCADE → Migration nötig
                if row and row[0] and "ON DELETE CASCADE" not in row[0].upper():
                    return True
    except Exception:
        return False
    return False


def _migrate_fk_cascade():
    """Recreate alle Tabellen mit ON DELETE CASCADE (SQLite kann FK nicht ALTER).

    SICHERHEIT: Erstellt vorher ein Backup der DB-Datei.
    """
    from sqlalchemy import text
    import logging
    import shutil
    from pathlib import Path
    log = logging.getLogger(__name__)

    # Backup vor destruktiver Migration — mit Verifikation
    # Dynamischer Pfad: nutzt die URL der aktuellen Engine
    try:
        raw = get_raw_engine()
        db_path = Path(str(raw.url).replace("sqlite:///", ""))
    except Exception:
        db_path = APP_ROOT / "pb_studio.db"
    backup_path = None
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.backup_before_fk_migration")
        shutil.copy2(db_path, backup_path)
        # Sicherheits-Check: Backup muss existieren und gleiche Groesse haben
        original_size = db_path.stat().st_size
        backup_size = backup_path.stat().st_size if backup_path.exists() else 0
        if not backup_path.exists() or backup_size != original_size:
            raise RuntimeError(
                f"FK-Migration abgebrochen: Backup-Verifikation fehlgeschlagen "
                f"(original={original_size}B, backup={backup_size}B). Daten unveraendert."
            )
        log.info("FK-CASCADE Migration: Backup verifiziert (%d Bytes): %s", backup_size, backup_path)

    log.info("FK-CASCADE Migration: Recreating tables with ON DELETE CASCADE...")

    try:
        with engine.begin() as conn:
            # FK temporaer aus, damit wir Tabellen droppen koennen
            conn.execute(text("PRAGMA foreign_keys=OFF"))

            table_names = [
                "clip_anchors", "audio_video_anchors", "scenes",
                "beatgrids", "waveform_data", "pacing_blueprints",
                "timeline_entries", "structure_segments", "hotcues",
                "ai_pacing_memory", "style_presets",
                "audio_tracks", "video_clips",
            ]
            _ALLOWED_TABLES = {
                "audio_tracks", "video_clips", "scenes", "beatgrids",
                "waveform_data", "pacing_blueprints", "audio_video_anchors",
                "clip_anchors", "timeline_entries", "structure_segments",
                "hotcues", "ai_pacing_memory", "style_presets",
            }
            for tname in table_names:
                # F-012 Fix: Echte Validierung statt assert (assert wird durch -O deaktiviert)
                if tname not in _ALLOWED_TABLES:
                    raise ValueError(f"Unerlaubter Tabellenname: {tname}")
                conn.execute(text('DROP TABLE IF EXISTS "' + tname + '"'))

            # FK wieder an
            conn.execute(text("PRAGMA foreign_keys=ON"))

        # Tabellen mit korrektem Schema neu erstellen
        Base.metadata.create_all(engine)
    except Exception:
        log.error("FK-CASCADE Migration FEHLGESCHLAGEN! Backup liegt unter: %s",
                  backup_path if db_path.exists() else "N/A")
        raise
    log.info("FK-CASCADE Migration abgeschlossen.")


def init_db():
    """Erstellt alle Tabellen und ein Default-Projekt, falls noch keines existiert."""
    Base.metadata.create_all(engine)

    from sqlalchemy import inspect, text
    _raw = get_raw_engine()
    insp = inspect(_raw)

    # Migration: ON DELETE CASCADE nachrüsten (SQLite braucht Table-Rebuild)
    if _needs_fk_cascade_migration(insp):
        _migrate_fk_cascade()

    # Phase 3: Migrate existing beatgrids table (add new columns if missing)
    insp = inspect(get_raw_engine())  # refresh nach möglicher Migration
    if "beatgrids" in insp.get_table_names():
        columns = {c["name"] for c in insp.get_columns("beatgrids")}
        with engine.begin() as conn:
            if "downbeat_positions" not in columns:
                conn.execute(text("ALTER TABLE beatgrids ADD COLUMN downbeat_positions TEXT"))
            if "energy_per_beat" not in columns:
                conn.execute(text("ALTER TABLE beatgrids ADD COLUMN energy_per_beat TEXT"))

    # Migration: source_start / source_end in timeline_entries nachrüsten
    insp = inspect(get_raw_engine())
    if "timeline_entries" in insp.get_table_names():
        te_columns = {c["name"] for c in insp.get_columns("timeline_entries")}
        with engine.begin() as conn:
            if "source_start" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN source_start FLOAT DEFAULT 0.0"))
            if "source_end" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN source_end FLOAT"))

    # Bug-13 Fix: crossfade_duration / brightness / contrast in timeline_entries nachrüsten
    # Diese Spalten existieren im ORM-Modell aber fehlten in den ALTER TABLE Migrationen.
    # Ohne diesen Block crasht _apply_effects() / _on_effects_clip_changed() auf bestehenden DBs
    # mit: OperationalError: no such column: timeline_entries.crossfade_duration
    insp = inspect(get_raw_engine())
    if "timeline_entries" in insp.get_table_names():
        te_columns = {c["name"] for c in insp.get_columns("timeline_entries")}
        with engine.begin() as conn:
            if "crossfade_duration" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN crossfade_duration FLOAT DEFAULT 0.0"))
            if "brightness" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN brightness FLOAT DEFAULT 0.0"))
            if "contrast" not in te_columns:
                conn.execute(text("ALTER TABLE timeline_entries ADD COLUMN contrast FLOAT DEFAULT 1.0"))

    # Migration: ai_pacing_memory Tabelle nachrüsten (neue Spalten falls Tabelle alt)
    insp = inspect(get_raw_engine())
    if "ai_pacing_memory" in insp.get_table_names():
        ai_cols = {c["name"] for c in insp.get_columns("ai_pacing_memory")}
        with engine.begin() as conn:
            import re as _re
            _VALID_COL = _re.compile(r"^[a-z_]+$")
            _VALID_TYPE = _re.compile(r"^[A-Z]+$")
            for col_name, col_type in [
                ("bass_energy", "FLOAT"), ("drum_energy", "FLOAT"),
                ("siglip_tags", "TEXT"), ("section_type", "TEXT"),
                ("audio_track_id", "INTEGER"), ("scene_id", "INTEGER"),
            ]:
                # F-012 Fix: Echte Validierung statt assert (assert wird durch -O deaktiviert)
                if not _VALID_COL.match(col_name):
                    raise ValueError(f"Ungueltiger Spaltenname: {col_name}")
                if not _VALID_TYPE.match(col_type):
                    raise ValueError(f"Ungueltiger Spaltentyp: {col_type}")
                if col_name not in ai_cols:
                    conn.execute(text(
                        'ALTER TABLE ai_pacing_memory ADD COLUMN "' + col_name + '" ' + col_type
                    ))

    # K2 Fix: stem_*_path Spalten in audio_tracks nachrüsten
    insp = inspect(get_raw_engine())
    if "audio_tracks" in insp.get_table_names():
        at_columns = {c["name"] for c in insp.get_columns("audio_tracks")}
        with engine.begin() as conn:
            for stem_col in ["stem_vocals_path", "stem_drums_path", "stem_bass_path", "stem_other_path"]:
                if stem_col not in at_columns:
                    import re as _re2
                    if not _re2.match(r"^[a-z_]+$", stem_col):
                        logging.warning("Ungültiger Spaltenname übersprungen: %s", stem_col)
                        continue
                    conn.execute(text(f"ALTER TABLE audio_tracks ADD COLUMN {stem_col} TEXT"))

    # Phase 4: Erweiterte Audio-Analyse Spalten nachrüsten
    insp = inspect(get_raw_engine())
    if "audio_tracks" in insp.get_table_names():
        at_columns = {c["name"] for c in insp.get_columns("audio_tracks")}
        import re as _re4
        _VALID_COL4 = _re4.compile(r"^[a-z_]+$")
        _VALID_TYPE4 = _re4.compile(r"^[A-Z]+$")
        with engine.begin() as conn:
            for col_name, col_type, col_default in [
                ("key_confidence", "FLOAT", None),
                ("lufs", "FLOAT", None),
                ("mood", "TEXT", None),
                ("genre", "TEXT", None),
                ("is_dj_mix", "BOOLEAN", "0"),
                ("spectral_bands", "TEXT", None),
            ]:
                if not _VALID_COL4.match(col_name):
                    raise ValueError(f"Ungueltiger Spaltenname: {col_name}")
                if not _VALID_TYPE4.match(col_type):
                    raise ValueError(f"Ungueltiger Spaltentyp: {col_type}")
                if col_name not in at_columns:
                    stmt = f"ALTER TABLE audio_tracks ADD COLUMN {col_name} {col_type}"
                    if col_default is not None:
                        # P2-06: SQL-Injection Schutz fuer col_default
                        if not re.match(r"^[a-zA-Z0-9_.'\"-]+$", str(col_default)):
                            logger.warning("Skipping unsafe col_default: %s", col_default)
                            continue
                        stmt += f" DEFAULT {col_default}"
                    conn.execute(text(stmt))

    # Phase 4: Indizes auf neue Tabellen
    insp = inspect(get_raw_engine())
    with engine.begin() as conn:
        if "structure_segments" in insp.get_table_names():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_structure_segments_audio_track_id ON structure_segments(audio_track_id)"))
        if "hotcues" in insp.get_table_names():
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hotcues_audio_track_id ON hotcues(audio_track_id)"))

    # Phase 4: Default Style-Presets einfügen (NullPool: init_db laeuft beim Start)
    with nullpool_session() as session:
        if "style_presets" in insp.get_table_names() and not session.query(StylePreset).first():
            defaults = [
                StylePreset(name="Standard", cut_rate=1.0, energy_reactivity=0.7, breakdown_behavior="halve", description="Ausgewogener Mix"),
                StylePreset(name="Techno", cut_rate=1.2, energy_reactivity=0.9, breakdown_behavior="halve", beat_weight=1.5, kick_weight=1.5, description="Kick-betont, schnelle Cuts"),
                StylePreset(name="House", cut_rate=0.8, energy_reactivity=0.6, breakdown_behavior="halve", description="Groovy, mittleres Tempo"),
                StylePreset(name="Drum & Bass", cut_rate=1.5, energy_reactivity=0.95, breakdown_behavior="16beat", beat_weight=1.2, snare_weight=1.5, description="Schnell, Snare-fokussiert"),
                StylePreset(name="Hip-Hop", cut_rate=0.6, energy_reactivity=0.5, breakdown_behavior="none", description="Laid-back, langsame Cuts"),
                StylePreset(name="Ambient", cut_rate=0.3, energy_reactivity=0.2, breakdown_behavior="none", min_clip_duration=4.0, max_clip_duration=15.0, description="Atmosphärisch, lange Clips"),
                StylePreset(name="Minimal", cut_rate=0.7, energy_reactivity=0.4, breakdown_behavior="halve", description="Reduziert, subtile Wechsel"),
                StylePreset(name="Cinematic", cut_rate=0.5, energy_reactivity=0.6, breakdown_behavior="none", min_clip_duration=3.0, max_clip_duration=12.0, description="Filmisch, dramatische Übergänge"),
                StylePreset(name="Festival", cut_rate=1.8, energy_reactivity=1.0, breakdown_behavior="16beat", beat_weight=1.5, kick_weight=1.5, snare_weight=1.2, description="Maximum Energy, schnellste Cuts"),
            ]
            session.add_all(defaults)
            # B-003 Fix: Fehlerbehandlung für session.commit() hinzufügen
            try:
                session.commit()
            except Exception as e:
                logger.error("Fehler beim Einfügen von Style-Presets: %s", e)
                # Rollback automatisch beim Kontext-Exit

    # H5 Fix: Indizes auf Foreign-Key-Spalten erstellen (SQLite macht das nicht automatisch)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_tracks_project_id ON audio_tracks(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_video_clips_project_id ON video_clips(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scenes_video_clip_id ON scenes(video_clip_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beatgrids_audio_track_id ON beatgrids(audio_track_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waveform_data_audio_track_id ON waveform_data(audio_track_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_timeline_entries_project_id ON timeline_entries(project_id)"))
        # DB-23/24 Fix: Fehlende Indizes auf audio_video_anchors + clip_anchors
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_video_anchors_audio_track_id ON audio_video_anchors(audio_track_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audio_video_anchors_video_clip_id ON audio_video_anchors(video_clip_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_clip_anchors_timeline_entry_id ON clip_anchors(timeline_entry_id)"))
        # P2-02: UNIQUE Index auf beatgrids.audio_track_id (verhindert Duplikate)
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_beatgrids_audio_track_id ON beatgrids(audio_track_id)"))
        # Index auf ai_pacing_memory.audio_track_id (Abfrage-Performance bei vielen gelernten Regeln)
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_pacing_memory_audio_track_id ON ai_pacing_memory(audio_track_id)"))

    # AUD-11: model_registry Index
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_model_registry_source ON model_registry(source)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_model_registry_last_used ON model_registry(last_used_at)"))

    # AUD-12: agent_feedback Index (AP-5 — Auto-Prompt-Optimization)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_feedback_rating ON agent_feedback(rating)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_feedback_action ON agent_feedback(action_name)"))

    with nullpool_session() as session:
        if not session.query(Project).first():
            session.add(Project(name="Default", path=".", resolution="1920x1080", fps=30.0))
            # B-003 Fix: Fehlerbehandlung für session.commit() hinzufügen
            try:
                session.commit()
            except Exception as e:
                logger.error("Fehler beim Einfügen des Standard-Projekts: %s", e)
                # Rollback automatisch beim Kontext-Exit

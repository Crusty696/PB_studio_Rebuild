from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Session, relationship

# Datenbank-Engine: SQLite-Datei im Projektordner
engine = create_engine("sqlite:///pb_studio.db", echo=False)


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
    audio_tracks = relationship("AudioTrack", back_populates="project")
    video_clips = relationship("VideoClip", back_populates="project")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', fps={self.fps})>"


class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
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

    project = relationship("Project", back_populates="audio_tracks")
    beatgrid = relationship("Beatgrid", back_populates="audio_track", uselist=False)
    waveform_data = relationship("WaveformData", back_populates="audio_track", uselist=False)

    def __repr__(self):
        return f"<AudioTrack(id={self.id}, title='{self.title}', bpm={self.bpm})>"


class VideoClip(Base):
    __tablename__ = "video_clips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    file_path = Column(String, nullable=False)
    proxy_path = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    codec = Column(String, nullable=True)

    project = relationship("Project", back_populates="video_clips")
    scenes = relationship("Scene", back_populates="video_clip")

    def __repr__(self):
        return f"<VideoClip(id={self.id}, path='{self.file_path}')>"


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id"), nullable=False)
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
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id"), nullable=False)
    bpm = Column(Float, nullable=False)
    offset = Column(Float, nullable=False, default=0.0)
    beat_positions = Column(Text, nullable=True)

    audio_track = relationship("AudioTrack", back_populates="beatgrid")

    def __repr__(self):
        return f"<Beatgrid(id={self.id}, bpm={self.bpm})>"


class WaveformData(Base):
    """Frequenz-basierte Wellenform-Daten (Rekordbox-Style) pro Audio-Track."""
    __tablename__ = "waveform_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id"), nullable=False)

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
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    style = Column(String, nullable=True)
    cuts_per_bar = Column(Integer, nullable=True, default=1)
    energy_curve = Column(Text, nullable=True)

    def __repr__(self):
        return f"<PacingBlueprint(id={self.id}, name='{self.name}')>"


class AudioVideoAnchor(Base):
    __tablename__ = "audio_video_anchors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id"), nullable=False)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id"), nullable=False)
    audio_time = Column(Float, nullable=False)
    video_time = Column(Float, nullable=False)
    anchor_type = Column(String, nullable=True, default="beat")

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
    timeline_entry_id = Column(Integer, ForeignKey("timeline_entries.id"), nullable=False)
    time_offset = Column(Float, nullable=False)  # Offset in Sekunden relativ zum Clip-Start
    label = Column(String, nullable=True, default="")
    color = Column(String, nullable=True, default="#FF3333")

    def __repr__(self):
        return f"<ClipAnchor(id={self.id}, entry={self.timeline_entry_id}, offset={self.time_offset})>"


class TimelineEntry(Base):
    """Ein Clip auf der Timeline mit Position und Spur."""
    __tablename__ = "timeline_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    track = Column(String, nullable=False)          # "audio" oder "video"
    media_id = Column(Integer, nullable=False)       # AudioTrack.id oder VideoClip.id
    start_time = Column(Float, nullable=False, default=0.0)
    end_time = Column(Float, nullable=True)
    lane = Column(Integer, nullable=False, default=0)

    # Phase 3: Crossfade-Dauer in Sekunden (0 = harter Cut)
    crossfade_duration = Column(Float, nullable=True, default=0.0)

    # Phase 3: Farbkorrektur-Parameter (FFmpeg-Filter)
    brightness = Column(Float, nullable=True, default=0.0)   # -1.0 bis 1.0
    contrast = Column(Float, nullable=True, default=1.0)     # 0.0 bis 3.0

    def __repr__(self):
        return f"<TimelineEntry(id={self.id}, track='{self.track}', start={self.start_time})>"


def init_db():
    """Erstellt alle Tabellen und ein Default-Projekt, falls noch keines existiert."""
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if not session.query(Project).first():
            session.add(Project(name="Default", path=".", resolution="1920x1080", fps=30.0))
            session.commit()

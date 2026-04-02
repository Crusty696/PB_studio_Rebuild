import datetime as _datetime

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, relationship


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

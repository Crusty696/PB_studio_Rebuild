"""
Database models for PB Studio.

P3-NOTE: No Soft Deletes - All deletes are hard CASCADE deletes for simplicity.
For production applications with user-generated content, consider implementing
a soft-delete pattern (deleted_at timestamp column) to allow recovery.
Current design prioritizes performance and simplicity for video editing workflow.
"""
import datetime as _datetime

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, Boolean, UniqueConstraint, JSON, DateTime, Index
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
    deleted_at = Column(DateTime, nullable=True)  # P1-FIX: Soft-Delete Support

    # Relationships — P1-FIX: lazy='selectin' verhindert N+1 Queries
    # M-37 Fix: Changed from lazy='selectin' to lazy='select' (on-demand loading)
    # This avoids 4 extra SELECTs on every Project load when relationships aren't needed
    audio_tracks = relationship("AudioTrack", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')
    video_clips = relationship("VideoClip", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')
    # Bug-20 Fix: fehlende back_populates ergänzt
    pacing_blueprints = relationship("PacingBlueprint", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')
    timeline_entries = relationship("TimelineEntry", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', fps={self.fps})>"


class AudioTrack(Base):
    __tablename__ = "audio_tracks"
    __table_args__ = (
        UniqueConstraint("project_id", "file_path", name="uq_audio_tracks_project_file"),
        Index("idx_audio_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    title = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    sample_rate = Column(Integer, nullable=True, default=44100)
    bpm = Column(Float, nullable=True)
    key = Column(String, nullable=True)
    energy_curve = Column(JSON, nullable=True)  # P1.7-FIX: JSON type for automatic serialization

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
    is_dj_mix = Column(Boolean, nullable=True)  # DJ-Mix erkannt? None=unbekannt
    spectral_bands = Column(JSON, nullable=True)        # P1.7-FIX: 8-Band Frequenz-Energien
    transcription = Column(JSON, nullable=True)         # DEPRECATED: kept for DB compatibility
    deleted_at = Column(DateTime, nullable=True)       # P1-FIX: Soft-Delete Support

    # AUD-84: ML Key Detection — Modulation + Tension
    key_modulation_data = Column(JSON, nullable=True)   # P1.7-FIX: [{time, key, camelot, confidence}, ...]
    harmonic_tension_curve = Column(JSON, nullable=True)  # P1.7-FIX: [float, ...] Dissonanz pro Zeitschritt

    # P1-FIX: Lazy loading optimiert für N+1 Query Prevention
    project = relationship("Project", back_populates="audio_tracks", lazy='joined')
    beatgrid = relationship("Beatgrid", back_populates="audio_track", uselist=False, cascade="all, delete-orphan", passive_deletes=True, lazy='joined')
    waveform_data = relationship("WaveformData", back_populates="audio_track", uselist=False, cascade="all, delete-orphan", passive_deletes=True, lazy='joined')
    structure_segments = relationship("StructureSegment", back_populates="audio_track", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')
    hotcues = relationship("HotCue", back_populates="audio_track", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')
    audio_video_anchors = relationship("AudioVideoAnchor", back_populates="audio_track", foreign_keys="AudioVideoAnchor.audio_track_id", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f"<AudioTrack(id={self.id}, title='{self.title}', bpm={self.bpm})>"


class VideoClip(Base):
    __tablename__ = "video_clips"
    __table_args__ = (
        UniqueConstraint("project_id", "file_path", name="uq_video_clips_project_file"),
        Index("idx_video_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    proxy_path = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    codec = Column(String, nullable=True)
    playback_offset = Column(Float, nullable=False, default=0.0)  # F-001: Persistence für Auto-Edit Offset
    deleted_at = Column(DateTime, nullable=True)                 # P1-FIX: Soft-Delete Support

    # P1-FIX: Lazy loading optimiert
    project = relationship("Project", back_populates="video_clips", lazy='joined')
    scenes = relationship("Scene", back_populates="video_clip", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')
    audio_video_anchors = relationship("AudioVideoAnchor", back_populates="video_clip", foreign_keys="AudioVideoAnchor.video_clip_id", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f"<VideoClip(id={self.id}, path='{self.file_path}')>"


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        Index("idx_scene_video", "video_clip_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    label = Column(String, nullable=True)
    energy = Column(Float, nullable=True)

    # AUD-128: Gemma 4 Vision captioning
    ai_caption = Column(JSON, nullable=True)    # P1.7-FIX: {description, mood, motion, tags}
    ai_mood = Column(String, nullable=True)     # energetic|calm|dramatic|ambient
    ai_tags = Column(JSON, nullable=True)       # P1.7-FIX: ['tag1', 'tag2', ...]

    video_clip = relationship("VideoClip", back_populates="scenes", lazy='joined')

    def __repr__(self):
        return f"<Scene(id={self.id}, start={self.start_time}, end={self.end_time})>"


class Beatgrid(Base):
    __tablename__ = "beatgrids"
    __table_args__ = (
        Index("idx_beatgrid_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False, unique=True)
    bpm = Column(Float, nullable=False)
    offset = Column(Float, nullable=False, default=0.0)
    beat_positions = Column(JSON, nullable=True)  # P1.7-FIX: JSON list of beat timestamps
    downbeat_positions = Column(JSON, nullable=True)   # P1.7-FIX: JSON list of downbeat timestamps
    energy_per_beat = Column(JSON, nullable=True)       # P1.7-FIX: JSON list of RMS energy per beat [0.0-1.0]
    stem_weighted_energy = Column(JSON, nullable=True)  # P1.7-FIX: JSON list of stem-weighted energy per beat [0.0-1.0]

    # AUD-83: Onset Rhythm Intelligence (OnsetRhythmService)
    onset_kick_data = Column(JSON, nullable=True)    # P1.7-FIX: [[time, strength], ...]
    onset_snare_data = Column(JSON, nullable=True)   # P1.7-FIX: [[time, strength], ...]
    onset_hihat_data = Column(JSON, nullable=True)   # P1.7-FIX: [[time, strength], ...]
    syncopation_score = Column(Float, nullable=True) # 0.0 (gerade) – 1.0 (synkopiert)
    groove_template = Column(String, nullable=True)  # String is correct for template name

    audio_track = relationship("AudioTrack", back_populates="beatgrid", lazy='joined')

    def __repr__(self):
        return f"<Beatgrid(id={self.id}, bpm={self.bpm})>"


class WaveformData(Base):
    """Frequenz-basierte Wellenform-Daten (Rekordbox-Style) pro Audio-Track."""
    __tablename__ = "waveform_data"
    __table_args__ = (
        Index("idx_waveform_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Anzahl der Samples (Zeitschritte) — typisch 1 pro ~23ms (hop_length=512 bei sr=22050)
    num_samples = Column(Integer, nullable=False, default=0)
    duration = Column(Float, nullable=False, default=0.0)

    # P1.7-FIX: JSON-Arrays mit Amplituden [0.0 .. 1.0] pro Zeitschritt
    band_low = Column(JSON, nullable=False)    # Bass: 20-250 Hz (blau)
    band_mid = Column(JSON, nullable=False)    # Mitten: 250-4000 Hz (rosa/rot)
    band_high = Column(JSON, nullable=False)   # Höhen: 4000-20000 Hz (weiß/gelb)

    audio_track = relationship("AudioTrack", back_populates="waveform_data", lazy='joined')

    def __repr__(self):
        return f"<WaveformData(id={self.id}, samples={self.num_samples})>"


class PacingBlueprint(Base):
    __tablename__ = "pacing_blueprints"
    __table_args__ = (
        Index("idx_blueprint_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    style = Column(String, nullable=True)
    cuts_per_bar = Column(Integer, nullable=True, default=1)
    energy_curve = Column(JSON, nullable=True)  # P1.7-FIX: JSON array of energy values

    # Bug-20 Fix: back_populates ergänzt
    project = relationship("Project", back_populates="pacing_blueprints", lazy='joined')

    def __repr__(self):
        return f"<PacingBlueprint(id={self.id}, name='{self.name}')>"


class AudioVideoAnchor(Base):
    __tablename__ = "audio_video_anchors"
    __table_args__ = (
        Index("idx_anchor_audio", "audio_track_id"),
        Index("idx_anchor_video", "video_clip_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id", ondelete="CASCADE"), nullable=False)
    audio_time = Column(Float, nullable=False)
    video_time = Column(Float, nullable=False)
    anchor_type = Column(String, nullable=True, default="beat")

    # Bug-20 Fix: fehlende Relationships ergänzt + DB-19 Fix: back_populates
    audio_track = relationship("AudioTrack", back_populates="audio_video_anchors", foreign_keys=[audio_track_id], lazy='joined')
    video_clip = relationship("VideoClip", back_populates="audio_video_anchors", foreign_keys=[video_clip_id], lazy='joined')

    def __repr__(self):
        return f"<AudioVideoAnchor(id={self.id}, type='{self.anchor_type}')>"


class ClipAnchor(Base):
    """Ein manueller Anker-Marker auf einem Timeline-Clip (Audio oder Video).

    Wird fuer die manuelle Synchronisation genutzt: Wenn ein Audio- und ein
    Video-Clip jeweils einen Anker haben, koennen sie exakt aufeinander
    ausgerichtet werden.
    """
    __tablename__ = "clip_anchors"
    __table_args__ = (
        Index("idx_clip_anchor_entry", "timeline_entry_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timeline_entry_id = Column(Integer, ForeignKey("timeline_entries.id", ondelete="CASCADE"), nullable=False)
    time_offset = Column(Float, nullable=False)  # Offset in Sekunden relativ zum Clip-Start
    label = Column(String, nullable=True, default="")
    color = Column(String, nullable=True, default="#FF3333")

    # Bug-20 Fix: Rückbeziehung zu TimelineEntry ergänzt
    timeline_entry = relationship("TimelineEntry", back_populates="anchors", lazy='joined')

    def __repr__(self):
        return f"<ClipAnchor(id={self.id}, entry={self.timeline_entry_id}, offset={self.time_offset})>"


class AIPacingMemory(Base):
    """KI-Langzeitgedaechtnis: Speichert manuelle Schnitt-Entscheidungen fuer zukuenftige Auto-Edits.

    Wird befuellt wenn der User auf 'Als KI-Regel lernen' klickt. Die Kombination
    aus Audio-Kontext und Video-Entscheidung beeinflusst kuenftige Auto-Edits.
    """
    __tablename__ = "ai_pacing_memory"
    __table_args__ = (
        Index("idx_pacing_memory_audio", "audio_track_id"),
        Index("idx_pacing_memory_scene", "scene_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=True, default=lambda: _datetime.datetime.utcnow())

    # ── Audio-Kontext ──
    bpm = Column(Float, nullable=True)
    bass_energy = Column(Float, nullable=True)    # 0.0-1.0
    drum_energy = Column(Float, nullable=True)    # 0.0-1.0
    overall_energy = Column(Float, nullable=True) # 0.0-1.0
    mood = Column(String, nullable=True)          # "drop", "peak", "buildup", "breakdown", "warmup"
    audio_time = Column(Float, nullable=True)     # Zeitstempel im Audio (Sekunden)

    # ── Video-Entscheidung ──
    raft_motion = Column(Float, nullable=True)       # RAFT motion score (0.0-1.0)
    siglip_tags = Column(JSON, nullable=True)        # P1.7-FIX: ["outdoor", "energetic", ...]
    cut_type = Column(String, nullable=True)         # "hard_cut", "crossfade", "loop", "trim"
    crossfade_duration = Column(Float, nullable=True, default=0.0)
    section_type = Column(String, nullable=True)     # "DROP", "BUILDUP", "BREAKDOWN", ...

    # ── Referenz ──
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="SET NULL"), nullable=True)
    label = Column(String, nullable=True)

    def __repr__(self):
        return f"<AIPacingMemory(id={self.id}, bpm={self.bpm}, mood='{self.mood}')>"


class StructureSegment(Base):
    """Song-Struktur Segment (INTRO, BUILDUP, DROP, BREAKDOWN, OUTRO etc.)."""
    __tablename__ = "structure_segments"
    __table_args__ = (
        Index("idx_structure_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)          # Sekunden
    end_time = Column(Float, nullable=False)             # Sekunden
    label = Column(String, nullable=False)               # "INTRO", "BUILDUP", "DROP", "BREAKDOWN", "OUTRO"
    energy = Column(Float, nullable=True)                # Durchschnittliche Energie 0.0-1.0
    confidence = Column(Float, nullable=True)            # Erkennungs-Confidence 0.0-1.0

    audio_track = relationship("AudioTrack", back_populates="structure_segments", lazy='joined')

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

    audio_track = relationship("AudioTrack", back_populates="hotcues", lazy='joined')

    def __repr__(self):
        return f"<HotCue(id={self.id}, time={self.time:.2f}, label='{self.label}')>"


class ModelRegistry(Base):
    """Registry aller installierten KI-Modelle (Ollama + HuggingFace).

    Verfolgt: Name, Quelle, Größe, letzte Nutzung, Installationsdatum, Status.
    Basis für Auto-Cleanup-Vorschläge (ungenutzte Modelle nach X Tagen).
    """
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, nullable=False, unique=True)   # "gemma4:e4b" | "google/siglip-so400m-patch14-384"
    source = Column(String, nullable=False)                   # "ollama" | "huggingface"
    display_name = Column(String, nullable=True)
    size_mb = Column(Float, nullable=True)
    installed_at = Column(DateTime, nullable=True)            # M-38 Fix: DateTime instead of String
    last_used_at = Column(DateTime, nullable=True)            # M-38 Fix: DateTime instead of String
    status = Column(String, nullable=False, default="installed")  # "installed" | "downloading" | "error"
    local_path = Column(String, nullable=True)                # HF-Cache-Pfad
    metadata_json = Column(JSON, nullable=True)               # P1.7-FIX: Parameter, Tags, Quantisierung

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
    created_at = Column(DateTime, nullable=True, default=lambda: _datetime.datetime.utcnow())

    # ── Kontext ──
    session_id = Column(String, nullable=True)           # Chat-Session-ID
    model_id = Column(String, nullable=True)             # "gemma4:e4b" oder "google/gemma-4-e4b"
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
    # M-39 LIMITATION: media_id has no FK constraint because it's polymorphic (AudioTrack OR VideoClip)
    # LOW-17 AUDIT: No FK on media_id — referential integrity is enforced at the application layer.
    # TODO: Redesign with audio_track_id + video_clip_id nullable FKs + CHECK constraint
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
    project = relationship("Project", back_populates="timeline_entries", lazy='joined')
    anchors = relationship("ClipAnchor", back_populates="timeline_entry", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f"<TimelineEntry(id={self.id}, track='{self.track}', start={self.start_time})>"


class AnalysisStatus(Base):
    """Status-Tracking fuer Daten-Analyse-Schritte pro Medien-Datei — VAD-36.

    Ermoeglicht Persistenz des Analyse-Fortschritts (scene_detection, bpm_detection, etc.)
    ueber App-Neustarts hinweg. Verhindert Doppel-Analysen und bietet Basis fuer UI-Dashboard.
    """
    __tablename__ = "analysis_status"
    __table_args__ = (
        UniqueConstraint("media_type", "media_id", "step_key", name="uq_analysis_status_media_step"),
        Index("idx_analysis_media", "media_type", "media_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_type = Column(String, nullable=False)              # "video" | "audio"
    media_id = Column(Integer, nullable=False)               # FK to video_clips.id or audio_tracks.id
    step_key = Column(String, nullable=False)                # "scene_detection", "bpm_detection", etc.
    status = Column(String, nullable=False, default="pending")  # "pending" | "running" | "done" | "error"
    value_summary = Column(JSON, nullable=True)              # Summary of results, e.g. {"scenes": 12, "avg_motion": 0.73}
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AnalysisStatus(id={self.id}, media_type='{self.media_type}', media_id={self.media_id}, step='{self.step_key}', status='{self.status}')>"


class StructStyleBucket(Base):
    """Stil-Cluster (Buckets) fuer Video-Szenen — Phase 3.
    
    Wird durch StyleClusterer (HDBSCAN) erstellt. Neue Clips werden dem
    naechsten Centroid zugewiesen.
    """
    __tablename__ = "struct_style_bucket"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    centroid_embedding = Column(JSON, nullable=False)  # P1.7-FIX: JSON array for embedding
    member_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: _datetime.datetime.utcnow())
    enricher_version = Column(String, nullable=False, default="1.0.0")
    active = Column(Boolean, nullable=False, default=True)

    clip_tags = relationship("StructClipTags", back_populates="style_bucket")

    def __repr__(self):
        return f"<StructStyleBucket(id={self.id}, name='{self.name}', count={self.member_count})>"


class StructClipTags(Base):
    """Anreicherungs-Daten fuer eine Video-Szene (Role, Refined Mood, Style)."""
    __tablename__ = "struct_clip_tags"

    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String, nullable=False)
    role_confidence = Column(Float, nullable=False, default=1.0)
    mood_refined = Column(String, nullable=False)
    mood_confidence = Column(Float, nullable=False, default=1.0)
    style_bucket_id = Column(Integer, ForeignKey("struct_style_bucket.id"), nullable=False)
    style_distance = Column(Float, nullable=False, default=0.0)
    enriched_at = Column(DateTime, nullable=False, default=lambda: _datetime.datetime.utcnow())
    enricher_version = Column(String, nullable=False, default="1.0.0")

    scene = relationship("Scene")
    style_bucket = relationship("StructStyleBucket", back_populates="clip_tags")

    def __repr__(self):
        return f"<StructClipTags(scene_id={self.scene_id}, role='{self.role}', mood='{self.mood_refined}')>"


class StructCompatEdge(Base):
    """Kompatibilitaets-Graph Kanten zwischen Video-Szenen."""
    __tablename__ = "struct_compat_edge"

    scene_id_a = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True)
    scene_id_b = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True)
    cosine_similarity = Column(Float, nullable=False)
    rank_in_a = Column(Integer, nullable=False)

    def __repr__(self):
        return f"<StructCompatEdge(a={self.scene_id_a}, b={self.scene_id_b}, sim={self.cosine_similarity:.3f})>"


class MemPacingRun(Base):
    """Represents a single automated pacing run for a project."""
    __tablename__ = "mem_pacing_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=lambda: _datetime.datetime.utcnow())
    completed_at = Column(DateTime, nullable=True)
    is_dj_mix = Column(Boolean, nullable=False, default=False)
    total_duration_sec = Column(Float, nullable=False, default=0.0)
    total_cuts = Column(Integer, nullable=False, default=0)
    agent_version = Column(String, nullable=False, default="1.0.0")
    weights_profile = Column(String, nullable=False, default="default")
    user_rating = Column(Integer, nullable=True)
    user_notes = Column(Text, nullable=True)
    steer_snapshot = Column(JSON, nullable=True)

    audio_track = relationship("AudioTrack")
    decisions = relationship("MemDecision", back_populates="run", cascade="all, delete-orphan")
    feedback_events = relationship("MemUserFeedbackEvent", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MemPacingRun(id={self.id}, audio_track_id={self.audio_track_id}, cuts={self.total_cuts})>"


class MemDecision(Base):
    """Persisted snapshot of a pacing decision with full context."""
    __tablename__ = "mem_decision"
    __table_args__ = (
        Index("idx_mem_decision_run", "run_id", "sequence_idx"),
        Index("idx_mem_decision_scene", "scene_id"),
        Index("idx_mem_decision_verdict", "user_verdict"),
        Index("idx_mem_decision_context_hash", "at_genre", "at_section_type", "at_bpm"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("mem_pacing_run.id", ondelete="CASCADE"), nullable=False)
    sequence_idx = Column(Integer, nullable=False)

    # Audio Context Snapshot
    at_timestamp_sec = Column(Float, nullable=False)
    at_beat_idx = Column(Integer, nullable=True)
    at_structure_segment_id = Column(Integer, nullable=True)
    at_bpm = Column(Float, nullable=True)
    at_energy = Column(Float, nullable=True)
    at_section_type = Column(String, nullable=True)
    at_key = Column(String, nullable=True)
    at_key_confidence = Column(Float, nullable=True)
    at_key_modulation = Column(Boolean, nullable=True)
    at_harmonic_tension = Column(Float, nullable=True)
    at_mood_audio = Column(String, nullable=True)
    at_genre = Column(String, nullable=True)
    at_sub_genre = Column(String, nullable=True)
    at_spectral_hash = Column(String, nullable=True)
    at_groove_template = Column(String, nullable=True)
    at_lufs = Column(Float, nullable=True)
    at_enricher_version = Column(String, nullable=True)

    # Video Context Snapshot
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    clip_role = Column(String, nullable=False)
    clip_mood_refined = Column(String, nullable=False)
    clip_style_bucket_id = Column(Integer, nullable=False)
    clip_motion_score = Column(Float, nullable=True)

    # Decision details
    agent_score = Column(Float, nullable=False)
    agent_rationale = Column(JSON, nullable=False)

    # User Feedback
    user_verdict = Column(String, nullable=True)  # accept|reject|skip|modify
    user_verdict_at = Column(DateTime, nullable=True)
    user_rating = Column(Integer, nullable=True)

    run = relationship("MemPacingRun", back_populates="decisions")
    scene = relationship("Scene")

    def __repr__(self):
        return f"<MemDecision(id={self.id}, run_id={self.run_id}, scene_id={self.scene_id}, verdict={self.user_verdict})>"


class MemLearnedPattern(Base):
    """Aggregated patterns learned from user feedback."""
    __tablename__ = "mem_learned_pattern"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_type = Column(String, nullable=False)  # context_preference | clip_blacklist | clip_whitelist | style_affinity
    context_fingerprint = Column(JSON, nullable=True)
    target_ref = Column(JSON, nullable=True)
    stat_accept_count = Column(Integer, nullable=False, default=0)
    stat_reject_count = Column(Integer, nullable=False, default=0)
    stat_sample_size = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=False, default=0.0)
    last_updated = Column(DateTime, nullable=False, default=lambda: _datetime.datetime.utcnow())

    def __repr__(self):
        return f"<MemLearnedPattern(id={self.id}, type='{self.pattern_type}', confidence={self.confidence:.3f})>"


class MemUserFeedbackEvent(Base):
    """Individual user feedback events."""
    __tablename__ = "mem_user_feedback_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(Integer, ForeignKey("mem_decision.id", ondelete="SET NULL"), nullable=True)
    run_id = Column(Integer, ForeignKey("mem_pacing_run.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String, nullable=False)  # accept|reject|skip|rate|replace
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: _datetime.datetime.utcnow())

    run = relationship("MemPacingRun", back_populates="feedback_events")

    def __repr__(self):
        return f"<MemUserFeedbackEvent(id={self.id}, type='{self.event_type}', run_id={self.run_id})>"

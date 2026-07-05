# B-538 Long Audio Service E2E - 2026-07-05

Status: service-e2e-pass, gui-live-pending

## Scope

User audio:

`C:\Users\David_Lochmann\Music\02 Mai19 - Kopie.wav`

Input evidence:

- Duration: 5531.005351 seconds
- Format: WAV PCM s16le
- Sample rate: 44100 Hz
- Channels: 2
- Size: 975669544 bytes

## Command Shape

Script:

`scripts/diag/e2e_audio_pipeline_orchestrator.py`

Run used isolated project and AppData roots:

- `test-report/b538-long-audio-20260705/project-isolated-cwd`
- `test-report/b538-long-audio-20260705/appdata-isolated-cwd`

The run used `--chdir-project-root` so relative pipeline state was isolated from the repo root.

## Result

JSON:

`test-report/b538-long-audio-20260705/isolated_cwd_result.json`

Summary:

- `status=pass`
- `failed=false`
- `total_seconds=3600.46`
- `track_id=1`

Stage timings:

- `stem_gen=1589.72s`
- `beat_grid=184.94s`
- `onset=10.76s`
- `key=27.85s`
- `structure=148.44s`
- `lufs=454.80s`
- `spectral=25.96s`
- `av_pacing=1157.88s`

Stage outputs:

- StemGen: `reused=false`, 4 stem WAVs written.
- BeatGrid: `bpm=136.4`
- Key: `A#`, Camelot `6B`, confidence `0.667`
- Structure: `341` segments
- LUFS: integrated `-14.83`, true peak `0.27`
- Spectral: dominant band `Sub Bass`, centroid mean `1802.36`
- AV-Pacing: `55311` samples

## DB Evidence

DB:

`test-report/b538-long-audio-20260705/project-isolated-cwd/pb_studio.db`

Counts:

- `audio_tracks=1`
- `beatgrids=1`
- `structure_segments=341`
- `analysis_artifacts=4`
- `analysis_jobs=1`
- `waveform_data=0`
- `hotcues=0`
- `timeline_entries=0`

Audio track:

- `duration=5531.01`
- `sample_rate=44100`
- `bpm=136.4`
- `key=A#`
- `key_confidence=0.667`
- `lufs=-14.83`
- `spectral_bands_len=302`
- `key_modulation_data_len=8`
- `harmonic_tension_curve_len=62`

Beat grid:

- `beat_positions_len=12569`
- `beat_positions_last=5518.66`
- `downbeat_positions_len=3746`
- `energy_per_beat_len=12569`
- `stem_weighted_energy_len=12569`
- `onset_kick_data_len=6528`
- `onset_snare_data_len=7685`
- `onset_hihat_data_len=6687`
- `syncopation_score=0.5565`
- `groove_template=house_offbeat`

Stem files:

- `drums.wav`: 1463504060 bytes
- `bass.wav`: 1463504060 bytes
- `other.wav`: 1463504060 bytes
- `vocals.wav`: 1463504060 bytes

## Limits

This does not prove B-538 fixed.

Open:

- No visible GUI workflow was driven to Timeline, Export, or Playback.
- `waveform_data=0`, `hotcues=0`, and `timeline_entries=0` in the isolated DB.
- `OnsetRhythmService` logged `Audio truncated to 1800 sec (file may be longer)`.

B-538 remains `partial-fix`.

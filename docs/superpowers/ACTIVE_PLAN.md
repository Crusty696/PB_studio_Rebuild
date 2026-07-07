# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07
repo_plan: docs/superpowers/plans/2026-07-07-schnitt-clipauswahl-thumbnails-fixplan.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-schnitt-clipauswahl-fixplan-2026-07-07.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-063-schnitt-clipauswahl-fixplan.md
updated: 2026-07-08

## Why This Plan Is Active

Nacharbeiten zum SCHNITT-Plan erforderlich (User-Feedback 2026-07-08):
1. Videospur zu kurz / letzter Clip zu fest gekürzt.
3. Clip-Auswahldiversität / Analysedaten-Einfluss verbessern.
6. GUI-Timeline vergrößern (ganze Fensterbreite nutzen, Spurhöhe anheben).
7. Render-Verifikation (Concat/Stream-Copy genau prüfen).

Sobald diese Nacharbeiten live verifiziert und durch den User abgenommen sind (fixed), wird wieder auf den Audit-Fixplan umgeschaltet.

## Current Next Task

```text
Nacharbeit Schnitt-Plan:
- Task 1: Videospur-Endkürzung korrigieren (Segmentverschmelzung bei Rest < 2s).
- Task 2: PacingScorer-Gewichte verfeinern (Lautstärke/Onsets an Motion koppeln).
- Task 3: Zoom-to-Fit + vergrößerte Spurhöhe standardmäßig in Timeline UI einbetten.
- Task 4: Log-Verify des ffmpeg-Concat-Prozesses.
```

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen.
- Höhlenmensch-Modus (German, terse) in der Kommunikation beibehalten.
- GPU-Regel unverändert (GTX 1060 / cuda:0).
- fixed-Marker setzt nur der User.

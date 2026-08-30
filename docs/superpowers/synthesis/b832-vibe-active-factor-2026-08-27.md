# B-832 — Vibe als aktiver Matching-Faktor

status: agent-live-verified-await-user-marker
date: 2026-08-27
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
decision: D-095

## Entscheidung

User waehlt aktiven Faktor statt Notfall-Fallback. Vibe nutzt vorhandene
semantische Mood-Achse; keine neue Gewichts-/Config-Achse.

## Root Cause

Regulaeres Fitness-Scoring kehrte vor dem Vibe-Zweig zurueck. Bei vorhandenen
SigLIP-/VectorDB-Kandidaten war Vibe deshalb wirkungslos. Aktivierter
Studio-Brain-Selector konnte Legacy-Matching zudem komplett umgehen.

## Fix

- Vibe-Text einmal pro Auto-Edit als SigLIP-Vektor berechnen.
- Cosine-Similarity gegen alle Scene-Embeddings vektorisieren.
- Legacy- und Cross-Modal-Matcher verwenden Similarity innerhalb bestehender
  Mood-Achse.
- Studio-Brain erhaelt denselben Vektor als `at_audio_mood_vec` vor
  `select_best`.
- Leerer Vibe/fehlendes Embedding behaelt bisheriges Verhalten und Fallback.

## Verifikation

`cmd /c run_pytest_schnitt.bat tests\test_services\test_b832_vibe_active_factor.py -q`

Ergebnis: `4 passed in 1.01s`; betroffene Module `py_compile` PASS.

Kein echter Auto-Edit-/UI-Lauf, keine sichtbare Clip-Auswahl-Abnahme, keine
breite Suite. Deshalb nicht `fixed`.

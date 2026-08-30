# B-912 — Cut-Rate als finaler Ruhe-Floor

status: agent-live-verified-await-user-marker
date: 2026-08-27
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16

## Beleg

Projekt `123454321`: 103 Video-Segmente auf 337.137 s; 34 unter 2 s,
9 unter 1 s, Minimum 0.395 s. Nur eines der 34 kurzen Segmente beruehrt eine
Section-Grenze. 103 verschiedene `media_id`; Wiederholung war in diesem
gespeicherten Lauf nicht Root Cause.

## Root Cause

`finalize_cut_beats` bereinigte Mindestdauern vor Drop-Burst und Onset-Snap.
Diese spaeten Stufen konnten anschliessend wieder Mini-Segmente erzeugen;
final blieben nur 0,2 s technischer Abstandsschutz. Gewaehlte UI-Cut-Rate war
damit keine verbindliche Ruhe-Untergrenze.

## Fix

- Robuste Beatdauer = Median plausibler Beatgrid-Abstaende.
- Finaler Floor = Beatdauer × `base_cut_rate` nach Drop-Burst/Onset-Snap.
- Gesnappte echte Section-Grenzen bleiben Pflichtpunkte.
- Source-Material-Maximaldauer wird nach Ausduennung erneut durchgesetzt.
- Keine feste neue Sekundenzahl; 1/2/4/8/16-Beat-Produktwahl bleibt erhalten.

## Verifikation

`cmd /c run_pytest_schnitt.bat tests\test_services\test_b912_cut_rate_ruhe_floor.py -q`

Ergebnis: `4 passed in 2.17s`.

Kein echter Auto-Edit-UI-Lauf, keine sichtbare Timeline-Abnahme, keine breite
Suite. Deshalb Status `code-fix-pending-live-verification`, nicht `fixed`.

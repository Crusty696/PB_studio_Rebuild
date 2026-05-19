# 90 — Globaler Live-Verify-Walkthrough

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Verifikation
> Status: planned · 2026-05-19

## Pflicht-Schritte (User)

1. **Kurzer Clip (Solo_Natur):** Import → "Alle ausstehenden starten" → alle Stages gruen, Status-Panel zeigt Done.
2. **Proxy-Playback:** Timeline laedt Proxy fluessig.
3. **Scene-Cuts ueberpruefen:** scenes.json plausibel.
4. **Keyframes manuelle Sichtkontrolle:** je 3 Frames pro Szene OK.
5. **SigLIP-Aehnlichkeit:** zwei aehnliche Clips → hohe Cosine.
6. **RAFT-Motion:** statisches Bild → niedrige Magnitude, schneller Pan → hoch.
7. **VLM-Caption (mit Plan B Backend):** Sample-Output deutsch + plausibel.
8. **Cross-Modal mit V2-Daten:** Cut-Plan-Vorschlag liegt vor + ist mit Beats plausibel.
9. **Resume-Test:** Mid-Pipeline kill via Task-Manager → Re-Start → weiter ab Checkpoint.
10. **Long-Form synthetisch:** 4 h geloopte Datei → durch alle Stages, Coverage-Report ≥ 99.5 %.
11. **GPU-Coexistence:** Audio-V2 parallel laufen lassen → kein OOM, Plan-A-Stage wartet bis V2-Lock frei.

## Akzept-Kriterien (User entscheidet)

- [ ] Alle 11 Schritte ohne Stacktrace
- [ ] Coverage-Garantie eingehalten
- [ ] V2-Coexistence stabil
- [ ] **Erst danach** vergibt User `status: fixed`

## Ergebnis

- Bericht in Vault `wiki/synthesis/live-verify-video-pipeline-<datum>.md`
- Decision-Status-Update in `D-045`

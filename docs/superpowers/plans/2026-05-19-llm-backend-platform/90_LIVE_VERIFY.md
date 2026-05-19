# 90 — Globaler Live-Verify-Walkthrough

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Verifikation
> Status: planned · 2026-05-19

## Ziel

End-to-End-Verifikation der gesamten LLM-Platform nach Plan-Abschluss.

## Pflicht-Schritte (User)

1. **Saubere Installation:** PB Studio Fresh-Install auf VM oder leeren User-Folder.
2. **First-Run-Wizard:** Modell waehlen (qwen3:8b-q4), Lizenz akzeptieren, Pull abwarten.
3. **Smoke-Chat:** "Hallo" → Antwort.
4. **HF-Token-Setup:** Token eingeben, Test gruen, HF-Modell pullen (z. B. minicpm-v).
5. **Vision-Caption-Test:** Bild laden, Caption generieren lassen → Output korrekt.
6. **Modell-Wechsel Hot-Reload:** Settings → anderes Modell, Chat-Call nutzt neues.
7. **VRAM-Coexistence:** Audio-V2 parallel starten, kein OOM, kein Crash.
8. **Modell-Pin pro Projekt:** Projekt A pin qwen3, Projekt B pin llama3, Wechsel funktioniert.
9. **Modell-Update-Notify (manuell):** Settings → "Modelle pruefen", Update-Check funktioniert.
10. **Single-Instance-Test:** Zweiter App-Start → erste vorne.
11. **App-Restart:** Daemon ueberlebt, kein Stale-PID-Problem.
12. **Diagnose-Bundle exportieren:** Settings → Diagnose-Tab, Bundle entsteht ohne Token-Leak.
13. **Uninstall-Walkthrough:** Modelle behalten / Token entfernt.

## Akzept-Kriterien

- [ ] Alle 13 Schritte ohne Stacktrace.
- [ ] Logs Token-frei.
- [ ] VRAM-Coexistence mit Audio-V2 ohne Crash.
- [ ] Single-Instance-Lock funktional.
- [ ] **Erst danach** vergibt User `status: fixed`.

## Ergebnis

- Bericht in Vault `wiki/synthesis/live-verify-llm-platform-<datum>.md`.
- Decision-Status-Eintrag in `D-044`.

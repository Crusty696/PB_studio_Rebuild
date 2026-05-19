# 99 — Offene Klaerungs-Punkte

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Verifikation
> Status: living document · 2026-05-19

Liste aller noch ungeklaerten Punkte vor Implementation-Start.

## Architektur

- [ ] **Tier 2 Boot:** Daemon eager vs lazy beim ersten Call? — Vorschlag eager + asynchron, UI nicht haengen.
- [ ] **Watchdog-Restart-Limit:** 3 × in 60 s ok?
- [ ] **`crashed`-State:** User-Dialog oder still im Status-Dot?

## Backend / Protocol

- [ ] **ChatRequest/Chunk-Dataclasses:** OpenAI-API-style ODER Ollama-native? — Vorschlag OpenAI (zukunfts-fest).
- [ ] **Ollama-eigene Endpoints** (`/api/chat`) als Zusatz fuer Funktionen die OpenAI nicht hat?

## Modelfile

- [ ] **SYSTEM-Prompts pro Rolle** Inhalt festlegen (PB-Studio-spezifisch).
- [ ] **num_ctx pro Modell** aus Registry oder Hard-Coded?
- [ ] **Sprache-Erzwingung:** SYSTEM-Prompt vs per-Request?

## Selector / VRAM

- [ ] **Safety-Margin VRAM:** 0.5 GB ok oder konfigurierbar?
- [ ] **Bei VRAM-Knappheit:** queuen vs kleineres Modell?

## Storage

- [ ] **Registry-User-Overrides** `<app_data>/llm_models.user.json` mit Merge-Logik?
- [ ] **sha256-Pflicht** fuer GGUF-Dateien?

## Tests

- [ ] **4 h Audio-Test-Datensatz:** Mischung — synthetisch jetzt, echte Datei spaeter (Pfad nennt User).
- [ ] **Long-form-Marker:** pytest-Flag `--long-form` ok?

## UI

- [ ] **Pull-Progress:** mehrere parallel ODER sequentiell? — Empfehlung sequentiell.
- [ ] **Empfehlungs-Toast:** Frequenz / Cooldown?

## Cross-Plan-Abhaengigkeiten

- [ ] **Audio-V2:** wann verfuegbar? Heute P2 in Sandbox, vor LLM-Plan-Start abwarten?
- [ ] **Brain V3:** GPU-Coexistence-Test moeglich? Brain-V3-Owner abstimmen.
- [ ] **Plan A (Video):** kommt parallel? Reihenfolge?

## Lizenzen

- [ ] **CC-BY-NC-Modelle:** komplett ausschliessen oder Warnung + zulassen?
- [ ] **Modell-Liste Cadence:** wie oft pruefen + Registry updaten?

## Sonstiges

- [ ] **Bind-Fallback:** wenn kein freier Port verfuegbar → App-Start abbrechen ok?
- [ ] **Diagnose-Bundle:** Token-Scrubber Pattern-Liste finalisieren.

## Aktualisierungs-Pflicht

Wenn ein Punkt geklaert → Eintrag mit Entscheidung + Datum + User-Bestaetigung in Vault-Decision-File `D-044` nachtragen.

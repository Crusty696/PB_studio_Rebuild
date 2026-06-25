# 03 — Modell-Recherche 2026 (Lizenz + VRAM)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 1 Foundation
> Status: planned · 2026-05-19 · Recherche-Step

## Ziel

Konkrete Modell-Liste fuer GTX 1060 (6 GB VRAM). Pro Modell: ID / Quant / VRAM-Realismus / Lizenz / Quelle (Ollama-Hub vs HF).

## Pflicht-Pruefung pro Modell

- Lizenz (Apache 2.0 / MIT / Llama-Community / Gemma / OpenRAIL / CC-BY-NC)
- VRAM-Bedarf real auf 1060 (kein theoretisches Marketing)
- Verfuegbar via Ollama-Hub direkt (`ollama pull <id>`) oder nur HF
- Default-Quant fuer 6 GB Budget
- Sprachen (Deutsch + Englisch fuer Reasoner)

## Vorab-Kandidaten (zu verifizieren)

### Reasoner (Text-only)
| Modell | Quant | VRAM-Schaetz | Lizenz | Quelle |
|---|---|---|---|---|
| qwen3:8b | Q4_K_M | ~5.0 GB | apache-2.0 | ollama-hub |
| llama3.1:8b | Q4_K_M | ~5.0 GB | llama-community | ollama-hub |
| phi4-mini | Q4_K_M | ~3.0 GB | mit | ollama-hub |
| gemma3:4b | Q4_K_M | ~3.0 GB | gemma-terms | ollama-hub |
| mistral-nemo:12b | Q4_K_M | ~7.5 GB ZU GROSS | apache-2.0 | ollama-hub |

### Vision (VLM)
| Modell | Quant | VRAM | Lizenz | Quelle |
|---|---|---|---|---|
| moondream:1.8b | Q4_K_M | ~2.0 GB | apache-2.0 | ollama-hub |
| llava-phi3 | Q4_K_M | ~3.0 GB | mit | ollama-hub |
| qwen2.5-vl:7b | Q4_K_M | ~5.0 GB | apache-2.0 | hf |
| minicpm-v:8b | Q4_K_M | ~5.2 GB | mit | ollama-hub |

### Omni (Audio + Vision + Text)
| Modell | Quant | VRAM | Lizenz | Quelle |
|---|---|---|---|---|
| minicpm-o:8b | Q4_K_M | ~5.5 GB knapp | mit | hf |
| phi-4-multimodal | Q4_K_M | ~5.0 GB | mit | hf (verfuegbarkeits-pruefung) |

### Embeddings (CPU-only)
| Modell | Quant | Output-Dim | Lizenz | Quelle |
|---|---|---|---|---|
| bge-m3 | f16 | 1024 | mit | hf / ollama-hub |
| nomic-embed-text | f16 | 768 | apache-2.0 | ollama-hub |
| mxbai-embed-large | f16 | 1024 | apache-2.0 | hf |

### Reasoning-Heavy (Chain-of-Thought, langsamer)
| Modell | Quant | VRAM | Lizenz | Quelle |
|---|---|---|---|---|
| deepseek-r1:8b | Q4_K_M | ~5.0 GB | mit | ollama-hub |
| qwq:32b | Q4_K_M | ~18 GB nur CPU-Offload | apache-2.0 | nur lmstudio (Stub-Path) |

## Pflichten

- Vor Plan-Start (Phase 11/13): jeden Eintrag durch echten Smoke-Test verifizieren — `ollama run <id>` startet + Antwort + VRAM-Messung via pynvml
- Nicht-verifizierte Eintraege bekommen `experimental: true` in Registry
- Tatsaechliche VRAM-Werte in Registry eintragen, **keine Schaetzungen**

## Offene Klaerungs-Punkte

- [ ] minicpm-o + phi-4-multimodal — sind die in Ollama-Hub registriert (Stand 2026-05) oder nur HF?
- [ ] CC-BY-NC-Modelle (pyannote-Variants) — komplett ausschliessen?
- [ ] Liste regelmaessig aktualisieren — Cadence?

## Verifikation

- Smoke-Test-Skript `scripts/spike_llm_models.py` laeuft alle Eintraege auf 1060 ab
- Ergebnis-Tabelle in `99_OPEN_QUESTIONS.md` und Vault

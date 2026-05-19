# 13 — Auto-Selector

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Pro Rolle automatisch das beste Modell waehlen, das **(a)** in das VRAM-Budget passt und **(b)** bereits installiert ist. Wenn ein besseres existiert aber nicht installiert → Notify.

## Scope

```python
# services/llm/selector.py
def select(role: str, *, installed: set[str], vram_budget_gb: float, 
           registry: Registry, project_pin: str | None) -> SelectionResult:
    """
    Priorisierung:
      1. project_pin gesetzt + installiert + passt → chosen
      2. installierte Kandidaten gefiltert auf VRAM-Budget, hoechster Score → chosen
      3. best_overall (ohne Install-Status) → Vorschlag fuer Notify
    """

@dataclass
class SelectionResult:
    chosen: ModelInfo | None
    best_overall: ModelInfo
    missing_better: list[ModelInfo]
    fallback_chain: list[ModelInfo]
    reason: str
```

- Score: `weights["quality"] * quality + weights["speed"] * speed` (Rolle-spezifische Weights).
- VRAM-Budget: kommt von `15_HARDWARE_PROBE_AND_FILTER.md` (live).
- Pin-Override: wenn Projekt-Pin gesetzt + installiert + passt → immer der.

## Out of Scope

- Pin-Setzen-UI — siehe `33_PROJECT_SETTINGS_PINS_LLM.md`.
- Notify-Dialog UX — siehe `31_NOTIFY_DOWNLOAD_UX.md`.

## Verifikation

- Unit-Test mit Mock-Registry + Mock-installed-set
- Edge-Cases: kein Modell installiert / Pin nicht installiert / VRAM zu klein
- `pytest tests/test_services/test_llm_selector.py -v` gruen

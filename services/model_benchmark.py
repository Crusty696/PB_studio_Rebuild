"""
Modell-Evaluierungs & Benchmark-Framework für PB Studio.

Bewertet lokale KI-Modelle (Ollama + HuggingFace) systematisch nach:
- Latenz (Sekunden bis erste Antwort)
- VRAM-Verbrauch (MB)
- Output-Qualität (JSON-Validität, Korrektheit)
- Fuzzy-Match-Erfolgsrate (Action-Parsing)
- Multi-Step-Reasoning (Orchestrierung)

Ergebnis: Modell-Empfehlungsmatrix nach GPU-Klasse.

Verwendung:
    from services.model_benchmark import ModelBenchmark
    bench = ModelBenchmark()
    results = bench.run_all()
    bench.print_report(results)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Benchmark-Aufgaben (Ground-Truth-Daten)
# ──────────────────────────────────────────────────────────────────────────────

PACING_BENCHMARK_PROMPT = """\
DJ-Mix Analyse:
- BPM: 128.0
- Dauer: 360s (6.0 Minuten)
- Verfuegbare Video-Clips: 12
- Sektionen:
  WARMUP       0s-   60s (60s) energy=0.25
  BUILDUP     60s-  120s (60s) energy=0.65
  DROP       120s-  180s (60s) energy=0.92
  BREAKDOWN  180s-  240s (60s) energy=0.30
  BUILDUP    240s-  300s (60s) energy=0.72
  DROP       300s-  360s (60s) energy=0.95

Erstelle einen JSON Pacing-Plan."""

EXPECTED_PACING_KEYS = {"sections", "global_min_duration", "variety_priority"}
EXPECTED_SECTION_KEYS = {"type", "start", "end", "cut_rate_beats", "mood"}

ACTION_BENCHMARK_PROMPTS = [
    ("analysiere alle audios",   "analyze_audio"),
    ("schneide automatisch",     "auto_edit"),
    ("erstelle proxy videos",    "create_proxies"),
    ("zeige gpu status",         "get_gpu_status"),
    ("starte stem trennung",     "separate_stems"),
    ("importiere ordner",        "import_folder"),
    ("exportiere timeline",      "export_timeline"),
]

MULTI_STEP_PROMPT = """\
Ich möchte meinen neuen Track analysieren und dann direkt einen automatischen Schnitt erstellen.
Der Track heißt 'set_2024.mp3' und ist im Import-Ordner.
Analysiere ihn, trenne die Stems und erstelle dann automatisch ein Video."""

EXPECTED_MULTI_STEP_ACTIONS = {"analyze_audio", "separate_stems", "auto_edit", "create_auto_edit"}


# ──────────────────────────────────────────────────────────────────────────────
# Daten-Strukturen
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskResult:
    task: str
    model: str
    backend: str                    # "ollama" | "huggingface"
    latency_sec: float
    vram_before_mb: float
    vram_after_mb: float
    success: bool
    score: float                    # 0.0 – 1.0
    raw_output: str = ""
    error: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    model: str
    backend: str
    gpu_class: str                  # "gtx1060_6gb", "rtx3080_10gb", "cpu", etc.
    tasks: list[TaskResult] = field(default_factory=list)

    @property
    def avg_latency(self) -> float:
        vals = [t.latency_sec for t in self.tasks if t.success]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def avg_score(self) -> float:
        vals = [t.score for t in self.tasks if t.success]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def success_rate(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.success) / len(self.tasks)

    @property
    def max_vram_delta_mb(self) -> float:
        deltas = [t.vram_after_mb - t.vram_before_mb for t in self.tasks]
        return max(deltas, default=0.0)


# ──────────────────────────────────────────────────────────────────────────────
# Benchmark-Engine
# ──────────────────────────────────────────────────────────────────────────────

class ModelBenchmark:
    """Führt Benchmark-Tests für lokale KI-Modelle durch.

    Testet:
    1. Pacing-Strategie-Generierung (JSON-Qualität)
    2. Action-Parsing (Fuzzy-Match-Erfolgsrate)
    3. Multi-Step-Reasoning (Orchestrierung)

    Kann Ollama-Modelle und lokale HuggingFace-Modelle vergleichen.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Minimal-System-Prompt für Benchmark-Tests."""
        return (
            "Du bist der KI-Assistent von PB Studio, einem DJ Video-Editor.\n"
            "WICHTIG: Antworte IMMER mit reinem JSON. Kein Text davor oder danach.\n"
            "Format: {\"action\": \"<name>\", \"params\": {}} oder [{...}, {...}] für mehrere Aktionen.\n"
            "Verfügbare Aktionen: analyze_audio, auto_edit, create_proxies, get_gpu_status, "
            "separate_stems, import_folder, export_timeline, create_auto_edit.\n"
            "Wenn keine Aktion passt: {\"action\": \"none\", \"params\": {}, \"message\": \"<Antwort>\"}"
        )

    def _get_vram_mb(self) -> float:
        """Gibt aktuellen VRAM-Verbrauch zurück (0 wenn kein CUDA)."""
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.memory_allocated() / 1024 / 1024
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # Task 1: Pacing-Strategie
    # ------------------------------------------------------------------

    def _score_pacing_output(self, raw: str) -> tuple[float, dict]:
        """Bewertet die Qualität eines generierten Pacing-Plans."""
        details: dict[str, Any] = {}
        score = 0.0

        # JSON-Parsing
        data = None
        for start_char in ('{', '['):
            idx = raw.find(start_char)
            if idx >= 0:
                try:
                    data = json.loads(raw[idx:])
                    if isinstance(data, list) and data:
                        data = data[0]
                    break
                except json.JSONDecodeError:
                    continue

        if data is None:
            details["error"] = "Kein valides JSON"
            return 0.0, details

        score += 0.3  # Grundpunkte für valides JSON
        details["valid_json"] = True

        # Schlüssel-Check
        found_keys = EXPECTED_PACING_KEYS & set(data.keys())
        key_score = len(found_keys) / len(EXPECTED_PACING_KEYS)
        score += key_score * 0.3
        details["found_keys"] = list(found_keys)
        details["missing_keys"] = list(EXPECTED_PACING_KEYS - found_keys)

        # Sektionen-Qualität
        sections = data.get("sections", [])
        if sections and isinstance(sections, list):
            section_scores = []
            for sec in sections[:6]:  # Max 6 Sektionen prüfen
                if isinstance(sec, dict):
                    found = EXPECTED_SECTION_KEYS & set(sec.keys())
                    section_scores.append(len(found) / len(EXPECTED_SECTION_KEYS))
            if section_scores:
                avg_section = sum(section_scores) / len(section_scores)
                score += avg_section * 0.3
                details["avg_section_completeness"] = round(avg_section, 2)
                details["section_count"] = len(sections)

        # Werte-Plausibilität
        min_dur = data.get("global_min_duration", -1)
        if 1.0 <= min_dur <= 10.0:
            score += 0.1
            details["min_duration_plausible"] = True
        variety = data.get("variety_priority", -1)
        if 0.0 <= variety <= 1.0:
            score += 0.0  # Kein extra Score, aber gut zu wissen
            details["variety_plausible"] = True

        details["final_score"] = round(score, 3)
        return min(score, 1.0), details

    def benchmark_pacing(self, model: str, backend: str = "ollama") -> TaskResult:
        """Benchmark-Task 1: Pacing-Strategie generieren."""
        vram_before = self._get_vram_mb()
        start = time.perf_counter()
        raw_output = ""
        error = ""

        try:
            if backend == "ollama":
                from services.ollama_client import get_ollama_client
                client = get_ollama_client(self.ollama_url)
                raw_output = client.chat(
                    model=model,
                    user_message=PACING_BENCHMARK_PROMPT,
                    system_prompt=(
                        "Du bist ein DJ-Video-Pacing-Experte. "
                        "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."
                    ),
                    temperature=0.1,
                    max_tokens=1024,
                )
            else:
                from services.model_manager import ModelManager, GPU_LOAD_LOCK
                with GPU_LOAD_LOCK:
                    mm = ModelManager()
                    tok, _, pipe = mm.load_transformers(model)
                    try:
                        outputs = pipe(
                            PACING_BENCHMARK_PROMPT,
                            max_new_tokens=1024,
                            do_sample=False,
                            return_full_text=False,
                        )
                        raw_output = outputs[0]["generated_text"].strip()
                    finally:
                        mm.unload()

        except Exception as e:
            error = str(e)
            logger.warning("Pacing-Benchmark Fehler für '%s': %s", model, e)

        latency = time.perf_counter() - start
        vram_after = self._get_vram_mb()
        score, details = self._score_pacing_output(raw_output) if not error else (0.0, {})

        return TaskResult(
            task="pacing_strategy",
            model=model,
            backend=backend,
            latency_sec=round(latency, 2),
            vram_before_mb=round(vram_before, 1),
            vram_after_mb=round(vram_after, 1),
            success=bool(raw_output and not error),
            score=score,
            raw_output=raw_output[:500] if raw_output else "",
            error=error,
            details=details,
        )

    # ------------------------------------------------------------------
    # Task 2: Action-Parsing
    # ------------------------------------------------------------------

    def _score_action_output(self, raw: str, expected_action: str) -> tuple[float, dict]:
        """Bewertet Action-Parsing-Qualität."""
        details: dict[str, Any] = {}

        data = None
        for i, ch in enumerate(raw):
            if ch in ('{', '['):
                try:
                    data = json.loads(raw[i:])
                    if isinstance(data, list) and data:
                        data = data[0]
                    break
                except json.JSONDecodeError:
                    continue

        if data is None:
            details["error"] = "Kein valides JSON"
            return 0.0, details

        action = data.get("action", "none")
        details["parsed_action"] = action
        details["expected_action"] = expected_action

        # Exakter Match
        if action == expected_action:
            details["match"] = "exact"
            return 1.0, details

        # Fuzzy-Match: Überlappende Wörter
        expected_parts = set(expected_action.replace("_", " ").split())
        parsed_parts = set(action.replace("_", " ").split())
        overlap = len(expected_parts & parsed_parts) / len(expected_parts)
        if overlap >= 0.5:
            details["match"] = f"fuzzy ({overlap:.0%})"
            return 0.6 + 0.4 * overlap, details

        details["match"] = "none"
        return 0.0, details

    def benchmark_action_parsing(self, model: str, backend: str = "ollama") -> TaskResult:
        """Benchmark-Task 2: Action-Parsing-Erfolgsrate."""
        scores: list[float] = []
        details_all: list[dict] = []
        total_latency = 0.0
        vram_before = self._get_vram_mb()
        error = ""

        for prompt, expected in ACTION_BENCHMARK_PROMPTS:
            start = time.perf_counter()
            raw = ""

            try:
                if backend == "ollama":
                    from services.ollama_client import get_ollama_client
                    client = get_ollama_client(self.ollama_url)
                    raw = client.chat(
                        model=model,
                        user_message=prompt,
                        system_prompt=self._system_prompt,
                        temperature=0.1,
                        max_tokens=256,
                    )
                else:
                    from services.local_agent_service import LocalAgentService, DEFAULT_MODEL_ID
                    agent = LocalAgentService(model_id=model, use_ollama=False)
                    raw = agent._generate(prompt, max_new_tokens=256)
            except Exception as e:
                error = str(e)
                break

            total_latency += time.perf_counter() - start
            score, d = self._score_action_output(raw, expected)
            scores.append(score)
            d["prompt"] = prompt
            details_all.append(d)

        avg_score = sum(scores) / len(scores) if scores else 0.0
        vram_after = self._get_vram_mb()

        return TaskResult(
            task="action_parsing",
            model=model,
            backend=backend,
            latency_sec=round(total_latency / max(len(scores), 1), 2),
            vram_before_mb=round(vram_before, 1),
            vram_after_mb=round(vram_after, 1),
            success=bool(scores and not error),
            score=round(avg_score, 3),
            error=error,
            details={
                "per_task": details_all,
                "tasks_evaluated": len(scores),
            },
        )

    # ------------------------------------------------------------------
    # Task 3: Multi-Step-Reasoning
    # ------------------------------------------------------------------

    def _score_multistep_output(self, raw: str) -> tuple[float, dict]:
        """Bewertet Multi-Step-Reasoning-Qualität."""
        details: dict[str, Any] = {}

        # Versuche JSON-Parsing
        data = None
        for i, ch in enumerate(raw):
            if ch in ('[', '{'):
                try:
                    data = json.loads(raw[i:])
                    break
                except json.JSONDecodeError:
                    continue

        if data is None:
            return 0.0, {"error": "Kein valides JSON"}

        # Multi-Action-Liste erwartet
        if not isinstance(data, list):
            data = [data]

        actions_found = {item.get("action", "none") for item in data if isinstance(item, dict)}
        details["actions_found"] = list(actions_found)
        details["action_count"] = len(data)

        # Wie viele der erwarteten Aktionen wurden erkannt?
        expected = EXPECTED_MULTI_STEP_ACTIONS
        found = actions_found & expected

        # Partial matching
        fuzzy_matches = set()
        for action in actions_found:
            for exp in expected:
                parts = set(exp.replace("_", " ").split())
                a_parts = set(action.replace("_", " ").split())
                if parts & a_parts:
                    fuzzy_matches.add(exp)

        coverage = len(fuzzy_matches) / len(expected)
        score = coverage

        # Bonus für richtige Reihenfolge
        if len(data) >= 2:
            score += 0.1
            details["multi_action"] = True

        details["coverage"] = round(coverage, 2)
        details["fuzzy_matches"] = list(fuzzy_matches)

        return min(score, 1.0), details

    def benchmark_multi_step(self, model: str, backend: str = "ollama") -> TaskResult:
        """Benchmark-Task 3: Multi-Step-Reasoning."""
        vram_before = self._get_vram_mb()
        start = time.perf_counter()
        raw_output = ""
        error = ""

        try:
            if backend == "ollama":
                from services.ollama_client import get_ollama_client
                client = get_ollama_client(self.ollama_url)
                raw_output = client.chat(
                    model=model,
                    user_message=MULTI_STEP_PROMPT,
                    system_prompt=self._system_prompt,
                    temperature=0.1,
                    max_tokens=512,
                )
            else:
                from services.local_agent_service import LocalAgentService
                agent = LocalAgentService(model_id=model, use_ollama=False)
                raw_output = agent._generate(MULTI_STEP_PROMPT, max_new_tokens=512)
        except Exception as e:
            error = str(e)

        latency = time.perf_counter() - start
        vram_after = self._get_vram_mb()
        score, details = self._score_multistep_output(raw_output) if not error else (0.0, {})

        return TaskResult(
            task="multi_step_reasoning",
            model=model,
            backend=backend,
            latency_sec=round(latency, 2),
            vram_before_mb=round(vram_before, 1),
            vram_after_mb=round(vram_after, 1),
            success=bool(raw_output and not error),
            score=score,
            raw_output=raw_output[:500] if raw_output else "",
            error=error,
            details=details,
        )

    # ------------------------------------------------------------------
    # Full Benchmark Run
    # ------------------------------------------------------------------

    def run_model(self, model: str, backend: str = "ollama") -> BenchmarkReport:
        """Führt alle Benchmark-Tasks für ein Modell aus."""
        logger.info("Benchmark: Teste '%s' (%s)...", model, backend)

        gpu_class = self._detect_gpu_class()
        report = BenchmarkReport(model=model, backend=backend, gpu_class=gpu_class)

        # Task 1: Pacing
        logger.info("  Task 1: Pacing-Strategie...")
        report.tasks.append(self.benchmark_pacing(model, backend))

        # Task 2: Action-Parsing
        logger.info("  Task 2: Action-Parsing...")
        report.tasks.append(self.benchmark_action_parsing(model, backend))

        # Task 3: Multi-Step
        logger.info("  Task 3: Multi-Step-Reasoning...")
        report.tasks.append(self.benchmark_multi_step(model, backend))

        logger.info(
            "  Ergebnis: Score=%.2f, Latenz=%.1fs, Erfolgsrate=%.0f%%",
            report.avg_score, report.avg_latency, report.success_rate * 100,
        )
        return report

    def run_all_ollama(self) -> list[BenchmarkReport]:
        """Testet alle verfügbaren Ollama-Modelle."""
        from services.ollama_client import get_ollama_client
        client = get_ollama_client(self.ollama_url)

        if not client.is_available():
            logger.warning("Benchmark: Ollama nicht verfügbar unter %s", self.ollama_url)
            return []

        models = client.list_models()
        if not models:
            logger.warning("Benchmark: Keine Ollama-Modelle installiert.")
            return []

        reports: list[BenchmarkReport] = []
        for model in models:
            report = self.run_model(model, backend="ollama")
            reports.append(report)

        return reports

    def _detect_gpu_class(self) -> str:
        """Erkennt GPU-Klasse für die Empfehlungsmatrix."""
        try:
            import torch
            if not torch.cuda.is_available():
                return "cpu"
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024 ** 3)
            name = props.name.lower()
            if vram_gb >= 20:
                return "rtx4090_24gb"
            elif vram_gb >= 16:
                return "rtx3090_24gb"
            elif vram_gb >= 10:
                return "rtx3080_10gb"
            elif vram_gb >= 8:
                return "rtx3070_8gb"
            elif vram_gb >= 6:
                return "gtx1060_6gb"
            else:
                return f"gpu_{vram_gb:.0f}gb"
        except Exception:
            return "cpu"

    # ------------------------------------------------------------------
    # Report-Ausgabe
    # ------------------------------------------------------------------

    def print_report(self, reports: list[BenchmarkReport]) -> str:
        """Erzeugt einen lesbaren Benchmark-Report."""
        lines = [
            "=" * 70,
            "PB STUDIO — MODELL-BENCHMARK-REPORT",
            "=" * 70,
            "",
        ]

        # Sortiert nach avg_score (beste zuerst)
        sorted_reports = sorted(reports, key=lambda r: r.avg_score, reverse=True)

        lines.append(f"{'Modell':<35} {'Backend':<12} {'Score':<8} {'Latenz':<10} {'Erfolg'}")
        lines.append("-" * 70)

        for r in sorted_reports:
            lines.append(
                f"{r.model[:34]:<35} {r.backend:<12} {r.avg_score:<8.2f} "
                f"{r.avg_latency:<10.1f}s {r.success_rate:.0%}"
            )

        lines.extend(["", "=" * 70, "EMPFEHLUNGSMATRIX", "=" * 70, ""])

        gpu_class = sorted_reports[0].gpu_class if sorted_reports else "unbekannt"
        lines.append(f"GPU-Klasse: {gpu_class}")
        lines.append("")

        if sorted_reports:
            best = sorted_reports[0]
            lines.append(f"EMPFOHLEN für {gpu_class}:")
            lines.append(f"  → {best.model} ({best.backend})")
            lines.append(f"  Score: {best.avg_score:.2f} | Latenz: {best.avg_latency:.1f}s")

        output = "\n".join(lines)
        logger.info("\n%s", output)
        return output

    def export_json(self, reports: list[BenchmarkReport]) -> dict:
        """Exportiert Benchmark-Ergebnisse als JSON-Dictionary."""
        return {
            "gpu_class": reports[0].gpu_class if reports else "unknown",
            "models": [
                {
                    "model": r.model,
                    "backend": r.backend,
                    "avg_score": r.avg_score,
                    "avg_latency_sec": r.avg_latency,
                    "success_rate": r.success_rate,
                    "max_vram_delta_mb": r.max_vram_delta_mb,
                    "tasks": [
                        {
                            "task": t.task,
                            "success": t.success,
                            "score": t.score,
                            "latency_sec": t.latency_sec,
                            "vram_delta_mb": round(t.vram_after_mb - t.vram_before_mb, 1),
                            "error": t.error,
                            "details": t.details,
                        }
                        for t in r.tasks
                    ],
                }
                for r in sorted(reports, key=lambda r: r.avg_score, reverse=True)
            ],
        }

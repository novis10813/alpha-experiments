"""Serial OpenEvolve component integration with a project-owned final gate.

Do not use the generic upstream Evaluator: it can import candidate modules and
retry/swallow infrastructure failures. Candidates here go only to Policy's AST
interpreter. OpenEvolve owns population sampling, MAP-Elites and prompt assembly.
"""

import asyncio
from dataclasses import asdict, dataclass
from importlib.metadata import version
from math import atan, isfinite, pi
import os

from openevolve.config import DatabaseConfig, LLMConfig, LLMModelConfig, PromptConfig
from openevolve.database import Program, ProgramDatabase
from openevolve.llm.ensemble import LLMEnsemble
from openevolve.llm.openai import OpenAILLM
from openevolve.prompt.sampler import PromptSampler

from experiments.open_evolve.search import CandidateJournal, canonical, feedback, write_json


@dataclass(frozen=True)
class SearchSettings:
    random_seed: int = 42
    population_size: int = 32
    num_islands: int = 2
    migration_interval: int = 10
    feature_bins: int = 5

    def __post_init__(self):
        if any(type(v) is not int for v in asdict(self).values()):
            raise ValueError("OpenEvolve search settings must be integers")
        if (self.random_seed < 0 or self.num_islands < 1
                or self.population_size < self.num_islands or self.migration_interval < 1
                or self.feature_bins < 2):
            raise ValueError("invalid OpenEvolve population/island settings")


def backend_contract(settings):
    return {"backend": "openevolve", "version": version("openevolve"),
            "adapter": "serial-components-v1", "settings": asdict(settings),
            "search_score": "feasibility-bands-v1", "enable_thinking": False,
            "feature_dimensions": ["trade_count", "turnover"]}


class NoThinkingLLM(OpenAILLM):
    """Upstream client extension point; the override injects enable_thinking into extra_body."""

    async def _call_api(self, params):
        params = {**params, "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        response = await asyncio.to_thread(self.client.chat.completions.create, **params)
        choice = response.choices[0]
        if choice.finish_reason != "stop" or not (choice.message.content or "").strip():
            raise ValueError("model returned empty or incomplete content")
        return choice.message.content


def make_ensemble(model, settings):
    endpoint = os.environ["EVOLVE_MODEL_ENDPOINT"].rstrip("/")
    suffix = "/chat/completions"
    if not endpoint.endswith(suffix):
        raise ValueError("EVOLVE_MODEL_ENDPOINT must end with /chat/completions")
    # Credentials stay only in memory; never serialize LLMConfig to the run.
    config = LLMConfig(
        api_base=endpoint[:-len(suffix)], api_key=os.environ["EVOLVE_MODEL_API_KEY"],
        temperature=model["temperature"], max_tokens=model["max_tokens"],
        timeout=120, retries=0, random_seed=settings.random_seed,
        models=[LLMModelConfig(name=model["model"], init_client=NoThinkingLLM)],
    )
    return LLMEnsemble(config.models)


def parse_source(response):
    """Accept plain source or a single fence, without discarding extra program text."""
    source = response.strip()
    if source.startswith("```"):
        lines = source.splitlines()
        if lines[0].strip() not in ("```", "```python") or lines[-1].strip() != "```":
            return source  # AST validation records malformed responses as invalid.
        source = "\n".join(lines[1:-1]).strip()
    return source


def search_feedback(record, config):
    """A bounded search-only score; authoritative rank_results remains unchanged.

    Invalid: 0; executable but ineligible: (0, 1]; eligible: (2, 3).
    Each normalized violation contributes d/(1+d), averaged across cells.
    No NaN/None goes into the OpenEvolve numeric metric database.
    """
    deficits = []
    cells = record["cells"]
    for cell in cells:
        if cell.get("status") != "valid":
            deficits.append({"execution": 1.0})
            continue
        m = cell["metrics"]
        sharpe = m["sharpe"]
        deficits.append({
            "trade_count": max(0, config.min_trades - m["trade_count"]) / config.min_trades,
            "drawdown": max(0, m["max_drawdown"] - config.max_drawdown) / max(config.max_drawdown, 1e-12),
            "turnover": max(0, m["turnover"] - config.max_turnover) / config.max_turnover,
            "sharpe": 1.0 if sharpe is None else
                max(0, config.min_worst_sharpe - sharpe) / max(1, abs(config.min_worst_sharpe)),
            "coverage": max(max(0, config.min_markout_coverage - cell["markout"][h]["coverage"])
                            / max(config.min_markout_coverage, 1e-12) for h in config.markout_horizons),
        })
    penalty = sum(sum(d / (1 + d) for d in row.values()) for row in deficits) / max(1, len(deficits))
    if "undefined ranking metric" in record["ranking"].get("violations", []):
        penalty += 1.0
    status = record["ranking"]["status"]
    if status == "valid":
        fitness = record["ranking"]["fitness"]
        combined = 2.5 + atan(fitness) / pi
    elif status == "invalid_candidate":
        combined = 0.0
    else:
        combined = 1 / (1 + penalty)
    valid_cells = [c for c in cells if c.get("status") == "valid"]
    metrics = {
        "combined_score": combined, "eligible": float(status == "valid"),
        "constraint_distance": penalty,
        "trade_count": sum(c["metrics"]["trade_count"] for c in valid_cells) / max(1, len(valid_cells)),
        "turnover": sum(c["metrics"]["turnover"] for c in valid_cells) / max(1, len(valid_cells)),
    }
    if not all(isfinite(v) for v in metrics.values()):
        raise ValueError("non-finite evaluator feedback")
    summary = feedback(record)
    summary["normalized_violations"] = deficits
    return metrics, {"evaluation": canonical(summary)}


class OpenEvolveSearch(CandidateJournal):
    def __init__(self, *, settings, system_prompt, **kwargs):
        system_prompt += (
            "\nSearch score: combined_score is higher-is-better. Eligible candidates score"
            " between 2 and 3; executable but ineligible candidates score at most 1."
            " constraint_distance is lower-is-better; zero alone does not imply eligibility."
            " trade_count and turnover are diversity coordinates, NOT objectives to maximize."
            " The final gate is unchanged; a failed policy may be a parent but cannot be selected."
        )
        contract = {**kwargs.pop("contract"), "search": backend_contract(settings),
                    "system_prompt": system_prompt}
        super().__init__(contract=contract, **kwargs)
        self.settings = settings
        self.database = ProgramDatabase(DatabaseConfig(
            population_size=settings.population_size, archive_size=settings.population_size,
            num_islands=settings.num_islands, migration_interval=settings.migration_interval,
            feature_dimensions=["trade_count", "turnover"], feature_bins=settings.feature_bins,
            random_seed=settings.random_seed, cleanup_old_artifacts=False,
            artifacts_base_path=str(self.output / "openevolve-artifacts"),
        ))
        self.sampler = PromptSampler(PromptConfig(
            system_message=system_prompt, use_template_stochasticity=False,
            num_top_programs=2, num_diverse_programs=2, include_artifacts=True,
        ))

    def run(self, seeds, *, budget, ensemble=None):
        return asyncio.run(self.run_async(seeds, budget=budget, ensemble=ensemble))

    async def run_async(self, seeds, *, budget, ensemble=None):
        if not seeds or budget < len(seeds):
            raise ValueError("budget must cover a nonempty seed population")
        if budget > len(seeds) and ensemble is None:
            raise ValueError("OpenEvolve LLM ensemble required beyond seed budget")
        # Database IDs identify attempts, not source hashes: duplicate proposals
        # keep their true lineage but reuse evaluation through CandidateJournal.
        latest = None
        artifacts_by_hash = {}
        for generation in range(budget):
            parent, prompt, inspirations, response = None, None, [], None
            island = generation % self.settings.num_islands
            try:
                if generation < len(seeds):
                    source = seeds[generation]
                else:
                    if not self.database.programs:
                        raise ValueError("no executable seed available as an OpenEvolve parent")
                    parent, inspirations = self.database.sample_from_island(island, num_inspirations=2)
                    top = self.database.get_top_programs(2, island_idx=island)
                    # Upstream migration copies metrics/metadata, not artifacts.
                    # Resolve by immutable source hash so migrated parents retain feedback.
                    artifacts = artifacts_by_hash[parent.metadata["candidate_hash"]]
                    if latest is not None:
                        artifacts = {**artifacts, "latest_attempt": canonical(feedback(latest))}
                    prompt = self.sampler.build_prompt(
                        current_program=parent.code, parent_program=parent.code,
                        program_metrics=parent.metrics, top_programs=[p.to_dict() for p in top],
                        inspirations=[p.to_dict() for p in inspirations], language="python",
                        evolution_round=generation, diff_based_evolution=False,
                        program_artifacts=artifacts,
                        feature_dimensions=self.database.config.feature_dimensions,
                    )
                    response = await ensemble.generate_with_context(
                        system_message=prompt["system"], messages=[{"role": "user", "content": prompt["user"]}])
                    source = parse_source(response)
            except Exception as exc:
                write_json(self.output / "search-error.json", {
                    "generation": generation, "stage": "proposer", "error_type": type(exc).__name__,
                })
                raise
            request = {"backend": "openevolve", "island": island,
                       "parent_id": parent.id if parent else None,
                       "inspiration_ids": [p.id for p in inspirations], "prompt": prompt,
                       "response": response}
            latest = self.record(source, generation=generation, request=request,
                                 parent_hash=parent.metadata["candidate_hash"] if parent else None)
            metrics, artifacts = search_feedback(latest, self.score)
            write_json(self.output / f"feedback-{generation:05d}.json", {
                "metrics": metrics, "artifacts": artifacts,
            })
            artifacts_by_hash[latest["candidate_hash"]] = artifacts
            if latest["ranking"]["status"] != "invalid_candidate":
                program = Program(
                    id=f"attempt-{generation:05d}", code=source,
                    parent_id=parent.id if parent else None,
                    generation=parent.generation + 1 if parent else 0, metrics=metrics,
                    metadata={"candidate_hash": latest["candidate_hash"]},
                )
                self.database.add(program, iteration=generation, target_island=island)
                self.database.store_artifacts(program.id, artifacts)
            self.database.increment_island_generation(island)
            if self.database.should_migrate():
                self.database.migrate_programs()
            self.database.save(str(self.output / "openevolve-database"), iteration=generation)
        # Deliberately do not use database.get_best_program() for final selection.
        return self.select(budget)

"""Versioned candidate journal, legacy search and isolated final evaluation."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import resource

from experiments.open_evolve.policy import Policy, InvalidPolicy, PolicyLimits
from experiments.open_evolve.evaluation import rank_results, ScoreConfig


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()


def write_json(path: Path, value):
    payload = canonical(value) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload)
    temporary.replace(path)


def feedback(record):
    """Only evolution summaries, never raw events or the run/holdout contract."""
    if record is None:
        return None
    return {
        "source": record["source"], "ranking": record["ranking"],
        "metrics": [{**{k: cell.get(k) for k in ("fold", "scenario", "status", "reason")},
                     "metrics": {k: v for k, v in cell.get("metrics", {}).items()
                                 if not isinstance(v, (list, dict))}}
                    for cell in record["cells"]],
        "markout": [{h: {k: v for k, v in summary.items() if k != "rows"}
                     for h, summary in cell.get("markout", {}).items()} for cell in record["cells"]],
    }


class CandidateJournal:
    """Shared evaluation/cache and authoritative final gate, not a search algorithm."""

    def __init__(self, *, output: Path, contract: dict, limits: PolicyLimits,
                 score: ScoreConfig, evaluate, expected_cells=None):
        if output.exists() and any(output.iterdir()):
            raise ValueError("search output must be empty; do not overwrite an existing run")
        output.mkdir(parents=True, exist_ok=True)
        self.output, self.contract = output, contract
        self.limits, self.score, self.evaluate = limits, score, evaluate
        self.expected_cells = set(expected_cells) if expected_cells is not None else None
        self.identity = fingerprint({"contract": contract, "limits": asdict(limits), "score": asdict(score)})
        self.cache, self.records, self.best = {}, [], None
        write_json(output / "contract.json", {
            "hash": self.identity, "contract": contract,
            "limits": asdict(limits), "score": asdict(score),
        })

    def record(self, source, *, generation, parent_hash=None, request=None):
        if not isinstance(source, str):
            raise ValueError("proposer must return Python source text")
        candidate_hash = sha256(source.encode()).hexdigest()
        started = perf_counter()
        cached = candidate_hash in self.cache
        if cached:
            cells, ranking, complexity = self.cache[candidate_hash]
        else:
            try:
                policy = Policy(source, self.limits)
                complexity = policy.complexity
                cells = self.evaluate(policy)
                if any(c.get("status") == "infrastructure_error" for c in cells):
                    raise RuntimeError("infrastructure error: stop run, do not rank incomplete cells")
                if self.expected_cells is not None:
                    keys = [(c.get("fold"), c.get("scenario")) for c in cells]
                    if len(keys) != len(self.expected_cells) or set(keys) != self.expected_cells:
                        raise RuntimeError("incomplete or duplicate fold/scenario results")
                ranking = rank_results(cells, complexity, self.score)
                if any(c.get("status") == "invalid_candidate" for c in cells):
                    ranking = {"status": "invalid_candidate", "fitness": None,
                               "violations": [c.get("reason") for c in cells
                                              if c.get("status") == "invalid_candidate"]}
            except InvalidPolicy as exc:
                cells, complexity = [], None
                ranking = {"status": "invalid_candidate", "fitness": None, "violations": [str(exc)]}
            except Exception as exc:
                write_json(self.output / "search-error.json", {
                    "generation": generation, "candidate_hash": candidate_hash,
                    "stage": "evaluation", "error_type": type(exc).__name__,
                })
                raise
            self.cache[candidate_hash] = cells, ranking, complexity
        record = {
            "generation": generation, "candidate_hash": candidate_hash,
            "contract_hash": self.identity, "parent_hash": parent_hash,
            "source": source, "request": request, "cells": cells, "ranking": ranking,
            "complexity": complexity, "cached": cached, "runtime_seconds": perf_counter() - started,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
        write_json(self.output / f"candidate-{generation:05d}.json", record)
        self.records.append(record)
        if ranking["status"] == "valid" and (self.best is None or
                (-ranking["fitness"], candidate_hash) <
                (-self.best["ranking"]["fitness"], self.best["candidate_hash"])):
            self.best = record
        return record

    def select(self, budget):
        best = self.best
        selection = {
            "contract_hash": self.identity, "budget": budget,
            "status": "selected" if best else "no_eligible_candidate",
            "candidate_hash": best["candidate_hash"] if best else None,
            "source": best["source"] if best else None,
            "ranking": best["ranking"] if best else None,
        }
        write_json(self.output / "selection.json", selection)
        with (self.output / "selection.sha256").open("x") as file:
            file.write(fingerprint(selection) + "\n")
        return selection


class EvolutionSearch(CandidateJournal):
    """Legacy best/latest loop retained as a comparison baseline."""

    def run(self, seeds: list[str], *, budget: int, propose=None):
        if not seeds or budget < len(seeds):
            raise ValueError("budget must cover a nonempty seed population")
        if budget > len(seeds) and propose is None:
            raise ValueError("a proposer is required beyond the seed budget")
        for generation in range(budget):
            request = {"generation": generation, "best": feedback(self.best),
                       "latest": feedback(self.records[-1]) if self.records else None}
            try:
                source = seeds[generation] if generation < len(seeds) else propose(request)
            except Exception as exc:
                write_json(self.output / "search-error.json", {
                    "generation": generation, "stage": "proposer", "error_type": type(exc).__name__,
                })
                raise
            self.record(source, generation=generation, request=request,
                        parent_hash=self.best["candidate_hash"] if self.best and generation >= len(seeds) else None)
        return self.select(budget)


def finalize(run_dir: Path, *, expected_contract_hash: str, evaluate_holdout):
    manifest = json.loads((run_dir / "contract.json").read_text())
    identity = fingerprint({k: manifest[k] for k in ("contract", "limits", "score")})
    selection = json.loads((run_dir / "selection.json").read_text())
    if fingerprint(selection) != (run_dir / "selection.sha256").read_text().strip():
        raise ValueError("frozen selection manifest changed")
    if identity != expected_contract_hash or manifest["hash"] != identity or selection["contract_hash"] != identity:
        raise ValueError("frozen contract mismatch")
    if selection["status"] != "selected":
        raise ValueError("no eligible final candidate")
    policy = Policy(selection["source"], PolicyLimits(**manifest["limits"]))
    if policy.source_hash != selection["candidate_hash"]:
        raise ValueError("frozen candidate hash mismatch")
    # Exclusive marker precedes any holdout access, including failed evaluations.
    # Infrastructure failures require an explicit external audited recovery procedure.
    marker = run_dir / "holdout-started.json"
    with marker.open("x") as file:
        file.write(canonical({"contract_hash": identity, "candidate_hash": policy.source_hash}))
    try:
        cells = evaluate_holdout(policy, manifest["contract"])
        result = {"contract_hash": identity, "candidate_hash": policy.source_hash, "cells": cells}
        write_json(run_dir / "holdout-result.json", result)
        return result
    except Exception as exc:
        write_json(run_dir / "holdout-error.json", {"error_type": type(exc).__name__})
        raise

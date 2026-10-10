# Evolution Collaboration Instructions

This file is the AI collaboration entry point for `evolution/`. Read the root
[`AGENTS.md`](../AGENTS.md) first. When instructions conflict, this file has priority
for files under `evolution/`, as in [`research/AGENTS.md`](../research/AGENTS.md).

## Scope

`evolution/` holds the OpenEvolve strategy search runtime, its sandbox, the evolution
protocols, and the hypothesis family preregistrations. Evolution experiments are tasks
under `tasks/`, and their reports follow the root workflow.

## Branches and tasks

- Changes to the evolution runtime or its protocols are `chore/` work, or part of the
  task that needs them under the root file rule.

## Families

- New families go in new `evolution/families/<id>/` directories, not in edits to existing
  families.
- A family's `README.md` bytes are hashed into its signal diagnostics. Editing it changes
  results.

## Protocols

- [Strategy evolution guide](docs/strategy-evolution.md)
- [Promotion protocol](docs/promotion-protocol.md)
- [Experiment ledger](docs/experiment-ledger.md)
- [Execution cost profile v2](docs/execution-cost-profile-v2.md)

## Boundaries

Discovery folds support repeated search and diagnosis. Validation selects from a
preregistered candidate set only after executable discovery qualification passes.
Holdout evaluates the validation champion once, under a family-level lock. Do not use
validation or holdout artifacts, results, or data to guide a hypothesis, feature, fitness
rule, or search configuration. Machine gates, not documentation or operator intent,
control access.

The governance ledgers in `data/evolution-governance/` follow the root data rules.

## Configuration

- `evolve` and `resume` use the self-hosted idlab vLLM endpoint and `qwen3.8-27b` from
  `evolution/configs/base.yaml`. Set `VLLM_API_KEY` outside the repository only if the
  endpoint requires it.
- `--iterations` is a total target. `resume` defaults to the last approved target.
- New runs never overwrite existing run directories.
- Legacy runs without identity snapshots cannot resume safely.

## Sandbox

Build the sandbox image and point the runner at it:

```bash
docker build -f evolution/docker/Dockerfile -t alpha-evolution-sandbox:0.2 .
EVOLUTION_SANDBOX_IMAGE=alpha-evolution-sandbox:0.2 \
  uv run python -m evolution --help
```

The image build uses `uv sync --frozen --no-dev` and copies only the sandbox runtime
packages. A full evolution run also needs schema-v2 discovery data and idlab vLLM access.
Use `--dataset-root data/evolution-data-v2` for the existing v2 catalogs. Do not relabel
v1 manifests to pass preflight.

## Verification

```bash
uv run python -m evolution --help
```

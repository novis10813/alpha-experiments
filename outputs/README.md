# Experiment Outputs

`outputs/` is a local scratch area for generated experiment artifacts.

Generated CSV, HTML, image, and diagnostic files should not be committed. They
should be reproducible from commands recorded in `docs/research/`.

Expected subdirectories:

- `outputs/alphas/` for generated canonical alpha-shaped CSVs.
- `outputs/market/` for exported market-data CSVs used by diagnostics.
- `outputs/reports/` for generated HTML, image, and report artifacts.

After an experiment is complete, clean generated files from this directory and
keep the durable findings in the relevant research note.

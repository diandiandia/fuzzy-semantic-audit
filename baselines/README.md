# V3 Golden Baselines Benchmark Framework

This directory contains the definitions and case targets for system regression, recall rates, and static prune metrics.

## Directory Structure

- `repos.yaml`: Target repository identifiers and notes.
- `cases/`: Standard test cases for testing candidate recall and pruning behavior.
  - `python_airflow_like.yaml`
  - `ts_supabase_like.yaml`
  - `go_grafana_like.yaml`

## Running Evaluations

You can execute evaluations using the `scripts/evaluate_baseline.py` script.

Default single-case mode runs the synthetic fixture:

```bash
python3 scripts/evaluate_baseline.py
```

Full baseline mode reads `repos.yaml` and all files in `cases/`:

```bash
python3 scripts/evaluate_baseline.py --all --include-disabled
```

Real repositories are not downloaded by the evaluator. Point the evaluator at local checkouts using one of:

- `FSA_BASELINE_AIRFLOW_DIR`, `FSA_BASELINE_GRAFANA_DIR`, `FSA_BASELINE_SUPABASE_DIR`
- `FSA_BASELINE_REPO_ROOT`, with checkout directories matching `checkout_dir`
- `local_path` entries in `repos.yaml`

Use `--fail-on-skipped` in CI to ensure missing real baselines fail the run instead of being reported as skipped.

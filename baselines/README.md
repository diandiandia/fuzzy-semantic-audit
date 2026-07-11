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

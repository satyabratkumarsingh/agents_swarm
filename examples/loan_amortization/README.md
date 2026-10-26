# Loan amortization example

A sample end-to-end goal for the agents_swarm planner and worker team. It asks the swarm to build a deterministic fixed-rate loan amortization and scenario comparison CLI, with monthly schedules, annual roll-ups, reports, and tests. Input scenarios are synthetic and are not financial advice or offers of credit.

## Run from the repository root

Activate the Python environment where agents_swarm is installed, configure `ANTHROPIC_API_KEY` locally, and make sure the QuickSand runtime is installed. Then run:

```sh
TEAM_WORKSPACE=examples/loan_amortization .venv/bin/agents-swarm run-file examples/loan_amortization/goal.md --agents analyst-1,analyst-2,integrator
```

This mounts the example directory into each QuickSand VM at `/workspace`. The goal and `loan_scenarios.csv` are available there. Agents should place generated source code and tests under `output/`; the final project report is saved under `output/reports/project-<id>-final.md`. Shared coordination state remains under `.team/team.sqlite3` by default.

The sample includes 30-, 20-, and 15-year fixed-rate scenarios plus a zero-interest case to exercise edge-case handling.

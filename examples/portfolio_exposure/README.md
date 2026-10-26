# Portfolio exposure analyzer example

A sample end-to-end goal for the agents_swarm planner and worker team. It asks the swarm to build a local CSV-based portfolio exposure CLI, tests, and report formats. The holdings are synthetic and for software testing only; this is not investment advice.

## Run from the repository root

First activate the project virtual environment, install the project if needed, and set `ANTHROPIC_API_KEY` in the repository's local `.env` or shell. Then run:

```sh
TEAM_WORKSPACE=examples/portfolio_exposure .venv/bin/agents-swarm run-file examples/portfolio_exposure/goal.md --agents analyst-1,analyst-2,integrator
```

This mounts this example directory into each Quicksand VM at `/workspace`. The brief and `holdings.csv` are readable there. Agents are instructed to put all generated source and tests in `output/`; the final project summary is written by the runner to `output/reports/project-<id>-final.md`. The SQLite coordination data remains in `.team/team.sqlite3` by default.

The test dataset totals $1,000,000 and intentionally contains blank sector labels and a zero-value position to exercise metadata and validation handling.

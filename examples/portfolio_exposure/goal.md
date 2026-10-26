# Goal: Build a local portfolio exposure analyzer

Create a small, reliable Python command-line application that reads a user-provided CSV of investment holdings and produces an auditable exposure report. This is a coding task on the synthetic sample data in this example; do not fetch live prices or external data, and do not make investment recommendations.

## Required behavior

1. Read the supplied `holdings.csv`. Each row represents one position and includes `symbol`, `name`, `asset_class`, `sector`, `region`, `currency`, and `market_value`.
2. Validate required columns, non-empty symbols, numeric finite non-negative market values, and a positive total portfolio value. Fail with a clear actionable error for invalid input rather than silently dropping rows.
3. Calculate total market value and each position's portfolio weight.
4. Report exposure and weights grouped by asset class, sector, region, and currency. Treat blank/unknown metadata as `Unknown` and disclose its share.
5. Report concentration indicators: largest position and weight, top-five position weight, and Herfindahl-Hirschman Index (HHI) on fractional weights.
6. Provide a CLI that accepts an input CSV and output directory, writes both `report.md` and `report.json`, and has a useful `--help` message.
7. Include automated tests covering normal calculations, missing metadata, malformed input, and concentration calculations. Use deterministic math; no network calls.
8. Put all generated source, tests, and other deliverables under the `output/` directory in this example workspace. Do not change the brief, input CSV, repository files outside this example, or any secrets.

## Acceptance checks

- Running the tool against `holdings.csv` produces Markdown and JSON reports with totals and all four exposure dimensions.
- Position weights sum to 100% (within floating-point tolerance); each exposure dimension also totals 100%.
- HHI is `sum(weight_fraction ** 2)` and is reported as a value from 0 to 1.
- The tests pass in the provided isolated execution environment. Record the exact test command and result in the final summary.
- The output explicitly states that this report is descriptive, based only on supplied market values/labels, and is not financial advice.

## Coordination guidance

Agents may divide implementation, validation, and report-format work, but avoid editing the same files concurrently. Share assumptions and verified results on the team board. One worker should integrate and run the complete test suite before marking integration work complete.

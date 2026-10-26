# Goal: Build a loan amortization and scenario comparison tool

Create a small, reliable Python command-line application that reads a CSV of fixed-rate loan scenarios and produces auditable monthly amortization schedules and a comparison report. Use only the synthetic inputs included with this example: do not fetch rates or external data, and do not provide personalized financial recommendations.

## Input format

Read `loan_scenarios.csv`. Each row is one independent fixed-rate loan scenario with:

- `scenario`: unique non-empty label
- `principal`: positive starting balance in dollars
- `annual_rate`: nominal annual percentage rate (for example, `6.25` means 6.25%; zero is allowed)
- `term_months`: positive whole-number term
- `origination_fee`: non-negative one-time fee in dollars, reported separately and not financed into principal

## Required behavior

1. Validate required columns, unique scenario names, finite numeric values, principal > 0, annual rate >= 0, positive integer term, and fee >= 0. Fail clearly on invalid input; do not silently skip rows.
2. Calculate the fixed monthly payment using the standard amortizing-loan formula, using the monthly rate `annual_rate / 100 / 12`. Handle zero interest as principal divided by number of payments.
3. Generate a month-by-month schedule with opening balance, payment, principal paid, interest paid, and closing balance. Round currency values to cents; adjust the last payment if needed so the balance reaches exactly zero without overpayment.
4. Summarize each scenario with scheduled payment, total interest, origination fee, total cash paid (principal + interest + fee), and payoff month. Clearly state fees are excluded from the scheduled installment.
5. Include annual roll-ups of principal and interest paid, plus a side-by-side scenario comparison. Include the payment and total-interest difference relative to the lowest-rate scenario, but do not recommend a product.
6. Provide a CLI accepting an input CSV and output directory. Write `report.md` and `report.json`; provide helpful `--help` output and actionable errors.
7. Add automated tests for normal amortization, zero-interest loans, validation failures, final-payment adjustment, and scenario comparison. Use deterministic calculations and no network access.
8. Place all generated source, tests, and deliverables under `output/` in this example workspace. Do not alter the brief, input CSV, repository files outside this example, or secrets.

## Acceptance checks

- Running the tool against `loan_scenarios.csv` writes Markdown and JSON reports containing complete monthly schedules, annual roll-ups, and a scenario comparison.
- Each schedule ends at zero balance; total principal repaid equals starting principal; total cash paid equals principal + interest + fee.
- Zero-rate loan payment equals principal divided by term, to the nearest cent with the final payment adjusted for rounding.
- Tests pass in the isolated execution environment. Record the exact command and result in the final summary.
- Reports are descriptive calculations based only on the supplied assumptions and explicitly state they are not financial advice or an offer of credit.

## Coordination guidance

Agents may split calculation logic, CLI/reporting, and tests, but avoid editing the same files concurrently. Share assumptions and verified results on the team board. One worker should integrate the implementation and run the entire test suite before marking the integration task complete.

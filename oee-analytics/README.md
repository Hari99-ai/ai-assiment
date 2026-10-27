# Industrial OEE Analytics and Machine Monitoring

A reproducible synthetic manufacturing analytics project for the YottaFlex.ai Associate AI Forward Deployed Engineer challenge. It generates linked plant, line, machine, shift, product, order, state, count, inspection and downtime data; preserves injected faults; detects rule based anomalies; calculates machine OEE; and exports CSV, JSON, SQLite and reports.

## Run it

Python 3.11 or newer is recommended (the implementation was executed with Python 3.12). From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/run_pipeline.py --scale small --seed 20261022
python -m pytest -q
```

For full target volumes run `python scripts/run_pipeline.py --scale full --seed 20261022`. This creates 100,000 state intervals, 500,000 production count transactions, and 500,000 inspections (the ambiguous requirement is interpreted as separate minimums). `config/config.yaml` defines both scales. The small scale runs the same implementation with 2 lines, 5 machines, 7 days and a few thousand records.

CLI commands: `python -m src.cli generate --scale small --seed 20261022`, `python -m src.cli validate`, `python -m src.cli calculate-oee`, and `python -m src.cli report`. The last three currently regenerate the small dataset as a self-contained demonstration.

## Design and business rules

See [architecture](docs/architecture.md), [business rules](docs/business_rules.md), [data dictionary](docs/data_dictionary.md), [database schema](docs/database_schema.md), and [validation report](docs/validation_report.md). The main flow is deterministic generation → anomaly injection → rule validation and detection → calculation → exports. Seeded NumPy generators and stable identifiers make generated operational tables repeatable. Ground truth is written separately under `data/ground_truth/` and is only used to score detections.

OEE formulas use minutes and units: availability = operating / planned; performance = sum(ideal cycle minutes × total units) / operating minutes; quality = good / total; OEE = product of the three fractions. Planned breaks are excluded from a shift's 480 minutes, leaving 450 planned minutes. Changeovers count as downtime. Performance above 100% is flagged and never capped. Undefined denominators return explicit statuses. The generator uses increment counts; rework is not included in good-unit totals. Count corrections are append-only by model, while the deliberately invalid negative transaction demonstrates a missing correction link.

State events are half-open intervals `[start, end)`. Normal synthetic intervals are scheduled without overlap; the labelled overlap is preserved. The detector reports intersections and does not rewrite source rows. A known reference rule detects the deliberate cycle-time mutation; production data alone cannot prove that a plausible cycle-time value is wrong.

## Outputs

`data/generated/` contains entity CSVs, key JSON snapshots, `oee_aggregates.csv`, `oee.sqlite`, and a SHA-256 manifest. `data/ground_truth/ground_truth.csv` holds five injected scenarios. `data/reports/` contains inventory, validation, evaluation and anomaly JSON, machine/line/shift CSVs, detected anomalies and charts. Full-scale generation uses pandas in-memory tables and can require substantial RAM; generation runtime and file checksums are recorded. No full-scale runtime is claimed until run.

## Tests and CI

`pytest -q` covers the independent OEE fixture, undefined cases, injected anomaly detection, separation of truth labels, and fixed-seed output. GitHub Actions runs the suite on pushes and pull requests using Python 3.11. The local run reported in this delivery is 4 passed.

## Limitations and next steps

The current materialized OEE grain is machine over the full configured horizon; line totals are exported, while shift output currently marks that its OEE is not calculated. Daily and order level aggregates, robust count-to-inspection reconciliation, cycle-time effective dating, correction linkage examples, deeper structural/FK validation summaries and full-scale resource measurements remain follow-up work. The SQL schema includes all eleven entities; generated persistence currently loads the ten operational entities and machine aggregates. No public repository has been created or committed from this workspace.

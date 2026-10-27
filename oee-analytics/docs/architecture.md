# Architecture

`src/generator/generate.py` creates master and operational tables in dependency order using a local seeded NumPy generator. It injects five clearly specified faults after baseline generation and writes their labels to a separate ground-truth CSV. `src/analytics` contains metric formulas and source-driven detectors. `src/database` provides a SQLite schema and connection setup. `scripts/run_pipeline.py` orchestrates generation, scoring, exports, database load, and charts.

```text
config → generator → CSV inputs → detector + OEE calculator → reports / SQLite
                                      ↘ isolated ground truth → evaluation
```

All timestamps are ISO local-naive timestamps on the synthetic plant calendar. State intervals are half open. Files are sorted by primary key before CSV output. See [database schema](database_schema.md) for entity relationships.

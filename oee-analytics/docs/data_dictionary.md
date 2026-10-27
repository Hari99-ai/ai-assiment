# Data dictionary

All IDs are immutable strings and are primary keys unless marked FK. Times use ISO 8601 local-naive synthetic timestamps. Quantities are units; time durations are minutes; cycle time is seconds/unit.

| Entity/table | Key fields | Relationships and constraints |
|---|---|---|
| Plant | plant_id, name | One plant → many lines |
| Line | line_id, plant_id FK, name | One line → many machines |
| Machine | machine_id, line_id FK, name, ideal_cycle_seconds | Positive reference cycle; one line per machine |
| Shift | shift_id, report_date, code, start_hour, duration_minutes, break_minutes | Stable date + A/B/C identifier |
| Product | product_id, name | Used by orders/inspections |
| ProductionOrder | order_id, machine_id FK, product_id FK, shift_id FK, status, ideal_cycle_seconds | Snapshot of cycle-time reference; lifecycle status string |
| StateEvent | event_id, machine_id FK, state, start_ts, end_ts, source, reason_code | Allowed states: RUNNING, IDLE, PLANNED_STOP, UNPLANNED_STOP, CHANGEOVER, MAINTENANCE, SETUP; end > start |
| ProductionCount | count_id, order_id FK, machine_id FK, timestamp, quantity, count_type, correction_of | PRODUCTION/SCRAP/REWORK/CORRECTION; correction_of nullable |
| QualityInspection | inspection_id, order_id FK, product_id FK, machine_id FK, timestamp, inspected_qty, accepted_qty, rejected_qty, status | Nonnegative; accepted + rejected = inspected for complete inspections |
| DowntimeReason | reason_id, code, planned | Controlled reason vocabulary; code unique |
| OEEAggregate | aggregate_id, scope_type, scope_id, report_date, shift_id, times, quantities, fractions, status, algorithm_version | Unique scope/date/shift grain; metric fractions in [0,1] when valid |

The schema includes the eleven required entities. A product-machine compatibility bridge and effective-dated master history are not yet implemented; order rows preserve cycle time snapshots for past calculations.

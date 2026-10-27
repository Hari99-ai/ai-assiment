# Business rules

* Shift length is 480 minutes. A 30-minute planned break is excluded, yielding 450 planned production minutes. Config selects `exclude_from_planned_time`.
* RUNNING is operating time. IDLE, UNPLANNED_STOP, CHANGEOVER, MAINTENANCE and SETUP are not running; planned break time is excluded. Changeover is included in downtime.
* State intervals use `[start_ts, end_ts)`. Overlaps are retained and flagged; time attribution requires review. The aggregate currently subtracts the sum of downtime intervals capped at planned time, so overlapping intervals can overstate downtime and affected metrics need review.
* Count transactions are unit increments. Negative values are allowed only for a linked correction; the injected negative has no correction reference and is an error. Originals are never overwritten.
* Inspection accepted + rejected should equal inspected. The injected inspection violates rejected ≤ inspected and its quality result is untrustworthy.
* Good quantity is total produced multiplied by the inspection acceptance fraction at machine rollup; rework is excluded. This sample method is not a substitute for lot-level traceability.
* Ideal cycle time is stored on each order as a historical snapshot in seconds/unit. The injected value is checked against the synthetic reference mapping; absent an independent reference, correctness is not inferable.
* OEE components are fractions. Undefined denominators are null with status. Performance is not capped at 1.

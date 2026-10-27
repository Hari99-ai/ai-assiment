# Database schema

`src/database/schema.sql` defines eleven tables with primary keys and foreign keys. Plant 1:M Line, Line 1:M Machine, Product 1:M ProductionOrder, Machine 1:M ProductionOrder/StateEvent/OEEAggregate, Shift 1:M ProductionOrder, ProductionOrder 1:M ProductionCount/QualityInspection, and DowntimeReason is a controlled lookup referenced by `reason_code` in state records. Machine/product compatibility is represented by orders rather than a bridge in this iteration.

SQLite enables foreign-key enforcement on each connection. `OEEAggregate` has a unique scope type, scope ID, date and shift key. SQL output is self-contained in `data/generated/oee.sqlite`.

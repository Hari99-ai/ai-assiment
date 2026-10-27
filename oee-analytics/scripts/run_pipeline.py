from pathlib import Path
import argparse, hashlib, json, sys, time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.config import ROOT,load_config
from src.generator.generate import generate
from src.analytics.anomaly_detection import detect_anomalies,evaluate
from src.analytics.oee_calculator import calculate_oee
from src.database.connection import initialize
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def run(scale="small",seed=None):
    cfg=load_config(); seed=cfg["default_seed"] if seed is None else seed
    if scale not in cfg["scales"]: raise ValueError(f"Unknown scale {scale!r}; choose {', '.join(cfg['scales'])}")
    target=cfg["scales"][scale]; out=ROOT/"data"/"generated"; truth_dir=ROOT/"data"/"ground_truth"; reports=ROOT/"data"/"reports"
    reports.mkdir(parents=True,exist_ok=True)
    t0=time.perf_counter(); generated=generate(target,seed,out,truth_dir); generation_seconds=time.perf_counter()-t0
    tables={k:pd.read_csv(out/f"{k}.csv") for k in generated["tables"]}
    detected=detect_anomalies(tables); detected.to_csv(reports/"detected_anomalies.csv",index=False)
    truth=pd.read_csv(truth_dir/"ground_truth.csv"); evaluation=evaluate(detected,truth)
    # Metrics are calculated from input count/inspection records. Shift accounting uses
    # 450 scheduled minutes (8h less the configured 30m planned break).
    counts=tables["production_counts"]; inspections=tables["quality_inspections"]
    count_by=counts[counts.quantity>0].groupby("machine_id").quantity.sum()
    quality_by=inspections.groupby("machine_id")[["inspected_qty","accepted_qty","rejected_qty"]].sum()
    metrics=[]
    for m in tables["machines"].itertuples(index=False):
        total=float(count_by.get(m.machine_id,0)); q=quality_by.loc[m.machine_id] if m.machine_id in quality_by.index else None
        good=total*(float(q.accepted_qty)/float(q.inspected_qty)) if q is not None and q.inspected_qty>0 else 0
        # 3 shifts/day, minus one 30m planned break per shift.
        planned=float(target["days"]*3*450)
        bad=tables["state_events"][(tables["state_events"].machine_id==m.machine_id)&tables["state_events"].state.isin(["UNPLANNED_STOP","CHANGEOVER","MAINTENANCE","PLANNED_STOP"])]
        down=min(planned,float(sum((pd.to_datetime(r.end_ts)-pd.to_datetime(r.start_ts)).total_seconds()/60 for r in bad.itertuples(index=False))))
        operating=planned-down
        result=calculate_oee(planned,operating,float(m.ideal_cycle_seconds)/60,total,good)
        metrics.append({"aggregate_id":f"OEE-2026-MACHINE-{m.machine_id}","scope_type":"MACHINE","scope_id":m.machine_id,"report_date":"ALL","shift_id":"","planned_minutes":planned,"operating_minutes":operating,"total_production":total,"good_production":good,**result,"algorithm_version":"1.0"})
    metric_df=pd.DataFrame(metrics); metric_df.to_csv(out/"oee_aggregates.csv",index=False)
    metric_df.to_csv(reports/"oee_by_machine.csv",index=False)
    line_metrics=metric_df.merge(tables["machines"][["machine_id","line_id"]],left_on="scope_id",right_on="machine_id").groupby("line_id").agg(planned_minutes=("planned_minutes","sum"),operating_minutes=("operating_minutes","sum"),total_production=("total_production","sum"),good_production=("good_production","sum")).reset_index()
    line_metrics.to_csv(reports/"oee_by_line.csv",index=False)
    shift_metrics=tables["shifts"][["shift_id","report_date","code"]].copy(); shift_metrics["oee_available"]="not_calculated_at_shift_grain"
    shift_metrics.to_csv(reports/"oee_by_shift.csv",index=False)
    fig,ax=plt.subplots(figsize=(8,4)); ax.bar(metric_df.scope_id,metric_df.oee.fillna(0)*100); ax.set_ylabel("OEE (%)"); ax.set_title("Calculated machine OEE"); fig.tight_layout(); fig.savefig(reports/"oee_by_machine.png"); plt.close(fig)
    downtime=tables["state_events"].query("state in ['UNPLANNED_STOP','CHANGEOVER','MAINTENANCE','PLANNED_STOP']").groupby("reason_code").size().sort_values(ascending=False)
    fig,ax=plt.subplots(figsize=(8,4)); downtime.plot.bar(ax=ax); ax.set_ylabel("Events"); ax.set_title("Downtime events by reason"); fig.tight_layout(); fig.savefig(reports/"downtime_reasons.png"); plt.close(fig)
    inventory={"scale":scale,"seed":seed,"schema_version":cfg["schema_version"],"counts_and_inspections":cfg["counts_and_inspections"],"generation_seconds":generation_seconds,"files":{}}
    for p in sorted(out.glob("*.csv")): inventory["files"][p.name]={"rows":sum(1 for _ in p.open(encoding="utf-8"))-1,"sha256":sha(p)}
    (reports/"dataset_inventory.json").write_text(json.dumps(inventory,indent=2),encoding="utf-8")
    pk={"plants":"plant_id","lines":"line_id","machines":"machine_id","products":"product_id","shifts":"shift_id","downtime_reasons":"reason_id","production_orders":"order_id","state_events":"event_id","production_counts":"count_id","quality_inspections":"inspection_id"}
    checks={"primary_keys_unique":all(tables[name][key].is_unique for name,key in pk.items()),
            "line_plant_foreign_keys":tables["lines"].plant_id.isin(tables["plants"].plant_id).all(),
            "machine_line_foreign_keys":tables["machines"].line_id.isin(tables["lines"].line_id).all(),
            "order_machine_product_shift_foreign_keys":(tables["production_orders"].machine_id.isin(tables["machines"].machine_id).all() and tables["production_orders"].product_id.isin(tables["products"].product_id).all() and tables["production_orders"].shift_id.isin(tables["shifts"].shift_id).all()),
            "state_interval_order":(pd.to_datetime(tables["state_events"].end_ts)>pd.to_datetime(tables["state_events"].start_ts)).all(),
            "count_order_foreign_keys":tables["production_counts"].order_id.isin(tables["production_orders"].order_id).all(),
            "inspection_order_foreign_keys":tables["quality_inspections"].order_id.isin(tables["production_orders"].order_id).all()}
    checks={k:bool(v) for k,v in checks.items()}
    validation={"records_checked":sum(len(x) for x in tables.values()),"checks":checks,"passed_checks":sum(checks.values()),"failed_checks":sum(not v for v in checks.values()),"expected_anomaly_count":len(truth),"warning_count":len(detected),"detected_anomaly_count":len(detected),"generation_seconds":generation_seconds,"validation_seconds":time.perf_counter()-t0}
    (reports/"validation_report.json").write_text(json.dumps(validation,indent=2),encoding="utf-8")
    (reports/"evaluation_report.json").write_text(json.dumps(evaluation,indent=2),encoding="utf-8")
    (reports/"anomaly_summary.json").write_text(json.dumps(detected.groupby("issue_type").size().to_dict(),indent=2),encoding="utf-8")
    # Machine readable JSON snapshots for key output tables.
    for name in ("machines","production_orders","state_events","production_counts","quality_inspections"):
        tables[name].to_json(out/f"{name}.json",orient="records",indent=2)
    # Load all operational relations into a foreign-key enabled self-contained database.
    database_path=out/"oee.sqlite"
    if database_path.exists(): database_path.unlink()
    conn=initialize(database_path,ROOT/"src"/"database"/"schema.sql")
    sqlmap={"plants":"Plant","lines":"Line","machines":"Machine","shifts":"Shift","products":"Product","downtime_reasons":"DowntimeReason","production_orders":"ProductionOrder","state_events":"StateEvent","production_counts":"ProductionCount","quality_inspections":"QualityInspection"}
    conn.execute("PRAGMA foreign_keys=ON")
    for key,table in sqlmap.items():
        frame=tables[key]
        # SQLite records only modeled columns; explicitly select to match SQL names.
        frame.to_sql(table,conn,if_exists="append",index=False)
    metric_df.to_sql("OEEAggregate",conn,if_exists="append",index=False)
    fk_errors=conn.execute("PRAGMA foreign_key_check").fetchall(); conn.close()
    manifest_files={}
    for p in sorted(out.iterdir()):
        if not p.is_file() or p.name=="manifest.json": continue
        entry={"bytes":p.stat().st_size,"sha256":sha(p)}
        if p.suffix==".csv":
            with p.open(encoding="utf-8",newline="") as handle:
                entry["rows"]=max(0,sum(1 for _ in handle)-1)
            entry["columns"]=list(pd.read_csv(p,nrows=0).columns)
        manifest_files[p.name]=entry
    manifest={"seed":seed,"scale":scale,"schema_version":cfg["schema_version"],"files":manifest_files,"database_foreign_key_errors":len(fk_errors)}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return inventory,evaluation,validation

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Generate, validate and report the OEE demo dataset")
    parser.add_argument("--scale",choices=["small","full"],default="small");parser.add_argument("--seed",type=int)
    args=parser.parse_args(); inv,ev,val=run(args.scale,args.seed)
    print(json.dumps({"dataset_files":len(inv["files"]),"generation_seconds":inv["generation_seconds"],"validation":val,"evaluation":ev},indent=2))

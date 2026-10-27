"""Build deterministic operational tables with separate injected-label truth."""
from __future__ import annotations
import hashlib, json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd

STATES = ["RUNNING", "IDLE", "PLANNED_STOP", "UNPLANNED_STOP", "CHANGEOVER", "MAINTENANCE", "SETUP"]
REASONS = ["MECHANICAL_FAILURE", "ELECTRICAL_FAILURE", "MATERIAL_SHORTAGE", "CHANGEOVER", "OPERATOR_BREAK", "PLANNED_MAINTENANCE", "QUALITY_HOLD", "UNKNOWN"]

def generate(scale: dict, seed: int, output: Path, truth_dir: Path) -> dict:
    rng = np.random.default_rng(seed)
    output.mkdir(parents=True, exist_ok=True); truth_dir.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)
    plants = pd.DataFrame([{"plant_id":"PLANT-001","name":"Synthetic Plant"}])
    lines = pd.DataFrame([{"line_id":f"LINE-{i+1:03d}","plant_id":"PLANT-001","name":f"Line {i+1}"} for i in range(scale["lines"])])
    machines = pd.DataFrame([{"machine_id":f"MACHINE-{i+1:03d}","line_id":f"LINE-{i%scale['lines']+1:03d}","name":f"Machine {i+1}","ideal_cycle_seconds":int(18+i%6)} for i in range(scale["machines"])])
    products = pd.DataFrame([{"product_id":f"PRODUCT-{i+1:03d}","name":f"Product {i+1}"} for i in range(scale["products"])])
    shifts=[]
    for d in range(scale["days"]):
        day=start+timedelta(days=d)
        for shift in "ABC": shifts.append({"shift_id":f"SHIFT-{day.isoformat()}-{shift}","report_date":day.isoformat(),"code":shift,"start_hour":(0,8,16)["ABC".index(shift)],"duration_minutes":480,"break_minutes":30})
    shifts=pd.DataFrame(shifts)
    reasons=pd.DataFrame([{"reason_id":f"DOWN-{i+1:03d}","code":r,"planned":r in ("OPERATOR_BREAK","PLANNED_MAINTENANCE")} for i,r in enumerate(REASONS)])
    orders=[]
    for i in range(max(scale["machines"]*scale["days"],1)):
        m=i%scale["machines"]; p=i%scale["products"]; sh=shifts.iloc[i%len(shifts)]
        orders.append({"order_id":f"PO-2026-{i+1:06d}","machine_id":machines.iloc[m].machine_id,"product_id":products.iloc[p].product_id,"shift_id":sh.shift_id,"status":"COMPLETED","ideal_cycle_seconds":int(18+m%6)})
    orders=pd.DataFrame(orders)
    event_n=scale["state_events"]
    ev_machine=np.arange(event_n)%scale["machines"]
    ev_day=(np.arange(event_n)//scale["machines"])%scale["days"]
    slots_per_bucket=max(1,int(np.ceil(event_n/(scale["machines"]*scale["days"]))))
    slot=np.arange(event_n)//(scale["machines"]*scale["days"])
    spacing=450/slots_per_bucket
    ev_minute=np.minimum(449,(slot+.05)*spacing).astype(int)
    dur=np.maximum(1,np.minimum(rng.choice([1,2,5,10,20,30],event_n,p=[.12,.15,.28,.23,.17,.05]),max(1,int(spacing*.75))))
    state=rng.choice(STATES,event_n,p=[.67,.10,.04,.08,.05,.03,.03])
    events=[]
    for i in range(event_n):
        dt=datetime.combine(start+timedelta(days=int(ev_day[i])),datetime.min.time())+timedelta(minutes=int(ev_minute[i]))
        events.append({"event_id":f"EVT-MACHINE-{int(ev_machine[i])+1:03d}-{i+1:06d}","machine_id":f"MACHINE-{int(ev_machine[i])+1:03d}","state":state[i],"start_ts":dt.isoformat(),"end_ts":(dt+timedelta(minutes=int(dur[i]))).isoformat(),"source":"SYNTHETIC","reason_code":str(rng.choice(REASONS)) if state[i] in ("UNPLANNED_STOP","CHANGEOVER","MAINTENANCE","PLANNED_STOP") else ""})
    events=pd.DataFrame(events)
    count_n=scale["production_counts"]
    order_ix=rng.integers(0,len(orders),count_n)
    quantities=rng.poisson(100,count_n)+1
    counts=pd.DataFrame({"count_id":[f"CNT-{orders.iloc[int(j)].order_id}-{i+1:06d}" for i,j in enumerate(order_ix)],"order_id":orders.iloc[order_ix].order_id.to_numpy(),"machine_id":orders.iloc[order_ix].machine_id.to_numpy(),"timestamp":[(datetime.combine(start+timedelta(days=int(rng.integers(scale['days']))),datetime.min.time())+timedelta(minutes=int(rng.integers(1440)))).isoformat() for _ in range(count_n)],"quantity":quantities,"count_type":"PRODUCTION","correction_of":""})
    insp_n=scale["quality_inspections"]
    insp_ix=rng.integers(0,len(orders),insp_n)
    inspected=rng.integers(10,121,insp_n); rejected=rng.binomial(inspected,.025)
    inspections=pd.DataFrame({"inspection_id":[f"QC-2026-{i+1:09d}" for i in range(insp_n)],"order_id":orders.iloc[insp_ix].order_id.to_numpy(),"product_id":orders.iloc[insp_ix].product_id.to_numpy(),"machine_id":orders.iloc[insp_ix].machine_id.to_numpy(),"timestamp":[(datetime.combine(start+timedelta(days=int(rng.integers(scale['days']))),datetime.min.time())+timedelta(minutes=int(rng.integers(1440)))).isoformat() for _ in range(insp_n)],"inspected_qty":inspected,"accepted_qty":inspected-rejected,"rejected_qty":rejected,"status":"COMPLETE"})
    # Stable five scenarios. All injected rows remain in operational tables.
    truth=[]
    if len(events)>3:
        a=events.iloc[0]; b=events.iloc[1]; events.loc[1,"machine_id"]=a.machine_id; events.loc[1,"start_ts"]=a.start_ts; events.loc[1,"end_ts"]=(datetime.fromisoformat(a.start_ts)+timedelta(minutes=4)).isoformat()
        truth.append(_truth("ANOM-001","OVERLAPPING_STATES","StateEvent",str(a.machine_id),[str(a.event_id),str(b.event_id)],"interval_overlap","overlap detected","HIGH"))
    if len(counts):
        counts.loc[0,"quantity"]=-int(counts.loc[0,"quantity"]); truth.append(_truth("ANOM-002","INVALID_COUNT_DECREASE","ProductionCount",str(counts.loc[0,"order_id"]),[counts.loc[0,"count_id"]],"negative_delta_without_correction","invalid count flagged","HIGH"))
    if len(inspections):
        inspections.loc[0,"rejected_qty"]=int(inspections.loc[0,"inspected_qty"])+1; inspections.loc[0,"accepted_qty"]=0
        truth.append(_truth("ANOM-003","SCRAP_EXCEEDS_INSPECTED","QualityInspection",str(inspections.loc[0,"order_id"]),[str(inspections.loc[0,"inspection_id"])],"rejected_gt_inspected","quality metric withheld","HIGH"))
    orders.loc[0,"ideal_cycle_seconds"]*=4
    truth.append(_truth("ANOM-004","WRONG_IDEAL_CYCLE_TIME","ProductionOrder",str(orders.loc[0,"order_id"]),[str(orders.loc[0,"order_id"])],"known_reference_mismatch","review against independent master","MEDIUM"))
    if len(events)>5:
        events.loc[2,"state"]="PLANNED_STOP"; events.loc[2,"reason_code"]="OPERATOR_BREAK"
        events.loc[2,"start_ts"]="2026-01-01T10:05:00"; events.loc[2,"end_ts"]="2026-01-01T10:20:00"
        truth.append(_truth("ANOM-005","DOWNTIME_OVERLAPS_BREAK","StateEvent",str(events.loc[2,"machine_id"]),[str(events.loc[2,"event_id"])],"intersection_with_break_window","exclude break time from denominator","LOW"))
    tables={"plants":plants,"lines":lines,"machines":machines,"products":products,"shifts":shifts,"downtime_reasons":reasons,"production_orders":orders,"state_events":events,"production_counts":counts,"quality_inspections":inspections}
    for name,df in tables.items(): df.sort_values(df.columns[0]).to_csv(output/f"{name}.csv",index=False)
    pd.DataFrame(truth).to_csv(truth_dir/"ground_truth.csv",index=False)
    return {"tables":tables,"truth":pd.DataFrame(truth)}

def _truth(aid, issue, entity, entity_id, ids, rule, expected, severity):
    return {"anomaly_id":aid,"issue_type":issue,"entity_type":entity,"entity_id":entity_id,"related_record_ids":"|".join(map(str,ids)),"injection_rule":rule,"expected_detection":expected,"severity":severity,"resolution_status":"OPEN"}

from datetime import datetime
import pandas as pd

def detect_anomalies(tables: dict[str,pd.DataFrame]) -> pd.DataFrame:
    found=[]
    events=tables["state_events"].sort_values(["machine_id","start_ts","end_ts"])
    previous={}
    for row in events.itertuples(index=False):
        start=datetime.fromisoformat(row.start_ts); end=datetime.fromisoformat(row.end_ts)
        prev=previous.get(row.machine_id)
        if prev and start < prev[1]:
            mins=max(0,(min(end,prev[1])-start).total_seconds()/60)
            found.append({"issue_type":"OVERLAPPING_STATES","entity_type":"Machine","entity_id":row.machine_id,"related_record_ids":f"{prev[0]}|{row.event_id}","severity":"HIGH","overlap_minutes":mins})
        if prev is None or end>prev[1]: previous[row.machine_id]=(row.event_id,end)
    c=tables["production_counts"]
    for row in c[c.quantity<0].itertuples(index=False): found.append({"issue_type":"INVALID_COUNT_DECREASE","entity_type":"ProductionOrder","entity_id":row.order_id,"related_record_ids":row.count_id,"severity":"HIGH","overlap_minutes":0})
    q=tables["quality_inspections"]
    for row in q[q.rejected_qty>q.inspected_qty].itertuples(index=False): found.append({"issue_type":"SCRAP_EXCEEDS_INSPECTED","entity_type":"QualityInspection","entity_id":row.order_id,"related_record_ids":row.inspection_id,"severity":"HIGH","overlap_minutes":0})
    # Known-master comparison is explicitly a reference check, not inference from run data.
    o=tables["production_orders"]
    for row in o.itertuples(index=False):
        expected=18+(int(row.machine_id.split("-")[-1])-1)%6
        if row.ideal_cycle_seconds != expected: found.append({"issue_type":"WRONG_IDEAL_CYCLE_TIME","entity_type":"ProductionOrder","entity_id":row.order_id,"related_record_ids":row.order_id,"severity":"MEDIUM","overlap_minutes":0})
    for row in events[events.reason_code=="OPERATOR_BREAK"].itertuples(index=False):
        start=datetime.fromisoformat(row.start_ts); end=datetime.fromisoformat(row.end_ts)
        break_start=start.replace(hour=10,minute=0,second=0,microsecond=0); break_end=break_start.replace(minute=30)
        overlap=max(0,(min(end,break_end)-max(start,break_start)).total_seconds()/60)
        if overlap>0: found.append({"issue_type":"DOWNTIME_OVERLAPS_BREAK","entity_type":"StateEvent","entity_id":row.machine_id,"related_record_ids":row.event_id,"severity":"LOW","overlap_minutes":overlap})
    return pd.DataFrame(found,columns=["issue_type","entity_type","entity_id","related_record_ids","severity","overlap_minutes"])

def evaluate(detected: pd.DataFrame, truth: pd.DataFrame) -> dict:
    truth_types=set(truth.issue_type) if len(truth) else set()
    det_types=set(detected.issue_type) if len(detected) else set()
    by_type={}
    for kind in sorted(truth_types|det_types):
        tp=int(kind in truth_types and kind in det_types); fp=int(kind in det_types and kind not in truth_types); fn=int(kind in truth_types and kind not in det_types)
        precision=tp/(tp+fp) if tp+fp else None; recall=tp/(tp+fn) if tp+fn else None
        by_type[kind]={"ground_truth":int((truth.issue_type==kind).sum()),"detected":int((detected.issue_type==kind).sum()),"true_positives":tp,"false_positives":fp,"false_negatives":fn,"precision":precision,"recall":recall,"f1":(2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None)}
    return {"by_type":by_type,"ground_truth_anomaly_count":len(truth),"detected_anomaly_count":len(detected)}

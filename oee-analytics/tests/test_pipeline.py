import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from src.analytics.anomaly_detection import detect_anomalies,evaluate
from src.generator.generate import generate

def test_small_data_generation_and_truth_separation(tmp_path):
    scale={"plants":1,"lines":2,"machines":5,"products":5,"days":7,"state_events":100,"production_counts":100,"quality_inspections":100}
    a=generate(scale,20261022,tmp_path/"gen",tmp_path/"truth")
    assert len(a["tables"]["machines"])==5
    assert "anomaly_id" not in a["tables"]["state_events"].columns
    assert len(a["truth"])==5
    detections=detect_anomalies(a["tables"])
    assert set(a["truth"].issue_type).issubset(set(detections.issue_type))

def test_fixed_seed_csv_reproducible(tmp_path):
    scale={"plants":1,"lines":1,"machines":2,"products":2,"days":2,"state_events":30,"production_counts":30,"quality_inspections":30}
    generate(scale,7,tmp_path/"a",tmp_path/"ta"); generate(scale,7,tmp_path/"b",tmp_path/"tb")
    assert (tmp_path/"a"/"production_counts.csv").read_bytes()==(tmp_path/"b"/"production_counts.csv").read_bytes()

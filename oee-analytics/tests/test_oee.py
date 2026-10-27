import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from src.analytics.oee_calculator import calculate_oee,performance,quality,availability

def test_example_oee_fixture():
    r=calculate_oee(360,300,.25,1000,950)
    assert r["availability"]==pytest.approx(5/6)
    assert r["performance"]==pytest.approx(5/6)
    assert r["quality"]==pytest.approx(.95)
    assert r["oee"]==pytest.approx((5/6)*(5/6)*.95)

def test_explicit_undefined_and_review_statuses():
    assert performance(.25,10,0).status=="UNDEFINED_NO_OPERATING_TIME"
    assert quality(0,0).status=="UNDEFINED_NO_PRODUCTION"
    assert availability(0,0).value is None
    assert performance(1,20,10).status=="REVIEW_OVER_100_PERCENT"

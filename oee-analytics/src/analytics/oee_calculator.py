from dataclasses import dataclass

@dataclass(frozen=True)
class Metric:
    value: float | None
    status: str

def availability(planned_minutes: float, operating_minutes: float) -> Metric:
    if planned_minutes <= 0:
        return Metric(None, "UNDEFINED_NO_PLANNED_TIME")
    if operating_minutes < 0 or operating_minutes > planned_minutes:
        return Metric(None, "INVALID_TIME_ACCOUNTING")
    return Metric(operating_minutes / planned_minutes, "OK")

def performance(ideal_minutes: float | None, total_units: float, operating_minutes: float) -> Metric:
    if ideal_minutes is None or ideal_minutes <= 0:
        return Metric(None, "UNDEFINED_INVALID_CYCLE_TIME")
    if operating_minutes <= 0:
        return Metric(None, "UNDEFINED_NO_OPERATING_TIME")
    if total_units < 0:
        return Metric(None, "INVALID_NEGATIVE_PRODUCTION")
    value = ideal_minutes * total_units / operating_minutes
    return Metric(value, "REVIEW_OVER_100_PERCENT" if value > 1 else "OK")

def quality(good_units: float, total_units: float) -> Metric:
    if total_units <= 0:
        return Metric(None, "UNDEFINED_NO_PRODUCTION")
    if good_units < 0 or good_units > total_units:
        return Metric(None, "INVALID_QUALITY_RECONCILIATION")
    return Metric(good_units / total_units, "OK")

def calculate_oee(planned_minutes: float, operating_minutes: float, ideal_minutes: float | None,
                  total_units: float, good_units: float) -> dict:
    a = availability(planned_minutes, operating_minutes)
    p = performance(ideal_minutes, total_units, operating_minutes)
    q = quality(good_units, total_units)
    vals = [a.value, p.value, q.value]
    return {"availability": a.value, "performance": p.value, "quality": q.value,
            "oee": None if any(v is None for v in vals) else a.value * p.value * q.value,
            "status": "REVIEW" if any(v is None for v in vals) or p.value > 1 else "OK"}

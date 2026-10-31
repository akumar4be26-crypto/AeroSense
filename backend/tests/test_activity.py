from datetime import datetime

from app.core.config import load_config
from app.services.activity import assess, hourly_index, status_for


def _hourly(pm25_by_hour, start="2026-11-01T00:00"):
    base = datetime.fromisoformat(start)
    times = [f"2026-11-01T{h:02d}:00" for h in range(len(pm25_by_hour))]
    n = len(pm25_by_hour)
    return {
        "time": times,
        "pm2_5": pm25_by_hour,
        "pm10": [v * 1.5 if v is not None else None for v in pm25_by_hour],
        "nitrogen_dioxide": [20.0] * n,
        "carbon_monoxide": [500.0] * n,
        "sulphur_dioxide": [10.0] * n,
        "ozone": [30.0] * n,
    }


def test_index_none_when_particulates_missing():
    cfg = load_config()
    h = {"time": ["t"], "pm2_5": [None], "pm10": [None], "nitrogen_dioxide": [20.0], "ozone": [30.0], "sulphur_dioxide": [5.0]}
    assert hourly_index(cfg, h, 0)["index"] is None


def test_status_thresholds():
    p = load_config().activity.profiles["runner"]
    assert status_for(p, 50) == "safe"
    assert status_for(p, 120) == "caution"
    assert status_for(p, 300) == "avoid"
    assert status_for(p, None) == "unknown"


def test_best_window_is_cleanest_waking_hour_and_ignores_night_and_past():
    cfg = load_config()
    values = [5.0] + [200.0] * 5 + [15.0] + [200.0] * 16  # 00:00 is very clean but outside waking hours
    result = assess(cfg, _hourly(values), datetime(2026, 11, 1, 0))
    best = result["profiles"]["runner"]["best_windows"]
    assert all(5 <= int(w["start"][11:13]) < 22 for w in best)
    cleanest = min(best, key=lambda w: w["mean_index"])
    assert cleanest["start"].endswith("06:00") and cleanest["status"] == "safe"
    past = assess(cfg, _hourly(values), datetime(2026, 11, 1, 7))
    assert all(h["time"] >= "2026-11-01T07:00" for h in past["hours"])


def test_all_polluted_reports_no_safe_hours():
    cfg = load_config()
    result = assess(cfg, _hourly([250.0] * 24), datetime(2026, 11, 1, 0))
    for profile in result["profiles"].values():
        assert profile["safe_hours_waking"] == 0
        assert all(w["status"] != "safe" for w in profile["best_windows"])

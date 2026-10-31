from datetime import datetime

import pytest

from app.core.config import load_config
from app.services.diversion import assess, build_grid, classify

CFG = load_config()
D = CFG.diversion


def test_grid_is_centred_and_north_first():
    cells = build_grid(D, 30.0, 76.0)
    assert len(cells) == D.grid.size**2
    assert cells[0]["row"] == 0 and cells[0]["label"].startswith("NW")
    centre = [c for c in cells if c["label"] == "Centre"]
    assert len(centre) == 1 and (centre[0]["latitude"], centre[0]["longitude"]) == (30.0, 76.0)


@pytest.mark.parametrize(
    "wind,blh,pm25,pm10,tier",
    [
        (1.0, 200, 120, 200, "divert"),  # calm + severe
        (1.0, 200, 70, 90, "watch"),  # calm + elevated
        (5.0, 1500, 120, 200, "watch"),  # well ventilated but severe
        (5.0, 1500, 30, 60, "clear"),
        (1.0, 200, 20, 40, "clear"),  # calm but clean air is not flagged
    ],
)
def test_classify_tiers(wind, blh, pm25, pm10, tier):
    assert classify(D, wind, blh, pm25, pm10)["tier"] == tier


def test_missing_data_is_unknown_not_clear():
    assert classify(D, None, 500, 100, 100)["tier"] == "unknown"
    assert classify(D, 2.0, 500, None, None)["tier"] == "unknown"


def _provider_rows(hours, wind, blh, pm25):
    times = [f"2026-11-01T{h:02d}:00" for h in range(hours)]
    weather = {"hourly": {"time": times, "wind_speed_10m": [wind(h) for h in range(hours)], "boundary_layer_height": [blh(h) for h in range(hours)]}}
    air = {"hourly": {"time": times, "pm2_5": [pm25(h) for h in range(hours)], "pm10": [pm25(h) * 2 for h in range(hours)], "nitrogen_dioxide": [20.0] * hours, "carbon_monoxide": [500.0] * hours}}
    return weather, air


def test_assess_finds_windows_and_ranks_zones():
    cells = build_grid(D, 30.0, 76.0)
    weather, air = [], []
    for i, _ in enumerate(cells):
        # Cell 0 is stagnant for hours 2-5; others are well ventilated.
        stagnant = lambda h, i=i: i == 0 and 2 <= h <= 5
        w, a = _provider_rows(8, lambda h, s=stagnant: 0.8 if s(h) else 5.0, lambda h, s=stagnant: 150 if s(h) else 1500, lambda h: 100.0 if 2 <= h <= 5 else 20.0)
        weather.append(w)
        air.append(a)
    result = assess(CFG, cells, weather, air, datetime(2026, 11, 1, 0))
    windows = result["windows"]
    assert len(windows) == 1 and windows[0]["tier"] == "divert"
    assert windows[0]["start"].endswith("02:00") and windows[0]["end"].endswith("05:00")
    assert windows[0]["ranked_zones"][0] == cells[0]["id"]
    assert result["hours"][0]["tier"] == "clear"


def test_assess_ignores_past_hours():
    cells = build_grid(D, 30.0, 76.0)
    w, a = _provider_rows(6, lambda h: 5.0, lambda h: 1500, lambda h: 20.0)
    result = assess(CFG, cells, [w] * len(cells), [a] * len(cells), datetime(2026, 11, 1, 3))
    assert result["hours"][0]["time"].endswith("03:00") and len(result["hours"]) == 3

# state/

Files the workflows commit back after each run. GitHub Actions throws away
everything else, so this directory is the agent's only memory.

| File | Written by | What it is |
|---|---|---|
| `forecast_log.json` | `run_forecast.py` | Every forecast issued, and its score once verified |
| `snowline_calibration.json` | `run_verify.py` | The learned snow-line offset. Inactive until 20 verified events |
| `home_gauge.json` | **you, by hand** | The stake reading at CR 500 |

## home_gauge.json — the one file you maintain

Same pattern as `config/fire_status.json` in the conditions bot: edit it, push,
done. Keyed by ISO date.

```json
{
  "2026-11-04": {
    "new_snow_in": 6.5,
    "precip_in": 0.41,
    "snow_line_observed_ft": 7300,
    "note": "wind scoured the stake, probably closer to 8"
  }
}
```

`snow_line_observed_ft` is the most valuable number in the entire system. It is
the only direct observation of the thing the forecast is named for, and it is
what calibrates the heuristic. Roughly: the elevation where you could see the
transition from wet to sticking — up the 501, up the 240, or across on
Missionary Ridge. An estimate to the nearest hundred feet is worth far more
than a blank.

Nothing breaks if you skip days. Calibration just takes longer to reach 20
events.

# Self-test — live endpoint check

Run: 2026-08-31T03:40:23+00:00
Result: **12/16 sources reachable**

## The elevation thesis
**PASS.** The bands return different forecasts, so the elevation parameter is being honoured and elevation-band forecasting works.

| Band | Elevation requested (m) | Elevation used (m) | First-hour temp |
|---|---|---|---|
| Durango and the Animas Valley | 1981 | 1981.0 | 64.5 |
| Bayfield and up the Pine | 2103 | 2103.0 | 63.4 |
| Vallecito and the Florida | 2332 | 2332.0 | 61.0 |
| The high Weminuche | 3200 | 3200.0 | 49.8 |

## NWS zones
| Point | Forecast zone | Fire zone | Grid |
|---|---|---|---|
| vallecito | COZ019 | COZ295 | GJT/124,23 |
| durango | COZ022 | COZ295 | GJT/111,19 |

Confirmed: Vallecito (COZ019) is in a different forecast zone than Durango (COZ022). Polling only one of them would miss the other's warnings.

## Every source

| Source | OK | Detail |
|---|---|---|
| CAIC zone for Vallecito | NO | only 1 polygon(s) published -- CAIC is out of season. Re-run mid-Nov to mid-Apr. Do NOT trust a point-in-polygon result against a single statewide shape. |
| CDOT road conditions | NO | CDOT_API_KEY not set -- free at data.cotrip.org |
| CoCoRaHS reports | NO | AL: HTTP Error 500: Internal Server Error |
| Colorado DWR reservoir | yes |  |
| NRCS SNOTEL | yes |  |
| NWS AFD (GJT) | yes |  |
| NWS alerts (COZ019 + COZ022) | yes |  |
| NWS gridpoint durango | yes |  |
| NWS gridpoint vallecito | yes |  |
| Open-Meteo bayfield @ 6900ft | yes |  |
| Open-Meteo durango @ 6500ft | yes |  |
| Open-Meteo model spread | yes |  |
| Open-Meteo vallecito @ 7650ft | yes |  |
| Open-Meteo weminuche @ 10500ft | yes |  |
| USGS streamflow | NO | HTTP Error 503:  |
| elevation_thesis | yes |  |

## Endpoint probes

Variants tried against the endpoints that failed. The one that returns 200 with real content is the shape the adapter should use.

### Colorado DWR (CDSS)

| Status | Rows | Variant | First data row |
|---|---|---|
| 400 | - | raw + min/max-measurementDate (current code) | `"Error: \"measurementDate\" is not a valid URL query key"` |
| 200 | 0 | raw + parameter=STORAGE + startDate/endDate mm/dd/yyyy | `(header only, NO DATA ROWS)` |
| 200 | 0 | raw + parameter=STORAGE + iso dates | `(header only, NO DATA ROWS)` |
| 200 | 0 | day + parameter=STORAGE | `(header only, NO DATA ROWS)` |
| 200 | 0 | station metadata only (is the abbrev right?) | `(header only, NO DATA ROWS)` |
| 200 | 0 | hourly + parameter=STORAGE | `(header only, NO DATA ROWS)` |

### CoCoRaHS

| Status | Rows | Variant | First data row |
|---|---|---|
| 200 | 29 | county=LP, mm/dd/yyyy (current code) | `2026-08-30, 07:00 AM, 2026-08-30 08:10 AM, CO-LP-22, Durango 0.8 SSW, 37.2736, -107.8749, T, NA, NA, NA, NA, 2026-08-30 02:09 PM` |
| 200 | 29 | county=LP, iso dates | `2026-08-30, 07:00 AM, 2026-08-30 08:10 AM, CO-LP-22, Durango 0.8 SSW, 37.2736, -107.8749, T, NA, NA, NA, NA, 2026-08-30 02:09 PM` |
| 200 | 28 | state only, no county | `2026-08-30, 12:00 AM, 2026-08-30 09:20 AM, CO-DN-326, Denver 6.6 SSE, 39.6444, -104.90306, 0.03, NA, NA, NA, NA, 2026-08-30 03:20 PM` |
| 200 | 29 | county=LP, wider window (7 days) | `2026-08-30, 07:00 AM, 2026-08-30 08:10 AM, CO-LP-22, Durango 0.8 SSW, 37.2736, -107.8749, T, NA, NA, NA, NA, 2026-08-30 02:09 PM` |
| 200 | 91 | XML instead of CSV | `<Cocorahs>` |
| 200 | 29 | ReportType=DailyPrecipReports | `2026-08-30, 07:00 AM, 2026-08-30 08:10 AM, CO-LP-22, Durango 0.8 SSW, 37.2736, -107.8749, T, NA, NA, NA, NA, 2026-08-30 02:09 PM` |

## Needs attention

- **USGS streamflow** — HTTP Error 503: 
- **CoCoRaHS reports** — AL: HTTP Error 500: Internal Server Error
- **CDOT road conditions** — CDOT_API_KEY not set -- free at data.cotrip.org
- **CAIC zone for Vallecito** — only 1 polygon(s) published -- CAIC is out of season. Re-run mid-Nov to mid-Apr. Do NOT trust a point-in-polygon result against a single statewide shape.

A failure here is information, not a crash. CDOT without a key and CAIC out of season are both expected.

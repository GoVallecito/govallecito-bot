# Self-test — live endpoint check

Run: 2026-08-31T03:35:39+00:00
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
| Colorado DWR reservoir | NO | HTTP Error 400: Bad Request |
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
| USGS streamflow | yes |  |
| elevation_thesis | yes |  |

## Endpoint probes

Variants tried against the endpoints that failed. The one that returns 200 with real content is the shape the adapter should use.

### Colorado DWR (CDSS)

| Status | Variant | First bytes |
|---|---|---|
| 400 | raw + min/max-measurementDate (current code) | `"Error: \"measurementDate\" is not a valid URL query key"` |
| 200 | raw + parameter=STORAGE + startDate/endDate mm/dd/yyyy | `{"PageNumber":1,"PageCount":1,"ResultCount":373,"ResultDateTime":"2026-08-30T21:35:48.1181222-06:00","ResultList":[{"abbrev":"VALRESCO","parameter":"S` |
| 200 | raw + parameter=STORAGE + iso dates | `{"PageNumber":1,"PageCount":1,"ResultCount":373,"ResultDateTime":"2026-08-30T21:35:48.2743393-06:00","ResultList":[{"abbrev":"VALRESCO","parameter":"S` |
| 200 | day + parameter=STORAGE | `{"PageNumber":1,"PageCount":1,"ResultCount":3,"ResultDateTime":"2026-08-30T21:35:48.4149574-06:00","ResultList":[{"abbrev":"VALRESCO","parameter":"STO` |
| 200 | station metadata only (is the abbrev right?) | `{"PageNumber":1,"PageCount":1,"ResultCount":1,"ResultDateTime":"2026-08-30T21:35:48.6760228-06:00","ResultList":[{"division":7,"waterDistrict":31,"cou` |
| 200 | hourly + parameter=STORAGE | `{"PageNumber":1,"PageCount":1,"ResultCount":93,"ResultDateTime":"2026-08-30T21:35:48.8010201-06:00","ResultList":[{"abbrev":"VALRESCO","parameter":"ST` |

### CoCoRaHS

| Status | Variant | First bytes |
|---|---|---|
| 200 | county=LP, mm/dd/yyyy (current code) | `ObservationDate,ObservationTime,EntryDateTime,StationNumber,StationName,Latitude,Longitude,TotalPrecipAmt,NewSnowDepth,NewSnowSWE,TotalSnowDepth,Total` |
| 200 | county=LP, iso dates | `ObservationDate,ObservationTime,EntryDateTime,StationNumber,StationName,Latitude,Longitude,TotalPrecipAmt,NewSnowDepth,NewSnowSWE,TotalSnowDepth,Total` |
| 200 | state only, no county | `ObservationDate,ObservationTime,EntryDateTime,StationNumber,StationName,Latitude,Longitude,TotalPrecipAmt,NewSnowDepth,NewSnowSWE,TotalSnowDepth,Total` |
| 200 | county=LP, wider window (7 days) | `ObservationDate,ObservationTime,EntryDateTime,StationNumber,StationName,Latitude,Longitude,TotalPrecipAmt,NewSnowDepth,NewSnowSWE,TotalSnowDepth,Total` |
| 200 | XML instead of CSV | `<?xml version="1.0" encoding="utf-8"?> \| <Cocorahs> \|   <DailyPrecipReports> \|     <DailyPrecipReport> \|       <ObservationDate>2026-08-30</Observ` |
| 200 | ReportType=DailyPrecipReports | `ObservationDate,ObservationTime,EntryDateTime,StationNumber,StationName,Latitude,Longitude,TotalPrecipAmt,NewSnowDepth,NewSnowSWE,TotalSnowDepth,Total` |

## Needs attention

- **Colorado DWR reservoir** — HTTP Error 400: Bad Request
- **CoCoRaHS reports** — AL: HTTP Error 500: Internal Server Error
- **CDOT road conditions** — CDOT_API_KEY not set -- free at data.cotrip.org
- **CAIC zone for Vallecito** — only 1 polygon(s) published -- CAIC is out of season. Re-run mid-Nov to mid-Apr. Do NOT trust a point-in-polygon result against a single statewide shape.

A failure here is information, not a crash. CDOT without a key and CAIC out of season are both expected.

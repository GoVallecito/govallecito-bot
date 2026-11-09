# Self-test: live endpoint check

Run: 2026-11-09T22:58:40+00:00
Result: **15/16 sources reachable**

## The elevation thesis
**PASS.** The bands return different forecasts, so the elevation parameter is being honoured and elevation-band forecasting works.

| Band | Elevation requested (m) | Elevation used (m) | First-hour temp |
|---|---|---|---|
| Durango and the Animas Valley | 1981 | 1981.0 | 39.7 |
| Bayfield and up the Pine | 2103 | 2103.0 | 37.0 |
| Vallecito and the Florida | 2332 | 2332.0 | 37.7 |
| The high Weminuche | 3200 | 3200.0 | 32.9 |

## NWS zones
| Point | Forecast zone | Fire zone | Grid |
|---|---|---|---|
| vallecito | COZ019 | COZ295 | GJT/124,23 |
| durango | COZ022 | COZ295 | GJT/111,19 |

Confirmed: Vallecito (COZ019) is in a different forecast zone than Durango (COZ022). Polling only one of them would miss the other's warnings.

## Every source

| Source | OK | Detail |
|---|---|---|
| CAIC zone for Vallecito | yes |  |
| CDOT road conditions | NO | CDOT_API_KEY not set -- free at data.cotrip.org |
| CoCoRaHS reports | yes | AL: HTTP Error 500: Internal Server Error |
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
| USGS streamflow | yes |  |
| elevation_thesis | yes |  |

## Needs attention

- **CDOT road conditions**: CDOT_API_KEY not set -- free at data.cotrip.org

A failure here is information, not a crash. CDOT without a key and CAIC out of season are both expected.

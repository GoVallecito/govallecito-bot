# Self-test: live endpoint check

Run: 2026-11-16T22:56:29+00:00
Result: **10/16 sources reachable**

## The elevation thesis
**FAIL.** Every band returned the same temperature, which means the elevation parameter is being ignored. The elevation-band product does not work as designed. Stop and investigate before building further.

| Band | Elevation requested (m) | Elevation used (m) | First-hour temp |
|---|---|---|---|
| Durango and the Animas Valley | 1981 | - | - |
| Bayfield and up the Pine | 2103 | - | - |
| Vallecito and the Florida | 2332 | - | - |
| The high Weminuche | 3200 | 3200.0 | 28.6 |

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
| NRCS SNOTEL | NO | HTTP Error 502: Bad Gateway |
| NWS AFD (GJT) | yes |  |
| NWS alerts (COZ019 + COZ022) | yes |  |
| NWS gridpoint durango | yes |  |
| NWS gridpoint vallecito | yes |  |
| Open-Meteo bayfield @ 6900ft | NO | <urlopen error _ssl.c:1001: The handshake operation timed out> |
| Open-Meteo durango @ 6500ft | NO | <urlopen error _ssl.c:1001: The handshake operation timed out> |
| Open-Meteo model spread | yes |  |
| Open-Meteo vallecito @ 7650ft | NO | <urlopen error _ssl.c:1001: The handshake operation timed out> |
| Open-Meteo weminuche @ 10500ft | yes |  |
| USGS streamflow | yes |  |
| elevation_thesis | NO |  |

## Needs attention

- **Open-Meteo durango @ 6500ft**: <urlopen error _ssl.c:1001: The handshake operation timed out>
- **Open-Meteo bayfield @ 6900ft**: <urlopen error _ssl.c:1001: The handshake operation timed out>
- **Open-Meteo vallecito @ 7650ft**: <urlopen error _ssl.c:1001: The handshake operation timed out>
- **elevation_thesis**: None
- **NRCS SNOTEL**: HTTP Error 502: Bad Gateway
- **CDOT road conditions**: CDOT_API_KEY not set -- free at data.cotrip.org

A failure here is information, not a crash. CDOT without a key and CAIC out of season are both expected.

"""
National Weather Service adapter.

Three things this pulls that the existing conditions bot does not:

1. Alerts for BOTH forecast zones. Vallecito is COZ019, Durango and Bayfield
   are COZ022. The existing bot queries by point= for Vallecito only, which is
   correct for a lake-conditions card but wrong for a three-town forecast --
   a Winter Storm Warning covering Durango would be invisible.

2. The full alert set, not the narrow flood/fire/evacuation allowlist. The
   conditions bot deliberately excludes Winter Storm Warnings so genuine
   emergencies don't get lost in weather noise. For a weather product that is
   exactly backwards: a Winter Storm Warning IS the story.

3. The Grand Junction Area Forecast Discussion. The AFD is a working
   meteorologist's reasoning in prose -- which model they trust today and why.
   It is the single best input for the "name the model, then say whether you
   believe it" voice rule, and no consumer product surfaces it.
"""

from .. import constants as C
from .http import SourceResult, get_json

API = "https://api.weather.gov"
GEO_HEADERS = {"Accept": "application/geo+json"}

# Alerts we treat as life-safety. Anything in this set forces human review
# before publishing -- see guardrails.py.
LIFE_SAFETY_EVENTS = {
    "Flash Flood Warning", "Flash Flood Emergency", "Flood Warning",
    "Areal Flood Warning", "Winter Storm Warning", "Blizzard Warning",
    "Ice Storm Warning", "Avalanche Warning", "Red Flag Warning",
    "Extreme Cold Warning", "Wind Chill Warning", "Severe Thunderstorm Warning",
    "Tornado Warning", "High Wind Warning", "Evacuation Immediate",
    "Civil Emergency Message", "Local Area Emergency",
}


def fetch_alerts(zones=None):
    """Active alerts across our forecast zones, de-duplicated by alert id.

    An alert covering both zones appears once, with a `zones` list showing
    where it applies -- so a post can say "COZ019 only" (Vallecito and up)
    rather than implying the whole county is under a warning.
    """
    zones = zones or C.FORECAST_ZONES
    by_id = {}
    errors = []
    for zone in zones:
        url = f"{API}/alerts/active?zone={zone}"
        try:
            data = get_json(url, GEO_HEADERS)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{zone}: {exc}")
            continue
        for feature in data.get("features", []):
            try:
                p = feature.get("properties", {})
                if p.get("status") != "Actual":
                    continue
                aid = p.get("id") or feature.get("id")
                if aid in by_id:
                    by_id[aid]["zones"].append(zone)
                    continue
                event = p.get("event", "")
                by_id[aid] = {
                    "id": aid,
                    "event": event,
                    "headline": p.get("headline") or event,
                    "description": (p.get("description") or "")[:4000],
                    "instruction": (p.get("instruction") or "")[:2000],
                    "severity": p.get("severity"),
                    "urgency": p.get("urgency"),
                    "onset": p.get("onset"),
                    "expires": p.get("expires"),
                    "sender": p.get("senderName"),
                    "life_safety": event in LIFE_SAFETY_EVENTS,
                    "zones": [zone],
                }
            except Exception as exc:  # noqa: BLE001
                # One malformed feature must not discard the rest -- same
                # isolate-per-item rule the existing bot uses.
                errors.append(f"malformed feature in {zone}: {exc}")

    if errors and not by_id:
        return SourceResult(False, source="NWS alerts", url=API,
                            error="; ".join(errors[:3]))
    return SourceResult(True, list(by_id.values()), source="NWS alerts",
                        url=f"{API}/alerts/active?zone=" + ",".join(zones),
                        error="; ".join(errors) if errors else None)


def fetch_afd(office=None):
    """Latest Area Forecast Discussion from the WFO.

    Returns the raw product text. The composer is told to read it for the
    forecaster's reasoning, never to quote it verbatim -- it is a government
    work product written for a technical audience, and copying it would both
    read wrong and defeat the point of having a voice.
    """
    office = office or C.WFO
    try:
        listing = get_json(f"{API}/products/types/AFD/locations/{office}")
        items = listing.get("@graph") or listing.get("graph") or []
        if not items:
            return SourceResult(False, source="NWS AFD", error="no products listed")
        newest = items[0]
        product = get_json(newest["@id"])
        return SourceResult(
            True,
            {
                "issued": product.get("issuanceTime"),
                "text": product.get("productText", ""),
            },
            source=f"NWS {office} AFD",
            url=newest["@id"],
        )
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="NWS AFD", error=str(exc))


def fetch_point_forecast(lat, lon):
    """Gridpoint forecast periods for one coordinate.

    Used as a cross-check against Open-Meteo, not as the primary. NWS gives one
    forecast per grid cell at the cell's own elevation, which is precisely the
    limitation this product exists to route around -- but disagreement between
    NWS and Open-Meteo is a genuine uncertainty signal worth surfacing.
    """
    try:
        pt = get_json(f"{API}/points/{lat},{lon}", GEO_HEADERS)
        props = pt["properties"]
        fc = get_json(props["forecast"], GEO_HEADERS)
        periods = fc["properties"]["periods"]
        return SourceResult(
            True,
            {
                "grid": f"{props.get('gridId')}/{props.get('gridX')},{props.get('gridY')}",
                "forecast_zone": (props.get("forecastZone") or "").rsplit("/", 1)[-1],
                "fire_zone": (props.get("fireWeatherZone") or "").rsplit("/", 1)[-1],
                "periods": periods[:8],
            },
            source="NWS gridpoint",
            url=props["forecast"],
        )
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="NWS gridpoint", error=str(exc))

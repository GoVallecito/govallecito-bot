"""
Colorado Avalanche Information Center adapter.

TWO HARD RULES, both learned the expensive way.

1. NEVER HARDCODE A ZONE ID. CAIC re-mints zone ids every season, and 18+
   historical ids share the name "Southern San Juan Mountains." A hardcoded id
   works until it silently returns last season's forecast. Resolve by NAME at
   runtime, every run.

2. CAIC's map-layer collapses to a single statewide polygon out of season, so
   a point-in-polygon test silently mis-assigns every point all summer. Which
   zone actually contains Vallecito and the Weminuche -- Northern or Southern
   San Juan -- could not be resolved during research for exactly this reason.
   Run resolve_zone() between mid-November and mid-April to settle it.

The forecaster LINKS avalanche information and never interprets it. That is a
deliberate lane boundary copied from the model this persona is built on, who
uses CAIC as a data source for SNOTEL and models but never issues avalanche
opinions of his own.
"""

from .http import SourceResult, get_json

MAP_LAYER = "https://api.avalanche.org/v2/public/products/map-layer/CAIC"
PRODUCT = "https://api.avalanche.org/v2/public/product"

CANDIDATE_ZONE_NAMES = ["Southern San Juan Mountains", "Northern San Juan Mountains"]


def _point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def _contains(geometry, lon, lat):
    if not geometry:
        return False
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    polys = [coords] if gtype == "Polygon" else coords if gtype == "MultiPolygon" else []
    for poly in polys:
        if not poly:
            continue
        if _point_in_ring(lon, lat, poly[0]):
            if not any(_point_in_ring(lon, lat, hole) for hole in poly[1:]):
                return True
    return False


def resolve_zone(lat, lon):
    """Find the CAIC zone containing a point, by geometry, right now.

    Refuses to answer if the layer has collapsed to one statewide polygon --
    an out-of-season answer is worse than no answer, because it looks correct.
    """
    try:
        layer = get_json(MAP_LAYER)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="CAIC map-layer", url=MAP_LAYER, error=str(exc))

    feats = layer.get("features") or []
    if len(feats) <= 1:
        return SourceResult(
            False, source="CAIC map-layer", url=MAP_LAYER,
            error=(f"only {len(feats)} polygon(s) published -- CAIC is out of "
                   "season. Re-run mid-Nov to mid-Apr. Do NOT trust a "
                   "point-in-polygon result against a single statewide shape."))

    for f in feats:
        if _contains(f.get("geometry"), lon, lat):
            p = f.get("properties") or {}
            return SourceResult(True, {
                "zone_id": p.get("id"),
                "zone_name": p.get("name"),
                "danger": (p.get("danger") or {}),
                "travel_advice": p.get("travel_advice"),
            }, source="CAIC map-layer", url=MAP_LAYER)

    return SourceResult(False, source="CAIC map-layer", url=MAP_LAYER,
                        error="point not inside any published zone polygon")

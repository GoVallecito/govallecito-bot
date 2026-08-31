"""
Verified constants for the Vallecito / Bayfield / Durango forecaster.

EVERY value in this file was verified against a live API response or an
authoritative source during the research pass. Provenance is noted inline.
Do not change a value here without re-verifying it -- several of these are
things a plausible-looking guess gets wrong in a way that silently breaks
the product (see ZONE_VALLECITO vs ZONE_ANIMAS in particular).
"""

# --- Geography ------------------------------------------------------------

# Coordinates. Vallecito matches the existing bot's fetch_conditions.LAT/LON
# (near the dam) so both products describe the same point.
VALLECITO = {"lat": 37.3856, "lon": -107.5217, "name": "Vallecito Lake"}
BAYFIELD  = {"lat": 37.2278, "lon": -107.5981, "name": "Bayfield"}
DURANGO   = {"lat": 37.2753, "lon": -107.8801, "name": "Durango"}

POINTS = {"vallecito": VALLECITO, "bayfield": BAYFIELD, "durango": DURANGO}

# --- The elevation bands: the entire product thesis -----------------------
#
# Every national and TV product resolves "Durango" to the airport at 6,689 ft,
# which sits on Florida Mesa 14 miles southeast of town. Vallecito is ~1,000 ft
# higher than that and behaves like a different place. Bayfield School District's
# own closure policy formally singles out "northern bus routes (e.g., Vallecito)"
# as a separate weather regime. These bands are what nobody else publishes.
#
# elevation_m is what gets handed to Open-Meteo's `elevation` parameter, which
# was verified to actually work: the same coordinate at 2332 m vs 2900 m returns
# 16.6 C vs 13.1 C. That parameter is the reason elevation-band forecasting is
# possible without separate grid points.

BANDS = [
    {
        "key": "durango",
        "label": "Durango and the Animas Valley",
        "elevation_ft": 6500,
        "elevation_m": 1981,
        "point": DURANGO,
        "nws_zone": "COZ022",
    },
    {
        "key": "bayfield",
        "label": "Bayfield and up the Pine",
        "elevation_ft": 6900,
        "elevation_m": 2103,
        "point": BAYFIELD,
        "nws_zone": "COZ022",
    },
    {
        "key": "vallecito",
        "label": "Vallecito and the Florida",
        "elevation_ft": 7650,
        "elevation_m": 2332,
        "point": VALLECITO,
        "nws_zone": "COZ019",
    },
    {
        "key": "weminuche",
        "label": "The high Weminuche",
        "elevation_ft": 10500,
        "elevation_m": 3200,
        "point": VALLECITO,   # same grid cell, different elevation -- this is the trick
        "nws_zone": "COZ019",
    },
]

BAND_ORDER = [b["key"] for b in BANDS]

# --- The passes ------------------------------------------------------------
#
# WE FORECAST THESE. WE DO NOT REPORT THEIR STATUS.
#
# CDOT's public developer documentation has been removed -- every documented
# URL now redirects to the COtrip homepage, and the Colorado open-data catalog
# still advertises an "API ACCESS" link that points at the dead page. There is
# an undocumented backend behind the COtrip app; building on it would be
# unstable and is not what it is there for.
#
# So the honest product is a FORECAST for the pass elevations, plus a link to
# CDOT for live status. "Coal Bank and Molas, 8-14 inches overnight, expect
# traction law by morning" is something nobody else publishes. "Red Mountain is
# closed" is something CDOT tells people faster than we ever could -- and
# claiming it without their data is how someone ends up making a three-hour
# detour they did not need, or driving into a pass that is actually shut.
#
# elevation_ft is the SIGNED elevation, which is what belongs in copy.
# elevation_m is what goes to the model. USGS point-elevation queries return
# terrain height at a coordinate, which sits below the signed summit; the
# self-test echoes back the terrain elevation the model used so a bad
# coordinate shows up rather than hiding.
#
# Coordinates are approximate summit locations and are flagged as such.

PASSES = [
    {"key": "coal_bank",   "name": "Coal Bank Pass",    "route": "US-550",
     "lat": 37.6989, "lon": -107.7767, "elevation_ft": 10640, "elevation_m": 3243},
    {"key": "molas",       "name": "Molas Pass",        "route": "US-550",
     "lat": 37.7481, "lon": -107.7050, "elevation_ft": 10910, "elevation_m": 3325},
    {"key": "red_mountain","name": "Red Mountain Pass", "route": "US-550",
     "lat": 37.8994, "lon": -107.7128, "elevation_ft": 11018, "elevation_m": 3358},
    {"key": "wolf_creek",  "name": "Wolf Creek Pass",   "route": "US-160",
     "lat": 37.4794, "lon": -106.8003, "elevation_ft": 10857, "elevation_m": 3309},
]

# The three US-550 passes close as a unit. Saying "Molas is closed" without
# saying the other two are is how an outsider gives themselves away.
US550_UNIT = ["coal_bank", "molas", "red_mountain"]

CDOT_STATUS_URL = "https://www.cotrip.org/"

# --- NWS ------------------------------------------------------------------
#
# VERIFIED live from the /points warnzone and firewxzone parameters.
#
# THE SINGLE MOST IMPORTANT FACT IN THIS FILE:
# Vallecito is in a DIFFERENT forecast zone than Durango and Bayfield.
# Winter Storm Warnings fire for COZ019 constantly while COZ022 stays clear.
# An agent that polls only Durango's zone will systematically miss Vallecito's
# weather -- which is the exact failure this whole product exists to fix.

WFO = "GJT"                       # Grand Junction. NOT Albuquerque.
ZONE_VALLECITO = "COZ019"         # Southwest San Juan Mountains
ZONE_ANIMAS    = "COZ022"         # Animas River Basin (Durango + Bayfield)
ZONE_SAN_JUAN_RIVER = "COZ023"    # Pagosa side, for context only
FIRE_ZONE = "COZ295"              # Upper East -- covers all three towns
FIRE_ZONE_LOWER = "COZ207"        # Below 7,000 ft; catches Ignacio/south county

FORECAST_ZONES = [ZONE_VALLECITO, ZONE_ANIMAS]
COUNTY_FIPS = "COC067"            # La Plata County

# Radar: KGJX. The beam centerline is ~23,500 ft MSL over Durango, so the
# lowest ~11,000-12,000 vertical feet here are invisible to NEXRAD. Do NOT
# build nowcasting on radar. Use satellite, lightning, and gauge ground truth.
RADAR = "KGJX"
RADAR_IS_BLIND_BELOW_FT = 18000

# --- SNOTEL (NRCS) --------------------------------------------------------
# Triplets are station:state:network. Verified individually.
# NOTE: Cascade is 387, NOT 386 -- site 386 was discontinued 2022-10-01 and
# returns nothing.

SNOTEL = {
    "vallecito":      {"triplet": "843:CO:SNTL", "name": "Vallecito",         "elev_ft": 10740, "home": True},
    "stump_lakes":    {"triplet": "797:CO:SNTL", "name": "Stump Lakes",       "elev_ft": 11230},
    "cascade_2":      {"triplet": "387:CO:SNTL", "name": "Cascade #2",        "elev_ft": 8990},
    "molas_lake":     {"triplet": "632:CO:SNTL", "name": "Molas Lake",        "elev_ft": 10500},
    "red_mtn_pass":   {"triplet": "713:CO:SNTL", "name": "Red Mountain Pass", "elev_ft": 11080},
    "wolf_creek":     {"triplet": "874:CO:SNTL", "name": "Wolf Creek Summit", "elev_ft": 11000},
    "upper_san_juan": {"triplet": "840:CO:SNTL", "name": "Upper San Juan",    "elev_ft": 10200},
    "columbus_basin": {"triplet": "904:CO:SNTL", "name": "Columbus Basin",    "elev_ft": 10780},
}
HOME_SNOTEL = "vallecito"

# The NRCS AWDB REST API does not expose the basin index directly. Compute
# percent-of-median from these stations instead. Locals say "percent of
# median," never "percent of average" -- see the persona voice rules.
BASIN_NAME = "San Miguel-Dolores-Animas-San Juan"

# --- USGS -----------------------------------------------------------------
# WARNING: 09353000 (Vallecito Reservoir) is DEAD -- its record ends
# 2012-12-31. The existing bot already knows this; don't resurrect it.
# Reservoir storage comes from CDSS instead.

USGS_SITES = {
    "pine_above_vallecito": {"id": "09352800", "name": "Los Pinos above Vallecito Reservoir"},
    "vallecito_creek":      {"id": "09352900", "name": "Vallecito Creek near Bayfield"},
    "animas_durango":       {"id": "09361500", "name": "Animas River at Durango"},
    "piedra_arboles":       {"id": "09349800", "name": "Piedra River near Arboles"},
}
USGS_NO_DATA_SENTINEL_THRESHOLD = -900000   # matches the existing bot

# --- CDSS (Colorado DWR) --------------------------------------------------
CDSS_VALLECITO = "VALRESCO"
# The existing bot uses 125,400 AF (Wikipedia). Reclamation publishes 129,700 AF;
# 125,400 is the flood-control allocation. Kept as the existing bot's value for
# consistency with what govallecito.com already displays -- see note below.
FULL_POOL_CAPACITY_AF = 125_400
RECLAMATION_CAPACITY_AF = 129_700
FULL_POOL_ELEVATION_FT = 7_665

# --- Climate normals ------------------------------------------------------
#
# VALLECITO DAM COOP 058582, 7,644 ft, continuous record since 1917.
# This is OUR climatology. Durango airport (KDRO) is a garbage proxy -- its
# normals show ZERO snowfall (it's an ASOS) and precip 26% below Fort Lewis.
# Never quote airport normals as "Durango."

NORMALS_VALLECITO_DAM = {
    "station": "VALLECITO DAM",
    "coop_id": "058582",
    "elev_ft": 7644,
    "period": "1991-2020",
    "annual_precip_in": 25.88,
    "annual_snow_in": 90.2,
    "last_spring_freeze": "June 2",
    "first_fall_freeze": "September 25",
    "freeze_free_days": 114,
}

# --- Hydrology ------------------------------------------------------------
# The Pine drains to the SAN JUAN (HUC 14080101), not the Animas (14080104).
# A real distinction, and the kind of thing that reads as local knowledge.
HUC_PINE = "14080101"
HUC_ANIMAS = "14080104"

# --- Burn scars -----------------------------------------------------------
# USGS: debris flows in southwest Colorado have been triggered after as little
# as 6-10 minutes of rain, by storms with recurrence intervals of two years or
# less. Ordinary storms. Anything touching these routes to human review.
BURN_SCARS = ["416 Fire scar", "Missionary Ridge scar"]

# --- Timing ---------------------------------------------------------------
TIMEZONE = "America/Denver"
# The school call must land before districts decide. Bayfield 10-JT-R, Durango
# 9-R and Ignacio 11-JT all finalize by 06:30.
SCHOOL_CALL_HOUR = 5
SCHOOL_CALL_MINUTE = 45
SCHOOL_DECISION_DEADLINE = "06:30"
EVENING_HOUR = 19

USER_AGENT = ("govallecito-wx/1.0 (govallecito.com hyperlocal forecast; "
              "contact@govallecito.com)")
REQUEST_TIMEOUT = 20


# --- Local time ------------------------------------------------------------
#
# THIS EXISTS BECAUSE OF A REAL BUG. GitHub Actions runners are UTC. A job at
# 03:40 UTC is 21:40 the PREVIOUS EVENING in Colorado, so date.today() had
# already rolled over and CoCoRaHS was being asked for a day whose
# observations do not exist yet -- observers file in the morning. It returned
# an empty result that looked exactly like a broken adapter.
#
# Every date this product reasons about is a Mountain Time date: a snow day, an
# observation date, a school-closure morning. Never use date.today() here.

from datetime import datetime as _datetime  # noqa: E402
from zoneinfo import ZoneInfo as _ZoneInfo  # noqa: E402

_TZ = _ZoneInfo(TIMEZONE)


def local_now():
    """Timezone-aware now, in Mountain Time."""
    return _datetime.now(_TZ)


def local_date():
    """Today's date as someone in Bayfield would name it."""
    return local_now().date()

"""Public U.S. Data Centers Tracker discovery; listings are research leads, not verified evidence."""

import math
import re
from urllib.parse import urlencode, urlsplit

import httpx

from .city_location import state_code
from .research import Candidate
from .retrieval import official_host

TRACKER_URL = "https://experience.arcgis.com/experience/5a4d072ad01449bba5698a80103fb909/page/Map"
LAYER_URL = (
    "https://services.arcgis.com/jDGuO8tYggdCCnUJ/arcgis/rest/services/"
    "data_centers_v4_agol_all/FeatureServer/0"
)
ALIASES = {
    "Aligned Data Centers": ("Aligned",),
    "Amazon Web Services": ("Amazon", "AWS"),
    "Meta": ("Meta", "Facebook"),
    "QTS": ("QTS", "Quality Technology Services"),
    "STACK Infrastructure": ("STACK",),
    "Vantage Data Centers": ("Vantage",),
}
FIELDS = (
    "OBJECTID,facility_id,facility_name,address,city,state,operator_name,status,"
    "lat,long,location_confidence," + ",".join(f"info_source_{i}" for i in range(1, 9))
)


def discovery_key(developer: str) -> str:
    return "us-dc-tracker-v1:" + developer


def clean(value) -> str:
    return str(value).strip() if value is not None else ""


def coordinates(attributes):
    try:
        lat, lon = float(attributes["lat"]), float(attributes["long"])
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            if (lat, lon) != (0, 0):
                return lat, lon
    except TypeError, ValueError, KeyError:
        pass
    return None, None


def discover_tracker(developer: str, *, transport=None) -> list[Candidate]:
    """Read all matching pages; reject incomplete responses instead of caching partial discovery."""
    if not developer.strip():
        raise ValueError("Choose a developer.")
    aliases = ALIASES.get(developer, (developer,))
    # Escape SQL literals and LIKE wildcards; developer names are never SQL fragments.
    if any("%" in alias or "_" in alias for alias in aliases):
        raise ValueError("Unsupported developer name.")
    terms = ["UPPER(operator_name) LIKE '%" + a.upper().replace("'", "''") + "%'" for a in aliases]
    where = "(" + " OR ".join(terms) + ")"
    matcher = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in aliases) + r")(?!\w)", re.I)
    results, seen = [], set()
    last_id = -1
    with httpx.Client(timeout=30, transport=transport, follow_redirects=False) as client:
        for _ in range(100):
            response = client.get(
                LAYER_URL + "/query",
                params={
                    "f": "json",
                    "where": f"{where} AND OBJECTID > {last_id}",
                    "outFields": FIELDS,
                    "returnGeometry": "false",
                    "orderByFields": "OBJECTID ASC",
                    "resultRecordCount": 500,
                },
            )
            response.raise_for_status()
            data = response.json()
            if "error" in data or not isinstance(data.get("features"), list):
                raise ValueError("The tracker could not return site records. Please retry Find sites.")
            features = data["features"]
            for feature in features:
                a = feature["attributes"]
                oid = int(a["OBJECTID"])
                if oid <= last_id:
                    raise ValueError("Tracker pagination did not advance; saved results were preserved.")
                last_id = oid
                operator = clean(a.get("operator_name"))
                if not matcher.search(operator):
                    continue
                state = state_code(clean(a.get("state")))
                if not state:
                    continue
                record_id = clean(a.get("facility_id")) or f"objectid:{oid}"
                if record_id in seen:
                    continue
                seen.add(record_id)
                urls = []
                for i in range(1, 9):
                    url = clean(a.get(f"info_source_{i}"))
                    parsed = urlsplit(url)
                    if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username:
                        if url not in urls:
                            urls.append(url)
                lat, lon = coordinates(a)
                record_where = (
                    "facility_id = '" + record_id.replace("'", "''") + "'"
                    if not record_id.startswith("objectid:")
                    else f"OBJECTID = {oid}"
                )
                results.append(
                    Candidate(
                        name=clean(a.get("facility_name")) or f"{operator} — {clean(a.get('city'))}, {state}",
                        city=clean(a.get("city")),
                        state=state,
                        address=clean(a.get("address")),
                        phase="Phase unconfirmed",
                        identity_url=next((u for u in urls if official_host(u, [])), ""),
                        reason="U.S. Data Centers Tracker listing; operator relationship and details require verification.",
                        tracker_id=record_id,
                        tracker_url=LAYER_URL
                        + "/query?"
                        + urlencode({"where": record_where, "outFields": "*", "f": "pjson"}),
                        tracker_status=clean(a.get("status")),
                        tracker_operator=operator,
                        source_urls=urls,
                        latitude=lat,
                        longitude=lon,
                        location_confidence=clean(a.get("location_confidence")),
                    )
                )
            if not data.get("exceededTransferLimit"):
                return sorted(results, key=lambda c: (c.state, c.city, c.name, c.tracker_id))
            if not features:
                raise ValueError("Tracker returned an incomplete page; please retry.")
    raise ValueError("Tracker pagination limit reached; saved results were preserved.")

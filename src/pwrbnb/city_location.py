"""Offline, state-scoped Census place matching for approximate city map markers."""

import csv
import re
from functools import lru_cache
from pathlib import Path

STATE_NAMES = dict(
    zip(
        "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
        "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming".split(
            "|"
        ),
        strict=True,
    )
)


def normalize_city(value: str) -> str:
    value = re.sub(r"\s+(city|town|village|borough|municipality|CDP)$", "", value.strip(), flags=re.I)
    return " ".join(value.casefold().split())


def state_code(value: str) -> str:
    value = value.strip()
    if value.upper() in STATE_NAMES:
        return value.upper()
    return next((code for code, name in STATE_NAMES.items() if name.casefold() == value.casefold()), "")


@lru_cache(maxsize=1)
def places() -> dict:
    result = {}
    with (Path(__file__).parent / "resources/us_places.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (normalize_city(row["name"]), row["state"])
            result.setdefault(key, []).append(row)
    return result


def locate_city(city: str = "", state: str = "", address: str = "") -> dict | None:
    """Never fall back to a nearby metro or choose between ambiguous place matches."""
    code = state_code(state)
    if not city.strip() or not code:
        # Older discovery caches have only an address. Accept a city/state suffix,
        # including street, city, state ZIP, without sending it to another service.
        address = re.sub(r",?\s+(USA|US|United States)$", "", address.strip(), flags=re.I)
        address = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", address)
        found = None
        for abbreviation, name in STATE_NAMES.items():
            match = re.search(rf"(?:,\s*|\s+)({re.escape(name)}|{abbreviation})$", address, re.I)
            if match:
                found = (address[: match.start()].split(",")[-1].strip(), abbreviation)
                break
        if not found:
            return None
        city, code = found
    matches = places().get((normalize_city(city), code), [])
    if len(matches) != 1:
        return None
    row = matches[0]
    return {
        "label": f"{city.strip()}, {code}",
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
    }

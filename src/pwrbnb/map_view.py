"""Selectable city markers and bundled historical service-area reference layers."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pydeck as pdk
import streamlit as st

from .city_location import locate_city

REGIONS = {
    "PJM": [211, 168, 72, 100],
    "MIDCONTINENT": [108, 149, 193, 90],
    "SOUTHWEST": [104, 174, 142, 90],
    "ELECTRIC RELIABILITY": [205, 126, 104, 100],
    "CALIFORNIA": [146, 127, 210, 95],
    "NEW YORK": [190, 113, 154, 95],
    "ISO NEW ENGLAND": [165, 193, 100, 95],
}


def candidate_id(developer, candidate):
    identity = [developer, candidate.name, candidate.address, candidate.phase, candidate.identity_url]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]


def city_markers(developer, candidates):
    groups, missing = {}, []
    for candidate in candidates:
        cid = candidate_id(developer, candidate)
        location = locate_city(candidate.city, candidate.state, candidate.address)
        if not location:
            missing.append(cid)
            continue
        label = location["label"]
        group = groups.setdefault(
            label,
            {
                "name": label,
                "lon": location["longitude"],
                "lat": location["latitude"],
                "candidate_ids": [],
                "names": [],
            },
        )
        if cid not in group["candidate_ids"]:
            group["candidate_ids"].append(cid)
            group["names"].append(candidate.name)
    points = list(groups.values())
    for point in points:
        point["site_names"] = " / ".join(point.pop("names"))
        point["city_label"] = point["name"] + " · City reference point"
        point["info"] = point["site_names"]
        point["properties"] = {"name": point["name"], "info": point["info"]}
    return points, missing


def selected_candidates(event, points):
    """Resolve only known marker identities, never trust site data from client events."""
    objects = (event or {}).get("selection", {}).get("objects", {}).get("datacenters", [])
    if not objects:
        return []
    ids = objects[0].get("candidate_ids", [])
    return next((p["candidate_ids"] for p in points if p["candidate_ids"] == ids), [])


@lru_cache(maxsize=2)
def boundaries(kind):
    data = json.loads(
        (Path(__file__).parent / "resources" / f"{kind}_regions.geojson").read_text(encoding="utf-8")
    )
    for feature in data["features"]:
        props = feature["properties"]
        name = props.get("NAME", "Reference territory")
        props["name"] = name
        props["info"] = "Historical reference boundary; not evidence of available power"
        props["color"] = next((v for k, v in REGIONS.items() if name.startswith(k)), [175, 182, 190, 40])
    return data


def show_map(developer, candidates, utilities=False):
    points, missing = city_markers(developer, candidates)
    layers = [
        pdk.Layer(
            "GeoJsonLayer",
            boundaries("grid"),
            id="grid-regions",
            pickable=False,
            get_fill_color="properties.color",
            get_line_color=[130, 145, 158, 160],
            line_width_min_pixels=1,
            stroked=True,
            filled=True,
        )
    ]
    if utilities:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                boundaries("utility"),
                id="utility-regions",
                pickable=False,
                filled=False,
                stroked=True,
                get_line_color=[87, 108, 121, 120],
                line_width_min_pixels=1,
                auto_highlight=True,
            )
        )
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            points,
            id="datacenters",
            pickable=True,
            get_position="[lon, lat]",
            get_fill_color=[20, 44, 58, 240],
            get_line_color=[255, 255, 255],
            stroked=True,
            line_width_min_pixels=2,
            get_radius=1500,
            radius_min_pixels=9,
            radius_max_pixels=18,
        )
    )
    deck = pdk.Deck(
        map_provider="carto",
        map_style="light",
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=39, longitude=-103, zoom=2.7),
        tooltip={"text": "{site_names}\n{city_label}"},
    )
    catalog = hashlib.sha256(json.dumps(points, sort_keys=True).encode()).hexdigest()[:12]
    event = st.pydeck_chart(
        deck,
        height=630,
        on_select="rerun",
        selection_mode="single-object",
        key=f"developer-map-{developer}-{catalog}",
        alt="US datacenter cities with historical ISO/RTO and optional utility boundaries",
    )
    st.markdown(
        ":orange-badge[PJM] :blue-badge[MISO] :green-badge[SPP] :red-badge[ERCOT] "
        ":violet-badge[CAISO] :violet-badge[NYISO] :green-badge[ISO-NE] :gray-badge[Non-ISO/RTO]"
    )
    st.markdown(
        "Map references: [ISO/RTO boundaries](https://services1.arcgis.com/4yjifSiIG17X0gW4/ArcGIS/rest/services/Data_Center_Demand_by_Region/FeatureServer/2) · "
        "[HIFLD utility territories](https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/Electric_Retail_Service_Territories_HIFLD/FeatureServer/0) · "
        "[Census city points](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html). Basemap: CARTO / OpenStreetMap."
    )
    return selected_candidates(event, points), missing

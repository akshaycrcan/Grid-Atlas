import httpx
import pytest

from pwrbnb.map_view import candidate_id, candidate_location, city_markers
from pwrbnb.tracker import discover_tracker


def feature(oid, **overrides):
    return {
        "attributes": dict(
            OBJECTID=oid,
            facility_id=f"facility-{oid}",
            facility_name=f"Campus {oid}",
            operator_name="Amazon",
            city="Ashburn",
            state="Virginia",
            status="Cancelled",
            lat=39.1,
            long=-77.5,
            location_confidence="Medium",
            **overrides,
        )
    }


def test_pages_aliases_provenance_and_stable_ids():
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "features": [feature(1, info_source_1="https://aws.amazon.com/site")],
                    "exceededTransferLimit": True,
                },
            )
        return httpx.Response(200, json={"features": [feature(2)]})

    sites = discover_tracker("Amazon Web Services", transport=httpx.MockTransport(respond))
    assert len(sites) == 2
    assert "AMAZON" in calls[0].url.params["where"] and "AWS" in calls[0].url.params["where"]
    assert "OBJECTID > 1" in calls[1].url.params["where"]
    site = sites[0]
    assert site.state == "VA" and site.tracker_status == "Cancelled"
    assert site.phase == "Phase unconfirmed"
    assert site.identity_url == "https://aws.amazon.com/site"
    assert site.source_urls == [site.identity_url]
    assert "facility_id" in site.tracker_url
    assert candidate_location(site)["latitude"] == 39.1
    assert "Medium" in city_markers("Amazon", sites)[0][0]["city_label"]
    changed = site.model_copy(update={"name": "Renamed", "tracker_status": "Operating"})
    assert candidate_id("Amazon", site) == candidate_id("Amazon", changed)


def test_missing_coordinates_and_nonofficial_sources():
    row = feature(1)
    row["attributes"].update(lat=None, long=None, info_source_1="https://example.com/news")
    sites = discover_tracker(
        "Amazon Web Services",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"features": [row]})),
    )
    assert sites[0].identity_url == ""
    assert sites[0].source_urls == ["https://example.com/news"]
    assert candidate_location(sites[0])["source"].startswith("US Census")


@pytest.mark.parametrize(
    "payload", [{"error": {"code": 400}}, {}, {"features": [], "exceededTransferLimit": True}]
)
def test_arcgis_errors_do_not_become_empty_success(payload):
    with pytest.raises(ValueError):
        discover_tracker(
            "Google", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        )


def test_repeated_page_rejected():
    with pytest.raises(ValueError, match="pagination"):
        discover_tracker(
            "Amazon Web Services",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"features": [feature(1)], "exceededTransferLimit": True}
                )
            ),
        )


def test_operator_boundaries_and_deduplication():
    row = feature(1)
    row["attributes"]["operator_name"] = "Metaverse Properties"
    match = feature(2)
    match["attributes"]["operator_name"] = "Meta / Developer LLC"
    duplicate = feature(3)
    duplicate["attributes"].update(operator_name="Meta", facility_id="facility-2")
    sites = discover_tracker(
        "Meta",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"features": [row, match, duplicate]})
        ),
    )
    assert len(sites) == 1 and sites[0].tracker_id == "facility-2"

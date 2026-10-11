from pwrbnb.brief import cited_statement, section_findings
from pwrbnb.evidence import validate_claims
from pwrbnb.map_view import boundaries, candidate_id, city_markers, selected_candidates
from pwrbnb.models import Claim, Document, Evidence, Site, Snapshot
from pwrbnb.research import Candidate
from pwrbnb.retrieval import permitted_url
from pwrbnb.topics import METRIC_CATEGORY, SECTIONS


def campus(name="Campus", city="Ashburn", state="VA"):
    return Candidate(
        name=name,
        city=city,
        state=state,
        address=f"{city}, {state}",
        phase="Phase 1",
        identity_url="https://equinix.com/site",
        reason="Official page",
    )


def test_city_clusters_and_selection_ignore_forged_objects():
    candidates = [campus(), campus("Campus two"), campus("Unknown", "Not a city", "VA")]
    points, missing = city_markers("Equinix", candidates)
    assert len(points) == 1 and len(points[0]["candidate_ids"]) == 2
    assert missing == [candidate_id("Equinix", candidates[2])]
    assert 38 < points[0]["lat"] < 40
    event = {"selection": {"objects": {"datacenters": [points[0]]}}}
    assert selected_candidates(event, points) == points[0]["candidate_ids"]
    assert not selected_candidates({"selection": {"objects": {"utility-regions": [points[0]]}}}, points)
    assert not selected_candidates(
        {"selection": {"objects": {"datacenters": [{"candidate_ids": ["forged"]}]}}}, points
    )


def test_bundled_regions_have_finite_geographic_coordinates():
    def positions(value):
        if isinstance(value[0], (float, int)):
            assert -180 <= value[0] <= 180 and -90 <= value[1] <= 90
        else:
            for child in value:
                positions(child)

    for kind, count in (("grid", 11), ("utility", 2919)):
        features = boundaries(kind)["features"]
        assert len(features) == count
        for feature in features:
            assert feature["properties"]["name"]
            positions(feature["geometry"]["coordinates"])


def finding(url, category="Power", metric="contracted_power", scope="Site", classification="Documented"):
    text = "The campus has a documented 50 MW utility commitment."
    doc = Document(
        title="Source report",
        url=url,
        pages=[text],
        status="Retrieved",
        official=url.startswith("https://equinix.com"),
    )
    claim = Claim(
        statement=text,
        category=category,
        metric=metric,
        scope=scope,
        classification=classification,
        phase="Phase 1",
        status="Documented",
        evidence=[Evidence(document_id=doc.id, page=1, quote=text)],
    )
    return Snapshot(site=Site(name="Campus", phase="Phase 1"), documents=[doc], claims=[claim])


def test_seven_sections_direct_references_and_missing_metrics():
    snap = finding("https://equinix.com/site")
    grouped = section_findings(snap)
    assert len(SECTIONS) == 7 and set(grouped) == set(METRIC_CATEGORY)
    assert grouped["contracted_power"] == snap.claims
    assert not grouped["expansion_power"]
    assert "[Source report](https://equinix.com/site)" in cited_statement(snap, snap.claims[0])
    snap.claims[0].metric = "pue"
    assert not validate_claims(snap, snap.claims)[0]


def test_specialist_sources_cannot_establish_site_power():
    for url in (
        "https://cbre.com/report",
        "https://jll.com/report",
        "https://cushmanwakefield.com/report",
        "https://peeringdb.com/fac/1",
    ):
        assert permitted_url(url, [])
        snap = finding(url)
        assert not validate_claims(snap, snap.claims)[0]
    market = finding("https://cbre.com/report", "Economics", "vacancy", "Market")
    assert validate_claims(market, market.claims)[0]
    assert cited_statement(market, market.claims[0]).startswith("Market context:")
    dcd = finding("https://datacenterdynamics.com/news/report")
    assert not validate_claims(dcd, dcd.claims)[0]
    dcd.claims[0].classification = "Announced"
    assert validate_claims(dcd, dcd.claims)[0]
    assert not permitted_url("https://cbre.com.evil.example/report", [])


def test_hover_marker_contains_names_and_city():
    points, _ = city_markers("Equinix", [campus("Campus One"), campus("Campus Two")])
    assert "Campus One" in points[0]["site_names"]
    assert "Campus Two" in points[0]["site_names"]
    assert "Ashburn" in points[0]["city_label"]

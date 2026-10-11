from fixtures import DEMO_SITES, build_demo

from pwrbnb.brief import supported_brief
from pwrbnb.evidence import validate_claims
from pwrbnb.models import Claim, Document, Evidence, Site, Snapshot
from pwrbnb.retrieval import official_host, retrieve_document, wikipedia_article


def test_live_summary_omits_unknown_inferred_and_unverified():
    snap = build_demo(DEMO_SITES[0])
    snap.site.mode = "Live"
    for doc in snap.documents:
        doc.official = True
    unknown = snap.claims[0].model_copy(deep=True)
    unknown.classification = "Unknown"
    unknown.statement = "UNVERIFIABLE DETAIL"
    inferred = unknown.model_copy(update={"classification": "Inferred"})
    unsupported = snap.claims[0].model_copy(deep=True)
    unsupported.statement = "UNSUPPORTED DETAIL"
    unsupported.evidence[0].quote = "This quote is entirely invented."
    snap.claims.extend([unknown, inferred, unsupported])
    paragraph, sources, claims = supported_brief(snap)
    assert paragraph and sources
    assert all(c.classification in {"Documented", "Announced"} for c in claims)
    for text in (paragraph,):
        assert "UNVERIFIABLE DETAIL" not in text
        assert "UNSUPPORTED DETAIL" not in text
    assert "Attributed announcement/report" in paragraph
    assert "[S1]" not in paragraph
    for doc in snap.documents:
        doc.official = False
    assert supported_brief(snap) == ("", [], [])


def test_wikipedia_is_secondary_and_cannot_prove_power_or_permits(tmp_path, monkeypatch):
    from pwrbnb import retrieval

    url = "https://en.wikipedia.org/wiki/Ashburn,_Virginia"
    content = b"<html><title>Ashburn</title><p>Ashburn is located in Loudoun County, Virginia.</p></html>"
    monkeypatch.setattr(retrieval, "public_get", lambda *args: (content, "text/html", url))
    doc = retrieve_document(Document(title="Ashburn", url=url), tmp_path, [], 1)
    assert doc.status == "Retrieved"
    assert not doc.official
    snap = Snapshot(site=Site(name="Test", phase="Phase 1"), documents=[doc])
    claim = Claim(
        statement="Ashburn is located in Loudoun County, Virginia.",
        category="Regional context",
        classification="Documented",
        phase="Phase 1",
        status="Documented",
        evidence=[
            Evidence(document_id=doc.id, page=1, quote="Ashburn is located in Loudoun County, Virginia.")
        ],
    )
    assert validate_claims(snap, [claim])[0]
    assert not validate_claims(snap, [claim.model_copy(update={"category": "Power"})])[0]
    assert not validate_claims(snap, [claim.model_copy(update={"category": "Planning & permits"})])[0]
    assert official_host("https://www.nerc.com/pa", [])
    assert not wikipedia_article("https://en.wikipedia.org.evil.example/wiki/Ashburn")
    assert not wikipedia_article("https://en.wikipedia.org/wiki/User:Example")
    assert not wikipedia_article("https://en.wikipedia.org/wiki/Talk%3AAshburn")

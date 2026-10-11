import pytest

from pwrbnb.models import Document, Evidence, Limits, Site
from pwrbnb.research import Extracted, ResearchClaim, Researcher, SourceLink, SourceLinks, Verdict, Verdicts
from pwrbnb.retrieval import permitted_url


@pytest.mark.parametrize(
    "developer,city,state,url,quote,metric",
    [
        (
            "Google",
            "Mesa",
            "AZ",
            "https://blog.google/mesa",
            "The Mesa campus uses air cooling technology.",
            "cooling",
        ),
        (
            "Microsoft",
            "Quincy",
            "WA",
            "https://local.microsoft.com/quincy",
            "The Quincy campus reuses water for cooling.",
            "water",
        ),
    ],
)
def test_identity_retrieval_budget_and_visible_finding(
    tmp_path, monkeypatch, developer, city, state, url, quote, metric
):
    # Synthetic source fixtures exercise the pipeline, not the truth of published claims.
    import pwrbnb.research as module

    site = Site(name=city, developer=developer, city=city, state=state, phase="Existing")
    researcher = Researcher("fake", "test", Limits(documents=1), client=object())
    queries = []

    def search(query):
        queries.append(query)
        return "results", {url}

    monkeypatch.setattr(researcher, "search", search)

    def retrieve(doc, *args):
        if doc.url == url:
            return doc.model_copy(update={"pages": [quote], "official": True, "status": "Retrieved"})
        return doc.model_copy(update={"status": "Inaccessible"})

    monkeypatch.setattr(module, "retrieve_document", retrieve)
    claim = None

    def parse(schema, prompt):
        nonlocal claim
        if schema is SourceLinks:
            return SourceLinks(
                sources=[
                    SourceLink(
                        url=url, title="Campus record", publisher=developer, family="Developer / operator"
                    )
                ]
            )
        if schema is Extracted:
            import json

            # Recover the actual retrieved document ID passed to extraction.
            payload = json.loads(prompt[prompt.index('{"site":') :])
            doc = payload["passages"][0]
            claim = ResearchClaim(
                statement=quote,
                category="Economics",
                metric=metric,
                classification="Documented",
                phase="Phase unconfirmed",
                status="Documented",
                evidence=[Evidence(document_id=doc["document_id"], page=1, quote=quote)],
            )
            return Extracted(claims=[claim], questions=[])
        return Verdicts(verdicts=[Verdict(claim_id=claim.id, supported=True, reason="Fixture supported")])

    monkeypatch.setattr(researcher, "parse", parse)
    result = researcher.research(
        site,
        tmp_path,
        [],
        lambda _: None,
        supplied=[
            Document(title="Unreadable", url="https://microsoft.com/missing", family="Developer / operator")
        ],
    )
    assert developer in queries[0] and city in queries[0] and state in queries[0]
    assert len(result.documents) == 2  # Failed record did not consume the readable limit.
    assert len(result.claims) == 1 and result.claims[0].category == "Cooling and water"
    assert result.site.phase == "Phase unconfirmed" and result.site.stage == "Existing"
    assert result.research_status == "complete" and result.report_version == 2
    assert result.proposed_claims


def test_no_records_is_not_success(tmp_path, monkeypatch):
    researcher = Researcher("fake", "test", Limits(), client=object())
    result = researcher.research(Site(name="Empty"), tmp_path, [], lambda _: None, discover=False)
    assert result.research_status == "no_findings" and not result.claims


def test_official_domains_and_strict_metric():
    assert permitted_url("https://blog.google/announcement", [])
    assert permitted_url("https://www.srpnet.com/report", [])
    assert not permitted_url("https://blog.google.evil.example/report", [])
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResearchClaim(
            statement="Test",
            category="Power",
            metric="invented",
            classification="Documented",
            phase="Phase 1",
            status="Documented",
        )


def test_phase_formatting_does_not_reject_but_different_phase_does():
    from pwrbnb.evidence import validate_claims
    from pwrbnb.models import Claim, Snapshot

    doc = Document(
        title="Record",
        url="https://microsoft.com/test",
        official=True,
        status="Retrieved",
        pages=["The site has a water reuse facility."],
    )
    snap = Snapshot(site=Site(name="Site", phase="Phase unconfirmed"), documents=[doc])
    claim = Claim(
        statement=doc.pages[0],
        category="Cooling and water",
        metric="water",
        phase="  Phase  unconfirmed. ",
        classification="Documented",
        status="Documented",
        evidence=[Evidence(document_id=doc.id, page=1, quote=doc.pages[0])],
    )
    assert validate_claims(snap, [claim])[0]
    claim.phase = "Phase 2"
    assert not validate_claims(snap, [claim])[0]


def test_saved_analysis_never_searches_or_downloads_and_retains_checked_batches(tmp_path, monkeypatch):
    import pwrbnb.research as module

    researcher = Researcher("fake", "test", Limits(), client=object())

    def unexpected(*args):
        raise AssertionError("Saved-only analysis must not use network retrieval")

    monkeypatch.setattr(researcher, "search", unexpected)
    monkeypatch.setattr(module, "retrieve_document", unexpected)
    quote = "The site has a water reuse facility."
    docs = [
        Document(
            title=f"Record {i}",
            url=f"https://microsoft.com/{i}",
            official=True,
            status="Retrieved",
            pages=[quote + " " * 9990],
        )
        for i in range(3)
    ]
    docs.append(Document(title="Blocked", url="https://unverified.example/test"))
    seen = []
    claim = None

    def parse(schema, prompt):
        nonlocal claim
        import json

        if schema is Extracted:
            payload = json.loads(prompt[prompt.index('{"site":') :])
            seen.append(payload)
            if len(seen) == 2:
                raise TimeoutError("Later batch failed")
            passage = payload["passages"][0]
            claim = ResearchClaim(
                statement=quote,
                category="Power",
                metric="water",
                phase="Phase unconfirmed.",
                classification="Documented",
                status="Documented",
                evidence=[Evidence(document_id=passage["document_id"], page=1, quote=quote)],
            )
            return Extracted(claims=[claim], questions=[])
        return Verdicts(verdicts=[Verdict(claim_id=claim.id, supported=True, reason="Supported")])

    monkeypatch.setattr(researcher, "parse", parse)
    result = researcher.research(
        Site(name="Test", identity_url="https://microsoft.com/new"),
        tmp_path,
        [],
        lambda _: None,
        supplied=docs,
        discover=False,
    )
    assert len(seen) == 2
    assert all(sum(len(p["text"]) for p in batch["passages"]) <= 24000 for batch in seen)
    assert len(result.claims) == 1 and result.research_status == "partial"
    assert len(result.documents) == 3

from types import SimpleNamespace

import pytest
from fixtures import DEMO_SITES, build_demo
from pydantic import ValidationError

from pwrbnb.evidence import validate_claims
from pwrbnb.models import Document, Evidence, Limits, Site
from pwrbnb.research import Candidate, Candidates, Researcher, cited_urls
from pwrbnb.retrieval import extract_document, official_host, validate_url
from pwrbnb.store import Store, changes


def test_demo_evidence_and_units():
    snap = build_demo(DEMO_SITES[0])
    valid, rejected = validate_claims(snap, snap.claims)
    assert not rejected
    assert len(valid) == len(snap.claims)
    assert [(c.capacity_mw, c.capacity_basis, c.status) for c in valid[:2]] == [
        (120, "IT load", "Announced"),
        (150, "Total facility demand", "Requested"),
    ]
    assert valid[4].capacity_mw is None
    assert valid[3].classification == "Conflicting"


def test_reject_cross_site_phase_false_quote_and_unverified():
    snap = build_demo(DEMO_SITES[0])
    claim = snap.claims[0].model_copy(deep=True)
    claim.phase = "Phase 2"
    assert not validate_claims(snap, [claim])[0]
    claim = snap.claims[0].model_copy(deep=True)
    claim.evidence = [Evidence(document_id="other-site", page=1, quote="invented evidence")]
    assert not validate_claims(snap, [claim])[0]
    claim = snap.claims[0].model_copy(deep=True)
    claim.evidence[0].quote = "An executed service agreement guarantees 120 MW."
    assert not validate_claims(snap, [claim])[0]
    snap.site.mode = "Live"
    assert not validate_claims(snap, snap.claims[:1])[0]


def test_unknown_capacity_cannot_be_zero():
    snap = build_demo(DEMO_SITES[0])
    claim = snap.claims[4].model_copy(update={"capacity_mw": 0})
    assert not validate_claims(snap, [claim])[0]


def test_persistence_snapshot_immutability_scoping_and_idempotency(tmp_path):
    store = Store(tmp_path)
    first = build_demo(DEMO_SITES[0])
    other = build_demo(DEMO_SITES[1])
    store.save(first)
    store.save(other)
    store.save(first)
    assert len(store.history(first.site.id)) == 1
    first.claims[0].statement = "This mutation must not overwrite history"
    store.save(first)
    assert "mutation" not in store.load(first.id).claims[0].statement
    matches = store.retrieve(first.id, "power demand substation")
    assert matches and all(m["document_id"].startswith(first.site.id) for m in matches)
    assert store.begin("paid-request-1")
    assert not store.begin("paid-request-1")
    store.add_message("message-1", first, "user", "What is requested?")
    store.add_message("message-1", first, "user", "duplicate")
    reopened = Store(tmp_path)
    assert len(reopened.messages(first.site.id)) == 1
    assert not reopened.messages(other.site.id)


def test_snapshot_changes():
    before = build_demo(DEMO_SITES[0])
    after = build_demo(DEMO_SITES[0], revision=2)
    assert "1 new or changed" in changes(before, after)[0]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/a",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "https://user:pass@example.org",
        "https://example.org:8080",
    ],
)
def test_url_rejection(url):
    def resolver(host, *args, **kwargs):
        return [(None, None, None, None, (host, 443))]

    with pytest.raises(ValueError):
        validate_url(url, resolver)


def test_dns_mixed_private_and_public_is_rejected():
    def resolver(*args, **kwargs):
        return [(0, 0, 0, 0, ("8.8.8.8", 443)), (0, 0, 0, 0, ("10.0.0.1", 443))]

    with pytest.raises(ValueError):
        validate_url("https://example.org", resolver)
    assert official_host("https://eia.gov/data", [])
    assert not official_host("https://eia.gov.evil.example/data", [])
    assert not official_host("https://utility.example", [])
    assert official_host("https://filings.utility.example/a", ["utility.example"])


def test_extract_html_and_broken_pdf(tmp_path):
    data = b'<html><title>Planning record</title><meta property="article:published_time" content="2026-01-01"><body><p>Conditional approval granted. A building permit has not been issued.</p></body></html>'
    doc = extract_document(Document(title="test"), data, "text/html", tmp_path)
    assert doc.status == "Retrieved" and doc.published == "2026-01-01"
    assert "Conditional approval" in doc.pages[0]
    broken = extract_document(Document(title="broken"), b"%PDF-broken", "application/pdf", tmp_path)
    assert broken.status == "Extraction failed"


def test_coordinate_pair_and_limits():
    with pytest.raises(ValidationError):
        Site(name="invalid", latitude=33)
    with pytest.raises(ValidationError):
        Limits(documents=500)


def test_discovery_excludes_invented_urls():
    candidate = Candidate(
        name="A", address="Ohio", phase="Phase 1", identity_url="https://invented.example", reason="x"
    )

    class Client:
        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            assert kwargs["store"] is False and kwargs["max_tool_calls"] == 3
            return SimpleNamespace(
                output_text="official discovery",
                output=[SimpleNamespace(type="web_search_call")],
                usage=None,
                model_dump=lambda: {
                    "content": [{"type": "url_citation", "url": "https://official.gov/site"}]
                },
            )

        def parse(self, **kwargs):
            return SimpleNamespace(output_parsed=Candidates(candidates=[candidate]), output=[], usage=None)

    researcher = Researcher("fake-test-key", "test-model", Limits(), client=Client())
    assert researcher.discover("A") == []
    assert researcher.usage["search_calls"] == 1
    assert cited_urls({"text": "https://invented.example"}) == set()


def test_partial_failure_preserves_sources(tmp_path, monkeypatch):
    snap = build_demo(DEMO_SITES[0])
    snap.site.mode = "Live"
    for doc in snap.documents:
        doc.official = True
    researcher = Researcher("fake", "test", Limits(), client=object())

    def broken(*args, **kwargs):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(researcher, "parse", broken)
    result = researcher.research(
        snap.site, tmp_path, [], lambda _: None, supplied=snap.documents, discover=False
    )
    assert len(result.documents) == 4
    assert not result.claims
    assert any("Research stopped" in n for n in result.notes)

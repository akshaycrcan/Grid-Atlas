"""Mocked checks for the live evidence gate. Never spends API credits."""

from fixtures import DEMO_SITES, build_demo

from pwrbnb.models import Limits
from pwrbnb.research import Extracted, ResearchClaim, Researcher, Verdict, Verdicts


def test_live_synthesis_omits_semantically_unsupported_claim(tmp_path, monkeypatch):
    fixture = build_demo(DEMO_SITES[0])
    fixture.site.mode = "Live"
    for doc in fixture.documents:
        doc.official = True
    supported = fixture.claims[0]
    overstated = fixture.claims[1].model_copy(deep=True)
    overstated.statement = "150 MW is guaranteed and already energized."
    supported = ResearchClaim.model_validate(supported.model_dump() | {"metric": "contracted_power"})
    overstated = ResearchClaim.model_validate(overstated.model_dump() | {"metric": "contracted_power"})
    output = iter(
        [
            Extracted(claims=[supported, overstated], questions=["Is service executed?"]),
            Verdicts(
                verdicts=[
                    Verdict(claim_id=supported.id, supported=True, reason="Exact attribution"),
                    Verdict(claim_id=overstated.id, supported=False, reason="Requested is not energized"),
                ]
            ),
        ]
    )
    researcher = Researcher("test-key", "test-model", Limits(), client=object())
    monkeypatch.setattr(researcher, "parse", lambda *a: next(output))
    result = researcher.research(
        fixture.site, tmp_path, [], lambda _: None, supplied=fixture.documents, discover=False
    )
    assert [c.id for c in result.claims] == [supported.id]
    assert any("Requested is not energized" in n for n in result.notes)

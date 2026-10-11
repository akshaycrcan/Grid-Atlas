"""Fictional, deterministic fixtures. No API key or research network calls."""

import hashlib

from pwrbnb.models import Claim, Coverage, Document, Evidence, Site, Snapshot

DEMO_SITES = [
    Site(
        id="demo-riverbend",
        name="Riverbend Compute Campus",
        mode="Demo",
        address="Columbus, Ohio · fictional project",
        developer="Riverbend Development (fictional)",
        operator="Not disclosed",
        phase="Phase 1",
        stage="Announced",
        latitude=39.9612,
        longitude=-82.9988,
        location_precision="Illustrative city center",
        location_source="Demo fixture: approximate Columbus city center, not a real campus",
    ),
    Site(
        id="demo-mesa",
        name="Mesa Ridge Data Center",
        mode="Demo",
        address="Phoenix, Arizona · fictional project",
        developer="Mesa Ridge Partners (fictional)",
        operator="Mesa Cloud (fictional)",
        phase="Expansion phase",
        stage="Existing campus / proposed expansion",
        latitude=33.4484,
        longitude=-112.0740,
        location_precision="Illustrative city center",
        location_source="Demo fixture: approximate Phoenix city center, not a real campus",
    ),
    Site(
        id="demo-north",
        name="Northstar Digital Campus",
        mode="Demo",
        address="Anchorage, Alaska · fictional project",
        developer="Northstar Development (fictional)",
        phase="Phase 1",
        stage="Announced",
        latitude=61.2181,
        longitude=-149.9003,
        location_precision="Illustrative city center",
        location_source="Demo fixture: approximate Anchorage city center, not a real campus",
    ),
]


def build_demo(site: Site, revision: int = 1) -> Snapshot:
    site = site.model_copy(deep=True)
    phase = site.phase
    texts = [
        (
            "announcement",
            "Developer announcement",
            "Developer / operator",
            "2026-02-12",
            f"{site.name}, {phase}: the developer announces 120 MW of IT load. Target energization is Q4 2028. "
            "The ultimate campus concept is 300 MW of IT load; this includes Phase 1. The operator is not confirmed.",
        ),
        (
            "utility",
            "Utility service application · DEMO-26-014",
            "Utility / commission",
            "2026-04-08",
            f"{site.name}, {phase}: the requested total facility demand is 150 MW. "
            "Service depends on completion of a new substation and transmission reinforcement. "
            "This application is not an executed service agreement. The utility planning assumption is Q2 2029.",
        ),
        (
            "planning",
            "Planning decision · DEMO-Z-2026-07",
            "Local planning / permits",
            "2026-05-19",
            f"{site.name}, {phase}: conditional land-use approval was granted. "
            "The applicant must submit a final traffic plan and construction access plan before building permit issuance. "
            "This decision does not issue a building permit.",
        ),
        (
            "grid",
            "Illustrative regional load forecast",
            "ISO / grid authority",
            "2026-03-01",
            "The regional forecast anticipates increasing large-load demand. "
            "This forecast provides no site-specific service commitment or available-capacity allocation.",
        ),
    ]
    if revision > 1:
        texts.append(
            (
                "update",
                "Planning condition update",
                "Local planning / permits",
                "2026-06-15",
                f"{site.name}, {phase}: the final traffic plan was accepted. "
                "The construction access plan remains outstanding. No building permit is issued by this update.",
            )
        )
    docs = [
        Document(
            id=f"{site.id}-{key}",
            title=title + " (fictional)",
            publisher="Fictional demonstration publisher",
            family=family,
            published=date,
            status="Retrieved",
            official=False,
            provenance="Built-in fictional fixture; not official evidence",
            pages=[text],
            sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        for key, title, family, date, text in texts
    ]

    def ev(key: str, quote: str) -> Evidence:
        return Evidence(document_id=f"{site.id}-{key}", page=1, quote=quote)

    claims = [
        Claim(
            category="Power",
            statement="120 MW of IT load announced for this phase.",
            classification="Announced",
            phase=phase,
            capacity_mw=120,
            capacity_basis="IT load",
            status="Announced",
            evidence=[ev("announcement", "the developer announces 120 MW of IT load.")],
        ),
        Claim(
            category="Power",
            statement="150 MW of total facility demand requested; this is not committed service.",
            classification="Documented",
            phase=phase,
            capacity_mw=150,
            capacity_basis="Total facility demand",
            status="Requested",
            evidence=[
                ev("utility", "the requested total facility demand is 150 MW."),
                ev("utility", "This application is not an executed service agreement."),
            ],
        ),
        Claim(
            category="Power",
            statement="A new substation and transmission reinforcement are service dependencies.",
            classification="Documented",
            phase=phase,
            status="Required / completion unverified",
            evidence=[
                ev(
                    "utility",
                    "Service depends on completion of a new substation and transmission reinforcement.",
                )
            ],
        ),
        Claim(
            category="Power",
            statement="Energization dates conflict: developer Q4 2028; utility assumption Q2 2029.",
            classification="Conflicting",
            phase=phase,
            status="Unresolved",
            evidence=[
                ev("announcement", "Target energization is Q4 2028."),
                ev("utility", "The utility planning assumption is Q2 2029."),
            ],
        ),
        Claim(
            category="Power",
            statement="Executed service agreement and committed MW not located in the reviewed example records.",
            classification="Unknown",
            phase=phase,
            capacity_mw=None,
            capacity_basis="Committed facility demand",
        ),
        Claim(
            category="Planning & permits",
            statement="Conditional land-use approval granted; building permit issuance is unverified.",
            classification="Documented",
            phase=phase,
            status="Conditionally approved",
            evidence=[
                ev("planning", "conditional land-use approval was granted."),
                ev("planning", "This decision does not issue a building permit."),
            ],
        ),
        Claim(
            category="Planning & permits",
            statement="Final traffic and construction access plans are approval conditions.",
            classification="Documented",
            phase=phase,
            status="Conditions outstanding",
            evidence=[
                ev(
                    "planning",
                    "The applicant must submit a final traffic plan and construction access plan before building permit issuance.",
                )
            ],
        ),
        Claim(
            category="Regional context",
            statement="The regional forecast is context, not a site-specific power allocation.",
            classification="Documented",
            phase=phase,
            status="Regional only",
            evidence=[
                ev(
                    "grid",
                    "This forecast provides no site-specific service commitment or available-capacity allocation.",
                )
            ],
        ),
    ]
    if revision > 1:
        claims[6] = Claim(
            category="Planning & permits",
            statement="Traffic plan accepted; construction access plan remains outstanding.",
            classification="Documented",
            phase=phase,
            status="One condition outstanding",
            evidence=[
                ev("update", "the final traffic plan was accepted."),
                ev("update", "The construction access plan remains outstanding."),
            ],
        )
    return Snapshot(
        site=site,
        documents=docs,
        claims=claims,
        coverage=[
            Coverage(family=f, status=s, note=n)
            for f, s, n in [
                ("Developer / operator", "Retrieved", "Fictional announcement"),
                ("Corporate filings", "Searched but not located", "Demonstrated missing record"),
                ("Utility / commission", "Retrieved", "Application only; agreement not located"),
                ("ISO / grid authority", "Retrieved", "Regional context only"),
                ("EIA", "Not searched", "No site-specific EIA dataset selected in this demo"),
                (
                    "Local planning / permits",
                    "Manual review required",
                    "Planning decision available; permit portal inaccessible",
                ),
            ]
        ],
        questions=[
            "Has an executed utility service agreement been signed, and for what capacity?",
            "What is the approved completion schedule for the substation and transmission upgrades?",
            "Which energization date applies to the selected phase?",
            "Have the remaining planning conditions been discharged and building permits issued?",
        ],
        notes=[
            "Fictional demonstration. No real project, developer, utility, or official record is represented.",
            "Refresh simulates a later planning update; it does not access the internet.",
        ],
        usage={"api_calls": 0, "input_tokens": 0, "output_tokens": 0},
    )

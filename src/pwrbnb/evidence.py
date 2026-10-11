"""Fail closed on unsupported quotes, phase leakage, and unverified publishers."""

import re

from .models import Claim, Snapshot
from .retrieval import eligible_source, secondary_source, wikipedia_article
from .topics import METRIC_CATEGORY


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_phase(value: str) -> str:
    return normalize(value).rstrip(".").strip()


def validate_claims(snapshot: Snapshot, claims: list[Claim]) -> tuple[list[Claim], list[str]]:
    docs = {d.id: d for d in snapshot.documents}
    accepted, rejected = [], []
    for claim in claims:
        problem = ""
        if snapshot.site.mode == "Live" and claim.classification not in {"Documented", "Announced"}:
            problem = "only documented facts and attributed announcements may be presented"
        elif normalize_phase(claim.phase) != normalize_phase(snapshot.site.phase):
            problem = "claim belongs to a different or unspecified phase"
        elif claim.metric and METRIC_CATEGORY.get(claim.metric) != claim.category:
            problem = "finding does not match a requested metric and section"
        elif claim.classification != "Unknown" and not claim.evidence:
            problem = "no supporting evidence"
        elif claim.capacity_mw is not None and not claim.capacity_basis:
            problem = "capacity has no definition"
        elif claim.classification == "Unknown" and claim.capacity_mw is not None:
            problem = "unknown capacity must be null"
        for ev in claim.evidence:
            doc = docs.get(ev.document_id)
            if not doc or doc.status != "Retrieved" or ev.page > len(doc.pages):
                problem = "citation is missing or outside the retrieved document"
                break
            if snapshot.site.mode != "Demo" and not eligible_source(doc):
                problem = "publisher provenance has not been verified"
                break
            specialist = secondary_source(doc.url)
            if specialist.endswith("market report") and (
                claim.category not in {"Economics", "Market and competitive landscape"}
                or claim.scope not in {"Market", "Regional"}
            ):
                problem = "market reports must be labeled market or regional context"
                break
            if specialist.startswith("PeeringDB") and claim.category != "Location and connectivity":
                problem = "PeeringDB supports connectivity findings only"
                break
            if specialist.startswith("Data Center Dynamics") and claim.classification != "Announced":
                problem = "industry reporting must remain attributed reporting"
                break
            if (
                snapshot.site.mode == "Live"
                and wikipedia_article(doc.url)
                and (claim.category not in {"Identity", "Regional context"} or claim.capacity_mw is not None)
            ):
                problem = "power, capacity and permitting findings require official records"
                break
            if len(normalize(ev.quote)) < 12 or normalize(ev.quote) not in normalize(doc.pages[ev.page - 1]):
                problem = "quoted passage is not present on the cited page"
                break
        if problem:
            rejected.append(f"Omitted finding: {problem}.")
        else:
            accepted.append(claim)
    return accepted, rejected

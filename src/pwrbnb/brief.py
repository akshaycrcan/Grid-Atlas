"""A cited paragraph assembled only from checked findings, without another paid model call."""

import re

from .evidence import validate_claims
from .models import Snapshot
from .topics import METRIC_CATEGORY


def reference_link(doc):
    title = re.sub(r"[\[\]<>]", "", doc.title).replace("\n", " ")
    url = doc.url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")
    return f"[{title}]({url})" if url.startswith(("https://", "http://")) else title


def cited_statement(snapshot, claim):
    docs = {d.id: d for d in snapshot.documents}
    links = list(dict.fromkeys(reference_link(docs[e.document_id]) for e in claim.evidence))
    prefix = "Attributed announcement/report: " if claim.classification == "Announced" else ""
    scope = f"{claim.scope} context: " if claim.scope != "Site" else ""
    return scope + prefix + claim.statement.strip() + " " + " · ".join(links)


def section_findings(snapshot):
    _, _, claims = supported_brief(snapshot)
    return {metric: [c for c in claims if c.metric == metric] for metric in METRIC_CATEGORY}


def supported_brief(snapshot: Snapshot):
    claims, _ = validate_claims(snapshot, snapshot.claims)
    claims = [c for c in claims if c.classification in {"Documented", "Announced"}]
    order = {"Identity": 0, "Power": 1, "Planning & permits": 2, "Regional context": 3}
    claims.sort(key=lambda c: order.get(c.category, 4))
    docs = {d.id: d for d in snapshot.documents}
    sources, seen, sentences = [], set(), []
    for claim in claims:
        for ev in claim.evidence:
            if ev.document_id not in seen:
                sources.append(docs[ev.document_id])
                seen.add(ev.document_id)
        sentences.append(cited_statement(snapshot, claim))
    return " ".join(sentences), sources, claims

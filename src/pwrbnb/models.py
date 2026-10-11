"""Evidence contracts for live research and backward-compatible saved snapshots."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


Classification = Literal["Documented", "Announced", "Inferred", "Unknown", "Conflicting"]
Category = Literal[
    "Identity",
    "Power",
    "Planning & permits",
    "Regional context",
    "Cooling and water",
    "Location and connectivity",
    "Design and reliability",
    "Economics",
    "Market and competitive landscape",
    "Land, permitting and community",
]
CoverageState = Literal[
    "Retrieved",
    "Extraction failed",
    "Inaccessible",
    "Manual review required",
    "Searched but not located",
    "Not searched",
]
FAMILIES = [
    "Developer / operator",
    "Corporate filings",
    "Utility / commission",
    "ISO / grid authority",
    "EIA",
    "Local planning / permits",
    "Market reports",
    "Certification / reliability",
    "Connectivity",
    "Industry reporting",
]


class Site(BaseModel):
    id: str = Field(default_factory=uid)
    name: str
    mode: Literal["Demo", "Live"] = "Live"
    address: str = "Location unconfirmed"
    city: str = ""
    state: str = ""
    developer: str = "Unconfirmed"
    operator: str = "Unconfirmed"
    phase: str = "Phase unconfirmed"
    stage: str = "Unconfirmed"
    aliases: list[str] = Field(default_factory=list)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_precision: str = "Unconfirmed"
    location_source: str = ""
    identity_url: str = ""

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together")
        return self


class Document(BaseModel):
    id: str = Field(default_factory=uid)
    title: str
    publisher: str = "Unverified publisher"
    url: str = ""
    family: str = "User supplied"
    published: str | None = None
    retrieved: str = Field(default_factory=now)
    status: CoverageState = "Not searched"
    note: str = ""
    official: bool = False
    provenance: str = ""
    sha256: str = ""
    file_name: str = ""
    pages: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    quote: str


class Claim(BaseModel):
    id: str = Field(default_factory=uid)
    category: Category
    metric: str = ""
    scope: Literal["Site", "Market", "Regional", "Company"] = "Site"
    statement: str
    classification: Classification
    phase: str
    status: str = "Not established"
    capacity_mw: float | None = Field(default=None, ge=0)
    capacity_basis: str | None = None
    effective_date: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = ""


class Coverage(BaseModel):
    family: str
    status: CoverageState = "Not searched"
    note: str = ""


class Snapshot(BaseModel):
    report_version: int = 0
    research_status: Literal["not_started", "complete", "partial", "no_findings", "failed"] = "not_started"
    proposed_claims: list[dict] = Field(default_factory=list)
    id: str = Field(default_factory=uid)
    site: Site
    created: str = Field(default_factory=now)
    documents: list[Document] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class Limits(BaseModel):
    search_calls: int = Field(default=3, ge=1, le=8)
    documents: int = Field(default=8, ge=1, le=20)
    file_mb: int = Field(default=10, ge=1, le=15)
    output_tokens: int = Field(default=6000, ge=2000, le=16000)
    seconds: int = Field(default=240, ge=30, le=600)

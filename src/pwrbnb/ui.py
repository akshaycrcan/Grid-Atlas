"""Native Streamlit interface: developer discovery, selectable map and site findings."""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from .brief import cited_statement, section_findings
from .city_location import locate_city
from .errors import describe_error
from .map_view import candidate_id, show_map
from .models import Limits, Site, Snapshot, now, uid
from .research import Candidate, Researcher
from .retrieval import eligible_source, host_of
from .store import Store, changes
from .topics import MISSING, SECTIONS

DEVELOPERS = (
    "Aligned Data Centers",
    "Amazon Web Services",
    "CyrusOne",
    "DataBank",
    "Digital Realty",
    "Equinix",
    "Google",
    "Meta",
    "Microsoft",
    "QTS",
    "STACK Infrastructure",
    "Switch",
    "Vantage Data Centers",
)

PROJECT = Path(__file__).resolve().parents[2]


@st.cache_resource
def open_store(path: str) -> Store:
    return Store(path)


def selected(snapshot_id: str):
    st.session_state["selected"] = snapshot_id


def secret_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("OPENAI_API_KEY", "")
        except FileNotFoundError, st.errors.StreamlitSecretNotFoundError:
            pass
    return key


def perform_research(store, snapshot, key, model, limits, approved, discover=True):
    approved = list(set(approved) | {host_of(d.url) for d in snapshot.documents if d.official and d.url})
    operation = uid()
    if not store.begin(operation):
        return
    with st.status("Researching source records", expanded=True) as status:
        try:
            researcher = Researcher(key, model, limits)

            def checkpoint(partial):
                backup = partial.model_copy(deep=True)
                backup.id, backup.created = uid(), now()
                backup.notes.append("Retrieval checkpoint; synthesis not yet complete.")
                store.save(backup)

            supplied = [
                d.model_copy(update={"pages": [], "status": "Not searched"}) if discover and d.url else d
                for d in snapshot.documents
            ]
            result = researcher.research(
                snapshot.site,
                store.root,
                approved,
                st.write,
                supplied=supplied,
                discover=discover,
                checkpoint=checkpoint,
            )
            result.notes.extend(changes(snapshot, result))
            store.save(result)
            store.finish(operation, "complete", result.id)
            selected(result.id)
            status.update(
                label="Research saved"
                if result.research_status == "complete"
                else "Research needs attention",
                state="complete" if result.research_status == "complete" else "error",
                expanded=False,
            )
        except Exception as exc:
            message = describe_error(exc)
            store.finish(operation, "failed", message)
            status.update(label="Research could not finish", state="error")
            st.error(message + " Existing research is safe.")
            return
    st.rerun()


def investigate(candidate, developer, store, key, model, limits, approved):
    site_id = candidate_id(developer, candidate)
    history = store.history(site_id)
    if history:
        # Open saved results without silently charging for a retry, including old/empty runs.
        snapshots = [store.load(item["id"]) for item in history]
        completed = [s for s in snapshots if s.report_version > 0]
        selected((completed or snapshots)[0].id)
        return
    location = locate_city(candidate.city, candidate.state, candidate.address)
    site = Site(
        id=site_id,
        name=candidate.name,
        developer=developer,
        address=candidate.address,
        city=candidate.city,
        state=candidate.state,
        phase=candidate.phase or "Phase unconfirmed",
        identity_url=candidate.identity_url,
        latitude=location["latitude"] if location else None,
        longitude=location["longitude"] if location else None,
        location_precision="Approximate city location" if location else "Unconfirmed",
        location_source="US Census Bureau 2025 Places Gazetteer" if location else "",
    )
    snapshot = Snapshot(site=site)
    store.save(snapshot)
    selected(snapshot.id)
    perform_research(store, snapshot, key, model, limits, approved)


def render():
    st.set_page_config(
        page_title="Grid Atlas · Site research",
        page_icon=":material/electric_bolt:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    load_dotenv(PROJECT / ".env", override=False)
    store = open_store(os.getenv("PWRBNB_DATA_DIR", str(PROJECT / "data")))
    st.session_state.setdefault("selected", None)
    key = secret_key()
    with st.sidebar:
        st.title("Grid Atlas", anchor=False)
        st.subheader("Find your site", icon=":material/travel_explore:")
        developer = st.selectbox(
            "Developer name", DEVELOPERS, index=None, key="developer-name", placeholder="Choose a developer"
        )
        discover = st.button("Find sites", type="primary", disabled=not key or not developer)
        st.caption(
            "Find up to 20 announced or existing US sites, then click a city pin. Discovery is a bounded search, not a complete portfolio census."
        )
    model = os.getenv("OPENAI_MODEL", "gpt-6-astra")
    limits = Limits(search_calls=6, documents=16, file_mb=12, output_tokens=12000, seconds=480)
    # Optional administrator-maintained domains; no settings form in the user workflow.
    approved = [
        host_of("https://" + d.strip().removeprefix("https://").removeprefix("http://"))
        for d in os.getenv("GRID_ATLAS_VERIFIED_DOMAINS", "").replace(",", "\n").splitlines()
        if d.strip()
    ]

    if st.session_state.get("active_developer") != developer:
        st.session_state.update(active_developer=developer, selected=None, last_map_selection=None)
    if discover:
        try:
            with st.spinner("Finding developer sites and official identity sources…"):
                candidates = Researcher(key, model, limits).discover(
                    f"Find announced and existing US datacenter sites developed or operated by {developer}. "
                    "Return only sites with official identity sources supporting this company relationship. Include city and state."
                )
                store.save_discovery(developer, [c.model_dump() for c in candidates])
            if not candidates:
                st.info(
                    "No supported sites found within this search. Try another developer or retry Find sites."
                )
        except Exception as exc:
            st.error("Discovery failed: " + describe_error(exc))
    candidates = [Candidate.model_validate(c) for c in store.discovery(developer)] if developer else []
    st.title("Grid Atlas", anchor=False)
    st.markdown("### Understand the infrastructure behind a datacenter site.")
    st.markdown(
        "Grid Atlas is a US datacenter research workspace for developers evaluating announced and existing campuses. "
        "Choose an operator or developer to locate its discovered sites on the map, then select a map marker or a listed site to investigate "
        "the campus. Regional grid and utility reference layers put those locations in context."
    )
    st.markdown(
        "Each investigation brings together seven dimensions: **power; cooling and water; location and connectivity; "
        "design and reliability; economics; market and competition; and land, permitting and community**. "
        "Findings are checked against retrieved operator publications, investor filings, utilities, regulators, planning records "
        "and approved specialist sources, with direct links to the supporting references. Market statistics and announcements "
        "are labeled separately from site facts. Missing evidence is shown as **Details not available.** "
    )
    if not key:
        st.warning(
            "Set OPENAI_API_KEY in the project .env or Streamlit secrets and restart to enable discovery and new investigations."
        )
    st.subheader("Explore datacenter locations")
    utilities = st.checkbox("Show utility territories", value=False)
    chosen, _ = show_map(developer, candidates, utilities)
    lookup = {candidate_id(developer, c): c for c in candidates}
    choice = None
    if len(chosen) == 1:
        selection = (developer, chosen[0])
        if st.session_state.get("last_map_selection") != selection:
            st.session_state["last_map_selection"] = selection
            choice = chosen[0]
    elif chosen:
        st.session_state["last_map_selection"] = None
        st.info("Several sites share this city. Select one of the highlighted names below.")
    else:
        st.session_state["last_map_selection"] = None
    if candidates:
        st.subheader(f"{developer} datacenter sites")
        columns = st.columns(2)
        for index, (cid, candidate) in enumerate(lookup.items()):
            with columns[index % 2]:
                place = ", ".join(x for x in (candidate.city, candidate.state) if x)
                label = candidate.name + (f" · {place}" if place and place not in candidate.name else "")
                if st.button(
                    label,
                    key=f"site-{cid}",
                    width="stretch",
                    type="primary" if cid in chosen else "secondary",
                    disabled=not key,
                ):
                    choice = cid
    if choice and key:
        investigate(lookup[choice], developer, store, key, model, limits, approved)
    current_id = st.session_state["selected"]
    snapshot = store.load(current_id) if current_id else None
    if not snapshot or snapshot.site.mode != "Live":
        st.info(
            "Choose a developer in the sidebar and click Find sites, then select a datacenter on the map or from the list."
        )
        return
    st.subheader(snapshot.site.name, anchor=False)
    st.caption(f"{snapshot.site.developer} · {snapshot.site.phase} · Evidence saved {snapshot.created[:10]}")
    if snapshot.report_version < 2 or snapshot.research_status != "complete" or not snapshot.claims:
        st.warning(
            "Research is incomplete, empty, or from the earlier workflow. Missing fields do not prove that public information is unavailable."
        )
        retrieved = sum(bool(d.pages) and d.status == "Retrieved" for d in snapshot.documents)
        st.caption(
            f"Readable records: {retrieved} of {len(snapshot.documents)} attempted. Verified findings: {len(snapshot.claims)}."
        )
        for note in snapshot.notes:
            if any(
                word in note.lower() for word in ("stopped", "incomplete", "limit", "omitted", "no verified")
            ):
                st.caption(note)
        blocked = sorted(
            {host_of(d.url) for d in snapshot.documents if d.status == "Manual review required" and d.url}
        )
        if blocked:
            st.caption("Publisher verification needed: " + ", ".join(blocked))
        if any(eligible_source(d) for d in snapshot.documents):
            if st.button("Reanalyze saved documents", disabled=not key):
                perform_research(store, snapshot, key, model, limits, approved, discover=False)
            st.caption("Uses saved documents without another web search. AI analysis still uses API credits.")
        if st.button("Retry investigation", disabled=not key):
            perform_research(store, snapshot, key, model, limits, approved)
    st.subheader("Site summary")
    grouped = section_findings(snapshot)
    for number, (section, fields) in enumerate(SECTIONS.items(), 1):
        with st.container(border=True):
            st.markdown(f"### {number}. {section}")
            for metric, label in fields.items():
                findings = grouped[metric]
                text = " ".join(cited_statement(snapshot, c) for c in findings) if findings else MISSING
                st.markdown(f"**{label}:** {text}")
    st.caption(
        "Missing details mean no verified evidence was found in the retrieved sources; they do not establish that an asset, approval or service does not exist."
    )

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pwrbnb.models import Site, Snapshot
from pwrbnb.research import Candidate
from pwrbnb.store import Store
from pwrbnb.tracker import discovery_key

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PWRBNB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    return AppTest.from_file(str(APP), default_timeout=30).run()


def test_live_only_without_key(app, tmp_path):
    assert not app.exception
    assert any(t.value == "Grid Atlas" for t in app.title)
    assert not app.radio
    assert app.warning
    assert app.selectbox(key="developer-name").value is None
    assert not any(s.label == "Site name" for s in app.selectbox)
    assert next(b for b in app.button if b.label == "Find sites").disabled
    assert Store(tmp_path).list_sites("Demo") == []
    assert all(t.label != "Find a site" for t in app.text_input)


def test_developer_discovery_persists_and_is_scoped(app, tmp_path, monkeypatch):
    import pwrbnb.ui as ui

    calls = []

    def discover(query):
        calls.append(query)
        return [
            Candidate(
                name="Test campus",
                address="Virginia",
                phase="Phase unconfirmed",
                identity_url="https://example.com/site",
                reason="Test identity",
            )
        ]

    monkeypatch.setattr(ui, "secret_key", lambda: "")
    monkeypatch.setattr(ui, "discover_tracker", discover)
    app.selectbox(key="developer-name").select("Equinix").run()
    assert not calls
    next(b for b in app.button if b.label == "Find sites").click().run()
    assert not app.exception
    assert len(calls) == 1 and "Equinix" in calls[0]
    assert not any(b.label == "Create investigation" for b in app.button)
    assert not any("confirmed the project" in c.label for c in app.checkbox)
    app.selectbox(key="developer-name").select("Google").run()
    assert not any(s.label == "Site name" for s in app.selectbox)
    assert not any(b.label == "Create investigation" for b in app.button)
    reopened = AppTest.from_file(str(APP), default_timeout=30).run()
    reopened.selectbox(key="developer-name").select("Equinix").run()
    assert not reopened.exception
    assert Store(tmp_path).discovery(discovery_key("Equinix"))
    assert len(calls) == 1
    assert Store(tmp_path).discovery(discovery_key("Google")) == []


def test_saved_live_brief_without_chat(app, tmp_path, monkeypatch):
    import pwrbnb.ui as ui

    store = Store(tmp_path)
    snap = Snapshot(site=Site(name="Saved campus"))
    store.save(snap)
    store.save(Snapshot(site=Site(name="Old demo", mode="Demo")))
    monkeypatch.setattr(ui, "secret_key", lambda: "fake-test-key")
    app.run()
    assert not any(b.label == "Old demo" for b in app.button)
    assert not any(b.label == "Saved campus" for b in app.button)
    app.session_state["selected"] = snap.id
    app.run()
    assert not app.exception
    assert not app.tabs
    assert not any(t.label == "US overview" for t in app.toggle)
    assert any(s.value == "Site summary" for s in app.subheader)
    from pwrbnb.topics import METRIC_CATEGORY, SECTIONS

    assert all(any(f". {section}" in m.value for m in app.markdown) for section in SECTIONS)
    assert sum("Details not available." in m.value for m in app.markdown) >= len(METRIC_CATEGORY)
    assert not any("Visit GridAxon" in str(x) for x in app.get("link_button"))
    assert not any(e.label in ("Location details", "Research history and run details") for e in app.expander)
    assert not any(t.label == "Search saved investigations" for t in app.text_input)
    assert not app.chat_input
    assert not any("Ask AI" in s.value for s in app.subheader)
    assert any(b.label == "Retry investigation" for b in app.button)
    app.run()
    assert len(store.messages(snap.site.id)) == 0


def test_live_credit_error_shows_billing_action(app, monkeypatch):
    import pwrbnb.ui as ui

    class NoCredits(Exception):
        status_code = 429
        body = {"code": "credit_balance_exhausted", "message": "sk-secret-never-show"}

    def fail_discovery(query):
        raise NoCredits()

    monkeypatch.setattr(ui, "secret_key", lambda: "fake-test-key")
    monkeypatch.setattr(ui, "discover_tracker", fail_discovery)
    app.selectbox(key="developer-name").select("Equinix").run()
    next(b for b in app.button if b.label == "Find sites").click().run()
    assert not app.exception
    assert any("credits or billing quota are exhausted" in error.value for error in app.error)
    assert all("sk-secret" not in error.value for error in app.error)


def test_map_click_investigates_once_and_maps_city(app, tmp_path, monkeypatch):
    import pwrbnb.ui as ui

    store = Store(tmp_path)
    store.save_discovery(
        discovery_key("Equinix"),
        [
            Candidate(
                name="Test campus",
                city="Ashburn",
                state="VA",
                address="Ashburn, VA",
                phase="Phase unconfirmed",
                identity_url="https://example.com/site",
                reason="Test",
            ).model_dump()
        ],
    )
    monkeypatch.setattr(ui, "secret_key", lambda: "fake-test-key")
    calls = []

    def research(store, snapshot, key, model, limits, approved):
        calls.append((snapshot, approved))

    monkeypatch.setattr(ui, "perform_research", research)
    app.selectbox(key="developer-name").select("Equinix").run()
    from pwrbnb.map_view import candidate_id

    candidate = Candidate.model_validate(store.discovery(discovery_key("Equinix"))[0])
    cid = candidate_id("Equinix", candidate)
    monkeypatch.setattr(ui, "show_map", lambda *args: ([cid], []))
    app.run()
    assert not app.exception
    assert len(calls) == 1
    snapshot, approved = calls[0]
    assert snapshot.site.latitude > 38
    assert snapshot.site.location_precision == "City reference point"
    assert "example.com" not in approved  # Selecting a lead does not verify its publisher.
    assert not any(t.label == "Phase to investigate" for t in app.text_input)
    assert not any(b.label in {"Refresh research", "Export brief", "Export JSON"} for b in app.button)
    app.run()
    assert len(calls) == 1


def test_completed_map_research_reuses_saved_result(app, tmp_path, monkeypatch):
    import pwrbnb.ui as ui
    from pwrbnb.map_view import candidate_id

    candidate = Candidate(
        name="Campus",
        city="Ashburn",
        state="VA",
        address="Ashburn, VA",
        phase="Phase 1",
        identity_url="https://equinix.com/site",
        reason="Official",
    )
    store = Store(tmp_path)
    store.save_discovery(discovery_key("Equinix"), [candidate.model_dump()])
    cid = candidate_id("Equinix", candidate)
    snap = Snapshot(site=Site(id=cid, name="Campus", developer="Equinix"), report_version=1)
    store.save(snap)
    monkeypatch.setattr(ui, "secret_key", lambda: "fake")
    monkeypatch.setattr(
        ui, "show_map", lambda developer, *args: ([cid], []) if developer == "Equinix" else ([], [])
    )

    def unexpected(*args):
        raise AssertionError("Completed research must not trigger another paid call")

    monkeypatch.setattr(ui, "perform_research", unexpected)
    app.selectbox(key="developer-name").select("Equinix").run()
    assert not app.exception
    assert app.session_state["selected"] == snap.id
    app.run()
    app.selectbox(key="developer-name").select("Google").run()
    assert app.session_state["selected"] is None
    app.selectbox(key="developer-name").select("Equinix").run()
    assert not app.exception and app.session_state["selected"] == snap.id


def test_site_list_selects_unmapped_site_and_hides_settings(app, tmp_path, monkeypatch):
    import pwrbnb.ui as ui
    from pwrbnb.map_view import candidate_id

    candidate = Candidate(
        name="Unmapped campus",
        city="",
        state="",
        address="",
        phase="Phase unconfirmed",
        identity_url="https://microsoft.com/campus",
        reason="Official",
    )
    store = Store(tmp_path)
    store.save_discovery(discovery_key("Microsoft"), [candidate.model_dump()])
    monkeypatch.setattr(ui, "secret_key", lambda: "fake")
    calls = []
    monkeypatch.setattr(ui, "perform_research", lambda *args: calls.append(args))
    app.selectbox(key="developer-name").select("Microsoft").run()
    assert not app.exception
    assert not any(
        e.label in {"Research settings", "Sites without a confidently matched city pin"} for e in app.expander
    )
    assert not app.number_input
    cid = candidate_id("Microsoft", candidate)
    app.button(key=f"site-{cid}").click().run()
    assert not app.exception and len(calls) == 1
    assert calls[0][1].site.name == "Unmapped campus"
    assert calls[0][4].documents == 16 and calls[0][4].seconds == 480
    app.run()
    assert len(calls) == 1

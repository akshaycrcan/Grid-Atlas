"""Bounded public-URL retrieval and explicit extraction failures."""

import hashlib
import io
import ipaddress
import socket
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .models import Document

TRUSTED_DOMAINS = {
    "green.googleblog.com",
    "duke-energy.com",
    "cityoflenoir.com",
    "blog.google",
    "srpnet.com",
    "aligneddc.com",
    "aws.amazon.com",
    "cyrusone.com",
    "databank.com",
    "digitalrealty.com",
    "equinix.com",
    "datacenters.google",
    "google.com",
    "about.fb.com",
    "atmeta.com",
    "microsoft.com",
    "qtsdatacenters.com",
    "stackinfra.com",
    "switch.com",
    "vantage-dc.com",
    "uptimeinstitute.com",
    "nerc.com",
    "eia.gov",
    "sec.gov",
    "ferc.gov",
    "pjm.com",
    "misoenergy.org",
    "ercot.com",
    "caiso.com",
    "nyiso.com",
    "iso-ne.com",
    "spp.org",
    "bpa.gov",
    "tva.com",
}

SECONDARY_DOMAINS = {
    "cbre.com": "CBRE market report",
    "jll.com": "JLL market report",
    "cushmanwakefield.com": "Cushman & Wakefield market report",
    "datacenterdynamics.com": "Data Center Dynamics reporting",
    "peeringdb.com": "PeeringDB connectivity record",
}


def secondary_source(url: str) -> str:
    host = host_of(url)
    return next(
        (
            label
            for domain, label in SECONDARY_DOMAINS.items()
            if host == domain or host.endswith("." + domain)
        ),
        "",
    )


def permitted_url(url: str, approved: list[str]) -> bool:
    return official_host(url, approved) or wikipedia_article(url) or bool(secondary_source(url))


def wikipedia_article(url: str) -> bool:
    """Accept encyclopedia articles, not user/talk/special pages or lookalike domains."""
    from urllib.parse import unquote

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    title = unquote(parsed.path.removeprefix("/wiki/"))
    return (
        parsed.scheme == "https"
        and (host == "wikipedia.org" or host.endswith(".wikipedia.org"))
        and parsed.path.startswith("/wiki/")
        and bool(title)
        and ":" not in title
        and title != "Main_Page"
    )


def eligible_source(doc: Document) -> bool:
    return (
        doc.status == "Retrieved"
        and bool(doc.pages)
        and (doc.official or wikipedia_article(doc.url) or bool(secondary_source(doc.url)))
    )


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def official_host(url: str, approved: list[str]) -> bool:
    host = host_of(url)
    return host.endswith(".gov") or any(
        host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS | set(approved)
    )


def validate_url(url: str, resolver=socket.getaddrinfo) -> tuple[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP/HTTPS URLs without embedded credentials are allowed.")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Only standard web ports are allowed.")
    host = parsed.hostname.rstrip(".")
    if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local and private-network URLs are not allowed.")
    try:
        addresses = {
            info[4][0]
            for info in resolver(
                host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM
            )
        }
    except OSError as exc:
        raise ValueError("The source hostname could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("The source resolves to a private, reserved, or non-public address.")
    # Prefer IPv4 where both are available; some local networks lack IPv6 routing.
    return host, min(addresses, key=lambda a: (":" in a, a))


def public_get(url: str, max_bytes: int, timeout: float = 20) -> tuple[bytes, str, str]:
    """Pin each connection to a validated public IP; revalidate every redirect."""
    for _ in range(6):
        host, address = validate_url(url)
        parsed = urlsplit(url)
        netloc = f"[{address}]" if ":" in address else address
        if parsed.port:
            netloc += f":{parsed.port}"
        pinned = urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
        headers = {
            "Host": parsed.netloc,
            "User-Agent": "PwrbnbLocalResearch/0.1",
            "Accept": "text/html,application/pdf,application/json,text/plain",
        }
        with httpx.Client(timeout=max(1, timeout), follow_redirects=False, trust_env=False) as client:
            for attempt in range(2):
                try:
                    with client.stream(
                        "GET", pinned, headers=headers, extensions={"sni_hostname": host}
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            url = urljoin(url, response.headers.get("location", ""))
                            break
                        if response.status_code in {429, 503} and attempt == 0:
                            time.sleep(0.5)
                            continue
                        response.raise_for_status()
                        if int(response.headers.get("content-length", "0")) > max_bytes:
                            raise ValueError("Document exceeds the configured size limit.")
                        content = bytearray()
                        for chunk in response.iter_bytes():
                            content.extend(chunk)
                            if len(content) > max_bytes:
                                raise ValueError("Document exceeds the configured size limit.")
                        return bytes(content), response.headers.get("content-type", ""), url
                except httpx.TimeoutException, httpx.NetworkError:
                    if attempt:
                        raise
                    time.sleep(0.3)
            else:
                raise ValueError("Source request failed after retry.")
    raise ValueError("Too many redirects.")


def extract_document(doc: Document, data: bytes, content_type: str, root: Path) -> Document:
    doc = doc.model_copy(deep=True)
    doc.sha256 = hashlib.sha256(data).hexdigest()
    folder = root / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    is_pdf = data.startswith(b"%PDF-")
    suffix = ".pdf" if is_pdf else ".html" if "html" in content_type else ".txt"
    path = folder / (doc.sha256 + suffix)
    if not path.exists():
        path.write_bytes(data)
    doc.file_name = path.name
    try:
        if is_pdf:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF: provide an accessible copy.")
            if len(reader.pages) > 300:
                raise ValueError("PDF exceeds the 300-page processing limit; supply relevant pages.")
            doc.pages = [(p.extract_text() or "")[:80000] for p in reader.pages]
            empty_pages = [str(i + 1) for i, p in enumerate(doc.pages) if len(p.strip()) < 30]
            if empty_pages:
                doc.note = "Pages needing OCR/manual review: " + ", ".join(empty_pages[:30])
        elif "html" in content_type or data.lstrip().startswith((b"<!", b"<html")):
            soup = BeautifulSoup(data, "html.parser")
            if soup.title and soup.title.get_text(strip=True):
                doc.title = soup.title.get_text(strip=True)[:300]
            meta = soup.find("meta", attrs={"property": "article:published_time"})
            if meta and meta.get("content"):
                doc.published = str(meta["content"])[:40]
            for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                tag.decompose()
            # Keep table row boundaries in the extracted source text.
            text = soup.get_text("\n", strip=True)
            doc.pages = [text[i : i + 12000] for i in range(0, min(len(text), 600000), 12000)]
            doc.note = "HTML citations use numbered extracted sections, not print pages."
            if len(text) > 600000:
                doc.note += " Extraction truncated at 600,000 characters."
        elif any(t in content_type for t in ("text/plain", "text/csv", "application/json")):
            text = data.decode("utf-8", errors="replace")
            doc.pages = [text[i : i + 12000] for i in range(0, min(len(text), 600000), 12000)]
        else:
            raise ValueError("Unsupported format. Supply an accessible HTML page or text-based PDF.")
        if not doc.pages or not any(len(p.strip()) >= 30 for p in doc.pages):
            raise ValueError("No readable text extracted. OCR or manual review is required.")
        doc.status = "Retrieved"
    except Exception as exc:
        doc.status = "Extraction failed"
        doc.note = str(exc)[:300]
    return doc


def retrieve_document(
    doc: Document, root: Path, approved: list[str], max_mb: int, timeout: float = 20
) -> Document:
    result = doc.model_copy(deep=True)
    if not permitted_url(doc.url, approved):
        result.status = "Manual review required"
        result.note = "Verify the publisher and approve its domain before using it as official evidence."
        return result
    try:
        data, kind, final_url = public_get(doc.url, max_mb * 1024 * 1024, timeout)
        if not permitted_url(final_url, approved):
            result.status = "Manual review required"
            result.note = "Redirected to an unverified publisher. Review the final domain."
            result.url = final_url
            return result
        result.url = final_url
        result.official = official_host(final_url, approved) and not wikipedia_article(final_url)
        result.provenance = "Government/registered authority domain or user-verified publisher domain"
        if wikipedia_article(final_url):
            result.publisher = "Wikipedia"
            result.family = "Encyclopedia / background"
            result.provenance = "Wikipedia article; secondary background source, not an official record"
        elif secondary_source(final_url):
            result.official = False
            result.publisher = secondary_source(final_url)
            result.provenance = "User-approved specialist source; not an official utility commitment"
        result = extract_document(result, data, kind, root)
    except (ValueError, OSError, httpx.HTTPError) as exc:
        result.status = "Inaccessible"
        # Never include request objects, authorization headers, or provider secrets.
        result.note = f"{type(exc).__name__}: retrieval failed, blocked, timed out, or exceeded limits."
    return result
